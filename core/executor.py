"""
core/executor.py — Unified command router for J.A.R.V.I.S.

Routes voice/text commands through all handler modules in priority order,
with memory-aware AI fallback for unrecognized commands.

Command priority:
1. Exit / Quit
2. Routine commands (run, list, delete)
3. AI & Memory commands (remember, recall, notes, ask)
4. App launch commands (open, launch, start, close)
5. Browser navigation (google, youtube, github, wiki)
6. Media control (play, pause, next, volume)
7. System commands (shutdown, restart, battery, cpu)
8. Automation (screenshot, type, press)
9. File management (create folder, rename, delete)
10. Smart queries (time, date, weather, jokes)
11. Web search fallback
12. Custom user-taught commands
13. Memory recall (check if question matches stored facts)
14. AI conversation fallback
15. Unknown command
"""
import time
import threading
from datetime import datetime

from core.speaker import speak
from core.brain import (
    increment_usage, get_routine, delete_routine,
    list_routines, save_brain,
)
from core.logger import get_logger, log_command

log = get_logger("core.executor")

# Command log for UI display
_command_log: list[dict] = []
_log_lock = threading.Lock()
_MAX_LOG_SIZE = 50


def get_command_log() -> list[dict]:
    """Get the recent command log for HUD display."""
    with _log_lock:
        return list(_command_log)


def _add_log_entry(command: str, response: str) -> None:
    """Add an entry to the command log."""
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "command": command,
        "response": response,
    }
    with _log_lock:
        _command_log.append(entry)
        if len(_command_log) > _MAX_LOG_SIZE:
            _command_log.pop(0)
    log_command(command, response)


def execute(command: str) -> str | None:
    """
    Main command executor. Routes through all command modules in priority order.

    Args:
        command: The voice/text command to execute.

    Returns:
        "exit" to quit the application, None for normal continuation.
    """
    if not command:
        return None

    cmd = command.lower().strip()
    log.info("Processing: %s", cmd)
    increment_usage(cmd)

    # ─── 1. Exit / Quit ─────────────────────────────────
    if cmd in ("exit", "quit", "goodbye", "bye", "shut down jarvis",
               "shutdown jarvis", "close jarvis", "stop"):
        speak("Shutting down all systems. Goodbye, sir.")
        _add_log_entry(cmd, "Shutting down")
        return "exit"

    # ─── 2. Routine commands ────────────────────────────
    if cmd.startswith("run routine "):
        name = cmd.replace("run routine ", "").strip()
        steps = get_routine(name)
        if steps:
            speak(f"Running routine {name}")
            _add_log_entry(cmd, f"Running routine: {name}")
            for step in steps:
                execute(step)
                time.sleep(0.5)
        else:
            speak(f"I don't have a routine named {name}")
            _add_log_entry(cmd, f"Routine not found: {name}")
        return None

    if cmd in ("list routines", "show routines"):
        names = list_routines()
        if names:
            msg = "Available routines: " + ", ".join(names)
        else:
            msg = "You haven't created any routines yet"
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    if cmd.startswith("delete routine "):
        name = cmd.replace("delete routine ", "").strip()
        if delete_routine(name):
            msg = f"Routine {name} deleted"
        else:
            msg = f"No routine named {name} found"
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 3. AI & Memory commands ────────────────────────
    from commands.ai import handle_ai_command
    handled, ok, msg = handle_ai_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 4. App launch commands ─────────────────────────
    if any(cmd.startswith(p) for p in ("open ", "launch ", "start ", "close ")):
        if cmd.startswith("close "):
            from commands.apps import close_app
            app_name = cmd.replace("close ", "").strip()
            ok, msg = close_app(app_name)
        else:
            # Try browser sites first
            from commands.browser import handle_browser_command
            handled, ok, msg = handle_browser_command(cmd)
            if handled:
                speak(msg)
                _add_log_entry(cmd, msg)
                return None
            # Then try app launcher
            from commands.apps import handle_open
            ok, msg = handle_open(cmd)
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 5. Browser navigation ──────────────────────────
    from commands.browser import handle_browser_command
    handled, ok, msg = handle_browser_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 6. Media control ──────────────────────────────
    from commands.media import handle_media_command
    handled, ok, msg = handle_media_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 7. System commands ─────────────────────────────
    from commands.system import handle_system_command
    handled, ok, msg = handle_system_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 8. Automation commands ─────────────────────────
    from commands.automation import handle_automation_command
    handled, ok, msg = handle_automation_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 9. File management ────────────────────────────
    from commands.files import handle_file_command
    handled, ok, msg = handle_file_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 10. Smart queries ──────────────────────────────
    from commands.smart import handle_smart_command
    handled, ok, msg = handle_smart_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 11. Web search fallback ────────────────────────
    from commands.web import handle_web_command
    handled, ok, msg = handle_web_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 12. Custom commands ────────────────────────────
    from commands.custom import execute_custom
    handled, ok, msg = execute_custom(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 13. Memory recall ──────────────────────────────
    try:
        from commands.ai import handle_recall
        found, answer = handle_recall(command)
        if found:
            speak(answer)
            _add_log_entry(cmd, answer)
            return None
    except Exception as e:
        log.error("Memory recall error: %s", e)

    # ─── 14. AI conversation fallback ───────────────────
    try:
        from core.ai_engine import is_available, ask
        if is_available():
            response = ask(command)
            speak(response)
            truncated = response[:80] + "..." if len(response) > 80 else response
            _add_log_entry(cmd, truncated)
            return None
    except Exception as e:
        log.error("AI fallback error: %s", e)

    # ─── 15. Unknown command ───────────────────────────
    speak("I'm not sure how to handle that command, sir.")
    _add_log_entry(cmd, "Unrecognized command")
    return None
