"""
commands/system.py — System control commands for J.A.R.V.I.S.

Power management, screen control, brightness, and system information.
Volume control is handled by commands/media.py.
"""
import os
import ctypes

from core.logger import get_logger

log = get_logger("commands.system")


def shutdown_pc(delay: int = 5) -> tuple[bool, str]:
    """Shutdown the PC after a delay."""
    os.system(f"shutdown /s /t {delay}")
    log.info("Shutdown initiated with %ds delay", delay)
    return True, f"Shutting down in {delay} seconds"


def restart_pc(delay: int = 5) -> tuple[bool, str]:
    """Restart the PC after a delay."""
    os.system(f"shutdown /r /t {delay}")
    log.info("Restart initiated with %ds delay", delay)
    return True, f"Restarting in {delay} seconds"


def cancel_shutdown() -> tuple[bool, str]:
    """Cancel a pending shutdown/restart."""
    os.system("shutdown /a")
    log.info("Shutdown cancelled")
    return True, "Shutdown cancelled"


def lock_pc() -> tuple[bool, str]:
    """Lock the workstation."""
    ctypes.windll.user32.LockWorkStation()
    log.info("PC locked")
    return True, "Locking the PC"


def sleep_pc() -> tuple[bool, str]:
    """Put the PC to sleep."""
    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    log.info("PC put to sleep")
    return True, "Putting the PC to sleep"


def log_off() -> tuple[bool, str]:
    """Log off the current user."""
    os.system("shutdown /l")
    log.info("Logging off")
    return True, "Logging off"


def get_battery_status() -> tuple[bool, str]:
    """Get battery percentage and charging status."""
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery is None:
            return True, "No battery detected. This appears to be a desktop PC."
        status = "charging" if battery.power_plugged else "on battery"
        return True, f"Battery is at {battery.percent:.0f}%, {status}"
    except Exception as e:
        log.error("Battery check failed: %s", e)
        return False, "Couldn't check battery status"


def get_cpu_usage() -> tuple[bool, str]:
    """Get current CPU usage."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        return True, f"CPU usage is at {cpu:.0f}%"
    except Exception as e:
        log.error("CPU check failed: %s", e)
        return False, "Couldn't check CPU usage"


def get_ram_usage() -> tuple[bool, str]:
    """Get current RAM usage."""
    try:
        import psutil
        ram = psutil.virtual_memory()
        used_gb = round(ram.used / (1024 ** 3), 1)
        total_gb = round(ram.total / (1024 ** 3), 1)
        return True, f"RAM usage: {ram.percent:.0f}% — {used_gb}GB of {total_gb}GB used"
    except Exception as e:
        log.error("RAM check failed: %s", e)
        return False, "Couldn't check RAM usage"


def get_disk_usage() -> tuple[bool, str]:
    """Get disk usage."""
    try:
        import psutil
        disk = psutil.disk_usage('/')
        used_gb = round(disk.used / (1024 ** 3), 1)
        total_gb = round(disk.total / (1024 ** 3), 1)
        return True, f"Disk usage: {disk.percent:.0f}% — {used_gb}GB of {total_gb}GB used"
    except Exception as e:
        log.error("Disk check failed: %s", e)
        return False, "Couldn't check disk usage"


def get_internet_status() -> tuple[bool, str]:
    """Check internet connectivity."""
    try:
        import socket
        s = socket.create_connection(("8.8.8.8", 53), timeout=3)
        s.close()
        return True, "Internet connection is active"
    except OSError:
        return True, "No internet connection detected"


def set_brightness(level: int) -> tuple[bool, str]:
    """Set screen brightness (0-100) on supported hardware."""
    try:
        import subprocess
        level = max(0, min(100, level))
        subprocess.run(
            ["powershell", "-Command",
             f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
             f".WmiSetBrightness(0, {level})"],
            capture_output=True, timeout=5,
        )
        log.info("Brightness set to %d%%", level)
        return True, f"Brightness set to {level}%"
    except Exception as e:
        log.error("Brightness control failed: %s", e)
        return False, "Couldn't adjust brightness. This might not be supported on your device."


def handle_system_command(command: str) -> tuple[bool, bool, str]:
    """
    Route system-related commands.

    Returns:
        (handled, success, message)
    """
    cmd = command.lower().strip()

    # Power management
    if "shutdown" in cmd and "cancel" not in cmd:
        ok, msg = shutdown_pc()
        return True, ok, msg

    if "restart" in cmd or "reboot" in cmd:
        ok, msg = restart_pc()
        return True, ok, msg

    if "cancel shutdown" in cmd or "abort shutdown" in cmd:
        ok, msg = cancel_shutdown()
        return True, ok, msg

    if "lock" in cmd and any(w in cmd for w in ("pc", "computer", "screen", "lock")):
        ok, msg = lock_pc()
        return True, ok, msg

    if "sleep" in cmd and any(w in cmd for w in ("pc", "computer", "mode")):
        ok, msg = sleep_pc()
        return True, ok, msg

    if "log off" in cmd or "logoff" in cmd or "sign out" in cmd:
        ok, msg = log_off()
        return True, ok, msg

    # System info queries
    if "battery" in cmd:
        ok, msg = get_battery_status()
        return True, ok, msg

    if "cpu" in cmd and ("usage" in cmd or "how much" in cmd or "check" in cmd):
        ok, msg = get_cpu_usage()
        return True, ok, msg

    if "ram" in cmd or "memory usage" in cmd:
        ok, msg = get_ram_usage()
        return True, ok, msg

    if "disk" in cmd and ("usage" in cmd or "space" in cmd or "storage" in cmd):
        ok, msg = get_disk_usage()
        return True, ok, msg

    if "internet" in cmd and ("status" in cmd or "check" in cmd or "connection" in cmd):
        ok, msg = get_internet_status()
        return True, ok, msg

    # Brightness
    if "brightness" in cmd:
        import re
        match = re.search(r'(\d+)', cmd)
        if match:
            level = int(match.group(1))
            ok, msg = set_brightness(level)
            return True, ok, msg
        if "up" in cmd or "increase" in cmd:
            ok, msg = set_brightness(80)
            return True, ok, msg
        if "down" in cmd or "decrease" in cmd:
            ok, msg = set_brightness(30)
            return True, ok, msg

    return False, False, ""
