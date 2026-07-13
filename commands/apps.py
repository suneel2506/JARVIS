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
                # Track app usage
                try:
                    from core.memory import get_memory
                    get_memory().log_app_usage(key)
                except Exception:
                    pass
                return True, f"Opening {key.title()}"
            except Exception as e:
                log.error("Failed to open %s: %s", key, e)
                return False, f"Failed to open {key}: {e}"

    # Try to launch as a generic app
    try:
        os.system(f"start {app_name}")
        log.info("Generic app launch: %s", app_name)
        try:
            from core.memory import get_memory
            get_memory().log_app_usage(app_name)
        except Exception:
            pass
        return True, f"Trying to open {app_name}"
    except Exception:
        return False, f"I couldn't find an application called {app_name}, sir"


def close_app(app_name: str) -> tuple[bool, str]:
    """Close an application by process name."""
    try:
        os.system(f"taskkill /f /im {app_name}.exe")
        log.info("Closed app: %s", app_name)
        return True, f"Closing {app_name}"
    except Exception as e:
        log.error("Failed to close %s: %s", app_name, e)
        return False, f"I couldn't close {app_name}, sir"


def switch_to_app(app_name: str) -> tuple[bool, str]:
    """
    Bring an application window to the foreground.

    Uses ctypes to enumerate windows and find a match by title,
    then brings it to front.
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextLengthW = user32.GetWindowTextLengthW
        IsWindowVisible = user32.IsWindowVisible
        SetForegroundWindow = user32.SetForegroundWindow
        ShowWindow = user32.ShowWindow
        SW_RESTORE = 9

        app_lower = app_name.lower()
        found_hwnd = None

        def enum_callback(hwnd, lParam):
            nonlocal found_hwnd
            if IsWindowVisible(hwnd):
                length = GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.lower()
                    if app_lower in title:
                        found_hwnd = hwnd
                        return False  # Stop enumeration
            return True

        EnumWindows(EnumWindowsProc(enum_callback), 0)

        if found_hwnd:
            ShowWindow(found_hwnd, SW_RESTORE)
            SetForegroundWindow(found_hwnd)
            log.info("Switched to app: %s", app_name)
            return True, f"Switching to {app_name}"
        else:
            return False, f"I can't find a window for {app_name}, sir. It may not be running."

    except Exception as e:
        log.error("Switch to app failed: %s", e)
        return False, f"I couldn't switch to {app_name}, sir"


def list_running_apps() -> tuple[bool, str]:
    """List all visible application windows."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextLengthW = user32.GetWindowTextLengthW
        IsWindowVisible = user32.IsWindowVisible

        apps = []

        def enum_callback(hwnd, lParam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.strip()
                    if title and title not in ("Program Manager",):
                        # Truncate long titles
                        if len(title) > 50:
                            title = title[:47] + "..."
                        apps.append(title)
            return True

        EnumWindows(EnumWindowsProc(enum_callback), 0)

        if apps:
            count = len(apps)
            # For speech, read top 5
            top = apps[:5]
            summary = ", ".join(top)
            if count > 5:
                summary += f", and {count - 5} more"
            return True, f"You have {count} windows open. {summary}."
        else:
            return True, "No visible application windows are running, sir."

    except Exception as e:
        log.error("List running apps failed: %s", e)
        return False, f"I couldn't enumerate running apps, sir"


def search_apps(query: str) -> tuple[bool, str]:
    """Search for installed apps in common locations."""
    import glob

    query_lower = query.lower()
    found = []

    # Search Start Menu
    search_paths = [
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]

    for base in search_paths:
        if os.path.exists(base):
            for root, dirs, files in os.walk(base):
                for f in files:
                    if f.endswith(".lnk") and query_lower in f.lower():
                        name = f.replace(".lnk", "")
                        if name not in found:
                            found.append(name)

    if found:
        matches = ", ".join(found[:5])
        return True, f"I found these apps matching '{query}': {matches}."
    else:
        return False, f"I couldn't find any installed app matching '{query}', sir."

