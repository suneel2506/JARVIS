"""
commands/files.py — File management commands for J.A.R.V.I.S.

Create, rename, delete, and move files and folders via voice commands.
"""
import os
import shutil

from core.logger import get_logger

log = get_logger("commands.files")

# Default working directory for file operations
_DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")


def create_folder(name: str, path: str = "") -> tuple[bool, str]:
    """
    Create a new folder.

    Args:
        name: Folder name to create.
        path: Parent directory (defaults to Desktop).
    """
    base = path if path else _DESKTOP
    full_path = os.path.join(base, name)
    try:
        os.makedirs(full_path, exist_ok=True)
        log.info("Created folder: %s", full_path)
        return True, f"Created folder '{name}' on your Desktop"
    except Exception as e:
        log.error("Failed to create folder %s: %s", name, e)
        return False, f"Couldn't create folder '{name}': {e}"


def rename_file(old_name: str, new_name: str, path: str = "") -> tuple[bool, str]:
    """
    Rename a file or folder.

    Args:
        old_name: Current name.
        new_name: New name.
        path: Directory containing the file (defaults to Desktop).
    """
    base = path if path else _DESKTOP
    old_path = os.path.join(base, old_name)
    new_path = os.path.join(base, new_name)
    try:
        if not os.path.exists(old_path):
            return False, f"'{old_name}' not found on Desktop"
        os.rename(old_path, new_path)
        log.info("Renamed: %s → %s", old_path, new_path)
        return True, f"Renamed '{old_name}' to '{new_name}'"
    except Exception as e:
        log.error("Rename failed %s → %s: %s", old_name, new_name, e)
        return False, f"Couldn't rename: {e}"


def delete_file(name: str, path: str = "") -> tuple[bool, str]:
    """
    Delete a file or folder.

    Args:
        name: File or folder name to delete.
        path: Directory containing the file (defaults to Desktop).
    """
    base = path if path else _DESKTOP
    full_path = os.path.join(base, name)
    try:
        if not os.path.exists(full_path):
            return False, f"'{name}' not found on Desktop"
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
    """
    Move a file or folder.

    Args:
        name: File or folder to move.
        destination: Target directory path.
        source: Source directory (defaults to Desktop).
    """
    base = source if source else _DESKTOP
    src_path = os.path.join(base, name)
    dst_path = os.path.join(destination, name)
    try:
        if not os.path.exists(src_path):
            return False, f"'{name}' not found"
        shutil.move(src_path, dst_path)
        log.info("Moved: %s → %s", src_path, dst_path)
        return True, f"Moved '{name}' to '{destination}'"
    except Exception as e:
        log.error("Move failed for %s: %s", name, e)
        return False, f"Couldn't move '{name}': {e}"


def open_file(name: str, path: str = "") -> tuple[bool, str]:
    """Open a file with the default system application."""
    base = path if path else _DESKTOP
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


def list_desktop() -> tuple[bool, str]:
    """List files on the Desktop."""
    try:
        items = os.listdir(_DESKTOP)
        if not items:
            return True, "Your Desktop is empty."
        # Limit to first 15 items
        display = items[:15]
        listing = ", ".join(display)
        if len(items) > 15:
            listing += f", and {len(items) - 15} more items"
        return True, f"Desktop contents: {listing}"
    except Exception as e:
        return False, f"Couldn't list Desktop: {e}"


def handle_file_command(command: str) -> tuple[bool, bool, str]:
    """
    Route file management commands.

    Returns:
        (handled, success, message)
    """
    cmd = command.lower().strip()

    # Create folder
    if cmd.startswith(("create folder ", "make folder ", "new folder ")):
        for prefix in ("create folder ", "make folder ", "new folder "):
            if cmd.startswith(prefix):
                name = command[len(prefix):].strip()
                break
        ok, msg = create_folder(name)
        return True, ok, msg

    # Rename file
    if cmd.startswith("rename ") and " to " in cmd:
        parts = command[7:].split(" to ", 1)
        if len(parts) == 2:
            old_name = parts[0].strip()
            new_name = parts[1].strip()
            ok, msg = rename_file(old_name, new_name)
            return True, ok, msg

    # Delete file
    if cmd.startswith(("delete ", "remove ")):
        for prefix in ("delete file ", "delete folder ", "delete ", "remove "):
            if cmd.startswith(prefix):
                name = command[len(prefix):].strip()
                break
        ok, msg = delete_file(name)
        return True, ok, msg

    # Open file
    if cmd.startswith("open file "):
        name = command[10:].strip()
        ok, msg = open_file(name)
        return True, ok, msg

    # List desktop
    if cmd in ("list desktop", "what's on my desktop", "show desktop files", "list files"):
        ok, msg = list_desktop()
        return True, ok, msg

    return False, False, ""
