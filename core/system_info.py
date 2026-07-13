"""
core/system_info.py — Real-time system information for J.A.R.V.I.S. HUD.

Runs a background thread that polls CPU, RAM, battery, disk, network,
GPU, temperature, network speed, ping, active window, and uptime
stats every second and makes them available thread-safely.
"""
import psutil
import platform
import socket
import subprocess
import threading
import time
from typing import Any

from core.logger import get_logger

log = get_logger("core.system_info")

_stats: dict[str, Any] = {
    "cpu_percent": 0.0,
    "ram_percent": 0.0,
    "ram_used_gb": 0.0,
    "ram_total_gb": 0.0,
    "battery_percent": 100,
    "battery_plugged": False,
    "disk_percent": 0.0,
    "disk_used_gb": 0.0,
    "disk_total_gb": 0.0,
    "network_connected": False,
    "ip_address": "N/A",
    "hostname": platform.node(),
    "os_name": f"{platform.system()} {platform.release()}",
    "cpu_history": [0] * 30,
    # New stats
    "gpu_name": "N/A",
    "gpu_load": 0.0,
    "gpu_memory_used": 0,
    "gpu_memory_total": 0,
    "gpu_temp": 0,
    "cpu_temp": 0,
    "net_upload_speed": 0.0,
    "net_download_speed": 0.0,
    "ping_ms": 0,
    "active_window": "",
    "uptime_hours": 0,
    "process_count": 0,
}
_lock = threading.Lock()
_running = False

# For network speed calculation
_prev_net_io = None
_prev_net_time = 0.0

# For ping caching (every 10 seconds)
_ping_counter = 0
_cached_ping = 0


def get_stats() -> dict[str, Any]:
    """Get a snapshot of current system stats (thread-safe copy)."""
    with _lock:
        return dict(_stats)


def _get_gpu_stats() -> dict:
    """Get GPU stats (NVIDIA via GPUtil, fallback to WMI)."""
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            return {
                "gpu_name": gpu.name,
                "gpu_load": round(gpu.load * 100, 1),
                "gpu_memory_used": int(gpu.memoryUsed),
                "gpu_memory_total": int(gpu.memoryTotal),
                "gpu_temp": int(gpu.temperature),
            }
    except Exception:
        pass
    return {}


def _get_cpu_temp() -> int:
    """Get CPU temperature."""
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                for entry in entries:
                    if entry.current > 0:
                        return int(entry.current)
    except Exception:
        pass
    return 0


def _get_active_window() -> str:
    """Get the title of the currently active window."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if len(title) > 40:
            title = title[:37] + "..."
        return title
    except Exception:
        return ""


def _get_ping() -> int:
    """Get ping to Google DNS (cached, run every 10 cycles)."""
    global _ping_counter, _cached_ping
    _ping_counter += 1
    if _ping_counter < 10:
        return _cached_ping
    _ping_counter = 0
    try:
        result = subprocess.run(
            "ping -n 1 -w 1000 8.8.8.8",
            shell=True, capture_output=True, text=True, timeout=3,
        )
        import re
        match = re.search(r'time[=<](\d+)ms', result.stdout)
        if match:
            _cached_ping = int(match.group(1))
            return _cached_ping
    except Exception:
        pass
    return _cached_ping


def _update_loop() -> None:
    """Background thread that updates system stats every second."""
    global _running, _prev_net_io, _prev_net_time
    while _running:
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Battery
            battery = psutil.sensors_battery()
            bat_pct = battery.percent if battery else 100
            bat_plug = battery.power_plugged if battery else True

            # Network connectivity
            try:
                s = socket.create_connection(("8.8.8.8", 53), timeout=2)
                s.close()
                net_ok = True
            except OSError:
                net_ok = False

            # Local IP
            try:
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
            except Exception:
                ip = "N/A"

            # Network speed (bytes/sec → Mbps)
            net_io = psutil.net_io_counters()
            now = time.time()
            upload_speed = 0.0
            download_speed = 0.0
            if _prev_net_io is not None and (now - _prev_net_time) > 0:
                dt = now - _prev_net_time
                upload_speed = round((net_io.bytes_sent - _prev_net_io.bytes_sent) / dt / 125000, 2)  # Mbps
                download_speed = round((net_io.bytes_recv - _prev_net_io.bytes_recv) / dt / 125000, 2)
            _prev_net_io = net_io
            _prev_net_time = now

            # GPU (non-blocking, errors silently)
            gpu_stats = _get_gpu_stats()

            # CPU temperature
            cpu_temp = _get_cpu_temp()

            # Active window
            active_window = _get_active_window()

            # Ping (cached)
            ping = _get_ping()

            # Uptime
            boot_time = psutil.boot_time()
            uptime_hours = round((time.time() - boot_time) / 3600, 1)

            # Process count
            proc_count = len(psutil.pids())

            with _lock:
                _stats["cpu_percent"] = cpu
                _stats["ram_percent"] = ram.percent
                _stats["ram_used_gb"] = round(ram.used / (1024 ** 3), 1)
                _stats["ram_total_gb"] = round(ram.total / (1024 ** 3), 1)
                _stats["battery_percent"] = bat_pct
                _stats["battery_plugged"] = bat_plug
                _stats["disk_percent"] = disk.percent
                _stats["disk_used_gb"] = round(disk.used / (1024 ** 3), 1)
                _stats["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
                _stats["network_connected"] = net_ok
                _stats["ip_address"] = ip
                _stats["cpu_history"].pop(0)
                _stats["cpu_history"].append(cpu)

                # New stats
                _stats.update(gpu_stats)
                _stats["cpu_temp"] = cpu_temp
                _stats["net_upload_speed"] = upload_speed
                _stats["net_download_speed"] = download_speed
                _stats["ping_ms"] = ping
                _stats["active_window"] = active_window
                _stats["uptime_hours"] = uptime_hours
                _stats["process_count"] = proc_count

        except Exception as e:
            log.error("System info update error: %s", e)
            time.sleep(1)


def start_monitor() -> None:
    """Start the system monitoring background thread."""
    global _running
    if not _running:
        _running = True
        threading.Thread(target=_update_loop, daemon=True, name="SysMonitor").start()
        log.info("System monitor started")


def stop_monitor() -> None:
    """Stop the system monitor."""
    global _running
    _running = False
    log.info("System monitor stopped")
