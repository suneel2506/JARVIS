"""
commands/automation.py — Automation commands for Jarvis.
Screenshots, typing, key presses, clipboard.
"""
import os
import time


def take_screenshot():
    """Take a screenshot and save it."""
    try:
        import pyautogui
        from config import SCREENSHOT_DIR
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        filename = f"screenshot_{int(time.time())}.png"
        filepath = os.path.join(SCREENSHOT_DIR, filename)
        img = pyautogui.screenshot()
        img.save(filepath)
        return True, f"Screenshot saved as {filename}"
    except Exception as e:
        return False, f"Failed to take screenshot: {e}"


def type_text(text):
    """Type text using keyboard automation."""
    try:
        import keyboard
        keyboard.write(text)
        return True, f"Typed: {text}"
    except Exception as e:
        return False, f"Typing failed: {e}"


def press_key(key):
    """Press a keyboard key or key combination."""
    try:
        import keyboard
        keyboard.press_and_release(key)
        return True, f"Pressed {key}"
    except Exception as e:
        return False, f"Could not press {key}: {e}"


def press_hotkey(keys):
    """Press a hotkey combination like ctrl+c, alt+tab."""
    try:
        import keyboard
        keyboard.press_and_release(keys)
        return True, f"Pressed {keys}"
    except Exception as e:
        return False, f"Could not press {keys}: {e}"


def minimize_all():
    """Minimize all windows (show desktop)."""
    try:
        import keyboard
        keyboard.press_and_release('win+d')
        return True, "Minimized all windows"
    except Exception:
        return False, "Couldn't minimize windows"


def handle_automation_command(command):
    """
    Route automation commands.
    Returns (handled: bool, success: bool, message: str)
    """
    cmd = command.lower()

    # Screenshot
    if "screenshot" in cmd or "screen shot" in cmd or "capture screen" in cmd:
        ok, msg = take_screenshot()
        return True, ok, msg

    # Type text
    if cmd.startswith("type "):
        text = command[5:].strip()  # Keep original case
        ok, msg = type_text(text)
        return True, ok, msg

    # Press key
    if cmd.startswith("press "):
        key = cmd[6:].strip().replace(" ", "+")
        ok, msg = press_key(key)
        return True, ok, msg

    # Hotkey
    if cmd.startswith("hotkey "):
        keys = cmd[7:].strip().replace(" ", "+")
        ok, msg = press_hotkey(keys)
        return True, ok, msg

    # Minimize all / show desktop
    if "minimize all" in cmd or "show desktop" in cmd:
        ok, msg = minimize_all()
        return True, ok, msg

    # Alt+Tab
    if "switch window" in cmd or "alt tab" in cmd:
        ok, msg = press_hotkey("alt+tab")
        return True, ok, msg

    return False, False, ""
