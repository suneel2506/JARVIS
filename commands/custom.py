"""
commands/custom.py — User-taught custom commands for Jarvis.
Handles commands stored in brain.json via voice teaching.
"""
from core.brain import get_custom_command, save_custom_command
from core.speaker import speak
import os


def execute_custom(command):
    """
    Try to execute a custom (user-taught) command.
    Returns (handled: bool, success: bool, message: str)
    """
    action = get_custom_command(command)
    if action:
        try:
            os.system(action)
            return True, True, f"Executed custom command: {command}"
        except Exception as e:
            return True, False, f"Failed to run custom command: {e}"
    return False, False, ""


def teach_command(phrase, action):
    """
    Teach Jarvis a new command.
    phrase: the voice trigger
    action: the system command to run
    """
    save_custom_command(phrase, action)
    return True, f"Learned: when you say '{phrase}', I'll run '{action}'"
