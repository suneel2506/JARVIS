"""
core/listener.py — Voice listener for J.A.R.V.I.S.

Handles wake-word detection, active command listening, and audio level monitoring.
Supports both Vosk (offline) and Google Speech (online) recognition.
"""
import threading
import time
import numpy as np
import speech_recognition as sr
from typing import Optional, Callable

from core.logger import get_logger

log = get_logger("core.listener")

# State events
wake_event = threading.Event()
listening_event = threading.Event()
terminate_event = threading.Event()

# Audio levels for waveform visualization
_waveform_levels: list[float] = [0.0] * 32
_waveform_lock = threading.Lock()

# Callbacks
_on_command_callback: Optional[Callable] = None
_on_state_change_callback: Optional[Callable] = None

# States
STATE_IDLE = "idle"
STATE_WAKE_LISTENING = "wake_listening"
STATE_ACTIVE_LISTENING = "active_listening"
STATE_PROCESSING = "processing"
STATE_SPEAKING = "speaking"
_current_state = STATE_IDLE

# Vosk model (lazy-loaded)
_vosk_model = None
_vosk_available = False


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
        SetLogLevel(-1)  # Suppress Vosk's verbose logging
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


# ─── Audio stream for waveform visualization ────────────
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


# ─── Speech recognition (Vosk offline + Google fallback) ─

def _recognize_audio(recognizer: sr.Recognizer, audio: sr.AudioData) -> str:
    """
    Recognize speech from audio data.
    Tries Vosk first (offline), falls back to Google (online).

    Returns:
        Recognized text (lowercase) or empty string.
    """
    # Try Vosk offline first
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
                log.debug("Vosk recognized: %s", text)
                return text.lower()
        except Exception as e:
            log.debug("Vosk recognition failed, falling back to Google: %s", e)

    # Fallback to Google Speech API
    try:
        text = recognizer.recognize_google(audio)
        log.debug("Google recognized: %s", text)
        return text.lower()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        log.warning("Google Speech API error: %s", e)
        return ""


# ─── Wake-word detection loop ───────────────────────────

def _wake_loop() -> None:
    """Background thread: continuously listens for the wake word."""
    from core.mic import listen_with_sounddevice
    from config.config import WAKE_WORD

    recognizer = sr.Recognizer()
    set_state(STATE_WAKE_LISTENING)
    log.info("Wake-word loop started. Say '%s' to activate.", WAKE_WORD)

    while not terminate_event.is_set():
        if listening_event.is_set():
            time.sleep(0.3)
            continue
        try:
            audio = listen_with_sounddevice(recognizer, timeout=3, phrase_time_limit=2)
            text = _recognize_audio(recognizer, audio)
            if WAKE_WORD in text:
                log.info("Wake word detected!")
                wake_event.set()
        except sr.WaitTimeoutError:
            continue
        except Exception as e:
            if not terminate_event.is_set():
                log.debug("Wake loop cycle error: %s", e)
                time.sleep(0.5)


# ─── Active command listening ────────────────────────────

def listen_for_command() -> str:
    """
    Listen for a single voice command after wake-word activation.

    Returns:
        Recognized text (lowercase) or empty string.
    """
    from core.mic import listen_with_sounddevice
    from config.config import LISTEN_TIMEOUT, PHRASE_TIME_LIMIT

    recognizer = sr.Recognizer()
    set_state(STATE_ACTIVE_LISTENING)
    listening_event.set()

    try:
        log.info("Listening for command...")
        audio = listen_with_sounddevice(
            recognizer, timeout=LISTEN_TIMEOUT, phrase_time_limit=PHRASE_TIME_LIMIT
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
                speak("I didn't catch that.", block=False)
                set_state(STATE_WAKE_LISTENING)


# ─── Start / Stop ───────────────────────────────────────

def start_listener() -> None:
    """Start the voice listener (wake loop + command capture + audio stream)."""
    _init_vosk()
    start_audio_stream()
    threading.Thread(target=_wake_loop, daemon=True, name="WakeLoop").start()
    threading.Thread(target=_command_capture_loop, daemon=True, name="CommandCapture").start()
    log.info("Listener started (Vosk: %s)", "enabled" if _vosk_available else "disabled")


def stop_listener() -> None:
    """Stop the voice listener and all audio streams."""
    terminate_event.set()
    stop_audio_stream()
    log.info("Listener stopped")


def manual_activate() -> None:
    """Manually trigger the wake event (e.g., from UI click)."""
    wake_event.set()
