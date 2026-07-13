"""
commands/utilities.py — System utilities for J.A.R.V.I.S.

Recycle bin, process management, file compression, disk utilities,
screen/audio recording, clipboard, and internet speed.
"""
import os
import subprocess
import shutil
import time

from core.logger import get_logger

log = get_logger("commands.utilities")


# ─── Recycle Bin ─────────────────────────────────────────

def empty_recycle_bin() -> tuple[bool, str]:
    """Empty the Windows recycle bin."""
    try:
        from ctypes import windll
        windll.shell32.SHEmptyRecycleBinW(None, None, 0x07)
        log.info("Recycle bin emptied")
        return True, "Recycle bin emptied"
    except Exception as e:
        log.error("Failed to empty recycle bin: %s", e)
        return False, f"Couldn't empty recycle bin: {e}"


# ─── Process Management ────────────────────────────────

def list_running_tasks() -> tuple[bool, str]:
    """List top resource-consuming processes."""
    try:
        import psutil
        procs = []
        for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                if info['cpu_percent'] and info['cpu_percent'] > 0.1:
                    procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
        top = procs[:8]
        if not top:
            return True, "No processes with significant CPU usage"
        lines = [f"{p['name']}: CPU {p['cpu_percent']:.0f}%, RAM {p.get('memory_percent', 0):.0f}%" for p in top]
        return True, "Top processes: " + ". ".join(lines)
    except Exception as e:
        return False, f"Error listing tasks: {e}"


def kill_process(name: str) -> tuple[bool, str]:
    """Kill a process by name."""
    try:
        result = subprocess.run(
            f"taskkill /f /im {name}.exe",
            shell=True, capture_output=True, text=True,
        )
        if result.returncode == 0:
            log.info("Killed process: %s", name)
            return True, f"Killed {name}"
        return False, f"Couldn't kill {name}: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Error: {e}"


# ─── File Compression ──────────────────────────────────

def compress_folder(folder_path: str) -> tuple[bool, str]:
    """Compress a folder to a zip archive."""
    if not os.path.exists(folder_path):
        # Try Desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        candidate = os.path.join(desktop, folder_path)
        if os.path.exists(candidate):
            folder_path = candidate
        else:
            return False, f"Folder not found: {folder_path}"

    try:
        output_path = folder_path.rstrip("/\\")
        shutil.make_archive(output_path, 'zip', folder_path)
        log.info("Compressed: %s", folder_path)
        return True, f"Compressed {os.path.basename(folder_path)} to {output_path}.zip"
    except Exception as e:
        return False, f"Compression failed: {e}"


def extract_archive(archive_path: str) -> tuple[bool, str]:
    """Extract a zip archive."""
    if not os.path.exists(archive_path):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        candidate = os.path.join(desktop, archive_path)
        if os.path.exists(candidate):
            archive_path = candidate
        else:
            return False, f"Archive not found: {archive_path}"

    try:
        output_dir = archive_path.rsplit('.', 1)[0]
        shutil.unpack_archive(archive_path, output_dir)
        log.info("Extracted: %s to %s", archive_path, output_dir)
        return True, f"Extracted to {output_dir}"
    except Exception as e:
        return False, f"Extraction failed: {e}"


# ─── Disk Utilities ─────────────────────────────────────

def find_largest_files(directory: str = None, count: int = 5) -> tuple[bool, str]:
    """Find the largest files in a directory."""
    if directory is None:
        directory = os.path.expanduser("~")

    try:
        files = []
        for root, dirs, filenames in os.walk(directory):
            # Skip hidden and system directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('AppData', '.git', 'node_modules', '.venv')]
            for f in filenames:
                try:
                    path = os.path.join(root, f)
                    size = os.path.getsize(path)
                    if size > 1_000_000:  # Only files > 1MB
                        files.append((path, size))
                except (OSError, PermissionError):
                    continue

        files.sort(key=lambda x: x[1], reverse=True)
        top = files[:count]

        if not top:
            return True, "No large files found"

        lines = []
        for path, size in top:
            if size >= 1_000_000_000:
                size_str = f"{size / 1_000_000_000:.1f}GB"
            else:
                size_str = f"{size / 1_000_000:.0f}MB"
            lines.append(f"{os.path.basename(path)}: {size_str}")

        return True, "Largest files: " + ", ".join(lines)
    except Exception as e:
        return False, f"Search failed: {e}"


def search_files(query: str, directory: str = None) -> tuple[bool, str]:
    """Search for files by name pattern."""
    if directory is None:
        directory = os.path.expanduser("~")

    try:
        found = []
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('AppData', '.git', 'node_modules')]
            for f in files:
                if query.lower() in f.lower():
                    found.append(os.path.join(root, f))
            if len(found) >= 10:
                break

        if not found:
            return True, f"No files found matching '{query}'"
        lines = [os.path.basename(f) for f in found[:5]]
        return True, f"Found {len(found)} files: " + ", ".join(lines)
    except Exception as e:
        return False, f"Search failed: {e}"


# ─── Internet Speed ────────────────────────────────────

def check_internet_speed() -> tuple[bool, str]:
    """Quick internet speed estimate using download test."""
    try:
        import requests
        # Download a small file and measure speed
        url = "https://speed.cloudflare.com/__down?bytes=1000000"
        start = time.time()
        resp = requests.get(url, timeout=10)
        elapsed = time.time() - start
        size_mb = len(resp.content) / 1_000_000
        speed_mbps = (size_mb * 8) / elapsed
        log.info("Speed test: %.1f Mbps", speed_mbps)
        return True, f"Download speed is approximately {speed_mbps:.1f} Megabits per second"
    except Exception as e:
        return False, f"Speed test failed: {e}"


def check_ping() -> tuple[bool, str]:
    """Check ping to Google DNS."""
    try:
        result = subprocess.run(
            "ping -n 1 8.8.8.8",
            shell=True, capture_output=True, text=True, timeout=5,
        )
        if "time=" in result.stdout:
            import re
            match = re.search(r'time[=<](\d+)ms', result.stdout)
            if match:
                ms = match.group(1)
                return True, f"Ping is {ms} milliseconds"
        return True, "Ping test completed but couldn't parse result"
    except Exception as e:
        return False, f"Ping failed: {e}"


# ─── Screen / Audio Recording ──────────────────────────

def record_screen(duration: int = 10) -> tuple[bool, str]:
    """Start screen recording using ffmpeg (if available)."""
    try:
        from config.config import DATA_DIR
        output = os.path.join(DATA_DIR, f"screen_{int(time.time())}.mp4")
        cmd = f'ffmpeg -f gdigrab -t {duration} -framerate 15 -i desktop -y "{output}"'
        subprocess.Popen(cmd, shell=True)
        log.info("Screen recording started: %ds → %s", duration, output)
        return True, f"Recording screen for {duration} seconds"
    except Exception as e:
        return False, f"Screen recording failed: {e}. Make sure ffmpeg is installed."


def record_audio(duration: int = 10) -> tuple[bool, str]:
    """Record audio from microphone."""
    try:
        import sounddevice as sd
        import wave
        from config.config import DATA_DIR, SAMPLING_RATE

        output = os.path.join(DATA_DIR, f"audio_{int(time.time())}.wav")
        log.info("Recording audio: %ds → %s", duration, output)

        audio_data = sd.rec(int(duration * SAMPLING_RATE), samplerate=SAMPLING_RATE, channels=1, dtype='int16')
        sd.wait()

        with wave.open(output, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLING_RATE)
            wf.writeframes(audio_data.tobytes())

        return True, f"Audio recorded and saved ({duration} seconds)"
    except Exception as e:
        return False, f"Audio recording failed: {e}"


# ─── Clipboard ──────────────────────────────────────────

def show_clipboard() -> tuple[bool, str]:
    """Show current clipboard content."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        content = root.clipboard_get()
        root.destroy()
        if len(content) > 200:
            content = content[:200] + "..."
        return True, f"Clipboard contains: {content}"
    except Exception:
        return True, "Clipboard is empty or contains non-text content"


def clear_clipboard() -> tuple[bool, str]:
    """Clear the clipboard."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.destroy()
        return True, "Clipboard cleared"
    except Exception as e:
        return False, f"Couldn't clear clipboard: {e}"


# ─── System Panels ──────────────────────────────────────

def open_system_panel(panel: str) -> tuple[bool, str]:
    """Open Windows system panels."""
    panels = {
        "device manager": "devmgmt.msc",
        "control panel": "control",
        "disk management": "diskmgmt.msc",
        "services": "services.msc",
        "event viewer": "eventvwr.msc",
        "registry": "regedit",
        "system information": "msinfo32",
        "environment variables": "rundll32.exe sysdm.cpl,EditEnvironmentVariables",
        "programs": "appwiz.cpl",
        "windows update": "start ms-settings:windowsupdate",
        "sound settings": "mmsys.cpl",
        "network connections": "ncpa.cpl",
        "power options": "powercfg.cpl",
        "display settings": "start ms-settings:display",
        "bluetooth": "start ms-settings:bluetooth",
        "wifi": "start ms-settings:network-wifi",
        "startup": "start ms-settings:startupapps",
        "storage": "start ms-settings:storagesense",
        "about": "start ms-settings:about",
    }

    for key, cmd in panels.items():
        if key in panel:
            os.system(cmd)
            log.info("Opened system panel: %s", key)
            return True, f"Opening {key}"

    return False, f"Unknown panel: {panel}"


# ─── Command Router ────────────────────────────────────

def handle_utility_command(command: str) -> tuple[bool, bool, str]:
    """
    Route utility commands.
    Returns (handled, success, message)
    """
    cmd = command.lower().strip()

    # Recycle bin
    if "empty recycle" in cmd or "clear recycle" in cmd or "empty trash" in cmd:
        ok, msg = empty_recycle_bin()
        return True, ok, msg

    # Process management
    if cmd in ("show running tasks", "list tasks", "running processes",
               "show processes", "top processes", "task list"):
        ok, msg = list_running_tasks()
        return True, ok, msg
    if cmd.startswith("kill process ") or cmd.startswith("kill "):
        name = cmd.replace("kill process ", "").replace("kill ", "").strip()
        ok, msg = kill_process(name)
        return True, ok, msg

    # Compression
    if cmd.startswith("compress ") or cmd.startswith("zip "):
        folder = cmd.replace("compress folder ", "").replace("compress ", "").replace("zip ", "").strip()
        ok, msg = compress_folder(folder)
        return True, ok, msg
    if cmd.startswith("extract ") or cmd.startswith("unzip "):
        archive = cmd.replace("extract archive ", "").replace("extract ", "").replace("unzip ", "").strip()
        ok, msg = extract_archive(archive)
        return True, ok, msg

    # File search
    if "largest files" in cmd or "biggest files" in cmd:
        ok, msg = find_largest_files()
        return True, ok, msg
    if cmd.startswith("search for ") or cmd.startswith("find file ") or cmd.startswith("search files "):
        query = cmd.replace("search for ", "").replace("find file ", "").replace("search files ", "").strip()
        ok, msg = search_files(query)
        return True, ok, msg
    if cmd.startswith("search pdfs") or cmd.startswith("find pdfs"):
        ok, msg = search_files(".pdf")
        return True, ok, msg

    # Internet
    if "internet speed" in cmd or "speed test" in cmd or "download speed" in cmd:
        ok, msg = check_internet_speed()
        return True, ok, msg
    if cmd in ("check ping", "ping", "ping test"):
        ok, msg = check_ping()
        return True, ok, msg

    # Recording
    if "record screen" in cmd or "screen record" in cmd:
        import re
        dur_match = re.search(r'(\d+)\s*(second|sec|minute|min)', cmd)
        duration = 10
        if dur_match:
            amount = int(dur_match.group(1))
            if "min" in dur_match.group(2):
                duration = amount * 60
            else:
                duration = amount
        ok, msg = record_screen(duration)
        return True, ok, msg
    if "record audio" in cmd or "record voice" in cmd or "record mic" in cmd:
        import re
        dur_match = re.search(r'(\d+)\s*(second|sec|minute|min)', cmd)
        duration = 10
        if dur_match:
            amount = int(dur_match.group(1))
            if "min" in dur_match.group(2):
                duration = amount * 60
            else:
                duration = amount
        ok, msg = record_audio(duration)
        return True, ok, msg

    # Clipboard
    if "show clipboard" in cmd or "what's in clipboard" in cmd or "clipboard content" in cmd:
        ok, msg = show_clipboard()
        return True, ok, msg
    if "clear clipboard" in cmd or "empty clipboard" in cmd:
        ok, msg = clear_clipboard()
        return True, ok, msg

    # System panels
    panel_triggers = [
        "device manager", "control panel", "disk management", "services",
        "event viewer", "registry", "system information", "environment variables",
        "programs", "windows update", "sound settings", "network connections",
        "power options", "display settings", "bluetooth", "wifi", "startup",
        "storage", "about",
    ]
    for trigger in panel_triggers:
        if trigger in cmd and ("open" in cmd or cmd == trigger):
            ok, msg = open_system_panel(trigger)
            return True, ok, msg

    return False, False, ""
