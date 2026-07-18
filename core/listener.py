"""
core/listener.py — Immortal voice listener for J.A.R.V.I.S.

The wake-word loop NEVER dies. It runs indefinitely until the application
explicitly shuts down. If errors occur, it recovers with exponential backoff.

Features:
- Always-on wake word detection (OpenWakeWord / Vosk)
- Natural interruption handling — speaks while JARVIS is talking → stops TTS
- 3-tier confidence scoring (high→execute, medium→echo+confirm, low→repeat)
- Mic auto-recovery with exponential backoff + automatic failover
- OS sleep/lid-close recovery with auto-recalibration
- Idle-to-low-power transition (reduce polling after configurable idle period)
- Watchdog timer that restarts dead loops
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

# ─── Confidence thresholds (3-tier) ────────────────────
CONFIDENCE_HIGH = 0.65    # Execute immediately
CONFIDENCE_MEDIUM = 0.40  # Echo back and confirm
CONFIDENCE_LOW = 0.25     # Ask to repeat entirely

# ─── Diagnostics ────────────────────────────────────────
_last_confidence: float = 0.0
_idle_since: float = 0.0
_total_commands: int = 0
_total_retries: int = 0

# ─── Power saving ──────────────────────────────────────
_idle_power_save_minutes: int = 10  # Enter low-power after this idle time
_power_save_active: bool = False

# ─── OS sleep recovery ─────────────────────────────────
_last_activity_timestamp: float = 0.0


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
    """Update the current listener state and notify callbacks + event bus."""
    global _current_state
    prev = _current_state
    _current_state = state
    if _on_state_change_callback:
        try:
            _on_state_change_callback(state)
        except Exception:
            pass
    # Emit on event bus
    try:
        from core.event_bus import bus, Events
        from core.state_machine import machine
        machine.set_state(state)  # normalizes legacy names
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
        "power_save": _power_save_active,
        "mic_device": mic.get("device_name", "Unknown"),
        "mic_healthy": mic.get("healthy", False),
        "ambient_noise": mic.get("ambient_noise", 0),
        "available_mics": mic.get("available_mics", 0),
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
        from core.mic import calibrate, detect_microphone
        # Re-detect mic in case it changed during sleep
        detect_microphone()
        calibrate(duration=0.5)
        log.info("Mic re-detected and noise recalibrated after sleep exit")
    except Exception:
        pass

    log.info("Exiting sleep mode")


def is_sleeping() -> bool:
    """Check if the listener is in sleep mode."""
    return sleep_event.is_set()


# ─── Interruption Handling ──────────────────────────────

def check_interruption() -> bool:
    """
    Check if the user is speaking while JARVIS is talking.
    If so, interrupt TTS and switch to listening mode.

    Returns:
        True if an interruption was detected and handled.
    """
    try:
        from core.speaker import is_speaking, stop_speaking
        if not is_speaking():
            return False

        # Quick energy check from the audio stream
        with _waveform_lock:
            recent = _waveform_levels[-4:]  # Last ~400ms

        avg_energy = sum(recent) / max(len(recent), 1)

        # If energy is significantly above ambient, user is speaking
        from core.mic import get_ambient_noise
        ambient = get_ambient_noise()
        threshold = max(ambient * 2.5, 0.02)  # Dynamic threshold

        if avg_energy > threshold:
            log.info("Interruption detected (energy: %.4f, threshold: %.4f) — stopping TTS",
                     avg_energy, threshold)
            stop_speaking()
            return True

    except Exception as e:
        log.debug("Interruption check error: %s", e)

    return False


# ─── OS Sleep Recovery ──────────────────────────────────

def _detect_os_sleep_wake() -> bool:
    """
    Detect if the system just woke from OS sleep/hibernate.
    Uses a time gap heuristic — if the gap between ticks is > 5s,
    the system was likely sleeping.

    Returns:
        True if an OS wake event was detected.
    """
    global _last_activity_timestamp

    now = time.time()
    if _last_activity_timestamp == 0:
        _last_activity_timestamp = now
        return False

    gap = now - _last_activity_timestamp
    _last_activity_timestamp = now

    if gap > 5.0:
        log.info("OS sleep/wake detected (gap: %.1fs) — recalibrating...", gap)
        return True

    return False


def _handle_os_wake() -> None:
    """Handle recovery after OS sleep/lid-open."""
    try:
        from core.mic import detect_microphone, calibrate, enumerate_microphones

        # Re-enumerate devices (USB mics may have reconnected)
        enumerate_microphones()

        # Re-detect the best mic
        detect_microphone()

        # Recalibrate ambient noise
        calibrate(duration=0.5)

        log.info("OS wake recovery complete — mic and noise recalibrated")
    except Exception as e:
        log.warning("OS wake recovery error: %s", e)


# ─── Power Saving ───────────────────────────────────────

def _check_power_save() -> float:
    """
    Check if we should enter low-power mode and return the sleep duration.

    Returns:
        Sleep duration in seconds (longer = power saving active).
    """
    global _power_save_active

    if _idle_since == 0:
        return 0.3

    idle_seconds = time.time() - _idle_since
    idle_minutes = idle_seconds / 60.0

    if idle_minutes > _idle_power_save_minutes:
        if not _power_save_active:
            _power_save_active = True
            log.info("Entering low-power mode (idle for %.0f minutes)", idle_minutes)
        return 1.0  # Poll every 1s instead of 0.3s
    else:
        if _power_save_active:
            _power_save_active = False
            log.info("Exiting low-power mode")
        return 0.3  # Normal polling


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
    Detects OS sleep/wake and recalibrates.
    Reduces polling in idle for power saving.
    """
    global _idle_since, _last_activity_timestamp

    from core.mic import listen_with_sounddevice, detect_microphone

    recognizer = sr.Recognizer()
    set_state(STATE_WAKE_LISTENING)
    _wake_loop_alive.set()
    _idle_since = time.time()
    _last_activity_timestamp = time.time()

    backoff = 0.5
    max_backoff = 10.0
    consecutive_errors = 0
    heartbeat_interval = 300
    last_heartbeat = time.time()

    log.info("Wake-word loop started (immortal). Mode: %s", _listen_mode)

    while not terminate_event.is_set():
        # OS sleep/wake detection
        if _detect_os_sleep_wake():
            _handle_os_wake()

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
            sleep_duration = _check_power_save()
            time.sleep(sleep_duration)
            continue

        # Check for user interruption (speaking while JARVIS talks)
        check_interruption()

        # Heartbeat logging
        now = time.time()
        if now - last_heartbeat > heartbeat_interval:
            last_heartbeat = now
            log.info("Wake loop alive — mode: %s, errors: %d, idle: %ds, power_save: %s",
                     _listen_mode, consecutive_errors,
                     int(now - _idle_since),
                     "on" if _power_save_active else "off")
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
    - 3-tier confidence scoring:
      • HIGH (≥0.65): Execute immediately
      • MEDIUM (0.40-0.65): Echo back and confirm ("Did you say...?")
      • LOW (<0.40): Ask to repeat entirely
    - Recognition retry: on empty result, retry once with longer timeout
    - Natural interruption support: user can interrupt JARVIS
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

    max_attempts = 3  # Original + 2 retries

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
                # ─── 3-Tier Confidence Scoring ───────────
                if confidence >= CONFIDENCE_HIGH:
                    # HIGH: Execute immediately
                    log.info("Heard (HIGH conf %.2f): '%s'", confidence, text)
                    _total_commands += 1
                    _idle_since = time.time()
                    return text

                elif confidence >= CONFIDENCE_MEDIUM:
                    # MEDIUM: Echo back and confirm
                    log.info("Heard (MEDIUM conf %.2f): '%s' — confirming...",
                             confidence, text)
                    from core.speaker import speak
                    speak(f"Did you say: {text}?", block=True)

                    # Listen for yes/no confirmation
                    try:
                        confirm_audio = listen_with_sounddevice(
                            recognizer, timeout=4, phrase_time_limit=3,
                        )
                        confirm_text, _ = _recognize_audio(recognizer, confirm_audio)
                        confirm_lower = confirm_text.lower().strip()

                        affirmatives = {"yes", "yeah", "yep", "yup", "correct",
                                        "that's right", "right", "affirmative",
                                        "exactly", "sure", "ok", "okay"}

                        if any(a in confirm_lower for a in affirmatives):
                            log.info("Confirmed: '%s'", text)
                            _total_commands += 1
                            _idle_since = time.time()
                            return text
                        else:
                            log.info("User did not confirm: '%s' — retrying", text)
                            speak("Let me try again. Go ahead, sir.", block=True)
                            continue

                    except (sr.WaitTimeoutError, sr.UnknownValueError):
                        # No confirmation → treat as confirmed (common UX pattern)
                        log.info("No confirmation response — executing: '%s'", text)
                        _total_commands += 1
                        _idle_since = time.time()
                        return text

                else:
                    # LOW: Ask to repeat
                    if attempt < max_attempts - 1:
                        log.info("Low confidence (%.2f) for: '%s' — requesting repeat",
                                 confidence, text)
                        from core.speaker import speak
                        speak("Sorry sir, could you repeat that?", block=True)
                        continue
                    else:
                        # Last attempt — accept whatever we got
                        log.info("Last attempt — accepting low conf: '%s' (%.2f)",
                                 text, confidence)
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


# ─── Interruption Monitor ──────────────────────────────

def _interruption_monitor_loop() -> None:
    """
    Background thread that continuously checks for user interruptions.
    Runs only when JARVIS is speaking, checking every 100ms.
    """
    while not terminate_event.is_set():
        try:
            from core.speaker import is_speaking
            if is_speaking() and not listening_event.is_set():
                if check_interruption():
                    # Interruption handled — activate listening
                    log.info("Interruption handled — activating wake event")
                    wake_event.set()
            time.sleep(0.1)
        except Exception:
            time.sleep(0.5)


# ─── Start / Stop ───────────────────────────────────────

def start_listener() -> None:
    """Start the voice listener (mic detection + wake loop + command capture + watchdog)."""
    global _listen_mode, _idle_since, _idle_power_save_minutes
    from config.config import LISTEN_MODE
    _listen_mode = LISTEN_MODE
    _idle_since = time.time()

    # Load power-save config
    try:
        from config.config import get_setting
        _idle_power_save_minutes = get_setting("idle_power_save_minutes", 10)
    except Exception:
        pass

    # Auto-detect microphone (with multi-mic enumeration)
    from core.mic import detect_microphone, calibrate, enumerate_microphones
    enumerate_microphones()
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
    threading.Thread(target=_interruption_monitor_loop, daemon=True,
                     name="InterruptionMonitor").start()

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
