"""
core/scheduler.py — Scheduled routines and hotkey bindings for J.A.R.V.I.S.

Background thread checks scheduled routines once per minute and executes
them when the time matches. Also registers global hotkeys on startup.
"""
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from core.logger import get_logger

log = get_logger("core.scheduler")

_running = False


def _scheduler_loop(execute_fn: Callable) -> None:
    """Background thread that checks scheduled routines every 10 seconds."""
    global _running
    from core.brain import get_brain, save_brain, get_routine
    from core.speaker import speak

    last_check_minute = ""

    while _running:
        now = datetime.now()
        current_minute = now.strftime("%H:%M")

        # Only trigger once per minute
        if current_minute != last_check_minute:
            last_check_minute = current_minute
            brain = get_brain()
            schedules = brain.get("schedules", [])

            for sched in list(schedules):
                sched_time = sched.get("time")
                routine_name = sched.get("routine")
                repeat = sched.get("repeat", "once")

                if sched_time == current_minute and routine_name:
                    steps = get_routine(routine_name)
                    if steps:
                        log.info("Running scheduled routine: %s", routine_name)
                        speak(f"Running scheduled routine {routine_name}", block=False)
                        for step in steps:
                            try:
                                execute_fn(step)
                            except Exception as e:
                                log.error("Scheduled step error: %s", e)
                            time.sleep(0.5)

                    if repeat != "daily":
                        try:
                            brain["schedules"].remove(sched)
                            save_brain()
                            log.info("One-time schedule removed: %s", routine_name)
                        except Exception:
                            pass

        time.sleep(10)


def start_scheduler(execute_fn: Callable) -> None:
    """Start the scheduler background thread."""
    global _running
    if not _running:
        _running = True
        threading.Thread(
            target=_scheduler_loop,
            args=(execute_fn,),
            daemon=True,
            name="Scheduler",
        ).start()
        log.info("Scheduler started")


def stop_scheduler() -> None:
    """Stop the scheduler."""
    global _running
    _running = False
    log.info("Scheduler stopped")


def register_hotkeys(execute_fn: Callable) -> None:
    """Register all saved hotkeys from brain."""
    try:
        import keyboard
        from core.brain import get_hotkeys

        hotkeys = get_hotkeys()
        for keys, routine_name in hotkeys.items():
            try:
                keyboard.add_hotkey(
                    keys,
                    lambda r=routine_name: execute_fn(f"run routine {r}")
                )
                log.info("Hotkey registered: %s → routine '%s'", keys, routine_name)
            except Exception as e:
                log.error("Failed to bind hotkey %s: %s", keys, e)
    except ImportError:
        log.warning("keyboard module not available — hotkeys disabled")
