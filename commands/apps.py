"""
commands/apps.py — Application launcher for J.A.R.V.I.S.

Maps voice commands to system app launch commands on Windows.
Supports open, launch, start, and close operations.
"""
import os

from core.logger import get_logger

log = get_logger("commands.apps")

# Map of app keywords to their launch commands (Windows)
APP_MAP: dict[str, str] = {
    "chrome":             "start chrome",
    "google chrome":      "start chrome",
    "firefox":            "start firefox",
    "edge":               "start msedge",
    "microsoft edge":     "start msedge",
    "brave":              "start brave",
    "notepad":            "notepad",
    "notepad++":          "start notepad++",
    "calculator":         "calc",
    "calc":               "calc",
    "file explorer":      "explorer",
    "explorer":           "explorer",
    "task manager":       "taskmgr",
    "settings":           "start ms-settings:",
    "paint":              "mspaint",
    "vs code":            "code",
    "vscode":             "code",
    "visual studio code": "code",
    "visual studio":      "start devenv",
    "spotify":            "start spotify:",
    "discord":            "start discord:",
    "telegram":           "start telegram:",
    "slack":              "start slack:",
    "teams":              "start msteams:",
    "zoom":               "start zoom",
    "word":               "start winword",
    "excel":              "start excel",
    "powerpoint":         "start powerpnt",
    "outlook":            "start outlook",
    "onenote":            "start onenote:",
    "cmd":                "start cmd",
    "command prompt":     "start cmd",
    "terminal":           "start wt",
    "windows terminal":   "start wt",
    "powershell":         "start powershell",
    "snipping tool":      "snippingtool",
    "snip & sketch":      "start ms-screensketch:",
    "camera":             "start microsoft.windows.camera:",
    "clock":              "start ms-clock:",
    "alarms":             "start ms-clock:",
    "maps":               "start bingmaps:",
    "store":              "start ms-windows-store:",
    "microsoft store":    "start ms-windows-store:",
    "photos":             "start ms-photos:",
    "mail":               "start outlookmail:",
    "calendar":           "start outlookcal:",
    "vlc":                "start vlc",
    "obs":                "start obs64",
    "steam":              "start steam:",
    "epic games":         "start com.epicgames.launcher:",
    "blender":            "start blender",
    "gimp":               "start gimp-2.10",
    "audacity":           "start audacity",
}


def handle_open(command: str) -> tuple[bool, str]:
    """
    Handle 'open <app>' commands.

    Args:
        command: The full command string (e.g., "open chrome").

    Returns:
        (success, message)
    """
    cmd = command.lower().strip()
    for prefix in ("open ", "launch ", "start "):
        if cmd.startswith(prefix):
            app_name = cmd[len(prefix):].strip()
            break
    else:
        app_name = cmd.strip()

    # Look up in app map (supports partial matching)
    for key, launch_cmd in APP_MAP.items():
        if key in app_name or app_name in key:
            try:
                os.system(launch_cmd)
                log.info("Opened app: %s (%s)", key, launch_cmd)
                return True, f"Opening {key.title()}"
            except Exception as e:
                log.error("Failed to open %s: %s", key, e)
                return False, f"Failed to open {key}: {e}"

    # Try to launch as a generic app
    try:
        os.system(f"start {app_name}")
        log.info("Generic app launch: %s", app_name)
        return True, f"Trying to open {app_name}"
    except Exception:
        return False, f"I couldn't find an application called {app_name}"


def close_app(app_name: str) -> tuple[bool, str]:
    """
    Close an application by process name.

    Args:
        app_name: Application name (without .exe).

    Returns:
        (success, message)
    """
    try:
        os.system(f"taskkill /f /im {app_name}.exe")
        log.info("Closed app: %s", app_name)
        return True, f"Closing {app_name}"
    except Exception as e:
        log.error("Failed to close %s: %s", app_name, e)
        return False, f"Couldn't close {app_name}"
