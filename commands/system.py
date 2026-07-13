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


def get_gpu_usage() -> tuple[bool, str]:
    """Get GPU usage if available."""
    # Try GPUtil (NVIDIA)
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            return True, (f"GPU: {gpu.name}, Load: {gpu.load * 100:.0f}%, "
                         f"Memory: {gpu.memoryUsed:.0f}MB/{gpu.memoryTotal:.0f}MB, "
                         f"Temperature: {gpu.temperature}°C")
    except ImportError:
        pass
    except Exception:
        pass

    # Try WMI fallback (Windows)
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "path", "win32_videocontroller", "get", "name,adapterram"],
            capture_output=True, text=True, timeout=5,
        )
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip() and 'Name' not in l]
        if lines:
            return True, f"GPU: {lines[0]}"
    except Exception:
        pass

    return True, "GPU information not available. Install GPUtil for NVIDIA monitoring."


def get_cpu_temperature() -> tuple[bool, str]:
    """Get CPU temperature if available."""
    try:
        import psutil
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                for entry in entries:
                    if entry.current > 0:
                        return True, f"CPU temperature: {entry.current:.0f}°C"
    except Exception:
        pass

    # WMI fallback for Windows
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "/namespace:\\\\root\\wmi", "PATH", "MSAcpi_ThermalZoneTemperature",
             "get", "CurrentTemperature"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line.isdigit():
                temp_c = (int(line) - 2732) / 10.0
                return True, f"CPU temperature: {temp_c:.0f}°C"
    except Exception:
        pass

    return True, "Temperature monitoring not available on this system"


def get_uptime() -> tuple[bool, str]:
    """Get system uptime."""
    try:
        import psutil
        boot_time = psutil.boot_time()
        import time
        uptime_seconds = time.time() - boot_time
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        if hours > 24:
            days = hours // 24
            hours = hours % 24
            return True, f"System has been running for {days} days, {hours} hours, {minutes} minutes"
        return True, f"System has been running for {hours} hours and {minutes} minutes"
    except Exception as e:
        return False, f"Couldn't get uptime: {e}"


def list_drives() -> tuple[bool, str]:
    """List available drives with sizes."""
    try:
        import psutil
        drives = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                total_gb = usage.total / (1024 ** 3)
                free_gb = usage.free / (1024 ** 3)
                drives.append(f"{part.device} ({total_gb:.0f}GB total, {free_gb:.0f}GB free)")
            except (PermissionError, OSError):
                drives.append(f"{part.device}")
        return True, "Drives: " + ", ".join(drives)
    except Exception as e:
        return False, f"Couldn't list drives: {e}"


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

    if "cpu" in cmd and ("usage" in cmd or "how much" in cmd or "check" in cmd or "status" in cmd):
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

    # GPU
    if "gpu" in cmd and ("usage" in cmd or "status" in cmd or "info" in cmd or cmd.strip() == "gpu"):
        ok, msg = get_gpu_usage()
        return True, ok, msg

    # Temperature
    if "temperature" in cmd or "cpu temp" in cmd or "how hot" in cmd:
        ok, msg = get_cpu_temperature()
        return True, ok, msg

    # Uptime
    if "uptime" in cmd or "how long" in cmd and ("running" in cmd or "on" in cmd):
        ok, msg = get_uptime()
        return True, ok, msg

    # Drives
    if "list drives" in cmd or "show drives" in cmd or "drives" in cmd:
        ok, msg = list_drives()
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

