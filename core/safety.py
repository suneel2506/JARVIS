"""
core/safety.py — Destructive action confirmation system for J.A.R.V.I.S.

Provides voice-based confirmation for potentially dangerous operations.
Never executes destructive actions without explicit user consent.

Dangerous operations include:
- File/folder deletion
- System shutdown/restart/logoff
- Recycle bin emptying
- Process termination
- Format operations

Usage:
    from core.safety import confirm_action
    if confirm_action("delete the file report.pdf"):
        # proceed with deletion
"""
import threading
from typing import Optional

from core.logger import get_logger

log = get_logger("core.safety")

# Actions that require confirmation
DANGEROUS_ACTIONS = {
    "delete",
    "remove",
    "shutdown",
    "restart",
    "reboot",
    "log off",
    "logoff",
    "sign out",
    "empty recycle",
    "format",
    "kill process",
    "end process",
    "terminate",
    "wipe",
    "erase",
    "uninstall",
}

# State
_confirmation_pending = False
_confirmation_lock = threading.Lock()
_last_action_description = ""


def requires_confirmation(command: str) -> bool:
    """
    Check if a command requires user confirmation before execution.

    Args:
        command: The command string to check.

    Returns:
        True if the command involves a destructive action.
    """
    cmd_lower = command.lower().strip()
    for action in DANGEROUS_ACTIONS:
        if action in cmd_lower:
            return True
    return False


def confirm_action(description: str) -> bool:
    """
    Ask the user for voice confirmation before a destructive action.

    Speaks the confirmation prompt and waits for a yes/no response.

    Args:
        description: Human-readable description of the action
                     (e.g., "delete the folder Projects").

    Returns:
        True if the user confirmed (yes/yeah/confirm/do it/proceed),
        False if denied or timed out.
    """
    global _confirmation_pending, _last_action_description

    from core.speaker import speak

    with _confirmation_lock:
        _confirmation_pending = True
        _last_action_description = description

    log.info("Requesting confirmation: %s", description)
    speak(f"Are you sure you want to {description}? Say yes to confirm or no to cancel.")

    # Listen for confirmation
    try:
        from core.mic import recognize_speech
        response = recognize_speech(timeout=8, phrase_time_limit=4)

        confirmed = _is_affirmative(response)

        if confirmed:
            log.info("Action CONFIRMED: %s", description)
            speak("Confirmed. Proceeding.")
        else:
            log.info("Action DENIED: %s (response: '%s')", description, response)
            speak("Action cancelled.")

        return confirmed
    except Exception as e:
        log.error("Confirmation error: %s — defaulting to DENY", e)
        speak("I didn't get a clear response. Action cancelled for safety.")
        return False
    finally:
        with _confirmation_lock:
            _confirmation_pending = False
            _last_action_description = ""


def _is_affirmative(response: str) -> bool:
    """Check if a response is affirmative."""
    if not response:
        return False
    positives = {
        "yes", "yeah", "yep", "yup", "sure", "confirm", "confirmed",
        "do it", "proceed", "go ahead", "affirmative", "absolutely",
        "of course", "please", "okay", "ok",
    }
    resp_lower = response.lower().strip()
    return resp_lower in positives or any(p in resp_lower for p in positives)


def is_confirmation_pending() -> bool:
    """Check if a confirmation is currently pending."""
    with _confirmation_lock:
        return _confirmation_pending


def get_pending_action() -> str:
    """Get the description of the pending action."""
    with _confirmation_lock:
        return _last_action_description
