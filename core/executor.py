"""
core/executor.py — Unified command router for J.A.R.V.I.S.

Routes voice/text commands through all handler modules in priority order,
with memory-aware AI fallback for unrecognized commands.

Features:
- Multi-command chaining ("open Chrome and play music")
- Implicit intent handling ("thanks", "who are you", "good morning")
- Follow-up detection → routes back to AI with context
- Execution timing (logged for diagnostics)
- Conversational response for social intents (not robotic)

Command priority:
1. Exit / Quit / Sleep Mode
2. Listen mode switching
3. Routine commands (run, list, delete)
4. AI & Memory commands (remember, recall, notes, ask)
5. Productivity (reminders, timers, to-do, pomodoro)
6. Coding (git, run script, create project)
7. App launch commands (open, launch, start, close)
8. Communication apps (whatsapp, discord, gmail, etc.)
9. Browser navigation (google, youtube, github, wiki)
10. Media control (play, pause, next, volume)
11. System commands (shutdown, restart, battery, cpu, gpu)
12. Automation (screenshot, type, press)
13. Utilities (recycle bin, processes, compress, speed test)
14. File management (create folder, rename, delete, copy)
15. Smart queries (time, date, weather, news, translate)
16. Web search fallback
17. Custom user-taught commands
18. Memory recall
19. AI conversation fallback
20. Unknown command
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
from core.event_bus import bus, Events
from core.state_machine import machine, States

log = get_logger("core.executor")

# Command log for UI display
_command_log: list[dict] = []
_log_lock = threading.Lock()
_MAX_LOG_SIZE = 50

# Execution stats
_total_executed: int = 0
_total_exec_time_ms: int = 0
_last_exec_time_ms: int = 0


def get_command_log() -> list[dict]:
    """Get the recent command log for HUD display."""
    with _log_lock:
        return list(_command_log)


def get_exec_stats() -> dict:
    """Get execution statistics for diagnostics."""
    return {
        "total_commands": _total_executed,
        "total_exec_time_ms": _total_exec_time_ms,
        "last_exec_time_ms": _last_exec_time_ms,
        "avg_exec_time_ms": (
            _total_exec_time_ms // _total_executed if _total_executed > 0 else 0
        ),
    }


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


def _time_greeting() -> str:
    """Generate a time-appropriate greeting response."""
    hour = datetime.now().hour
    if hour < 6:
        return "Burning the midnight oil, sir? All systems at your disposal."
    elif hour < 12:
        return "Good morning, sir. Systems are online and ready."
    elif hour < 17:
        return "Good afternoon, sir. How may I assist?"
    elif hour < 21:
        return "Good evening, sir. What can I do for you?"
    else:
        return "Good evening, sir. Standing by."


def _handle_implicit_intent(intent) -> tuple[bool, str]:
    """
    Handle implicit intents (social/casual phrases).

    Returns:
        (handled, response_message)
    """
    action = intent.action

    if action == "acknowledge":
        return True, intent.response or "At your service, sir."

    if action == "cancel":
        return True, intent.response or "Understood. Standing by."

    if action == "dismiss":
        return True, intent.response or "Very well, sir."

    if action == "identity":
        return True, intent.response or "I am J.A.R.V.I.S., at your service."

    if action == "status_self":
        return True, intent.response or "All systems operational, sir."

    if action in ("greet_morning", "greet_evening", "greet_night"):
        return True, _time_greeting()

    if action == "welcome_back":
        return True, "Welcome back, sir. All systems nominal."

    if action == "capabilities":
        return True, (
            "I can manage your applications, control media, search the web, "
            "handle files, run diagnostics, remember information, and hold "
            "conversations, sir. Just say the word."
        )

    if action == "suggest":
        return True, "Perhaps a quick web search, or shall I run a system diagnostic, sir?"

    if action == "sleep":
        from core.listener import enter_sleep
        enter_sleep()
        return True, "Dimming systems. Rest well, sir."

    return False, ""


def execute(command: str) -> str | None:
    """
    Main command executor. Routes through all command modules in priority order.

    Handles multi-command chaining, implicit intents, follow-ups,
    and execution timing. Emits pipeline stage events for HUD.

    Args:
        command: The voice/text command to execute.

    Returns:
        "exit" to quit the application, None for normal continuation.
    """
    global _total_executed, _total_exec_time_ms, _last_exec_time_ms

    if not command:
        return None

    exec_start = time.time()
    cmd = command.lower().strip()

    # Emit command received event
    bus.emit(Events.COMMAND_RECEIVED, command=cmd, source="voice")

    # ─── Multi-command chaining ──────────────────────────
    from core.intent import split_multi_command
    parts = split_multi_command(cmd)
    if len(parts) > 1:
        log.info("Multi-command: executing %d parts", len(parts))
        for i, part in enumerate(parts):
            result = _execute_single(part.strip())
            if result == "exit":
                return "exit"
            if i < len(parts) - 1:
                time.sleep(0.3)  # Brief pause between commands

        duration_ms = int((time.time() - exec_start) * 1000)
        _total_executed += 1
        _last_exec_time_ms = duration_ms
        _total_exec_time_ms += duration_ms
        bus.emit(Events.COMMAND_COMPLETED, command=cmd, response="Multi-command done",
                 duration_ms=duration_ms, success=True)
        machine.set_state(States.IDLE)
        return None

    result = _execute_single(cmd)

    duration_ms = int((time.time() - exec_start) * 1000)
    _total_executed += 1
    _last_exec_time_ms = duration_ms
    _total_exec_time_ms += duration_ms

    # Emit completion
    bus.emit(Events.COMMAND_COMPLETED, command=cmd,
             response=_command_log[-1].get("response", "") if _command_log else "",
             duration_ms=duration_ms, success=(result != "exit"))
    machine.set_state(States.IDLE)

    return result


def _execute_single(cmd: str) -> str | None:
    """Execute a single command (after multi-command splitting)."""
    if not cmd:
        return None

    # ─── Stage: Understanding ───────────────────────────
    machine.set_state(States.UNDERSTANDING)
    bus.emit(Events.COMMAND_STAGE, stage="understanding", label="Understanding...")

    # ─── Follow-up detection ────────────────────────────
    from core.ai_engine import is_followup, is_cancellation, is_available, ask
    if is_cancellation(cmd):
        speak("Understood. Standing by, sir.")
        _add_log_entry(cmd, "Cancelled")
        return None

    if is_followup(cmd) and is_available():
        log.info("Follow-up detected: '%s' — routing to AI with context", cmd)
        response = ask(cmd)
        speak(response)
        truncated = response[:80] + "..." if len(response) > 80 else response
        _add_log_entry(cmd, truncated)
        return None

    # ─── Implicit intent detection ──────────────────────
    from core.intent import check_implicit_intent
    implicit = check_implicit_intent(cmd)
    if implicit:
        handled, msg = _handle_implicit_intent(implicit)
        if handled:
            speak(msg)
            _add_log_entry(cmd, msg)
            return None

    # ─── Intent normalization ────────────────────────────
    # Transform natural phrases into standard commands
    # e.g., "could you launch Chrome?" → "open chrome"
    from core.intent import normalize_command
    raw_cmd = cmd  # Preserve original for logging
    cmd = normalize_command(cmd)
    if cmd != raw_cmd:
        log.info("Intent: '%s' → '%s'", raw_cmd, cmd)

    log.info("Processing: %s", cmd)
    increment_usage(cmd)

    # ─── Stage: Planning ────────────────────────────────
    machine.set_state(States.THINKING)
    bus.emit(Events.COMMAND_STAGE, stage="planning", label="Planning...")

    # ─── Safety gate: confirm destructive actions ────────
    from config.config import CONFIRM_DESTRUCTIVE
    if CONFIRM_DESTRUCTIVE:
        from core.safety import requires_confirmation, confirm_action
        if requires_confirmation(cmd):
            if not confirm_action(cmd):
                _add_log_entry(cmd, "Cancelled by user (safety)")
                return None

    # ─── 1. Exit / Quit ─────────────────────────────────
    # ─── Stage: Executing ───────────────────────────────
    machine.set_state(States.EXECUTING)
    bus.emit(Events.COMMAND_STAGE, stage="executing", label=f"Executing: {cmd[:30]}")

    if cmd in ("exit", "quit", "goodbye", "bye", "shut down jarvis",
               "shutdown jarvis", "close jarvis", "stop"):
        speak("Shutting down all systems. Goodbye, sir.")
        _add_log_entry(cmd, "Shutting down")
        return "exit"

    # ─── 1b. Sleep / Wake mode ──────────────────────────
    if cmd in ("go to sleep", "sleep mode", "jarvis sleep"):
        from core.listener import enter_sleep
        enter_sleep()
        speak("Entering sleep mode. Say 'wake up' or click to reactivate.")
        _add_log_entry(cmd, "Sleep mode")
        return None
    if cmd in ("wake up", "i'm back", "jarvis wake up"):
        from core.listener import exit_sleep
        exit_sleep()
        speak("I'm awake, sir. What do you need?")
        _add_log_entry(cmd, "Woke up")
        return None

    # ─── 1c. Listen mode switching ──────────────────────
    if "continuous mode" in cmd or "always listen" in cmd:
        from core.listener import set_listen_mode
        set_listen_mode("continuous")
        speak("Switching to continuous listening mode. No wake word needed.")
        _add_log_entry(cmd, "Continuous mode")
        return None
    if "wake word mode" in cmd or "normal mode" in cmd:
        from core.listener import set_listen_mode
        set_listen_mode("wake_word")
        speak("Switching to wake word mode.")
        _add_log_entry(cmd, "Wake word mode")
        return None

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

    # ─── 2b. Workflow commands ──────────────────────────
    from core.workflow import handle_workflow_command, is_chained_command
    handled, msg = handle_workflow_command(cmd, execute)
    if handled:
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

    # ─── 4. Productivity commands ───────────────────────
    from commands.productivity import handle_productivity_command
    handled, ok, msg = handle_productivity_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 5. Coding commands ─────────────────────────────
    from commands.coding import handle_coding_command
    handled, ok, msg = handle_coding_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 6a. Switch to / List / Search apps ────────────────
    if cmd.startswith("switch to ") or cmd.startswith("go to "):
        from commands.apps import switch_to_app
        target = cmd.replace("switch to ", "").replace("go to ", "").strip()
        ok, msg = switch_to_app(target)
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    if cmd in ("what's running", "what apps are running", "list running apps",
               "show running apps", "running apps", "running applications"):
        from commands.apps import list_running_apps
        ok, msg = list_running_apps()
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    if cmd.startswith("find app ") or cmd.startswith("search app "):
        from commands.apps import search_apps
        query = cmd.replace("find app ", "").replace("search app ", "").strip()
        ok, msg = search_apps(query)
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 6b. App launch commands ────────────────────────
    if any(cmd.startswith(p) for p in ("open ", "launch ", "start ", "close ")):

        if cmd.startswith("close "):
            from commands.apps import close_app
            app_name = cmd.replace("close ", "").strip()
            ok, msg = close_app(app_name)
        else:
            # Try communication apps first
            from commands.communication import handle_communication_command
            handled, ok, msg = handle_communication_command(cmd)
            if handled:
                speak(msg)
                _add_log_entry(cmd, msg)
                return None

            # Then try browser sites
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

    # ─── 7. Communication apps (without "open" prefix) ──
    from commands.communication import handle_communication_command
    handled, ok, msg = handle_communication_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 8. Browser navigation ──────────────────────────
    from commands.browser import handle_browser_command
    handled, ok, msg = handle_browser_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 9. Media control ──────────────────────────────
    from commands.media import handle_media_command
    handled, ok, msg = handle_media_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 10. System commands ─────────────────────────────
    from commands.system import handle_system_command
    handled, ok, msg = handle_system_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 11. Automation commands ─────────────────────────
    from commands.automation import handle_automation_command
    handled, ok, msg = handle_automation_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 12. Utility commands ───────────────────────────
    from commands.utilities import handle_utility_command
    handled, ok, msg = handle_utility_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 13. File management ────────────────────────────
    from commands.files import handle_file_command
    handled, ok, msg = handle_file_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 14. Smart queries ──────────────────────────────
    from commands.smart import handle_smart_command
    handled, ok, msg = handle_smart_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 14b. Engineering commands ──────────────────────
    from commands.engineering import handle_engineering_command
    handled, ok, msg = handle_engineering_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 14c. Vision commands ───────────────────────────
    from commands.vision import handle_vision_command
    handled, ok, msg = handle_vision_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 14d. OS control & file intelligence ─────────────
    from commands.os_control import handle_os_control_command
    handled, ok, msg = handle_os_control_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 14e. Research & knowledge ───────────────────────
    from commands.research import handle_research_command
    handled, ok, msg = handle_research_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 15. Web search fallback ────────────────────────
    from commands.web import handle_web_command
    handled, ok, msg = handle_web_command(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 16. Custom commands ────────────────────────────
    from commands.custom import execute_custom
    handled, ok, msg = execute_custom(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 16b. Plugin commands ───────────────────────────
    from core.plugin_manager import handle_plugin_commands
    handled, ok, msg = handle_plugin_commands(cmd)
    if handled:
        speak(msg)
        _add_log_entry(cmd, msg)
        return None

    # ─── 17. Memory recall ──────────────────────────────
    try:
        from commands.ai import handle_recall
        found, answer = handle_recall(command)
        if found:
            speak(answer)
            _add_log_entry(cmd, answer)
            return None
    except Exception as e:
        log.error("Memory recall error: %s", e)

    # ─── 18. AI conversation fallback ───────────────────
    try:
        if is_available():
            response = ask(command)
            speak(response)
            truncated = response[:80] + "..." if len(response) > 80 else response
            _add_log_entry(cmd, truncated)
            return None
    except Exception as e:
        log.error("AI fallback error: %s", e)

    # ─── 19. Unknown command ───────────────────────────
    speak("I'm not sure how to handle that command, sir.")
    _add_log_entry(cmd, "Unrecognized command")
    return None
