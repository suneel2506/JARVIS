"""
core/system_info.py — Real-time system information for J.A.R.V.I.S. HUD.

Runs a background thread that polls CPU, RAM, battery, disk, and network
stats every second and makes them available thread-safely.
"""
import psutil
import platform
import socket
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
}
_lock = threading.Lock()
_running = False


def get_stats() -> dict[str, Any]:
    """Get a snapshot of current system stats (thread-safe copy)."""
    with _lock:
        return dict(_stats)


def _update_loop() -> None:
    """Background thread that updates system stats every second."""
    global _running
    while _running:
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Battery (may not exist on desktops)
            battery = psutil.sensors_battery()
            bat_pct = battery.percent if battery else 100
            bat_plug = battery.power_plugged if battery else True

            # Network connectivity check
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
                # Update CPU history (rolling window)
                _stats["cpu_history"].pop(0)
                _stats["cpu_history"].append(cpu)

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
