"""
core/wake_word.py — OpenWakeWord engine for J.A.R.V.I.S.

Provides always-on, low-CPU wake word detection using the OpenWakeWord
library (ONNX-based neural network). Falls back gracefully to the
existing Vosk-based substring matching if OpenWakeWord is not installed.

The engine runs on a dedicated audio stream, consuming minimal resources
while waiting for the wake phrase. When detected, it fires a callback
and pauses until the command is processed.

Supported wake words (pre-trained OpenWakeWord models):
- "hey jarvis"
- "alexa" (can be repurposed)
- Custom models via .onnx files in model/ directory
"""
import threading
import time
import numpy as np
from typing import Optional, Callable

from core.logger import get_logger

log = get_logger("core.wake_word")

_engine = None
_available = False
_running = False
_paused = False
_pause_lock = threading.Lock()
_on_wake_callback: Optional[Callable] = None

# Detection parameters
_threshold = 0.5
_cooldown = 2.0  # seconds between wake detections (idle)
_cooldown_active = 0.5  # shorter cooldown during active conversation
_last_detection = 0.0
_in_conversation = False  # Set by listener when in active conversation

# Expanded wake phrases for text-based detection
_WAKE_PHRASES = [
    "jarvis", "hey jarvis", "yo jarvis", "okay jarvis",
    "hey j", "hey jay",
]


class OpenWakeWordEngine:
    """
    Wake word detection using OpenWakeWord library.

    Processes 16kHz mono audio in 1280-sample chunks (80ms)
    through a lightweight ONNX neural network.
    """

    def __init__(self, model_names: list[str] = None, threshold: float = 0.5):
        """
        Initialize the OpenWakeWord engine.

        Args:
            model_names: List of wake word model names to load.
                         Defaults to ["hey_jarvis"].
            threshold: Detection confidence threshold (0.0 - 1.0).
        """
        from openwakeword.model import Model as OWWModel

        if model_names is None:
            model_names = ["hey_jarvis"]

        self.model = OWWModel(
            wakeword_models=model_names,
            inference_framework="onnx",
        )
        self.threshold = threshold
        self.model_names = model_names
        log.info("OpenWakeWord initialized — models: %s, threshold: %.2f",
                 model_names, threshold)

    def process_audio(self, audio_chunk: np.ndarray) -> Optional[str]:
        """
        Process an audio chunk and check for wake word detections.

        Args:
            audio_chunk: NumPy array of int16 audio samples (16kHz mono).

        Returns:
            The detected wake word name, or None if no detection.
        """
        prediction = self.model.predict(audio_chunk)

        for model_name in self.model_names:
            score = prediction.get(model_name, 0.0)
            if score >= self.threshold:
                log.info("Wake word detected: '%s' (score: %.3f)", model_name, score)
                # Reset the model to prevent repeated detections
                self.model.reset()
                return model_name

        return None

    def reset(self):
        """Reset internal state after a detection."""
        self.model.reset()


class VoskSubstringFallback:
    """
    Fallback wake word detection using Vosk transcription + substring matching.
    This is the legacy method — used when OpenWakeWord is not installed.
    """

    def __init__(self, wake_words: list[str]):
        self.wake_words = [w.lower() for w in wake_words]
        log.info("Using Vosk substring fallback for wake detection: %s", self.wake_words)

    def check_text(self, text: str) -> bool:
        """Check if transcribed text contains a wake word."""
        text_lower = text.lower().strip()
        for wake_word in self.wake_words:
            if wake_word in text_lower:
                return True
        return False


def init_wake_engine() -> bool:
    """
    Initialize the wake word engine.
    Tries OpenWakeWord first, falls back to Vosk substring matching.

    Returns:
        True if any engine was initialized successfully.
    """
    global _engine, _available, _threshold

    from config.config import WAKE_SENSITIVITY

    # Sensitivity maps to threshold (higher sensitivity = lower threshold)
    _threshold = max(0.1, min(0.9, 1.0 - (WAKE_SENSITIVITY - 1.0) * 0.3))

    # Try OpenWakeWord
    try:
        from config.config import WAKE_ENGINE, OPENWAKEWORD_MODELS
        if WAKE_ENGINE == "openwakeword":
            _engine = OpenWakeWordEngine(
                model_names=OPENWAKEWORD_MODELS,
                threshold=_threshold,
            )
            _available = True
            log.info("OpenWakeWord engine ready (threshold: %.2f)", _threshold)
            return True
    except ImportError:
        log.info("OpenWakeWord not installed — falling back to Vosk substring matching")
    except Exception as e:
        log.warning("OpenWakeWord init failed: %s — falling back", e)

    # Fallback to Vosk substring
    try:
        from config.config import WAKE_WORDS
        _engine = VoskSubstringFallback(WAKE_WORDS)
        _available = True
        return True
    except Exception as e:
        log.error("All wake word engines failed: %s", e)
        _available = False
        return False


def is_available() -> bool:
    """Check if any wake word engine is available."""
    return _available


def is_openwakeword() -> bool:
    """Check if the active engine is OpenWakeWord (vs. fallback)."""
    return isinstance(_engine, OpenWakeWordEngine)


def set_conversation_active(active: bool) -> None:
    """Set conversation state for adaptive cooldown."""
    global _in_conversation
    _in_conversation = active


def _get_current_cooldown() -> float:
    """Get the current cooldown based on conversation state."""
    return _cooldown_active if _in_conversation else _cooldown


def detect_from_audio(audio_chunk: np.ndarray) -> bool:
    """
    Process an audio chunk for wake word detection (OpenWakeWord path).

    Args:
        audio_chunk: 16kHz mono int16 audio samples.

    Returns:
        True if wake word detected.
    """
    global _last_detection

    if not _available or not isinstance(_engine, OpenWakeWordEngine):
        return False

    with _pause_lock:
        if _paused:
            return False

    # Adaptive cooldown check
    now = time.time()
    if now - _last_detection < _get_current_cooldown():
        return False

    result = _engine.process_audio(audio_chunk)
    if result is not None:
        _last_detection = now
        return True
    return False


def detect_from_text(text: str) -> bool:
    """
    Check transcribed text for wake word (Vosk fallback path).

    Supports expanded wake phrases including short forms ("J", "Hey J")
    for faster activation during active conversation.

    Args:
        text: Transcribed speech text.

    Returns:
        True if wake word detected.
    """
    global _last_detection

    if not _available:
        return False

    # Adaptive cooldown
    now = time.time()
    if now - _last_detection < _get_current_cooldown():
        return False

    text_lower = text.lower().strip()

    if isinstance(_engine, VoskSubstringFallback):
        if _engine.check_text(text):
            _last_detection = now
            return True
    elif isinstance(_engine, OpenWakeWordEngine):
        # Text-based fallback for OWW engine
        from config.config import WAKE_WORDS
        for ww in WAKE_WORDS:
            if ww in text_lower:
                _last_detection = now
                return True

    # Check expanded wake phrases (works with any engine)
    for phrase in _WAKE_PHRASES:
        if phrase in text_lower:
            _last_detection = now
            return True

    return False


def pause():
    """Pause wake word detection (e.g., during command processing)."""
    with _pause_lock:
        global _paused
        _paused = True


def resume():
    """Resume wake word detection."""
    with _pause_lock:
        global _paused
        _paused = False
    if isinstance(_engine, OpenWakeWordEngine):
        _engine.reset()


def set_on_wake(callback: Callable) -> None:
    """Set the callback for when a wake word is detected."""
    global _on_wake_callback
    _on_wake_callback = callback


def _run_oww_stream() -> None:
    """
    Background thread: runs OpenWakeWord on a continuous audio stream.
    Only used when OpenWakeWord is the active engine.
    """
    global _running

    try:
        import sounddevice as sd
    except ImportError:
        log.error("sounddevice required for OpenWakeWord streaming")
        return

    sample_rate = 16000
    chunk_size = 1280  # 80ms chunks — optimal for OpenWakeWord

    log.info("Starting OpenWakeWord audio stream (16kHz, %d samples/chunk)", chunk_size)
    _running = True

    while _running:
        try:
            with _pause_lock:
                if _paused:
                    time.sleep(0.1)
                    continue

            chunk = sd.rec(chunk_size, samplerate=sample_rate, channels=1, dtype='int16')
            sd.wait()
            audio_data = chunk.flatten()

            if detect_from_audio(audio_data):
                if _on_wake_callback:
                    _on_wake_callback()

        except Exception as e:
            if not _running:
                break
            log.debug("OWW stream error: %s", e)
            time.sleep(0.5)

    log.info("OpenWakeWord stream stopped")


def start_stream() -> None:
    """Start the OpenWakeWord background audio stream (if applicable)."""
    if isinstance(_engine, OpenWakeWordEngine):
        threading.Thread(target=_run_oww_stream, daemon=True, name="OWWStream").start()
        log.info("OpenWakeWord stream thread started")
    else:
        log.info("Not starting OWW stream — using Vosk fallback (integrated into listener)")


def stop_stream() -> None:
    """Stop the OpenWakeWord background stream."""
    global _running
    _running = False
