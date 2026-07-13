"""
commands/files.py — File management commands for J.A.R.V.I.S.

Create, rename, delete, move, copy, open, find, count, and compress
files and folders via voice commands. Supports natural language paths.
"""
import os
import shutil
import re

from core.logger import get_logger

log = get_logger("commands.files")

# Default working directory for file operations
_DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")


def _resolve_path(natural_path: str) -> str:
    """
    Resolve natural language path descriptions to actual paths.

    'desktop' → ~/Desktop
    'documents' / 'documents section' → ~/Documents
    'downloads' → ~/Downloads
    'pictures' / 'images' → ~/Pictures
    'music' → ~/Music
    'videos' → ~/Videos
    """
    home = os.path.expanduser("~")
    path_map = {
        "desktop": os.path.join(home, "Desktop"),
        "documents": os.path.join(home, "Documents"),
        "document section": os.path.join(home, "Documents"),
        "documents section": os.path.join(home, "Documents"),
        "downloads": os.path.join(home, "Downloads"),
        "download": os.path.join(home, "Downloads"),
        "pictures": os.path.join(home, "Pictures"),
        "images": os.path.join(home, "Pictures"),
        "music": os.path.join(home, "Music"),
        "videos": os.path.join(home, "Videos"),
        "home": home,
        "user folder": home,
    }

    lower = natural_path.lower().strip()
    for key, path in path_map.items():
        if key in lower:
            # Extract any remaining path after the keyword
            remainder = lower.split(key)[-1].strip()
            if remainder:
                return os.path.join(path, remainder)
            return path

    # If it looks like an absolute path, use it directly
    if os.path.isabs(natural_path) or ':' in natural_path:
        return natural_path

    # Default to Desktop
    return os.path.join(_DESKTOP, natural_path)


def create_folder(name: str, path: str = "") -> tuple[bool, str]:
    """Create a new folder."""
    if path:
        base = _resolve_path(path)
    else:
        # Check if name contains a path hint
        base = _resolve_path(name)
        if base != os.path.join(_DESKTOP, name):
            # Path was resolved from name — name is the last component
            full_path = base
        else:
            full_path = os.path.join(_DESKTOP, name)
    
    if 'full_path' not in dir():
        full_path = os.path.join(base, name)

    try:
        os.makedirs(full_path, exist_ok=True)
        log.info("Created folder: %s", full_path)
        return True, f"Created folder at {full_path}"
    except Exception as e:
        log.error("Failed to create folder %s: %s", name, e)
        return False, f"Couldn't create folder '{name}': {e}"


def rename_file(old_name: str, new_name: str, path: str = "") -> tuple[bool, str]:
    """Rename a file or folder."""
    base = _resolve_path(path) if path else _DESKTOP
    old_path = os.path.join(base, old_name)
    new_path = os.path.join(base, new_name)
    try:
        if not os.path.exists(old_path):
            return False, f"'{old_name}' not found"
        os.rename(old_path, new_path)
        log.info("Renamed: %s → %s", old_path, new_path)
        return True, f"Renamed '{old_name}' to '{new_name}'"
    except Exception as e:
        log.error("Rename failed %s → %s: %s", old_name, new_name, e)
        return False, f"Couldn't rename: {e}"


def delete_file(name: str, path: str = "") -> tuple[bool, str]:
    """Delete a file or folder."""
    base = _resolve_path(path) if path else _DESKTOP
    full_path = os.path.join(base, name)
    try:
        if not os.path.exists(full_path):
            return False, f"'{name}' not found"
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        log.info("Deleted: %s", full_path)
        return True, f"Deleted '{name}'"
    except Exception as e:
        log.error("Delete failed for %s: %s", name, e)
        return False, f"Couldn't delete '{name}': {e}"


def move_file(name: str, destination: str, source: str = "") -> tuple[bool, str]:
    """Move a file or folder to a destination."""
    base = _resolve_path(source) if source else _DESKTOP
    dst = _resolve_path(destination)
    src_path = os.path.join(base, name)
    dst_path = os.path.join(dst, name)
    try:
        if not os.path.exists(src_path):
            return False, f"'{name}' not found"
        os.makedirs(dst, exist_ok=True)
        shutil.move(src_path, dst_path)
        log.info("Moved: %s → %s", src_path, dst_path)
        return True, f"Moved '{name}' to {dst}"
    except Exception as e:
        log.error("Move failed for %s: %s", name, e)
        return False, f"Couldn't move '{name}': {e}"


def copy_file(name: str, destination: str, source: str = "") -> tuple[bool, str]:
    """Copy a file or folder to a destination."""
    base = _resolve_path(source) if source else _DESKTOP
    dst = _resolve_path(destination)
    src_path = os.path.join(base, name)
    try:
        if not os.path.exists(src_path):
            return False, f"'{name}' not found"
        os.makedirs(dst, exist_ok=True)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, os.path.join(dst, name))
        else:
            shutil.copy2(src_path, os.path.join(dst, name))
        log.info("Copied: %s → %s", src_path, dst)
        return True, f"Copied '{name}' to {dst}"
    except Exception as e:
        log.error("Copy failed for %s: %s", name, e)
        return False, f"Couldn't copy '{name}': {e}"


def open_file(name: str, path: str = "") -> tuple[bool, str]:
    """Open a file with the default system application."""
    base = _resolve_path(path) if path else _DESKTOP
    full_path = os.path.join(base, name)
    try:
        if not os.path.exists(full_path):
            return False, f"'{name}' not found"
        os.startfile(full_path)
        log.info("Opened file: %s", full_path)
        return True, f"Opening '{name}'"
    except Exception as e:
        log.error("Failed to open %s: %s", name, e)
        return False, f"Couldn't open '{name}': {e}"


def list_directory(path: str = "") -> tuple[bool, str]:
    """List files in a directory."""
    base = _resolve_path(path) if path else _DESKTOP
    try:
        items = os.listdir(base)
        if not items:
            return True, f"{os.path.basename(base)} is empty."
        display = items[:15]
        listing = ", ".join(display)
        if len(items) > 15:
            listing += f", and {len(items) - 15} more items"
        return True, f"Contents of {os.path.basename(base)}: {listing}"
    except Exception as e:
        return False, f"Couldn't list directory: {e}"


def count_files(path: str = "", extension: str = "") -> tuple[bool, str]:
    """Count files in a directory, optionally filtered by extension."""
    base = _resolve_path(path) if path else _DESKTOP
    try:
        count = 0
        for f in os.listdir(base):
            if os.path.isfile(os.path.join(base, f)):
                if extension and not f.lower().endswith(extension.lower()):
                    continue
                count += 1
        ext_str = f" {extension}" if extension else ""
        return True, f"There are {count}{ext_str} files in {os.path.basename(base)}"
    except Exception as e:
        return False, f"Couldn't count files: {e}"


def open_folder(path: str = "") -> tuple[bool, str]:
    """Open a folder in File Explorer."""
    base = _resolve_path(path) if path else _DESKTOP
    try:
        os.startfile(base)
        log.info("Opened folder: %s", base)
        return True, f"Opening {os.path.basename(base)}"
    except Exception as e:
        return False, f"Couldn't open folder: {e}"


def handle_file_command(command: str) -> tuple[bool, bool, str]:
    """
    Route file management commands.
    Returns (handled, success, message)
    """
    cmd = command.lower().strip()

    # Create folder — supports natural language paths
    if cmd.startswith(("create folder ", "make folder ", "new folder ", "create the folder ")):
        for prefix in ("create the folder name of ", "create the folder named ", "create the folder ",
                       "create folder named ", "create folder ", "make folder ", "new folder "):
            if cmd.startswith(prefix):
                raw = command[len(prefix):].strip()
                break
        else:
            raw = cmd.split("folder ", 1)[-1].strip()

        # Check for "in the X section" or "in X"
        location = ""
        in_match = re.search(r'\s+(?:in|on|at|inside)\s+(?:the\s+)?(.+?)(?:\s+section|\s+folder)?$', raw, re.IGNORECASE)
        if in_match:
            location = in_match.group(1).strip()
            name = raw[:in_match.start()].strip()
        else:
            name = raw
            location = ""

        if location:
            base = _resolve_path(location)
            full_path = os.path.join(base, name)
            try:
                os.makedirs(full_path, exist_ok=True)
                log.info("Created folder: %s", full_path)
                return True, True, f"Created folder '{name}' in {os.path.basename(base)}"
            except Exception as e:
                return True, False, f"Couldn't create folder: {e}"
        else:
            ok, msg = create_folder(name)
            return True, ok, msg

    # Rename file
    if cmd.startswith("rename ") and " to " in cmd:
        parts = command[7:].split(" to ", 1)
        if len(parts) == 2:
            ok, msg = rename_file(parts[0].strip(), parts[1].strip())
            return True, ok, msg

    # Delete file
    if cmd.startswith(("delete ", "remove ")):
        for prefix in ("delete file ", "delete folder ", "delete ", "remove "):
            if cmd.startswith(prefix):
                name = command[len(prefix):].strip()
                break
        ok, msg = delete_file(name)
        return True, ok, msg

    # Move file
    if cmd.startswith("move ") and " to " in cmd:
        parts = command[5:].split(" to ", 1)
        if len(parts) == 2:
            ok, msg = move_file(parts[0].strip(), parts[1].strip())
            return True, ok, msg

    # Copy file
    if cmd.startswith("copy ") and " to " in cmd:
        parts = command[5:].split(" to ", 1)
        if len(parts) == 2:
            ok, msg = copy_file(parts[0].strip(), parts[1].strip())
            return True, ok, msg

    # Open file
    if cmd.startswith("open file "):
        name = command[10:].strip()
        ok, msg = open_file(name)
        return True, ok, msg

    # Open folders
    folder_map = {
        "open downloads": "downloads",
        "open documents": "documents",
        "open pictures": "pictures",
        "open music": "music",
        "open videos": "videos",
        "open desktop": "desktop",
        "open home": "home",
    }
    for trigger, path_key in folder_map.items():
        if cmd == trigger:
            ok, msg = open_folder(path_key)
            return True, ok, msg

    # List directory
    if cmd in ("list desktop", "what's on my desktop", "show desktop files",
               "list files", "what's on desktop"):
        ok, msg = list_directory()
        return True, ok, msg
    if cmd.startswith("list ") and cmd not in ("list routines", "list reminders",
                                                "list tasks", "list drives"):
        path = cmd[5:].strip()
        ok, msg = list_directory(path)
        return True, ok, msg

    # Count files
    if cmd.startswith("count files"):
        path = cmd.replace("count files in ", "").replace("count files ", "").strip()
        ok, msg = count_files(path or "")
        return True, ok, msg

    # ─── File Intelligence (natural language) ────────────

    # "find the pdf I opened yesterday" / "find pdf files"
    if cmd.startswith("find the ") or cmd.startswith("find my ") or cmd.startswith("locate "):
        ok, msg = smart_find_file(cmd)
        return True, ok, msg

    # "show the biggest files" / "largest files on desktop"
    if "biggest file" in cmd or "largest file" in cmd:
        path = ""
        for loc in ("desktop", "documents", "downloads"):
            if loc in cmd:
                path = loc
                break
        ok, msg = find_largest_files(path or "desktop")
        return True, ok, msg

    # "open the latest screenshot"
    if "latest screenshot" in cmd or "last screenshot" in cmd or "recent screenshot" in cmd:
        ok, msg = find_latest_screenshot()
        return True, ok, msg

    # "show today's files" / "files from today"
    if "today's file" in cmd or "files from today" in cmd or "today files" in cmd:
        path = ""
        for loc in ("desktop", "documents", "downloads"):
            if loc in cmd:
                path = loc
                break
        ok, msg = find_todays_files(path or "desktop")
        return True, ok, msg

    # "open recycle bin" / "empty recycle bin"
    if cmd in ("open recycle bin", "open trash", "recycle bin"):
        os.system("start shell:RecycleBinFolder")
        return True, True, "Opening the Recycle Bin, sir."
    if cmd in ("empty recycle bin", "empty trash", "clear recycle bin"):
        ok, msg = empty_recycle_bin()
        return True, ok, msg

    # "open my downloads" / "show recent documents"
    if "my downloads" in cmd or "recent downloads" in cmd:
        ok, msg = open_folder("downloads")
        return True, ok, msg
    if "my documents" in cmd or "recent documents" in cmd:
        ok, msg = open_folder("documents")
        return True, ok, msg

    return False, False, ""


# ═══════════════════════════════════════════════════════════
# File Intelligence — Natural Language Queries
# ═══════════════════════════════════════════════════════════

def smart_find_file(query: str) -> tuple[bool, str]:
    """
    Find files using natural language queries.

    Examples:
    - "find the pdf I opened yesterday"
    - "find my python files"
    - "locate the document I edited last night"
    """
    from datetime import datetime, timedelta

    query_lower = query.lower()

    # Determine extension filter
    ext_map = {
        "pdf": ".pdf", "word": ".docx", "doc": ".docx",
        "excel": ".xlsx", "spreadsheet": ".xlsx",
        "python": ".py", "py": ".py",
        "image": (".png", ".jpg", ".jpeg", ".gif", ".bmp"),
        "photo": (".png", ".jpg", ".jpeg"),
        "video": (".mp4", ".avi", ".mkv", ".mov"),
        "text": ".txt", "txt": ".txt",
        "powerpoint": ".pptx", "pptx": ".pptx",
        "zip": ".zip", "archive": (".zip", ".rar", ".7z"),
    }

    target_ext = None
    for keyword, ext in ext_map.items():
        if keyword in query_lower:
            target_ext = ext
            break

    # Determine time filter
    time_filter = None
    now = datetime.now()
    if "yesterday" in query_lower:
        time_filter = now - timedelta(days=1)
    elif "today" in query_lower:
        time_filter = now.replace(hour=0, minute=0, second=0)
    elif "last night" in query_lower or "tonight" in query_lower:
        time_filter = now - timedelta(hours=12)
    elif "this week" in query_lower:
        time_filter = now - timedelta(days=7)
    elif "last week" in query_lower:
        time_filter = now - timedelta(days=14)

    # Determine search location
    search_dirs = []
    home = os.path.expanduser("~")
    for loc, folder in [("desktop", "Desktop"), ("documents", "Documents"),
                        ("downloads", "Downloads"), ("pictures", "Pictures")]:
        if loc in query_lower:
            search_dirs.append(os.path.join(home, folder))
    if not search_dirs:
        # Search common locations
        search_dirs = [
            os.path.join(home, "Desktop"),
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
        ]

    # Search
    results = []
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        try:
            for entry in os.scandir(search_dir):
                if not entry.is_file():
                    continue
                name = entry.name.lower()

                # Extension filter
                if target_ext:
                    if isinstance(target_ext, tuple):
                        if not any(name.endswith(e) for e in target_ext):
                            continue
                    elif not name.endswith(target_ext):
                        continue

                # Time filter
                if time_filter:
                    stat = entry.stat()
                    mod_time = datetime.fromtimestamp(stat.st_mtime)
                    if mod_time < time_filter:
                        continue

                stat = entry.stat()
                results.append({
                    "name": entry.name,
                    "path": entry.path,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                })
        except PermissionError:
            continue

    # Sort by modification time (newest first)
    results.sort(key=lambda x: x["modified"], reverse=True)

    if results:
        top = results[:3]
        names = [f["name"] for f in top]
        msg = f"I found {len(results)} matching files. The most recent: {', '.join(names)}."
        if len(results) == 1:
            # Auto-open if single result
            try:
                os.startfile(results[0]["path"])
                msg = f"Opening {results[0]['name']}, sir."
            except Exception:
                pass
        return True, msg
    else:
        return False, "I'm afraid I couldn't find any matching files, sir."


def find_largest_files(location: str = "desktop", limit: int = 5) -> tuple[bool, str]:
    """Find the largest files in a location."""
    search_dir = _resolve_path(location)
    if not os.path.exists(search_dir):
        return False, f"I can't access {location}, sir."

    files = []
    try:
        for entry in os.scandir(search_dir):
            if entry.is_file():
                stat = entry.stat()
                files.append((entry.name, stat.st_size))
    except PermissionError:
        return False, f"I don't have permission to scan {location}, sir."

    files.sort(key=lambda x: x[1], reverse=True)
    top = files[:limit]

    if top:
        lines = []
        for name, size in top:
            if size > 1_000_000_000:
                s = f"{size / 1_000_000_000:.1f} GB"
            elif size > 1_000_000:
                s = f"{size / 1_000_000:.1f} MB"
            elif size > 1_000:
                s = f"{size / 1_000:.0f} KB"
            else:
                s = f"{size} bytes"
            lines.append(f"{name} at {s}")
        return True, f"The biggest files in {location}: {', '.join(lines)}."
    else:
        return False, f"No files found in {location}, sir."


def find_latest_screenshot() -> tuple[bool, str]:
    """Find and open the most recent screenshot."""
    from config.config import SCREENSHOT_DIR

    search_dirs = [SCREENSHOT_DIR]

    # Also check common screenshot locations
    home = os.path.expanduser("~")
    for d in ["Pictures/Screenshots", "Desktop", "OneDrive/Pictures/Screenshots"]:
        full = os.path.join(home, d)
        if os.path.exists(full) and full not in search_dirs:
            search_dirs.append(full)

    latest = None
    latest_time = 0

    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        for entry in os.scandir(search_dir):
            if entry.is_file():
                name = entry.name.lower()
                if any(name.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.bmp')):
                    stat = entry.stat()
                    if stat.st_mtime > latest_time:
                        latest_time = stat.st_mtime
                        latest = entry.path

    if latest:
        try:
            os.startfile(latest)
            return True, f"Opening {os.path.basename(latest)}, sir."
        except Exception:
            return True, f"Latest screenshot: {os.path.basename(latest)}."
    else:
        return False, "I couldn't find any screenshots, sir."


def find_todays_files(location: str = "desktop") -> tuple[bool, str]:
    """Find files modified today."""
    from datetime import datetime
    search_dir = _resolve_path(location)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    files = []
    if os.path.exists(search_dir):
        for entry in os.scandir(search_dir):
            if entry.is_file():
                stat = entry.stat()
                mod = datetime.fromtimestamp(stat.st_mtime)
                if mod >= today:
                    files.append(entry.name)

    if files:
        count = len(files)
        names = ", ".join(files[:5])
        extra = f" and {count - 5} more" if count > 5 else ""
        return True, f"You have {count} files from today in {location}: {names}{extra}."
    else:
        return False, f"No files were modified today in {location}, sir."


def empty_recycle_bin() -> tuple[bool, str]:
    """Empty the Windows Recycle Bin."""
    try:
        import ctypes
        # SHEmptyRecycleBin(hwnd, path, flags)
        # SHERB_NOCONFIRMATION = 0x00000001
        # SHERB_NOPROGRESSUI = 0x00000002
        # SHERB_NOSOUND = 0x00000004
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x0007)
        return True, "Recycle Bin has been emptied, sir."
    except Exception as e:
        return False, f"I couldn't empty the Recycle Bin: {e}"

