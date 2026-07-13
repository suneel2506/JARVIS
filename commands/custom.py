"""
commands/custom.py — User-taught custom commands for J.A.R.V.I.S.

Handles commands stored in brain.json via voice teaching.
Users can teach JARVIS new commands by mapping phrases to system actions.
"""
import os

from core.brain import get_custom_command, save_custom_command
from core.logger import get_logger

log = get_logger("commands.custom")


def execute_custom(command: str) -> tuple[bool, bool, str]:
    """
    Try to execute a custom (user-taught) command.

    Args:
        command: The voice command phrase.

    Returns:
        (handled, success, message)
    """
    action = get_custom_command(command)
    if action:
        try:
            os.system(action)
            log.info("Custom command: '%s' → '%s'", command, action)
            return True, True, f"Executed custom command: {command}"
        except Exception as e:
            log.error("Custom command failed '%s': %s", command, e)
            return True, False, f"Failed to run custom command: {e}"
    return False, False, ""


def teach_command(phrase: str, action: str) -> tuple[bool, str]:
    """
    Teach JARVIS a new command.

    Args:
        phrase: The voice trigger phrase.
        action: The system command to run when triggered.

    Returns:
        (success, message)
    """
    save_custom_command(phrase, action)
    log.info("Taught command: '%s' → '%s'", phrase, action)
    return True, f"Learned: when you say '{phrase}', I'll run '{action}'"
