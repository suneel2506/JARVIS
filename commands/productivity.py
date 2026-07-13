"""
commands/productivity.py — Productivity commands for J.A.R.V.I.S.

Reminders, timers, alarms, to-do lists, and pomodoro timer.
All data persists to JSON files in data/.
"""
import json
import os
import time
import threading
from datetime import datetime, timedelta
from typing import Optional

from core.logger import get_logger
from core.speaker import speak

log = get_logger("commands.productivity")

# ─── Data Persistence ───────────────────────────────────

def _load_json(filepath: str) -> list | dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_json(filepath: str, data) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


# ─── Reminders ──────────────────────────────────────────

_reminder_threads: list[threading.Thread] = []


def _reminder_worker(message: str, delay_seconds: int) -> None:
    """Background thread that waits and then speaks the reminder."""
    time.sleep(delay_seconds)
    speak(f"Reminder: {message}")
    log.info("Reminder fired: %s", message)


def set_reminder(text: str) -> tuple[bool, str]:
    """
    Parse and set a reminder from natural language.
    Supports: "remind me to X in Y minutes/hours"
    """
    from config.config import REMINDERS_FILE

    text_lower = text.lower()
    message = ""
    delay_minutes = 0

    # Parse "in X minutes/hours"
    import re
    time_match = re.search(r'in\s+(\d+)\s+(minute|minutes|hour|hours|second|seconds)', text_lower)
    if time_match:
        amount = int(time_match.group(1))
        unit = time_match.group(2)
        if "hour" in unit:
            delay_minutes = amount * 60
        elif "second" in unit:
            delay_minutes = amount / 60
        else:
            delay_minutes = amount

        # Extract the message (everything between "to" and "in")
        to_match = re.search(r'(?:remind\s+me\s+to\s+|reminder\s+to\s+|remind\s+to\s+)(.*?)(?:\s+in\s+\d)', text_lower)
        if to_match:
            message = to_match.group(1).strip()
        else:
            message = text_lower.split("in ")[0].replace("remind me to ", "").replace("remind me ", "").replace("set reminder ", "").strip()
    else:
        # No time specified — default to 5 minutes
        delay_minutes = 5
        message = text_lower.replace("remind me to ", "").replace("remind me ", "").replace("set reminder ", "").strip()

    if not message:
        message = "You have a reminder"

    delay_seconds = int(delay_minutes * 60)
    fire_time = datetime.now() + timedelta(seconds=delay_seconds)

    # Save to file
    reminders = _load_json(REMINDERS_FILE)
    if not isinstance(reminders, list):
        reminders = []
    reminders.append({
        "message": message,
        "set_at": datetime.now().isoformat(),
        "fire_at": fire_time.isoformat(),
        "fired": False,
    })
    _save_json(REMINDERS_FILE, reminders)

    # Start background thread
    t = threading.Thread(target=_reminder_worker, args=(message, delay_seconds), daemon=True)
    t.start()
    _reminder_threads.append(t)

    if delay_minutes >= 60:
        time_str = f"{int(delay_minutes // 60)} hours and {int(delay_minutes % 60)} minutes"
    elif delay_minutes >= 1:
        time_str = f"{int(delay_minutes)} minutes"
    else:
        time_str = f"{delay_seconds} seconds"

    log.info("Reminder set: '%s' in %s", message, time_str)
    return True, f"I'll remind you to {message} in {time_str}"


def show_reminders() -> tuple[bool, str]:
    """Show active reminders."""
    from config.config import REMINDERS_FILE
    reminders = _load_json(REMINDERS_FILE)
    if not isinstance(reminders, list):
        reminders = []
    active = [r for r in reminders if not r.get("fired", True)]
    if not active:
        return True, "You have no active reminders"
    lines = []
    for r in active[-5:]:
        lines.append(f"{r['message']} — at {r.get('fire_at', 'unknown')}")
    return True, f"You have {len(active)} active reminders. " + ". ".join(lines)


# ─── Timers ─────────────────────────────────────────────

_active_timers: dict[str, dict] = {}


def _timer_worker(name: str, seconds: int) -> None:
    """Background timer thread."""
    time.sleep(seconds)
    if name in _active_timers:
        del _active_timers[name]
    speak(f"Timer {name} is done!")
    log.info("Timer completed: %s", name)


def set_timer(text: str) -> tuple[bool, str]:
    """Set a countdown timer. Supports "set timer for X minutes"."""
    import re
    text_lower = text.lower()

    time_match = re.search(r'(\d+)\s*(minute|minutes|min|second|seconds|sec|hour|hours|hr)', text_lower)
    if time_match:
        amount = int(time_match.group(1))
        unit = time_match.group(2)
        if "hour" in unit or "hr" in unit:
            seconds = amount * 3600
            label = f"{amount} hour{'s' if amount > 1 else ''}"
        elif "min" in unit:
            seconds = amount * 60
            label = f"{amount} minute{'s' if amount > 1 else ''}"
        else:
            seconds = amount
            label = f"{amount} second{'s' if amount > 1 else ''}"
    else:
        seconds = 300
        label = "5 minutes"

    name = f"timer_{len(_active_timers) + 1}"
    _active_timers[name] = {"seconds": seconds, "started": time.time()}

    t = threading.Thread(target=_timer_worker, args=(name, seconds), daemon=True)
    t.start()

    log.info("Timer set: %s for %s", name, label)
    return True, f"Timer set for {label}"


# ─── To-Do List ─────────────────────────────────────────

def add_todo(text: str) -> tuple[bool, str]:
    """Add an item to the to-do list."""
    from config.config import TODO_FILE

    # Extract the actual to-do text
    item = text.lower()
    for prefix in ("add to do ", "add todo ", "add to-do ", "to do ", "todo "):
        if item.startswith(prefix):
            item = text[len(prefix):].strip()
            break

    todos = _load_json(TODO_FILE)
    if not isinstance(todos, list):
        todos = []
    todos.append({
        "task": item,
        "done": False,
        "created": datetime.now().isoformat(),
    })
    _save_json(TODO_FILE, todos)
    log.info("To-do added: %s", item)
    return True, f"Added to your to-do list: {item}"


def show_todos() -> tuple[bool, str]:
    """Show all to-do items."""
    from config.config import TODO_FILE
    todos = _load_json(TODO_FILE)
    if not isinstance(todos, list):
        todos = []
    pending = [t for t in todos if not t.get("done", False)]
    if not pending:
        return True, "Your to-do list is empty. Nice work!"
    lines = [f"{i+1}. {t['task']}" for i, t in enumerate(pending[:8])]
    return True, f"You have {len(pending)} items. " + ". ".join(lines)


def complete_todo(text: str) -> tuple[bool, str]:
    """Mark a to-do item as complete."""
    from config.config import TODO_FILE
    import re

    todos = _load_json(TODO_FILE)
    if not isinstance(todos, list):
        todos = []

    # Try to parse index: "complete to-do 1" or "done task 2"
    num_match = re.search(r'(\d+)', text)
    if num_match:
        idx = int(num_match.group(1)) - 1
        pending = [t for t in todos if not t.get("done", False)]
        if 0 <= idx < len(pending):
            pending[idx]["done"] = True
            _save_json(TODO_FILE, todos)
            return True, f"Marked as done: {pending[idx]['task']}"

    return False, "I couldn't find that to-do item"


def clear_todos() -> tuple[bool, str]:
    """Clear all completed to-do items."""
    from config.config import TODO_FILE
    todos = _load_json(TODO_FILE)
    if not isinstance(todos, list):
        todos = []
    remaining = [t for t in todos if not t.get("done", False)]
    _save_json(TODO_FILE, remaining)
    return True, "Cleared all completed to-do items"


# ─── Pomodoro Timer ─────────────────────────────────────

_pomodoro_active = False
_pomodoro_thread: Optional[threading.Thread] = None


def _pomodoro_worker() -> None:
    """Run a single pomodoro cycle."""
    global _pomodoro_active
    from config.config import POMODORO_WORK_MINUTES, POMODORO_BREAK_MINUTES

    speak(f"Pomodoro started. Focus for {POMODORO_WORK_MINUTES} minutes.")
    time.sleep(POMODORO_WORK_MINUTES * 60)

    if _pomodoro_active:
        speak(f"Work session complete! Take a {POMODORO_BREAK_MINUTES} minute break.")
        time.sleep(POMODORO_BREAK_MINUTES * 60)
        if _pomodoro_active:
            speak("Break is over. Ready for another session?")
            _pomodoro_active = False


def start_pomodoro() -> tuple[bool, str]:
    """Start a pomodoro focus session."""
    global _pomodoro_active, _pomodoro_thread
    from config.config import POMODORO_WORK_MINUTES

    if _pomodoro_active:
        return True, "A pomodoro session is already running"

    _pomodoro_active = True
    _pomodoro_thread = threading.Thread(target=_pomodoro_worker, daemon=True)
    _pomodoro_thread.start()
    return True, f"Starting {POMODORO_WORK_MINUTES} minute focus session"


def stop_pomodoro() -> tuple[bool, str]:
    """Stop the current pomodoro session."""
    global _pomodoro_active
    _pomodoro_active = False
    return True, "Pomodoro session stopped"


# ─── Command Router ────────────────────────────────────

def handle_productivity_command(command: str) -> tuple[bool, bool, str]:
    """
    Route productivity commands.
    Returns (handled, success, message)
    """
    cmd = command.lower().strip()

    # Reminders
    if any(cmd.startswith(p) for p in ("remind me", "set reminder", "reminder ")):
        ok, msg = set_reminder(cmd)
        return True, ok, msg
    if cmd in ("show reminders", "list reminders", "my reminders"):
        ok, msg = show_reminders()
        return True, ok, msg

    # Timers
    if "set timer" in cmd or "start timer" in cmd or "timer for" in cmd:
        ok, msg = set_timer(cmd)
        return True, ok, msg

    # To-do
    if any(cmd.startswith(p) for p in ("add to do", "add todo", "add to-do")):
        ok, msg = add_todo(cmd)
        return True, ok, msg
    if cmd in ("show to do", "show todos", "show to-do", "my to do list",
               "to do list", "show my to do", "todo list", "my todos"):
        ok, msg = show_todos()
        return True, ok, msg
    if any(cmd.startswith(p) for p in ("complete to do", "complete todo", "done task", "finish task")):
        ok, msg = complete_todo(cmd)
        return True, ok, msg
    if cmd in ("clear to do", "clear todos", "clear completed"):
        ok, msg = clear_todos()
        return True, ok, msg

    # Pomodoro
    if "start pomodoro" in cmd or "begin pomodoro" in cmd or "focus mode" in cmd:
        ok, msg = start_pomodoro()
        return True, ok, msg
    if "stop pomodoro" in cmd or "end pomodoro" in cmd or "cancel pomodoro" in cmd:
        ok, msg = stop_pomodoro()
        return True, ok, msg

    return False, False, ""
