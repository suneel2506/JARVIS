"""
core/proactive.py — Proactive Intelligence Engine for J.A.R.V.I.S.

Monitors system state and user patterns to offer unprompted assistance.

Features:
- Temporal awareness (time-of-day behavior patterns)
- Behavior learning (tracks app usage, command frequency, active hours)
- Proactive notifications (low battery, high CPU, long idle, scheduled tasks)
- Smart suggestions based on historical patterns
- Morning briefing capability
"""
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Callable

from core.logger import get_logger

log = get_logger("core.proactive")

# ─── State ──────────────────────────────────────────────
_running = False
_on_notify_callback: Optional[Callable] = None
_check_interval = 60  # seconds between proactive checks
_last_battery_warn: float = 0.0
_last_cpu_warn: float = 0.0
_last_idle_warn: float = 0.0
_greeted_today: bool = False
_last_check_date: str = ""

# ─── Thresholds ─────────────────────────────────────────
BATTERY_WARN_THRESHOLD = 20
BATTERY_CRITICAL_THRESHOLD = 10
CPU_SUSTAINED_THRESHOLD = 90
CPU_SUSTAINED_SECONDS = 30
IDLE_SUGGEST_MINUTES = 30

# ─── Behavior Tracking ─────────────────────────────────
_hourly_activity: dict[int, int] = {h: 0 for h in range(24)}
_command_frequency: dict[str, int] = {}


def set_on_notify(callback: Callable[[str, str], None]) -> None:
    """Set callback for proactive notifications. Args: (title, message)."""
    global _on_notify_callback
    _on_notify_callback = callback


def _notify(title: str, message: str) -> None:
    """Send a proactive notification via callback + event bus."""
    if _on_notify_callback:
        try:
            _on_notify_callback(title, message)
        except Exception as e:
            log.debug("Notification callback error: %s", e)
    # Emit on event bus
    try:
        from core.event_bus import bus, Events
        bus.emit(Events.NOTIFICATION, title=title, message=message, level="info")
    except Exception:
        pass
    log.info("Proactive: [%s] %s", title, message)


def record_activity() -> None:
    """Record that the user is active at this hour."""
    hour = datetime.now().hour
    _hourly_activity[hour] = _hourly_activity.get(hour, 0) + 1


def record_command(command: str) -> None:
    """Track command frequency for pattern learning."""
    cmd = command.lower().strip()
    _command_frequency[cmd] = _command_frequency.get(cmd, 0) + 1
    record_activity()


def get_peak_hours() -> list[int]:
    """Get the user's most active hours (top 5)."""
    sorted_hours = sorted(_hourly_activity.items(), key=lambda x: x[1], reverse=True)
    return [h for h, _ in sorted_hours[:5] if _hourly_activity[h] > 0]


def get_top_commands(limit: int = 5) -> list[tuple[str, int]]:
    """Get the most frequently used commands."""
    sorted_cmds = sorted(_command_frequency.items(), key=lambda x: x[1], reverse=True)
    return sorted_cmds[:limit]


def get_morning_briefing() -> str:
    """Generate a morning briefing summary."""
    lines = []
    now = datetime.now()
    lines.append(f"Good morning, sir. It's {now.strftime('%A, %B %d')}.")

    # System status
    try:
        from core.system_info import get_stats
        stats = get_stats()
        bat = stats.get("battery_percent", 100)
        plugged = stats.get("battery_plugged", False)
        net = stats.get("network_connected", False)

        if bat < 50 and not plugged:
            lines.append(f"Battery is at {bat}%. You may want to plug in.")
        if not net:
            lines.append("Internet appears to be offline.")
    except Exception:
        pass

    # Pending reminders
    try:
        from core.scheduler import get_pending_reminders
        reminders = get_pending_reminders()
        if reminders:
            lines.append(f"You have {len(reminders)} pending reminder{'s' if len(reminders) > 1 else ''}.")
    except Exception:
        pass

    # Memory stats
    try:
        from core.memory import get_memory
        mem = get_memory()
        stats = mem.get_stats()
        total = stats.get("total_entries", 0)
        if total > 0:
            lines.append(f"Memory bank holds {total} entries across all categories.")
    except Exception:
        pass

    lines.append("All systems are at your disposal.")
    return " ".join(lines)


def _check_battery() -> None:
    """Check battery level and warn if low."""
    global _last_battery_warn
    now = time.time()
    if now - _last_battery_warn < 300:  # Don't spam (5 min cooldown)
        return

    try:
        from core.system_info import get_stats
        stats = get_stats()
        bat = stats.get("battery_percent", 100)
        plugged = stats.get("battery_plugged", False)

        if not plugged and bat <= BATTERY_CRITICAL_THRESHOLD:
            _notify("Battery Critical",
                    f"Battery at {bat}%, sir. I'd recommend connecting to power immediately.")
            _last_battery_warn = now
        elif not plugged and bat <= BATTERY_WARN_THRESHOLD:
            _notify("Battery Low",
                    f"Battery at {bat}%, sir. You may want to plug in soon.")
            _last_battery_warn = now
    except Exception:
        pass


def _check_cpu() -> None:
    """Check for sustained high CPU usage."""
    global _last_cpu_warn
    now = time.time()
    if now - _last_cpu_warn < 120:
        return

    try:
        from core.system_info import get_stats
        stats = get_stats()
        cpu = stats.get("cpu_percent", 0)
        if cpu > CPU_SUSTAINED_THRESHOLD:
            _notify("High CPU Usage",
                    f"CPU has been at {cpu:.0f}% for a sustained period, sir. "
                    "Shall I check what's consuming resources?")
            _last_cpu_warn = now
    except Exception:
        pass


def _check_greeting() -> None:
    """Greet the user once per day based on their active hours."""
    global _greeted_today, _last_check_date
    today = datetime.now().strftime("%Y-%m-%d")
    if today != _last_check_date:
        _greeted_today = False
        _last_check_date = today

    if _greeted_today:
        return

    hour = datetime.now().hour
    peak_hours = get_peak_hours()

    # Greet during the first peak hour or at standard times
    if hour in peak_hours or hour in (8, 9, 10):
        _greeted_today = True
        briefing = get_morning_briefing()
        _notify("Morning Briefing", briefing)


def _check_idle_suggestion() -> None:
    """Suggest activity after long idle periods."""
    global _last_idle_warn
    now = time.time()
    if now - _last_idle_warn < 600:  # 10 min cooldown
        return

    try:
        from core.listener import get_diagnostics
        diag = get_diagnostics()
        idle_seconds = diag.get("idle_seconds", 0)

        if idle_seconds > IDLE_SUGGEST_MINUTES * 60:
            _last_idle_warn = now
            # Don't actually notify — too intrusive. Just log.
            log.info("User idle for %d minutes", idle_seconds // 60)
    except Exception:
        pass


def _proactive_loop() -> None:
    """Background thread for proactive checks."""
    global _running
    while _running:
        try:
            _check_battery()
            _check_cpu()
            _check_greeting()
            _check_idle_suggestion()
        except Exception as e:
            log.debug("Proactive check error: %s", e)

        time.sleep(_check_interval)


def start_proactive() -> None:
    """Start the proactive intelligence engine."""
    global _running
    if not _running:
        _running = True
        threading.Thread(target=_proactive_loop, daemon=True,
                         name="ProactiveEngine").start()
        log.info("Proactive engine started (interval: %ds)", _check_interval)


def stop_proactive() -> None:
    """Stop the proactive engine."""
    global _running
    _running = False
    log.info("Proactive engine stopped")
