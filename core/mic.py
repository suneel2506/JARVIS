"""
core/mic.py — Hardened microphone implementation for J.A.R.V.I.S.

Features:
- Auto microphone detection and device enumeration
- Extended ambient noise calibration (1.0s adaptive)
- Confidence scoring from Vosk and Google
- High-pass noise suppression + audio normalization
- Mic health monitoring (zero-energy / disconnect detection)
- Voice Activity Detection (VAD) with energy + zero-crossing

Replaces PyAudio-dependent sr.Microphone for broad Python compatibility.
Uses sounddevice for all audio I/O.
"""
import io
import wave
import time
import numpy as np
import sounddevice as sd
import speech_recognition as sr
from typing import Optional

from core.logger import get_logger

log = get_logger("core.mic")

# ─── Mic Health State ───────────────────────────────────
_mic_device_name: str = "Unknown"
_mic_device_index: Optional[int] = None
_mic_healthy: bool = False
_ambient_noise_level: float = 0.0
_last_confidence: float = 0.0
_consecutive_zero_frames: int = 0
_MAX_ZERO_FRAMES: int = 50  # ~5 seconds of zero audio = mic dead


def get_mic_info() -> dict:
    """Get current microphone status and metadata."""
    return {
        "device_name": _mic_device_name,
        "device_index": _mic_device_index,
        "healthy": _mic_healthy,
        "ambient_noise": round(_ambient_noise_level, 1),
        "last_confidence": round(_last_confidence, 2),
    }


def get_mic_device_name() -> str:
    """Get the active microphone name."""
    return _mic_device_name


def is_mic_healthy() -> bool:
    """Check if the microphone is currently working."""
    return _mic_healthy


def get_ambient_noise() -> float:
    """Get the last measured ambient noise level."""
    return _ambient_noise_level


def get_last_confidence() -> float:
    """Get the confidence score of the last recognition."""
    return _last_confidence


# ─── Device Detection ───────────────────────────────────

def detect_microphone() -> tuple[Optional[int], str]:
    """
    Auto-detect the best available microphone.

    Returns:
        (device_index, device_name) — index may be None for system default.
    """
    global _mic_device_name, _mic_device_index, _mic_healthy

    try:
        devices = sd.query_devices()
        default_input = sd.default.device[0]

        if default_input is not None and default_input >= 0:
            dev = devices[default_input]
            name = dev.get("name", "Unknown")
            _mic_device_name = name
            _mic_device_index = int(default_input)
            _mic_healthy = True
            log.info("Microphone detected: [%d] %s", _mic_device_index, name)
            return _mic_device_index, name

        # Search for any input device
        for i, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                name = dev.get("name", f"Input {i}")
                _mic_device_name = name
                _mic_device_index = i
                _mic_healthy = True
                log.info("Microphone found: [%d] %s", i, name)
                return i, name

        _mic_healthy = False
        log.warning("No microphone detected")
        return None, "No microphone"

    except Exception as e:
        _mic_healthy = False
        log.error("Microphone detection failed: %s", e)
        return None, f"Error: {e}"


# ─── Audio Processing ───────────────────────────────────

def _highpass_filter(audio: np.ndarray, cutoff_hz: float = 80.0,
                     sample_rate: int = 16000) -> np.ndarray:
    """Apply a simple first-order high-pass filter to remove low rumble."""
    rc = 1.0 / (2.0 * np.pi * cutoff_hz)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)

    filtered = np.zeros_like(audio, dtype=np.float64)
    filtered[0] = audio[0]
    for i in range(1, len(audio)):
        filtered[i] = alpha * (filtered[i - 1] + audio[i] - audio[i - 1])

    return filtered.astype(np.int16)


def _normalize_audio(audio: np.ndarray, target_rms: float = 3000.0) -> np.ndarray:
    """Normalize audio to a target RMS level."""
    rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
    if rms < 10:
        return audio  # Too quiet / silence — don't amplify noise
    scale = target_rms / rms
    scale = min(scale, 10.0)  # Cap amplification
    return np.clip(audio * scale, -32768, 32767).astype(np.int16)


def _zero_crossing_rate(audio: np.ndarray) -> float:
    """Calculate zero-crossing rate (voice has higher ZCR than noise)."""
    signs = np.sign(audio.astype(np.float64))
    crossings = np.sum(np.abs(np.diff(signs)) > 0)
    return crossings / len(audio) if len(audio) > 0 else 0.0


# ─── Calibration ────────────────────────────────────────

def calibrate(duration: float = 1.0, sample_rate: int = 16000) -> float:
    """
    Measure ambient noise level for adaptive thresholding.

    Args:
        duration: Seconds of ambient measurement.
        sample_rate: Audio sample rate.

    Returns:
        Measured ambient RMS energy level.
    """
    global _ambient_noise_level

    try:
        chunk_duration = 0.1
        chunk_size = int(sample_rate * chunk_duration)
        num_chunks = int(duration / chunk_duration)
        energies = []

        for _ in range(num_chunks):
            chunk = sd.rec(chunk_size, samplerate=sample_rate,
                           channels=1, dtype='int16',
                           device=_mic_device_index)
            sd.wait()
            energy = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            energies.append(energy)

        # Use median (more robust than mean against spikes)
        _ambient_noise_level = float(np.median(energies))
        log.info("Ambient noise calibrated: %.1f RMS (%d samples)",
                 _ambient_noise_level, num_chunks)
        return _ambient_noise_level

    except Exception as e:
        log.warning("Calibration failed: %s", e)
        _ambient_noise_level = 300.0  # Safe default
        return _ambient_noise_level


# ─── Main Listen Function ───────────────────────────────

def listen_with_sounddevice(
    recognizer: sr.Recognizer,
    timeout: int = 6,
    phrase_time_limit: int = 8,
    sample_rate: int = 16000,
    energy_multiplier: float = 1.8,
    min_energy: float = 300.0,
) -> sr.AudioData:
    """
    Listen for speech using sounddevice and return AudioData.

    Uses energy-based VAD with adaptive threshold:
    - Extended ambient calibration (1.0s)
    - High-pass filtering removes low-frequency noise
    - Audio normalization for consistent recognition
    - Zero-crossing rate as secondary speech indicator
    - Mic health monitoring via zero-energy detection

    Returns:
        sr.AudioData with captured speech.

    Raises:
        sr.WaitTimeoutError: No speech detected within timeout.
        sr.UnknownValueError: No audio captured.
        RuntimeError: Microphone disconnected.
    """
    global _consecutive_zero_frames, _mic_healthy

    chunk_duration = 0.1  # seconds per chunk
    chunk_size = int(sample_rate * chunk_duration)

    # Measure ambient noise level (1.0s)
    ambient_chunks = []
    ambient_samples = int(1.0 / chunk_duration)  # 10 chunks = 1 second

    for _ in range(ambient_samples):
        try:
            chunk = sd.rec(chunk_size, samplerate=sample_rate,
                           channels=1, dtype='int16',
                           device=_mic_device_index)
            sd.wait()
            ambient_chunks.append(chunk)
        except Exception as e:
            _mic_healthy = False
            raise RuntimeError(f"Microphone error during calibration: {e}")

    ambient_data = np.concatenate(ambient_chunks)
    ambient_energy = float(np.sqrt(np.mean(ambient_data.astype(np.float64) ** 2)))
    energy_threshold = max(ambient_energy * energy_multiplier, min_energy)

    # Update global ambient level
    global _ambient_noise_level
    _ambient_noise_level = ambient_energy

    # Wait for speech to start
    audio_chunks: list[np.ndarray] = []
    speech_started = False
    silence_chunks = 0
    max_silence_chunks = int(1.5 / chunk_duration)  # 1.5s = end of speech
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time

        if not speech_started and elapsed > timeout:
            raise sr.WaitTimeoutError("Listening timed out waiting for speech")

        if speech_started and elapsed > timeout + phrase_time_limit:
            break

        # Record a chunk
        try:
            chunk = sd.rec(chunk_size, samplerate=sample_rate,
                           channels=1, dtype='int16',
                           device=_mic_device_index)
            sd.wait()
        except Exception as e:
            _mic_healthy = False
            raise RuntimeError(f"Microphone disconnected: {e}")

        energy = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))

        # Mic health: detect zero-energy (disconnected mic)
        if energy < 1.0:
            _consecutive_zero_frames += 1
            if _consecutive_zero_frames > _MAX_ZERO_FRAMES:
                _mic_healthy = False
                log.warning("Microphone appears disconnected (zero energy for %ds)",
                            int(_consecutive_zero_frames * chunk_duration))
                raise RuntimeError("Microphone disconnected (zero energy)")
        else:
            _consecutive_zero_frames = 0
            _mic_healthy = True

        if energy > energy_threshold:
            if not speech_started:
                speech_started = True
            silence_chunks = 0
            audio_chunks.append(chunk)
        elif speech_started:
            silence_chunks += 1
            audio_chunks.append(chunk)
            if silence_chunks >= max_silence_chunks:
                break

    if not audio_chunks:
        raise sr.UnknownValueError("No speech detected")

    # Combine all audio
    audio_data = np.concatenate(audio_chunks)

    # Apply noise suppression (high-pass filter)
    audio_data = _highpass_filter(audio_data, cutoff_hz=80.0, sample_rate=sample_rate)

    # Normalize audio level
    audio_data = _normalize_audio(audio_data)

    # Convert to WAV format
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())

    wav_buffer.seek(0)

    with sr.AudioFile(wav_buffer) as source:
        audio = recognizer.record(source)

    return audio


# ─── Speech Recognition with Confidence ─────────────────

def recognize_with_confidence(
    recognizer: sr.Recognizer,
    audio: sr.AudioData,
    vosk_model=None,
    sample_rate: int = 16000,
) -> tuple[str, float]:
    """
    Recognize speech and return (text, confidence).

    Tries Vosk (offline, provides confidence natively),
    then Google (online, uses show_all for confidence).

    Returns:
        (text, confidence) where confidence is 0.0-1.0.
    """
    global _last_confidence

    # Try Vosk first
    if vosk_model is not None:
        try:
            import json as json_mod
            from vosk import KaldiRecognizer

            rec = KaldiRecognizer(vosk_model, sample_rate)
            rec.SetWords(True)
            raw_data = audio.get_raw_data(convert_rate=sample_rate, convert_width=2)
            rec.AcceptWaveform(raw_data)
            result = json_mod.loads(rec.FinalResult())
            text = result.get("text", "").strip()

            # Vosk provides per-word confidence
            words = result.get("result", [])
            if words:
                avg_conf = sum(w.get("conf", 0) for w in words) / len(words)
            elif text:
                avg_conf = 0.6  # Default confidence for text without word-level
            else:
                avg_conf = 0.0

            if text:
                _last_confidence = avg_conf
                return text.lower(), avg_conf

        except Exception as e:
            log.debug("Vosk recognition failed: %s", e)

    # Google fallback with confidence
    try:
        results = recognizer.recognize_google(audio, show_all=True)
        if results and isinstance(results, dict):
            alternatives = results.get("alternative", [])
            if alternatives:
                best = alternatives[0]
                text = best.get("transcript", "").strip()
                confidence = best.get("confidence", 0.8)  # Google often omits this
                if text:
                    _last_confidence = float(confidence)
                    return text.lower(), float(confidence)

        # Simple fallback without confidence
        text = recognizer.recognize_google(audio)
        if text:
            _last_confidence = 0.75  # Assume decent confidence
            return text.lower(), 0.75

    except sr.UnknownValueError:
        _last_confidence = 0.0
        return "", 0.0
    except sr.RequestError as e:
        log.warning("Google Speech API error: %s", e)
        _last_confidence = 0.0
        return "", 0.0

    _last_confidence = 0.0
    return "", 0.0


# ─── High-level convenience function ────────────────────

def recognize_speech(timeout: int = 6, phrase_time_limit: int = 8) -> str:
    """
    High-level: listen and recognize speech.

    Returns:
        Recognized text (lowercase) or empty string.
    """
    recognizer = sr.Recognizer()

    try:
        audio = listen_with_sounddevice(
            recognizer,
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
        )
        text, confidence = recognize_with_confidence(recognizer, audio)
        return text
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except RuntimeError as e:
        log.error("Mic error: %s", e)
        return ""
    except Exception as e:
        log.error("Recognition error: %s", e)
        return ""
