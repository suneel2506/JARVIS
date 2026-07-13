"""
core/speaker.py — Multi-backend Text-to-Speech engine for J.A.R.V.I.S.

Supports multiple TTS backends via factory pattern:
- Piper TTS (preferred): Neural TTS, natural male voice, fully offline
- pyttsx3 (fallback): SAPI5 on Windows, espeak on Linux

The active backend is selected by config: "tts_engine": "piper" or "pyttsx3"
If the preferred backend fails to initialize, it falls back automatically.

Thread-safe speech queue with state callbacks for UI integration.
"""
import os
import io
import struct
import subprocess
import threading
import atexit
import queue
import wave
from abc import ABC, abstractmethod
from typing import Optional, Callable

from core.logger import get_logger

log = get_logger("core.speaker")

_speak_queue: queue.Queue = queue.Queue()
_speak_thread: Optional[threading.Thread] = None
_shutdown = threading.Event()
_on_speaking_callback: Optional[Callable] = None
_backend = None


def set_on_speaking(callback: Callable[[bool], None]) -> None:
    """
    Set a callback that fires when speaking starts/stops.

    Args:
        callback: Function(is_speaking: bool) called on state change.
    """
    global _on_speaking_callback
    _on_speaking_callback = callback


# ═══════════════════════════════════════════════════════════
# TTS Backend Interface
# ═══════════════════════════════════════════════════════════

class TTSBackend(ABC):
    """Abstract TTS backend interface."""

    @abstractmethod
    def speak_text(self, text: str) -> None:
        """Speak the given text (blocking)."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop any ongoing speech."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend display name."""
        ...


# ═══════════════════════════════════════════════════════════
# Piper TTS Backend
# ═══════════════════════════════════════════════════════════

class PiperTTSBackend(TTSBackend):
    """
    Neural TTS using Piper — fully offline, natural-sounding voice.

    Piper generates WAV audio from text via subprocess.
    Audio is played through sounddevice for low-latency output.

    Requires:
    - piper-tts Python package OR piper executable in PATH/model dir
    - A voice model (.onnx + .onnx.json) in model/piper/
    """

    def __init__(self, model_path: str = None, rate: int = 22050):
        self._model_path = model_path
        self._rate = rate
        self._process = None
        self._use_python_api = False

        # Try Python API first
        try:
            from piper import PiperVoice
            if model_path and os.path.exists(model_path):
                self._voice = PiperVoice.load(model_path)
                self._use_python_api = True
                log.info("Piper TTS initialized (Python API) — model: %s", model_path)
                return
        except ImportError:
            pass
        except Exception as e:
            log.debug("Piper Python API failed: %s", e)

        # Try CLI executable
        self._piper_exe = self._find_piper_exe()
        if self._piper_exe and model_path and os.path.exists(model_path):
            log.info("Piper TTS initialized (CLI) — exe: %s, model: %s",
                     self._piper_exe, model_path)
            return

        raise RuntimeError("Piper TTS not available. Install piper-tts or place piper.exe in model/piper/")

    def _find_piper_exe(self) -> Optional[str]:
        """Find the Piper executable."""
        from config.config import BASE_DIR

        # Check common locations
        candidates = [
            os.path.join(BASE_DIR, "model", "piper", "piper.exe"),
            os.path.join(BASE_DIR, "model", "piper", "piper"),
            "piper",  # System PATH
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
            # Check if it's in PATH
            if path == "piper":
                import shutil
                if shutil.which("piper"):
                    return "piper"
        return None

    def speak_text(self, text: str) -> None:
        """Generate and play speech using Piper."""
        if not text.strip():
            return

        try:
            if self._use_python_api:
                self._speak_python_api(text)
            else:
                self._speak_cli(text)
        except Exception as e:
            log.error("Piper TTS error: %s", e)

    def _speak_python_api(self, text: str) -> None:
        """Generate speech using Piper Python API."""
        import sounddevice as sd

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            self._voice.synthesize(text, wf)

        wav_buffer.seek(0)
        with wave.open(wav_buffer, 'rb') as wf:
            rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            import numpy as np
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        sd.play(audio, samplerate=rate)
        sd.wait()

    def _speak_cli(self, text: str) -> None:
        """Generate speech using Piper CLI executable."""
        import sounddevice as sd
        import numpy as np

        try:
            self._process = subprocess.Popen(
                [self._piper_exe, "--model", self._model_path, "--output-raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            raw_audio, _ = self._process.communicate(input=text.encode("utf-8"), timeout=30)
            self._process = None

            if raw_audio:
                audio = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
                sd.play(audio, samplerate=self._rate)
                sd.wait()
        except subprocess.TimeoutExpired:
            if self._process:
                self._process.kill()
                self._process = None
            log.warning("Piper TTS timed out")

    def stop(self) -> None:
        """Stop Piper speech."""
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    @property
    def name(self) -> str:
        return "Piper TTS"


# ═══════════════════════════════════════════════════════════
# pyttsx3 Backend (Legacy Fallback)
# ═══════════════════════════════════════════════════════════

class Pyttsx3Backend(TTSBackend):
    """
    Legacy TTS using pyttsx3 (SAPI5 on Windows, espeak on Linux).
    Serves as the reliable fallback when Piper is not available.
    """

    def __init__(self, rate: int = 200, volume: float = 1.0):
        import pyttsx3
        self._engine = pyttsx3.init()
        self._engine.setProperty('rate', rate)
        self._engine.setProperty('volume', volume)

        # Prefer a male English voice for JARVIS feel
        voices = self._engine.getProperty('voices')
        for v in voices:
            name_lower = v.name.lower()
            if 'david' in name_lower or 'male' in name_lower:
                self._engine.setProperty('voice', v.id)
                log.info("TTS voice set to: %s", v.name)
                break

        log.info("pyttsx3 TTS initialized (rate=%d)", rate)

    def speak_text(self, text: str) -> None:
        """Speak text using pyttsx3."""
        if not text.strip():
            return
        self._engine.say(text)
        self._engine.runAndWait()

    def stop(self) -> None:
        """Stop pyttsx3."""
        try:
            self._engine.stop()
        except Exception:
            pass

    @property
    def name(self) -> str:
        return "pyttsx3 (SAPI5)"


# ═══════════════════════════════════════════════════════════
# Backend Factory
# ═══════════════════════════════════════════════════════════

def _create_backend() -> TTSBackend:
    """
    Create the TTS backend based on configuration.
    Tries Piper first, falls back to pyttsx3.
    """
    try:
        from config.config import TTS_ENGINE, PIPER_MODEL_PATH, TTS_RATE, TTS_VOLUME

        if TTS_ENGINE == "piper":
            try:
                backend = PiperTTSBackend(model_path=PIPER_MODEL_PATH)
                log.info("Using Piper TTS backend")
                return backend
            except Exception as e:
                log.warning("Piper TTS unavailable (%s) — falling back to pyttsx3", e)

        # Default / fallback
        backend = Pyttsx3Backend(rate=TTS_RATE, volume=TTS_VOLUME)
        log.info("Using pyttsx3 TTS backend")
        return backend

    except Exception as e:
        log.error("TTS backend creation failed: %s — using pyttsx3 defaults", e)
        return Pyttsx3Backend()


# ═══════════════════════════════════════════════════════════
# Speech Queue Worker
# ═══════════════════════════════════════════════════════════

def _speak_worker() -> None:
    """Background worker that processes the speech queue sequentially."""
    global _backend
    _backend = _create_backend()

    while not _shutdown.is_set():
        try:
            text = _speak_queue.get(timeout=0.5)
            if text is None:
                break  # Poison pill — shutdown signal
            try:
                if _on_speaking_callback:
                    _on_speaking_callback(True)
                _backend.speak_text(text)
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

    # Normalize J.A.R.V.I.S. → Jarvis for natural pronunciation
    text_clean = str(text)
    for pattern in ("J.A.R.V.I.S.", "J.A.R.V.I.S", "J. A. R. V. I. S.", "J. A. R. V. I. S"):
        text_clean = text_clean.replace(pattern, "Jarvis")

    start_speaker()  # Ensure worker is running
    _speak_queue.put(text_clean)
    if block:
        _speak_queue.join()


def stop_speaker() -> None:
    """Shutdown the speaker cleanly."""
    _shutdown.set()
    _speak_queue.put(None)  # Poison pill
    if _backend:
        _backend.stop()
    log.info("Speaker stopped")


def get_backend_name() -> str:
    """Get the name of the active TTS backend."""
    if _backend:
        return _backend.name
    return "Not initialized"


atexit.register(stop_speaker)
