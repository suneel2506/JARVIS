"""
core/listener.py — Immortal voice listener for J.A.R.V.I.S.

The wake-word loop NEVER dies. It runs indefinitely until the application
explicitly shuts down. If errors occur, it recovers with exponential backoff.

Supports three listen modes:
- wake_word: Listen for wake words, then capture command (default)
- continuous: Always listening — every phrase is treated as a command
- push_to_talk: Only activates via manual trigger (UI click or hotkey)

Wake words are matched as substrings: "jarvis", "hey jarvis", "okay jarvis"
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
sleep_event = threading.Event()  # When set, wake loop pauses (sleep mode)

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
        blocksize = int(SAMPLING_RATE * FRAME_DURATION)
        _audio_stream = sd.InputStream(
            channels=1, samplerate=SAMPLING_RATE,
            blocksize=blocksize, callback=_audio_callback,
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


# ─── Speech Recognition (Vosk offline + Google fallback) ─

def _recognize_audio(recognizer: sr.Recognizer, audio: sr.AudioData) -> str:
    """
    Recognize speech from audio data.
    Tries Vosk first (offline), falls back to Google (online).
    """
    if _vosk_available and _vosk_model is not None:
        try:
            import json as json_mod
            from vosk import KaldiRecognizer
            from config.config import SAMPLING_RATE

            rec = KaldiRecognizer(_vosk_model, SAMPLING_RATE)
            raw_data = audio.get_raw_data(convert_rate=SAMPLING_RATE, convert_width=2)
            rec.AcceptWaveform(raw_data)
            result = json_mod.loads(rec.FinalResult())
            text = result.get("text", "").strip()
            if text:
                return text.lower()
        except Exception as e:
            log.debug("Vosk recognition failed, falling back to Google: %s", e)

    try:
        text = recognizer.recognize_google(audio)
        return text.lower()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        log.warning("Google Speech API error: %s", e)
        return ""


def _matches_wake_word(text: str) -> bool:
    """Check if text contains any registered wake word."""
    from config.config import WAKE_WORDS
    text_lower = text.lower().strip()
    for wake_word in WAKE_WORDS:
        if wake_word in text_lower:
            return True
    return False


# ─── Immortal Wake-Word Detection Loop ──────────────────

def _wake_loop() -> None:
    """
    Background thread: continuously listens for wake words.

    IMMORTAL — this loop never dies unless terminate_event is set.
    On error, it recovers with exponential backoff (0.5s → 5s cap).
    Logs a heartbeat every 5 minutes for diagnostics.
    """
    from core.mic import listen_with_sounddevice

    recognizer = sr.Recognizer()
    set_state(STATE_WAKE_LISTENING)
    _wake_loop_alive.set()

    backoff = 0.5
    max_backoff = 5.0
    consecutive_errors = 0
    heartbeat_interval = 300  # 5 minutes
    last_heartbeat = time.time()

    log.info("Wake-word loop started (immortal). Mode: %s", _listen_mode)

    while not terminate_event.is_set():
        # ─── Sleep mode check ────────────────────────
        if sleep_event.is_set():
            time.sleep(1.0)
            continue

        # ─── Push-to-talk mode: just wait for manual activation
        if _listen_mode == "push_to_talk":
            time.sleep(0.5)
            continue

        # ─── Skip if actively listening for a command ─
        if listening_event.is_set():
            time.sleep(0.3)
            continue

        # ─── Heartbeat logging ───────────────────────
        now = time.time()
        if now - last_heartbeat > heartbeat_interval:
            last_heartbeat = now
            log.info("Wake loop alive — mode: %s, errors: %d", _listen_mode, consecutive_errors)
            consecutive_errors = 0  # Reset error count after heartbeat

        # ─── Listen for audio ────────────────────────
        try:
            audio = listen_with_sounddevice(
                recognizer, timeout=3, phrase_time_limit=2,
            )
            text = _recognize_audio(recognizer, audio)

            if text:
                if _listen_mode == "continuous":
                    # In continuous mode, every phrase is a command
                    log.info("Continuous mode — heard: %s", text)
                    wake_event.set()
                    # Store the text so command capture can use it directly
                    _store_continuous_text(text)
                elif _matches_wake_word(text):
                    log.info("Wake word detected: '%s'", text)
                    wake_event.set()

            # Reset backoff on success
            consecutive_errors = 0
            backoff = 0.5

        except sr.WaitTimeoutError:
            # Normal — no speech detected within timeout
            continue
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
    In continuous mode, returns the already-captured text.
    """
    # In continuous mode, use the buffered text
    if _listen_mode == "continuous":
        text = _pop_continuous_text()
        if text:
            return text

    from core.mic import listen_with_sounddevice
    from config.config import LISTEN_TIMEOUT, PHRASE_TIME_LIMIT

    recognizer = sr.Recognizer()
    set_state(STATE_ACTIVE_LISTENING)
    listening_event.set()

    try:
        log.info("Listening for command...")
        audio = listen_with_sounddevice(
            recognizer, timeout=LISTEN_TIMEOUT, phrase_time_limit=PHRASE_TIME_LIMIT,
        )
        text = _recognize_audio(recognizer, audio)
        if text:
            log.info("Heard: %s", text)
        return text
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        log.warning("Speech API error during command capture")
        return ""
    except Exception as e:
        log.error("Listen error: %s", e)
        return ""
    finally:
        listening_event.clear()
        set_state(STATE_WAKE_LISTENING)


def _command_capture_loop() -> None:
    """Thread that monitors wake_event and captures commands."""
    from core.speaker import speak

    while not terminate_event.is_set():
        if wake_event.wait(timeout=0.5):
            wake_event.clear()

            # In continuous mode, skip the "Yes?" prompt
            if _listen_mode != "continuous":
                speak("Yes?", block=True)

            cmd = listen_for_command()
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
                    speak("I didn't catch that.", block=False)
                set_state(STATE_WAKE_LISTENING)


# ─── Start / Stop ───────────────────────────────────────

def start_listener() -> None:
    """Start the voice listener (wake loop + command capture + audio stream)."""
    global _listen_mode
    from config.config import LISTEN_MODE
    _listen_mode = LISTEN_MODE

    _init_vosk()
    start_audio_stream()

    threading.Thread(target=_wake_loop, daemon=True, name="WakeLoop").start()
    threading.Thread(target=_command_capture_loop, daemon=True, name="CommandCapture").start()

    log.info("Listener started — Vosk: %s, Mode: %s",
             "enabled" if _vosk_available else "disabled", _listen_mode)


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
