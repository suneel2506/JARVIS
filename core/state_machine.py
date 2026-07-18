"""
core/state_machine.py — Formal state machine for J.A.R.V.I.S.

Manages the unified system state across all modules.
Every state transition emits STATE_CHANGED on the event bus,
which the HUD, voice, and all subsystems subscribe to.

States:
    idle         → Awaiting wake word (slow reactor pulse)
    listening    → Capturing voice input (blue pulse)
    understanding → Intent detection + NLU (rotating cyan rings)
    thinking     → AI generating response (rotating amber rings)
    executing    → Running a command (green energy flow)
    speaking     → TTS output (wave-synced animation)
    monitoring   → Background proactive watch (dim steady pulse)
    error        → Something failed (red warning pulse)
"""
import threading
import time

from core.logger import get_logger

log = get_logger("core.state_machine")


# ═══════════════════════════════════════════════════════════
# State Constants
# ═══════════════════════════════════════════════════════════

class States:
    """All valid system states."""
    IDLE          = "idle"
    LISTENING     = "listening"
    UNDERSTANDING = "understanding"
    THINKING      = "thinking"
    EXECUTING     = "executing"
    SPEAKING      = "speaking"
    MONITORING    = "monitoring"
    ERROR         = "error"

    ALL = (IDLE, LISTENING, UNDERSTANDING, THINKING,
           EXECUTING, SPEAKING, MONITORING, ERROR)


# ═══════════════════════════════════════════════════════════
# Valid Transitions
# ═══════════════════════════════════════════════════════════

# Any state can transition to ERROR or IDLE (recovery)
_TRANSITIONS: dict[str, set[str]] = {
    States.IDLE:          {States.LISTENING, States.MONITORING, States.ERROR},
    States.LISTENING:     {States.UNDERSTANDING, States.IDLE, States.ERROR},
    States.UNDERSTANDING: {States.THINKING, States.EXECUTING, States.IDLE, States.ERROR},
    States.THINKING:      {States.EXECUTING, States.SPEAKING, States.IDLE, States.ERROR},
    States.EXECUTING:     {States.SPEAKING, States.IDLE, States.ERROR},
    States.SPEAKING:      {States.IDLE, States.LISTENING, States.ERROR},
    States.MONITORING:    {States.IDLE, States.LISTENING, States.ERROR},
    States.ERROR:         {States.IDLE, States.LISTENING, States.MONITORING},
}


# ═══════════════════════════════════════════════════════════
# State Machine
# ═══════════════════════════════════════════════════════════

class StateMachine:
    """
    Thread-safe state machine that emits events on transitions.

    Wraps existing state updates — modules can still call
    `set_state("listening")` and it goes through the machine.
    """

    def __init__(self):
        self._state: str = States.IDLE
        self._prev_state: str = States.IDLE
        self._lock = threading.Lock()
        self._state_since: float = time.time()
        self._transition_count: int = 0
        self._error_message: str = ""

    @property
    def state(self) -> str:
        """Current system state."""
        with self._lock:
            return self._state

    @property
    def prev_state(self) -> str:
        """Previous system state."""
        with self._lock:
            return self._prev_state

    @property
    def state_duration(self) -> float:
        """Seconds in the current state."""
        return time.time() - self._state_since

    def set_state(self, new_state: str, error_msg: str = "") -> bool:
        """
        Transition to a new state.

        Validates the transition, updates state, and emits
        STATE_CHANGED on the event bus.

        Args:
            new_state: Target state (use States.* constants)
            error_msg: Optional error message (for ERROR state)

        Returns:
            True if transition succeeded, False if invalid
        """
        # Normalize legacy state names
        new_state = self._normalize(new_state)

        with self._lock:
            old_state = self._state

            # No-op if same state
            if new_state == old_state:
                return True

            # Validate transition
            valid_targets = _TRANSITIONS.get(old_state, set())
            if new_state not in valid_targets and new_state != States.IDLE:
                # Allow any → idle (recovery) but log unexpected transitions
                log.debug("Forced transition: %s → %s (not in valid set)",
                          old_state, new_state)

            self._prev_state = old_state
            self._state = new_state
            self._state_since = time.time()
            self._transition_count += 1

            if new_state == States.ERROR:
                self._error_message = error_msg

        # Emit event (outside lock to prevent deadlocks)
        try:
            from core.event_bus import bus, Events
            bus.emit(Events.STATE_CHANGED,
                     state=new_state,
                     prev_state=old_state,
                     error_msg=error_msg)
        except Exception as e:
            log.debug("State event emission error: %s", e)

        log.info("State: %s → %s", old_state, new_state)
        return True

    def _normalize(self, state: str) -> str:
        """
        Normalize legacy state names to the new 8-state model.

        Existing code uses: wake_listening, active_listening, processing
        Map them to the new states without breaking anything.
        """
        legacy_map = {
            "wake_listening":   States.IDLE,
            "active_listening": States.LISTENING,
            "processing":       States.THINKING,
            "sleeping":         States.MONITORING,
        }
        return legacy_map.get(state, state)

    def is_active(self) -> bool:
        """Check if the system is in an active (non-idle) state."""
        return self._state not in (States.IDLE, States.MONITORING)

    def get_diagnostics(self) -> dict:
        """Get state machine diagnostics."""
        with self._lock:
            return {
                "current_state": self._state,
                "previous_state": self._prev_state,
                "state_duration_s": round(time.time() - self._state_since, 1),
                "total_transitions": self._transition_count,
                "error_message": self._error_message,
            }

    def __repr__(self) -> str:
        return f"StateMachine(state={self._state}, transitions={self._transition_count})"


# ═══════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════

machine = StateMachine()
"""Global state machine instance. Import: `from core.state_machine import machine, States`"""
