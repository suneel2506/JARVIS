"""
core/listener.py — Immortal voice listener for J.A.R.V.I.S.

The wake-word loop NEVER dies. It runs indefinitely until the application
explicitly shuts down. If errors occur, it recovers with exponential backoff.

Features:
- Always-on wake word detection (OpenWakeWord / Vosk)
- Low-confidence retry ("Sorry sir, could you repeat that?")
- Mic auto-recovery with exponential backoff
- Watchdog timer that restarts dead loops
- Auto-recalibrate ambient noise after sleep exit
- Silence tracking and idle time logging
- Recognition retry with adjusted parameters
- Three listen modes: wake_word, continuous, push_to_talk
"""
import threading
import time
import numpy as np
import speech_recognition as sr
from typing import Optional, Callable

from core.logger import get_logger

log = get_logger("core.listener")

# ─── State Events ───────────────────────────────────────
wake_event = threading.Event()
listening_event = threading.Event()
terminate_event = threading.Event()
sleep_event = threading.Event()

# ─── Audio levels for waveform visualization ────────────
_waveform_levels: list[float] = [0.0] * 32
_waveform_lock = threading.Lock()

# ─── Callbacks ──────────────────────────────────────────
_on_command_callback: Optional[Callable] = None
_on_state_change_callback: Optional[Callable] = None

# ─── States ─────────────────────────────────────────────
STATE_IDLE = "idle"
STATE_WAKE_LISTENING = "wake_listening"
STATE_ACTIVE_LISTENING = "active_listening"
STATE_PROCESSING = "processing"
STATE_SPEAKING = "speaking"
STATE_SLEEPING = "sleeping"
_current_state = STATE_IDLE

# ─── Listen mode ────────────────────────────────────────
_listen_mode = "wake_word"

# ─── Vosk model (lazy-loaded) ───────────────────────────
_vosk_model = None
_vosk_available = False

# ─── Wake loop health ──────────────────────────────────
_wake_loop_alive = threading.Event()
_last_wake_check = 0.0

# ─── Confidence threshold ──────────────────────────────
CONFIDENCE_THRESHOLD = 0.4  # Below this → ask to repeat

# ─── Diagnostics ────────────────────────────────────────
_last_confidence: float = 0.0
_idle_since: float = 0.0
_total_commands: int = 0
_total_retries: int = 0


def _init_vosk() -> bool:
    """Initialize Vosk offline model if available."""
    global _vosk_model, _vosk_available
    try:
        from config.config import VOSK_MODEL_PATH, USE_VOSK_OFFLINE
        if not USE_VOSK_OFFLINE:
            log.info("Vosk offline recognition disabled in settings")
            return False

        import os
        if not os.path.exists(VOSK_MODEL_PATH):
            log.warning("Vosk model not found at %s", VOSK_MODEL_PATH)
            return False

        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        _vosk_model = Model(VOSK_MODEL_PATH)
        _vosk_available = True
        log.info("Vosk offline model loaded from %s", VOSK_MODEL_PATH)
        return True
    except ImportError:
        log.info("Vosk not installed — using Google Speech API only")
        return False
    except Exception as e:
        log.warning("Vosk initialization failed: %s", e)
        return False


# ─── State Management ───────────────────────────────────

def set_state(state: str) -> None:
    """Update the current listener state and notify callbacks."""
    global _current_state
    _current_state = state
    if _on_state_change_callback:
        try:
            _on_state_change_callback(state)
        except Exception:
            pass


def get_state() -> str:
    """Get the current listener state."""
    return _current_state


def get_waveform_levels() -> list[float]:
    """Get a copy of the current waveform levels (thread-safe)."""
    with _waveform_lock:
        return list(_waveform_levels)


def set_on_command(callback: Callable) -> None:
    """Set the callback for when a command is recognized."""
    global _on_command_callback
    _on_command_callback = callback


def set_on_state_change(callback: Callable) -> None:
    """Set the callback for state changes."""
    global _on_state_change_callback
    _on_state_change_callback = callback


def set_listen_mode(mode: str) -> None:
    """Change the listen mode at runtime."""
    global _listen_mode
    if mode in ("wake_word", "continuous", "push_to_talk"):
        _listen_mode = mode
        log.info("Listen mode changed to: %s", mode)


def get_listen_mode() -> str:
    """Get the current listen mode."""
    return _listen_mode


# ─── Diagnostics ────────────────────────────────────────

def get_diagnostics() -> dict:
    """Get listener diagnostic information."""
    from core.mic import get_mic_info
    mic = get_mic_info()
    return {
        "state": _current_state,
        "mode": _listen_mode,
        "vosk_available": _vosk_available,
        "wake_loop_alive": _wake_loop_alive.is_set(),
        "last_confidence": _last_confidence,
        "idle_seconds": int(time.time() - _idle_since) if _idle_since else 0,
        "total_commands": _total_commands,
        "total_retries": _total_retries,
        "mic_device": mic.get("device_name", "Unknown"),
        "mic_healthy": mic.get("healthy", False),
        "ambient_noise": mic.get("ambient_noise", 0),
    }


# ─── Sleep Mode ─────────────────────────────────────────

def enter_sleep() -> None:
    """Enter sleep mode — wake loop pauses but thread stays alive."""
    sleep_event.set()
    set_state(STATE_SLEEPING)
    log.info("Entering sleep mode")


def exit_sleep() -> None:
    """Exit sleep mode — resume wake word listening."""
    sleep_event.clear()
    set_state(STATE_WAKE_LISTENING)

    # Recalibrate ambient noise after sleep
    try:
        from core.mic import calibrate
        calibrate(duration=0.5)
        log.info("Ambient noise recalibrated after sleep exit")
    except Exception:
        pass

    log.info("Exiting sleep mode")


def is_sleeping() -> bool:
    """Check if the listener is in sleep mode."""
    return sleep_event.is_set()


# ─── Audio Stream for Waveform Visualization ────────────
_audio_stream = None
_use_sounddevice = False


def _audio_callback(indata, frames, time_info, status) -> None:
    """Sounddevice callback for real-time audio level monitoring."""
    rms = float(np.sqrt(np.mean(indata ** 2)))
    with _waveform_lock:
        _waveform_levels.pop(0)
        _waveform_levels.append(rms)


def start_audio_stream() -> None:
    """Start the audio monitoring stream for waveform visualization."""
    global _audio_stream, _use_sounddevice
    try:
        import sounddevice as sd
        from config.config import SAMPLING_RATE, FRAME_DURATION
        from core.mic import _mic_device_index
        blocksize = int(SAMPLING_RATE * FRAME_DURATION)
        _audio_stream = sd.InputStream(
            channels=1, samplerate=SAMPLING_RATE,
            blocksize=blocksize, callback=_audio_callback,
            device=_mic_device_index,
        )
        _audio_stream.start()
        _use_sounddevice = True
        log.info("Audio waveform stream started")
    except Exception as e:
        log.warning("Sounddevice unavailable for waveform: %s", e)
        _use_sounddevice = False


def stop_audio_stream() -> None:
    """Stop the audio monitoring stream."""
    global _audio_stream
    if _audio_stream:
        try:
            _audio_stream.stop()
            _audio_stream.close()
        except Exception:
            pass


# ─── Speech Recognition with Confidence ─────────────────

def _recognize_audio(recognizer: sr.Recognizer, audio: sr.AudioData) -> tuple[str, float]:
    """
    Recognize speech and return (text, confidence).
    Uses the hardened mic module's confidence-aware recognizer.
    """
    from core.mic import recognize_with_confidence
    return recognize_with_confidence(
        recognizer, audio,
        vosk_model=_vosk_model if _vosk_available else None,
    )


def _matches_wake_word(text: str) -> bool:
    """Check if text contains any registered wake word."""
    from core.wake_word import detect_from_text
    return detect_from_text(text)


# ─── Immortal Wake-Word Detection Loop ──────────────────

def _wake_loop() -> None:
    """
    Background thread: continuously listens for wake words.

    IMMORTAL — never dies unless terminate_event is set.
    On error, recovers with exponential backoff (0.5s → 10s cap).
    Detects mic disconnection and attempts re-init.
    """
    global _idle_since

    from core.mic import listen_with_sounddevice, detect_microphone

    recognizer = sr.Recognizer()
    set_state(STATE_WAKE_LISTENING)
    _wake_loop_alive.set()
    _idle_since = time.time()

    backoff = 0.5
    max_backoff = 10.0
    consecutive_errors = 0
    heartbeat_interval = 300
    last_heartbeat = time.time()

    log.info("Wake-word loop started (immortal). Mode: %s", _listen_mode)

    while not terminate_event.is_set():
        # Sleep mode check
        if sleep_event.is_set():
            time.sleep(1.0)
            continue

        # Push-to-talk mode: just wait
        if _listen_mode == "push_to_talk":
            time.sleep(0.5)
            continue

        # Skip if actively listening for a command
        if listening_event.is_set():
            time.sleep(0.3)
            continue

        # Heartbeat logging
        now = time.time()
        if now - last_heartbeat > heartbeat_interval:
            last_heartbeat = now
            log.info("Wake loop alive — mode: %s, errors: %d, idle: %ds",
                     _listen_mode, consecutive_errors,
                     int(now - _idle_since))
            consecutive_errors = 0

        # Listen for audio
        try:
            audio = listen_with_sounddevice(
                recognizer, timeout=3, phrase_time_limit=2,
            )
            text, confidence = _recognize_audio(recognizer, audio)

            if text:
                if _listen_mode == "continuous":
                    log.info("Continuous mode — heard: '%s' (conf: %.2f)", text, confidence)
                    wake_event.set()
                    _store_continuous_text(text)
                elif _matches_wake_word(text):
                    log.info("Wake word detected: '%s' (conf: %.2f)", text, confidence)
                    wake_event.set()

            # Reset backoff on success
            consecutive_errors = 0
            backoff = 0.5

        except sr.WaitTimeoutError:
            continue
        except RuntimeError as e:
            # Mic disconnected — attempt recovery
            if terminate_event.is_set():
                break
            consecutive_errors += 1
            log.warning("Mic error (#%d): %s — attempting recovery...",
                        consecutive_errors, e)
            time.sleep(min(backoff, max_backoff))
            backoff = min(backoff * 2, max_backoff)

            # Try to re-detect microphone
            try:
                detect_microphone()
                log.info("Microphone re-detected after recovery")
                backoff = 0.5
            except Exception:
                pass

        except Exception as e:
            if terminate_event.is_set():
                break
            consecutive_errors += 1
            log.debug("Wake loop error (#%d): %s", consecutive_errors, e)
            time.sleep(min(backoff, max_backoff))
            backoff = min(backoff * 1.5, max_backoff)

    _wake_loop_alive.clear()
    log.info("Wake loop terminated")


# ─── Continuous mode text buffer ─────────────────────────
_continuous_text: Optional[str] = None
_continuous_lock = threading.Lock()


def _store_continuous_text(text: str) -> None:
    global _continuous_text
    with _continuous_lock:
        _continuous_text = text


def _pop_continuous_text() -> Optional[str]:
    global _continuous_text
    with _continuous_lock:
        text = _continuous_text
        _continuous_text = None
        return text


# ─── Active Command Listening ────────────────────────────

def listen_for_command() -> str:
    """
    Listen for a single voice command after wake-word activation.

    Features:
    - Confidence-based retry: if confidence < threshold, ask to repeat
    - Recognition retry: on empty result, retry once with longer timeout
    - Conversation-ready: returns clean text for executor
    """
    global _last_confidence, _idle_since, _total_commands, _total_retries

    # In continuous mode, use the buffered text
    if _listen_mode == "continuous":
        text = _pop_continuous_text()
        if text:
            _total_commands += 1
            _idle_since = time.time()
            return text

    from core.mic import listen_with_sounddevice
    from config.config import LISTEN_TIMEOUT, PHRASE_TIME_LIMIT

    recognizer = sr.Recognizer()
    set_state(STATE_ACTIVE_LISTENING)
    listening_event.set()

    max_attempts = 2  # Original + 1 retry

    for attempt in range(max_attempts):
        try:
            timeout = LISTEN_TIMEOUT if attempt == 0 else LISTEN_TIMEOUT + 2
            phrase_limit = PHRASE_TIME_LIMIT if attempt == 0 else PHRASE_TIME_LIMIT + 3

            if attempt > 0:
                log.info("Retry attempt %d — listening with extended timeout...", attempt)
                _total_retries += 1

            audio = listen_with_sounddevice(
                recognizer, timeout=timeout, phrase_time_limit=phrase_limit,
            )
            text, confidence = _recognize_audio(recognizer, audio)
            _last_confidence = confidence

            if text:
                # Low confidence — ask to repeat
                if confidence < CONFIDENCE_THRESHOLD and attempt == 0:
                    log.info("Low confidence (%.2f) for: '%s' — requesting repeat",
                             confidence, text)
                    from core.speaker import speak
                    speak("Sorry sir, could you repeat that?", block=True)
                    continue  # Retry

                log.info("Heard: '%s' (confidence: %.2f)", text, confidence)
                _total_commands += 1
                _idle_since = time.time()
                return text

        except sr.WaitTimeoutError:
            if attempt == 0:
                continue  # Silent retry
        except sr.UnknownValueError:
            if attempt == 0:
                continue
        except RuntimeError as e:
            log.error("Mic error during command: %s", e)
            break
        except Exception as e:
            log.error("Listen error: %s", e)
            break

    listening_event.clear()
    set_state(STATE_WAKE_LISTENING)
    return ""


def _command_capture_loop() -> None:
    """Thread that monitors wake_event and captures commands."""
    from core.speaker import speak

    while not terminate_event.is_set():
        if wake_event.wait(timeout=0.5):
            wake_event.clear()

            # In continuous mode, skip the "Yes?" prompt
            if _listen_mode != "continuous":
                speak("Yes, sir?", block=True)

            cmd = listen_for_command()

            # Clear listening state
            listening_event.clear()

            if cmd:
                set_state(STATE_PROCESSING)
                if _on_command_callback:
                    try:
                        result = _on_command_callback(cmd)
                        if result == "exit":
                            terminate_event.set()
                    except Exception as e:
                        log.error("Command callback error: %s", e)
                set_state(STATE_WAKE_LISTENING)
            else:
                if _listen_mode != "continuous":
                    speak("I didn't catch that, sir.", block=False)
                set_state(STATE_WAKE_LISTENING)


# ─── Watchdog ───────────────────────────────────────────

def _watchdog_loop() -> None:
    """
    Monitor the wake loop and restart it if it dies.
    Checks every 30 seconds.
    """
    while not terminate_event.is_set():
        time.sleep(30)
        if terminate_event.is_set():
            break

        if not _wake_loop_alive.is_set() and not terminate_event.is_set():
            log.warning("WATCHDOG: Wake loop is dead — restarting...")
            threading.Thread(target=_wake_loop, daemon=True, name="WakeLoop").start()
            time.sleep(5)


# ─── Start / Stop ───────────────────────────────────────

def start_listener() -> None:
    """Start the voice listener (mic detection + wake loop + command capture + watchdog)."""
    global _listen_mode, _idle_since
    from config.config import LISTEN_MODE
    _listen_mode = LISTEN_MODE
    _idle_since = time.time()

    # Auto-detect microphone
    from core.mic import detect_microphone, calibrate
    idx, name = detect_microphone()
    log.info("Using microphone: %s (index: %s)", name, idx)

    # Initial ambient calibration
    calibrate(duration=1.0)

    # Init Vosk
    _init_vosk()

    # Start audio waveform stream
    start_audio_stream()

    # Initialize wake word engine
    from core.wake_word import init_wake_engine, is_openwakeword, start_stream, set_on_wake
    init_wake_engine()

    if is_openwakeword():
        def _oww_wake_callback():
            if not sleep_event.is_set() and not listening_event.is_set():
                log.info("OpenWakeWord triggered wake event")
                wake_event.set()
        set_on_wake(_oww_wake_callback)
        start_stream()
        log.info("Using OpenWakeWord for wake detection")
    else:
        log.info("Using Vosk substring matching for wake detection")

    # Start threads
    threading.Thread(target=_wake_loop, daemon=True, name="WakeLoop").start()
    threading.Thread(target=_command_capture_loop, daemon=True, name="CommandCapture").start()
    threading.Thread(target=_watchdog_loop, daemon=True, name="Watchdog").start()

    log.info("Listener started — Vosk: %s, Mode: %s, Mic: %s",
             "enabled" if _vosk_available else "disabled", _listen_mode, name)


def stop_listener() -> None:
    """Stop the voice listener and all audio streams."""
    terminate_event.set()
    stop_audio_stream()
    log.info("Listener stopped")


def manual_activate() -> None:
    """Manually trigger the wake event (e.g., from UI click or hotkey)."""
    if sleep_event.is_set():
        exit_sleep()
    wake_event.set()


def is_wake_loop_alive() -> bool:
    """Check if the wake loop thread is still running."""
    return _wake_loop_alive.is_set()
