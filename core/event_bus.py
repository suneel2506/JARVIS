"""
core/event_bus.py — Central publish-subscribe event bus for J.A.R.V.I.S.

Decouples all modules so voice, AI, memory, HUD, and automation
communicate through events rather than direct function calls.

Thread-safe. Supports wildcard subscriptions.

Usage:
    from core.event_bus import bus, Events

    # Subscribe
    bus.on(Events.STATE_CHANGED, lambda **d: print(d["state"]))

    # Emit
    bus.emit(Events.STATE_CHANGED, state="listening")

    # Unsubscribe
    bus.off(Events.STATE_CHANGED, my_callback)
"""
import threading
from typing import Callable, Any
from collections import defaultdict

from core.logger import get_logger

log = get_logger("core.event_bus")


# ═══════════════════════════════════════════════════════════
# Event Name Constants
# ═══════════════════════════════════════════════════════════

class Events:
    """All event names used throughout J.A.R.V.I.S."""

    # ─── State ──────────────────────────────────────────
    STATE_CHANGED       = "state.changed"        # state: str, prev_state: str
    SYSTEM_READY        = "system.ready"          # (no data)

    # ─── Command Pipeline ───────────────────────────────
    COMMAND_RECEIVED    = "command.received"      # command: str, source: str ("voice"|"text")
    COMMAND_STAGE       = "command.stage"         # stage: str, label: str
    COMMAND_COMPLETED   = "command.completed"     # command: str, response: str, duration_ms: int, success: bool
    COMMAND_ERROR       = "command.error"         # command: str, error: str

    # ─── Voice ──────────────────────────────────────────
    SPEAK_START         = "speak.start"           # text: str
    SPEAK_END           = "speak.end"             # text: str
    WAKE_WORD_DETECTED  = "wake.detected"         # phrase: str

    # ─── AI ─────────────────────────────────────────────
    AI_RESPONSE         = "ai.response"           # query: str, response: str, latency_ms: int
    AI_STATUS_CHANGED   = "ai.status_changed"     # status: str, provider: str

    # ─── System ─────────────────────────────────────────
    SYSTEM_STATS        = "system.stats"          # stats: dict
    MIC_STATE_CHANGED   = "mic.state_changed"     # state: str, device: str
    ERROR               = "system.error"          # source: str, error: str

    # ─── Memory ─────────────────────────────────────────
    MEMORY_UPDATED      = "memory.updated"        # category: str, key: str
    MEMORY_RECALLED     = "memory.recalled"       # query: str, result: str

    # ─── Proactive ──────────────────────────────────────
    NOTIFICATION        = "notification"          # title: str, message: str, level: str

    # ─── Wildcard ───────────────────────────────────────
    ALL                 = "*"                     # Receives every event


# ═══════════════════════════════════════════════════════════
# Event Bus Implementation
# ═══════════════════════════════════════════════════════════

class EventBus:
    """
    Thread-safe publish-subscribe event bus.

    Subscribers are called synchronously in the emitting thread.
    Errors in subscribers are logged but never propagate.
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self._emit_count: int = 0
        self._error_count: int = 0

    def on(self, event: str, callback: Callable) -> None:
        """
        Subscribe to an event.

        Args:
            event: Event name (use Events.* constants)
            callback: Function(**kwargs) called when event fires
        """
        with self._lock:
            if callback not in self._subscribers[event]:
                self._subscribers[event].append(callback)

    def off(self, event: str, callback: Callable) -> None:
        """
        Unsubscribe from an event.

        Args:
            event: Event name
            callback: The callback to remove
        """
        with self._lock:
            try:
                self._subscribers[event].remove(callback)
            except ValueError:
                pass

    def emit(self, event: str, **data: Any) -> None:
        """
        Emit an event to all subscribers.

        Args:
            event: Event name
            **data: Keyword arguments passed to subscribers
        """
        self._emit_count += 1

        # Collect callbacks (snapshot under lock)
        with self._lock:
            callbacks = list(self._subscribers.get(event, []))
            # Also fire wildcard subscribers
            if event != Events.ALL:
                callbacks.extend(self._subscribers.get(Events.ALL, []))

        # Fire callbacks outside the lock
        for cb in callbacks:
            try:
                cb(event=event, **data)
            except Exception as e:
                self._error_count += 1
                log.debug("Event '%s' subscriber error: %s", event, e)

    def clear(self, event: str | None = None) -> None:
        """
        Remove all subscribers for an event, or all events if None.

        Args:
            event: Event name to clear, or None for all
        """
        with self._lock:
            if event is None:
                self._subscribers.clear()
            else:
                self._subscribers.pop(event, None)

    def subscriber_count(self, event: str | None = None) -> int:
        """Get subscriber count for an event, or total if None."""
        with self._lock:
            if event is None:
                return sum(len(v) for v in self._subscribers.values())
            return len(self._subscribers.get(event, []))

    def get_stats(self) -> dict:
        """Get bus diagnostics."""
        return {
            "total_events_emitted": self._emit_count,
            "total_errors": self._error_count,
            "subscriber_count": self.subscriber_count(),
            "event_types": len(self._subscribers),
        }

    def __repr__(self) -> str:
        return (
            f"EventBus(subscribers={self.subscriber_count()}, "
            f"emitted={self._emit_count})"
        )


# ═══════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════

bus = EventBus()
"""Global event bus instance. Import and use: `from core.event_bus import bus, Events`"""
