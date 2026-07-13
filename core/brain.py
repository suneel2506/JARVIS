"""
core/brain.py — Brain manager for J.A.R.V.I.S.

Handles persistent data: custom commands, usage tracking, routines, schedules, hotkeys.
Long-term user memory (facts, preferences, etc.) is handled by core/memory.py.
"""
import json
import os
import threading
from typing import Any, Optional

from core.logger import get_logger

log = get_logger("core.brain")

_lock = threading.Lock()
_brain: Optional[dict] = None
_brain_path: Optional[str] = None


def _default_brain() -> dict[str, Any]:
    """Default brain data structure."""
    return {
        "commands": {},
        "usage": {},
        "routines": {},
        "schedules": [],
        "hotkeys": {},
    }


def load_brain(path: Optional[str] = None) -> dict:
    """
    Load brain data from JSON file.

    Args:
        path: Path to brain.json. If None, uses BRAIN_FILE from config.
    """
    global _brain, _brain_path
    if path is None:
        from config.config import BRAIN_FILE
        path = BRAIN_FILE
    _brain_path = path
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = _default_brain()
        log.info("Created new brain file at %s", path)
    # Ensure all keys exist
    for key, default in _default_brain().items():
        data.setdefault(key, default)
    _brain = data
    log.info("Brain loaded from %s", path)
    return _brain


def save_brain() -> None:
    """Save brain to JSON file (thread-safe)."""
    global _brain, _brain_path
    if _brain is None or _brain_path is None:
        return
    with _lock:
        try:
            os.makedirs(os.path.dirname(_brain_path), exist_ok=True)
            with open(_brain_path, "w", encoding="utf-8") as f:
                json.dump(_brain, f, indent=4, ensure_ascii=False)
        except Exception as e:
            log.error("Brain save error: %s", e)


def get_brain() -> dict:
    """Get the brain data dict (lazy-loads if needed)."""
    global _brain
    if _brain is None:
        load_brain()
    return _brain


def increment_usage(cmd: str) -> None:
    """Track command usage count."""
    b = get_brain()
    b["usage"][cmd] = b["usage"].get(cmd, 0) + 1
    save_brain()


def get_custom_command(phrase: str) -> Optional[str]:
    """Look up a custom command action by phrase."""
    return get_brain()["commands"].get(phrase)


def save_custom_command(phrase: str, action: str) -> None:
    """Save a custom command mapping."""
    b = get_brain()
    b["commands"][phrase] = action
    save_brain()
    log.info("Custom command saved: '%s' → '%s'", phrase, action)


def get_routine(name: str) -> Optional[list[str]]:
    """Get a routine's steps by name."""
    return get_brain()["routines"].get(name)


def save_routine(name: str, steps: list[str]) -> None:
    """Save a routine."""
    b = get_brain()
    b["routines"][name] = steps
    save_brain()
    log.info("Routine saved: '%s' (%d steps)", name, len(steps))


def delete_routine(name: str) -> bool:
    """Delete a routine by name. Returns True if it existed."""
    b = get_brain()
    if name in b["routines"]:
        del b["routines"][name]
        save_brain()
        log.info("Routine deleted: '%s'", name)
        return True
    return False


def list_routines() -> list[str]:
    """List all routine names."""
    return list(get_brain().get("routines", {}).keys())


def get_schedules() -> list[dict]:
    """Get all schedules."""
    return get_brain().get("schedules", [])


def add_schedule(routine_name: str, time_str: str, repeat: str = "once") -> None:
    """Add a schedule entry."""
    b = get_brain()
    b["schedules"].append({
        "routine": routine_name,
        "time": time_str,
        "repeat": repeat,
    })
    save_brain()
    log.info("Schedule added: '%s' at %s (%s)", routine_name, time_str, repeat)


def remove_schedule(index: int) -> None:
    """Remove a schedule by index."""
    b = get_brain()
    if 0 <= index < len(b["schedules"]):
        b["schedules"].pop(index)
        save_brain()


def get_hotkeys() -> dict[str, str]:
    """Get all hotkey bindings."""
    return get_brain().get("hotkeys", {})


def save_hotkey(keys: str, routine_name: str) -> None:
    """Save a hotkey binding."""
    b = get_brain()
    b["hotkeys"][keys] = routine_name
    save_brain()
    log.info("Hotkey saved: %s → '%s'", keys, routine_name)


def get_top_commands(limit: int = 5) -> list[tuple[str, int]]:
    """Return most-used commands sorted by count."""
    usage = get_brain().get("usage", {})
    sorted_cmds = sorted(usage.items(), key=lambda x: x[1], reverse=True)
    return sorted_cmds[:limit]
