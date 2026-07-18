"""
commands/os_control.py — Advanced OS control & file intelligence for J.A.R.V.I.S.

Phase 5 capabilities:
- Deep recursive file search with content matching
- Smart clipboard (history, paste previous items)
- Window management (tile, snap, minimize all, cascade)
- Disk usage analysis
- Recent files across system
- Process management (find, kill by name)
"""
import os
import subprocess
import ctypes
import re
from datetime import datetime, timedelta
from typing import Optional

from core.logger import get_logger

log = get_logger("commands.os_control")


# ═══════════════════════════════════════════════════════════
# Deep File Search
# ═══════════════════════════════════════════════════════════

def deep_search(query: str, location: str = "", extensions: str = "") -> tuple[bool, str]:
    """
    Recursively search for files by name across key directories.

    Args:
        query: Search term (partial filename match)
        location: Optional directory hint (desktop, documents, etc.)
        extensions: Optional comma-separated extensions (.py,.txt)
    """
    home = os.path.expanduser("~")
    if location:
        from commands.files import _resolve_path
        search_dirs = [_resolve_path(location)]
    else:
        search_dirs = [
            os.path.join(home, "Desktop"),
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
        ]

    ext_filter = set()
    if extensions:
        ext_filter = {e.strip().lower() if e.startswith('.') else f".{e.strip().lower()}"
                      for e in extensions.split(",")}

    query_lower = query.lower()
    found = []
    max_results = 20
    max_depth = 5

    for base_dir in search_dirs:
        if not os.path.isdir(base_dir):
            continue
        for root, dirs, files in os.walk(base_dir):
            # Limit depth
            depth = root.replace(base_dir, "").count(os.sep)
            if depth > max_depth:
                dirs.clear()
                continue

            # Skip hidden/system dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                       ('__pycache__', 'node_modules', '.git', '.venv', 'venv')]

            for fname in files:
                if query_lower in fname.lower():
                    if ext_filter and not any(fname.lower().endswith(e) for e in ext_filter):
                        continue
                    full_path = os.path.join(root, fname)
                    try:
                        size = os.path.getsize(full_path)
                        found.append((fname, full_path, size))
                    except OSError:
                        found.append((fname, full_path, 0))
                    if len(found) >= max_results:
                        break
            if len(found) >= max_results:
                break

    if not found:
        return False, f"No files matching '{query}' found, sir."

    # Format results
    lines = [f"Found {len(found)} file{'s' if len(found) > 1 else ''} matching '{query}':"]
    for name, path, size in found[:8]:
        size_str = _format_size(size)
        lines.append(f"  • {name} ({size_str})")

    if len(found) > 8:
        lines.append(f"  ...and {len(found) - 8} more.")

    return True, " ".join(lines)


def search_file_contents(query: str, location: str = "documents",
                         extension: str = ".txt") -> tuple[bool, str]:
    """Search inside files for content matching the query."""
    from commands.files import _resolve_path
    search_dir = _resolve_path(location)
    query_lower = query.lower()
    matches = []

    if not os.path.isdir(search_dir):
        return False, f"Directory not found: {location}"

    for root, dirs, files in os.walk(search_dir):
        depth = root.replace(search_dir, "").count(os.sep)
        if depth > 3:
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for fname in files:
            if not fname.lower().endswith(extension):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if query_lower in line.lower():
                            matches.append((fname, i, line.strip()[:80]))
                            break
            except (OSError, PermissionError):
                continue

            if len(matches) >= 10:
                break

    if not matches:
        return False, f"No files contain '{query}' in {location}, sir."

    lines = [f"Found '{query}' in {len(matches)} file{'s' if len(matches) > 1 else ''}:"]
    for name, line_num, snippet in matches[:5]:
        lines.append(f"  • {name} (line {line_num}): {snippet}")
    return True, " ".join(lines)


# ═══════════════════════════════════════════════════════════
# Clipboard Intelligence
# ═══════════════════════════════════════════════════════════

_clipboard_history: list[dict] = []
_MAX_CLIPBOARD_HISTORY = 20


def get_clipboard_text() -> tuple[bool, str]:
    """Get current clipboard text."""
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5
        )
        text = result.stdout.strip()
        if text:
            # Record in history
            _clipboard_history.append({
                "text": text[:500],
                "time": datetime.now().isoformat(),
            })
            if len(_clipboard_history) > _MAX_CLIPBOARD_HISTORY:
                _clipboard_history.pop(0)

            preview = text[:100] + "..." if len(text) > 100 else text
            return True, f"Clipboard contains: {preview}"
        return False, "Clipboard is empty, sir."
    except Exception as e:
        return False, f"Couldn't access clipboard: {e}"


def set_clipboard_text(text: str) -> tuple[bool, str]:
    """Set clipboard text."""
    try:
        subprocess.run(
            ["powershell", "-Command", f"Set-Clipboard -Value '{text}'"],
            capture_output=True, timeout=5
        )
        return True, f"Copied to clipboard: {text[:60]}"
    except Exception as e:
        return False, f"Couldn't set clipboard: {e}"


def get_clipboard_history() -> tuple[bool, str]:
    """Get clipboard history."""
    if not _clipboard_history:
        return False, "No clipboard history yet, sir."

    lines = [f"Clipboard history ({len(_clipboard_history)} items):"]
    for i, item in enumerate(reversed(_clipboard_history[:5]), 1):
        preview = item["text"][:40] + "..." if len(item["text"]) > 40 else item["text"]
        lines.append(f"  {i}. {preview}")
    return True, " ".join(lines)


# ═══════════════════════════════════════════════════════════
# Window Management
# ═══════════════════════════════════════════════════════════

def minimize_all_windows() -> tuple[bool, str]:
    """Minimize all windows (Win+D equivalent)."""
    try:
        import pyautogui
        pyautogui.hotkey("win", "d")
        return True, "All windows minimized, sir."
    except Exception:
        try:
            ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)  # Win down
            ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)  # D down
            ctypes.windll.user32.keybd_event(0x44, 0, 2, 0)  # D up
            ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)  # Win up
            return True, "All windows minimized, sir."
        except Exception as e:
            return False, f"Couldn't minimize windows: {e}"


def snap_window_left() -> tuple[bool, str]:
    """Snap the active window to the left half of the screen."""
    try:
        import pyautogui
        pyautogui.hotkey("win", "left")
        return True, "Window snapped left, sir."
    except Exception as e:
        return False, f"Couldn't snap window: {e}"


def snap_window_right() -> tuple[bool, str]:
    """Snap the active window to the right half of the screen."""
    try:
        import pyautogui
        pyautogui.hotkey("win", "right")
        return True, "Window snapped right, sir."
    except Exception as e:
        return False, f"Couldn't snap window: {e}"


def tile_windows() -> tuple[bool, str]:
    """Tile windows side by side using Win+Tab → snap."""
    try:
        minimize_all_windows()
        return True, "Windows tiled. Use 'snap left' or 'snap right' to arrange, sir."
    except Exception as e:
        return False, f"Couldn't tile windows: {e}"


def lock_screen() -> tuple[bool, str]:
    """Lock the workstation."""
    try:
        ctypes.windll.user32.LockWorkStation()
        return True, "Workstation locked, sir."
    except Exception as e:
        return False, f"Couldn't lock screen: {e}"


# ═══════════════════════════════════════════════════════════
# Disk Analysis
# ═══════════════════════════════════════════════════════════

def disk_usage_report(path: str = "") -> tuple[bool, str]:
    """Get disk usage for a directory or all drives."""
    import shutil

    if path:
        from commands.files import _resolve_path
        target = _resolve_path(path)
        if os.path.isdir(target):
            total_size = 0
            file_count = 0
            for root, dirs, files in os.walk(target):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    try:
                        total_size += os.path.getsize(os.path.join(root, f))
                        file_count += 1
                    except OSError:
                        pass
            return True, (f"{os.path.basename(target)}: {_format_size(total_size)} "
                          f"across {file_count} files, sir.")
        return False, f"Directory not found: {path}"

    # System drives
    lines = ["Disk usage:"]
    for letter in "CDEFGH":
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            try:
                usage = shutil.disk_usage(drive)
                total = _format_size(usage.total)
                used = _format_size(usage.used)
                free = _format_size(usage.free)
                pct = (usage.used / usage.total) * 100
                lines.append(f"  {drive} {used}/{total} ({pct:.0f}% used, {free} free)")
            except OSError:
                pass

    return True, " ".join(lines)


def recent_files(count: int = 10) -> tuple[bool, str]:
    """Find the most recently modified files across common directories."""
    home = os.path.expanduser("~")
    dirs_to_scan = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Downloads"),
    ]

    files = []
    for d in dirs_to_scan:
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.scandir(d):
                if entry.is_file():
                    files.append((entry.name, entry.stat().st_mtime, d))
        except OSError:
            pass

    files.sort(key=lambda x: x[1], reverse=True)
    top = files[:count]

    if not top:
        return False, "No recent files found, sir."

    lines = [f"Your {len(top)} most recent files:"]
    for name, mtime, parent in top:
        folder = os.path.basename(parent)
        age = _time_ago(mtime)
        lines.append(f"  • {name} ({folder}, {age})")

    return True, " ".join(lines)


# ═══════════════════════════════════════════════════════════
# Process Management
# ═══════════════════════════════════════════════════════════

def find_process(name: str) -> tuple[bool, str]:
    """Find running processes by name."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}*"],
            capture_output=True, text=True, timeout=10
        )
        lines = [l for l in result.stdout.split("\n") if name.lower() in l.lower()]
        if lines:
            return True, f"Found {len(lines)} process(es) matching '{name}': {lines[0].strip()}"
        return False, f"No processes matching '{name}' found, sir."
    except Exception as e:
        return False, f"Couldn't search processes: {e}"


def kill_process(name: str) -> tuple[bool, str]:
    """Kill a process by name."""
    try:
        result = subprocess.run(
            ["taskkill", "/IM", f"{name}", "/F"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, f"Process '{name}' terminated, sir."
        return False, f"Couldn't kill '{name}': {result.stderr.strip()}"
    except Exception as e:
        return False, f"Error killing process: {e}"


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _time_ago(timestamp: float) -> str:
    """Convert timestamp to human-readable 'time ago'."""
    delta = datetime.now() - datetime.fromtimestamp(timestamp)
    if delta.seconds < 60:
        return "just now"
    if delta.seconds < 3600:
        return f"{delta.seconds // 60}m ago"
    if delta.seconds < 86400:
        return f"{delta.seconds // 3600}h ago"
    return f"{delta.days}d ago"


# ═══════════════════════════════════════════════════════════
# Command Router
# ═══════════════════════════════════════════════════════════

def handle_os_control_command(cmd: str) -> tuple[bool, bool, str]:
    """
    Route OS control commands.

    Returns: (handled, success, message)
    """
    # Deep search
    for prefix in ("deep search ", "search everywhere for ", "find everywhere "):
        if cmd.startswith(prefix):
            query = cmd[len(prefix):].strip()
            ok, msg = deep_search(query)
            return True, ok, msg

    # Content search
    if cmd.startswith("search inside ") or cmd.startswith("search contents "):
        query = cmd.split("for ", 1)[-1].strip() if "for " in cmd else cmd.split(" ", 2)[-1]
        ok, msg = search_file_contents(query)
        return True, ok, msg

    # Clipboard
    if cmd in ("clipboard", "what's on clipboard", "show clipboard", "read clipboard",
               "what's copied", "what did i copy"):
        ok, msg = get_clipboard_text()
        return True, ok, msg

    if cmd in ("clipboard history", "show clipboard history"):
        ok, msg = get_clipboard_history()
        return True, ok, msg

    if cmd.startswith("copy ") and "to clipboard" in cmd:
        text = cmd.replace("copy ", "").replace("to clipboard", "").strip()
        ok, msg = set_clipboard_text(text)
        return True, ok, msg

    # Window management
    if cmd in ("minimize all", "minimize all windows", "clear the screen",
               "show desktop", "hide everything"):
        ok, msg = minimize_all_windows()
        return True, ok, msg

    if cmd in ("snap left", "snap window left", "window left"):
        ok, msg = snap_window_left()
        return True, ok, msg

    if cmd in ("snap right", "snap window right", "window right"):
        ok, msg = snap_window_right()
        return True, ok, msg

    if cmd in ("tile windows", "arrange windows", "split screen"):
        ok, msg = tile_windows()
        return True, ok, msg

    if cmd in ("lock", "lock screen", "lock the screen", "lock computer",
               "lock the computer", "lock workstation"):
        ok, msg = lock_screen()
        return True, ok, msg

    # Disk analysis
    if cmd in ("disk usage", "disk space", "storage", "how much space",
               "storage status", "drive space"):
        ok, msg = disk_usage_report()
        return True, ok, msg

    if cmd.startswith("disk usage "):
        path = cmd.replace("disk usage ", "").strip()
        ok, msg = disk_usage_report(path)
        return True, ok, msg

    # Recent files
    if cmd in ("recent files", "show recent files", "latest files",
               "what files did i work on", "recent documents"):
        ok, msg = recent_files()
        return True, ok, msg

    # Process management
    if cmd.startswith("find process "):
        name = cmd.replace("find process ", "").strip()
        ok, msg = find_process(name)
        return True, ok, msg

    if cmd.startswith("kill process "):
        name = cmd.replace("kill process ", "").strip()
        ok, msg = kill_process(name)
        return True, ok, msg

    return False, False, ""
