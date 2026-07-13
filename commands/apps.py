"""
commands/apps.py — Application launcher for Jarvis.
Maps voice commands to system app launch commands.
"""
import os
import subprocess

# Map of app keywords to their launch commands (Windows)
APP_MAP = {
    "chrome":           "start chrome",
    "google chrome":    "start chrome",
    "firefox":          "start firefox",
    "edge":             "start msedge",
    "microsoft edge":   "start msedge",
    "notepad":          "notepad",
    "calculator":       "calc",
    "calc":             "calc",
    "file explorer":    "explorer",
    "explorer":         "explorer",
    "task manager":     "taskmgr",
    "settings":         "start ms-settings:",
    "paint":            "mspaint",
    "vs code":          "code",
    "vscode":           "code",
    "visual studio code": "code",
    "spotify":          "start spotify:",
    "discord":          "start discord:",
    "telegram":         "start telegram:",
    "word":             "start winword",
    "excel":            "start excel",
    "powerpoint":       "start powerpnt",
    "cmd":              "start cmd",
    "command prompt":   "start cmd",
    "terminal":         "start wt",
    "powershell":       "start powershell",
    "snipping tool":    "snippingtool",
    "camera":           "start microsoft.windows.camera:",
    "clock":            "start ms-clock:",
    "maps":             "start bingmaps:",
    "store":            "start ms-windows-store:",
    "photos":           "start ms-photos:",
    "mail":             "start outlookmail:",
    "calendar":         "start outlookcal:",
    "youtube":          "start chrome https://www.youtube.com",
    "gmail":            "start chrome https://mail.google.com",
    "github":           "start chrome https://github.com",
    "whatsapp":         "start chrome https://web.whatsapp.com",
}


def handle_open(command):
    """
    Handle 'open <app>' commands.
    Returns (success: bool, message: str)
    """
    # Extract the app name from command
    cmd = command.lower()
    if cmd.startswith("open "):
        app_name = cmd[5:].strip()
    elif cmd.startswith("launch "):
        app_name = cmd[7:].strip()
    elif cmd.startswith("start "):
        app_name = cmd[6:].strip()
    else:
        app_name = cmd.strip()

    # Look up in app map
    for key, launch_cmd in APP_MAP.items():
        if key in app_name or app_name in key:
            try:
                os.system(launch_cmd)
                return True, f"Opening {key.title()}"
            except Exception as e:
                return False, f"Failed to open {key}: {e}"

    # Try to launch as a generic app
    try:
        os.system(f"start {app_name}")
        return True, f"Trying to open {app_name}"
    except Exception:
        return False, f"I couldn't find an application called {app_name}"


def close_app(app_name):
    """Attempt to close an application by name."""
    try:
        os.system(f"taskkill /f /im {app_name}.exe")
        return True, f"Closing {app_name}"
    except Exception:
        return False, f"Couldn't close {app_name}"
