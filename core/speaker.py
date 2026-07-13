"""
core/speaker.py — Thread-safe Text-to-Speech engine for J.A.R.V.I.S.

Single global TTS engine with a background worker thread and speech queue.
Provides state callbacks for UI integration (speaking animation).
"""
import pyttsx3
import threading
import atexit
import queue
from typing import Optional, Callable

from core.logger import get_logger

log = get_logger("core.speaker")

_engine: Optional[pyttsx3.Engine] = None
_speak_queue: queue.Queue = queue.Queue()
_speak_thread: Optional[threading.Thread] = None
_shutdown = threading.Event()
_on_speaking_callback: Optional[Callable] = None


def set_on_speaking(callback: Callable[[bool], None]) -> None:
    """
    Set a callback that fires when speaking starts/stops.

    Args:
        callback: Function(is_speaking: bool) called on state change.
    """
    global _on_speaking_callback
    _on_speaking_callback = callback


def _init_engine() -> None:
    """Initialize the TTS engine (called once in the worker thread)."""
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
        try:
            from config.config import TTS_RATE, TTS_VOLUME
            _engine.setProperty('rate', TTS_RATE)
            _engine.setProperty('volume', TTS_VOLUME)
        except Exception:
            _engine.setProperty('rate', 165)

        # Prefer a male English voice for the JARVIS feel
        voices = _engine.getProperty('voices')
        for v in voices:
            name_lower = v.name.lower()
            if 'david' in name_lower or 'male' in name_lower:
                _engine.setProperty('voice', v.id)
                log.info("TTS voice set to: %s", v.name)
                break

        log.info("TTS engine initialized (rate=%s)", _engine.getProperty('rate'))


def _speak_worker() -> None:
    """Background worker that processes the speech queue sequentially."""
    _init_engine()
    while not _shutdown.is_set():
        try:
            text = _speak_queue.get(timeout=0.5)
            if text is None:
                break  # Poison pill — shutdown signal
            try:
                if _on_speaking_callback:
                    _on_speaking_callback(True)
                _engine.say(text)
                _engine.runAndWait()
            except Exception as e:
                log.error("TTS error: %s", e)
            finally:
                if _on_speaking_callback:
                    _on_speaking_callback(False)
            _speak_queue.task_done()
        except queue.Empty:
            continue


def start_speaker() -> None:
    """Start the background speech worker thread."""
    global _speak_thread
    if _speak_thread is None or not _speak_thread.is_alive():
        _speak_thread = threading.Thread(target=_speak_worker, daemon=True, name="Speaker")
        _speak_thread.start()
        log.info("Speaker started")


def speak(text: str, block: bool = True) -> None:
    """
    Speak text via TTS.

    Args:
        text: The text to speak.
        block: If True, waits until this text is spoken before returning.
               If False, queues the text and returns immediately.
    """
    if not text:
        return
    start_speaker()  # Ensure worker is running
    _speak_queue.put(str(text))
    if block:
        _speak_queue.join()


def stop_speaker() -> None:
    """Shutdown the speaker cleanly."""
    _shutdown.set()
    _speak_queue.put(None)  # Poison pill
    if _engine:
        try:
            _engine.stop()
        except Exception:
            pass
    log.info("Speaker stopped")


atexit.register(stop_speaker)
