"""
core/mic.py — Hardened microphone implementation for J.A.R.V.I.S.

Features:
- Auto microphone detection and device enumeration
- Multi-microphone support with quality scoring and automatic failover
- Extended ambient noise calibration (1.0s adaptive)
- Confidence scoring from Vosk and Google
- Spectral subtraction noise suppression + high-pass filter + audio normalization
- Automatic gain control (AGC) for consistent levels across hardware
- Mic health monitoring (zero-energy / disconnect detection)
- Voice Activity Detection (VAD) with energy + zero-crossing + spectral flatness

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

# ─── Multi-mic tracking ────────────────────────────────
_available_mics: list[dict] = []
_mic_failover_enabled: bool = True

# ─── Noise profile for spectral subtraction ─────────────
_noise_profile: Optional[np.ndarray] = None


def get_mic_info() -> dict:
    """Get current microphone status and metadata."""
    return {
        "device_name": _mic_device_name,
        "device_index": _mic_device_index,
        "healthy": _mic_healthy,
        "ambient_noise": round(_ambient_noise_level, 1),
        "last_confidence": round(_last_confidence, 2),
        "available_mics": len(_available_mics),
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


def get_available_mics() -> list[dict]:
    """Get list of all available input devices with quality scores."""
    return list(_available_mics)


# ─── Device Detection (Multi-Mic) ───────────────────────

def _score_mic_device(dev: dict) -> float:
    """Score a microphone device by quality (higher is better)."""
    score = 0.0
    name = dev.get("name", "").lower()

    # Prefer higher sample rates
    default_sr = dev.get("default_samplerate", 0)
    if default_sr >= 44100:
        score += 3.0
    elif default_sr >= 16000:
        score += 2.0
    elif default_sr > 0:
        score += 1.0

    # Prefer more channels (stereo mics tend to be better)
    channels = dev.get("max_input_channels", 0)
    if channels >= 2:
        score += 1.0

    # Prefer named devices over generic ones
    if any(kw in name for kw in ("microphone", "mic", "usb", "headset", "webcam")):
        score += 2.0

    # Penalize virtual/loopback devices
    if any(kw in name for kw in ("stereo mix", "loopback", "virtual", "what u hear")):
        score -= 5.0

    # Penalize devices with high latency
    latency = dev.get("default_low_input_latency", 1.0)
    if latency < 0.02:
        score += 1.0
    elif latency > 0.1:
        score -= 1.0

    return score


def enumerate_microphones() -> list[dict]:
    """
    Enumerate all available input devices and score them by quality.

    Returns:
        List of dicts with: index, name, channels, sample_rate, score
    """
    global _available_mics
    _available_mics = []

    try:
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                score = _score_mic_device(dev)
                _available_mics.append({
                    "index": i,
                    "name": dev.get("name", f"Input {i}"),
                    "channels": dev.get("max_input_channels", 0),
                    "sample_rate": int(dev.get("default_samplerate", 0)),
                    "latency": round(dev.get("default_low_input_latency", 0), 4),
                    "score": round(score, 1),
                })

        # Sort by score (best first)
        _available_mics.sort(key=lambda m: m["score"], reverse=True)
        log.info("Found %d input device(s)", len(_available_mics))

    except Exception as e:
        log.error("Device enumeration failed: %s", e)

    return _available_mics


def detect_microphone(preferred_index: Optional[int] = None) -> tuple[Optional[int], str]:
    """
    Auto-detect the best available microphone.

    Uses quality scoring to pick the best device. Supports manual override
    via preferred_index. Falls back through available devices on failure.

    Args:
        preferred_index: If set, try this device first.

    Returns:
        (device_index, device_name) — index may be None for system default.
    """
    global _mic_device_name, _mic_device_index, _mic_healthy

    # Enumerate all devices
    enumerate_microphones()

    # Try preferred index first
    if preferred_index is not None:
        for mic in _available_mics:
            if mic["index"] == preferred_index:
                _mic_device_name = mic["name"]
                _mic_device_index = preferred_index
                _mic_healthy = True
                log.info("Using preferred microphone: [%d] %s", preferred_index, mic["name"])
                return _mic_device_index, _mic_device_name

    # Try system default
    try:
        default_input = sd.default.device[0]
        if default_input is not None and default_input >= 0:
            devices = sd.query_devices()
            dev = devices[default_input]
            name = dev.get("name", "Unknown")
            _mic_device_name = name
            _mic_device_index = int(default_input)
            _mic_healthy = True
            log.info("Microphone detected (system default): [%d] %s", _mic_device_index, name)
            return _mic_device_index, name
    except Exception:
        pass

    # Fall back to highest-scored device
    if _available_mics:
        best = _available_mics[0]
        _mic_device_name = best["name"]
        _mic_device_index = best["index"]
        _mic_healthy = True
        log.info("Microphone selected (best score %.1f): [%d] %s",
                 best["score"], best["index"], best["name"])
        return _mic_device_index, _mic_device_name

    _mic_healthy = False
    log.warning("No microphone detected")
    return None, "No microphone"


def failover_microphone() -> bool:
    """
    Attempt to switch to the next available microphone.
    Called when the current mic fails or disconnects.

    Returns:
        True if failover succeeded, False if no alternatives available.
    """
    global _mic_device_name, _mic_device_index, _mic_healthy

    if not _mic_failover_enabled:
        return False

    # Re-enumerate in case devices changed
    enumerate_microphones()

    # Find an alternative (skip current device)
    for mic in _available_mics:
        if mic["index"] != _mic_device_index and mic["score"] > 0:
            old_name = _mic_device_name
            _mic_device_name = mic["name"]
            _mic_device_index = mic["index"]
            _mic_healthy = True
            log.warning("Mic failover: '%s' → '%s'", old_name, mic["name"])
            return True

    _mic_healthy = False
    log.error("Mic failover failed — no alternative devices available")
    return False


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


def _spectral_subtract(audio: np.ndarray, noise_profile: np.ndarray,
                        alpha: float = 2.0, beta: float = 0.01) -> np.ndarray:
    """
    Apply spectral subtraction noise reduction.

    Estimates noise spectrum from the noise profile and subtracts it from
    the signal. More effective than simple high-pass for stationary noise
    (fans, AC, hum).

    Args:
        audio: Input audio (int16).
        noise_profile: Captured noise-only audio for profiling.
        alpha: Over-subtraction factor (higher = more aggressive).
        beta: Spectral floor (prevents musical noise artifacts).

    Returns:
        Noise-reduced audio (int16).
    """
    audio_f = audio.astype(np.float64)
    noise_f = noise_profile.astype(np.float64)

    # Compute magnitude spectra
    fft_size = 512
    hop = fft_size // 2

    # Estimate noise magnitude spectrum (average over noise profile)
    noise_frames = []
    for start in range(0, len(noise_f) - fft_size, hop):
        frame = noise_f[start:start + fft_size]
        window = np.hanning(fft_size)
        noise_frames.append(np.abs(np.fft.rfft(frame * window)))

    if not noise_frames:
        return audio  # Not enough noise data

    noise_mag = np.mean(noise_frames, axis=0)

    # Process signal frame by frame
    output = np.zeros_like(audio_f)
    for start in range(0, len(audio_f) - fft_size, hop):
        frame = audio_f[start:start + fft_size]
        window = np.hanning(fft_size)
        spec = np.fft.rfft(frame * window)
        mag = np.abs(spec)
        phase = np.angle(spec)

        # Spectral subtraction with floor
        clean_mag = np.maximum(mag - alpha * noise_mag[:len(mag)], beta * mag)

        # Reconstruct
        clean_spec = clean_mag * np.exp(1j * phase)
        clean_frame = np.fft.irfft(clean_spec, n=fft_size)

        # Overlap-add
        output[start:start + fft_size] += clean_frame * window

    return np.clip(output, -32768, 32767).astype(np.int16)


def _normalize_audio(audio: np.ndarray, target_rms: float = 3000.0) -> np.ndarray:
    """Normalize audio to a target RMS level."""
    rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
    if rms < 10:
        return audio  # Too quiet / silence — don't amplify noise
    scale = target_rms / rms
    scale = min(scale, 10.0)  # Cap amplification
    return np.clip(audio * scale, -32768, 32767).astype(np.int16)


def _automatic_gain_control(audio: np.ndarray, target_rms: float = 3000.0,
                             attack: float = 0.01, release: float = 0.1,
                             sample_rate: int = 16000) -> np.ndarray:
    """
    Apply automatic gain control with smooth attack/release.

    Unlike simple normalization, AGC adapts dynamically to varying
    signal levels — boosting quiet speech and limiting loud peaks.

    Args:
        audio: Input audio (int16).
        target_rms: Desired RMS level.
        attack: Attack time constant (seconds) — how fast gain increases.
        release: Release time constant (seconds) — how fast gain decreases.
        sample_rate: Audio sample rate.
    """
    audio_f = audio.astype(np.float64)
    output = np.zeros_like(audio_f)

    # Process in small blocks (10ms)
    block_size = int(sample_rate * 0.01)
    gain = 1.0
    max_gain = 10.0
    min_gain = 0.1

    attack_coeff = 1.0 - np.exp(-1.0 / (attack * sample_rate / block_size))
    release_coeff = 1.0 - np.exp(-1.0 / (release * sample_rate / block_size))

    for start in range(0, len(audio_f), block_size):
        end = min(start + block_size, len(audio_f))
        block = audio_f[start:end]

        rms = np.sqrt(np.mean(block ** 2))
        if rms < 1.0:
            output[start:end] = block * gain
            continue

        target_gain = target_rms / rms
        target_gain = np.clip(target_gain, min_gain, max_gain)

        # Smooth gain transition
        if target_gain < gain:
            gain += (target_gain - gain) * attack_coeff  # Fast attack
        else:
            gain += (target_gain - gain) * release_coeff  # Slow release

        output[start:end] = block * gain

    return np.clip(output, -32768, 32767).astype(np.int16)


def _zero_crossing_rate(audio: np.ndarray) -> float:
    """Calculate zero-crossing rate (voice has higher ZCR than noise)."""
    signs = np.sign(audio.astype(np.float64))
    crossings = np.sum(np.abs(np.diff(signs)) > 0)
    return crossings / len(audio) if len(audio) > 0 else 0.0


def _spectral_flatness(audio: np.ndarray) -> float:
    """
    Calculate spectral flatness (Wiener entropy).

    Speech has low spectral flatness (harmonic structure).
    Noise has high spectral flatness (flat spectrum).

    Returns:
        Value between 0 (tonal/speech) and 1 (noise).
    """
    spec = np.abs(np.fft.rfft(audio.astype(np.float64)))
    spec = spec[spec > 0]  # Avoid log(0)
    if len(spec) == 0:
        return 1.0
    geometric_mean = np.exp(np.mean(np.log(spec)))
    arithmetic_mean = np.mean(spec)
    if arithmetic_mean == 0:
        return 1.0
    return min(1.0, geometric_mean / arithmetic_mean)


def _is_speech_vad(audio: np.ndarray, energy_threshold: float,
                   sample_rate: int = 16000) -> bool:
    """
    Multi-feature Voice Activity Detection.

    Combines three features for robust speech detection:
    1. Energy (RMS) — primary indicator
    2. Zero-crossing rate — speech has moderate ZCR
    3. Spectral flatness — speech is tonal (low flatness)

    Returns:
        True if the chunk likely contains speech.
    """
    energy = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    zcr = _zero_crossing_rate(audio.flatten())
    flatness = _spectral_flatness(audio.flatten())

    # Score each feature (0 to 1)
    energy_score = min(1.0, energy / max(energy_threshold, 1.0))
    zcr_score = 1.0 if 0.02 < zcr < 0.25 else 0.3  # Speech ZCR range
    flatness_score = 1.0 - flatness  # Low flatness = likely speech

    # Weighted combination
    vad_score = (energy_score * 0.6) + (zcr_score * 0.2) + (flatness_score * 0.2)

    return vad_score > 0.45


# ─── Calibration ────────────────────────────────────────

def calibrate(duration: float = 1.0, sample_rate: int = 16000) -> float:
    """
    Measure ambient noise level for adaptive thresholding.
    Also captures a noise profile for spectral subtraction.

    Args:
        duration: Seconds of ambient measurement.
        sample_rate: Audio sample rate.

    Returns:
        Measured ambient RMS energy level.
    """
    global _ambient_noise_level, _noise_profile

    try:
        chunk_duration = 0.1
        chunk_size = int(sample_rate * chunk_duration)
        num_chunks = int(duration / chunk_duration)
        energies = []
        noise_chunks = []

        for _ in range(num_chunks):
            chunk = sd.rec(chunk_size, samplerate=sample_rate,
                           channels=1, dtype='int16',
                           device=_mic_device_index)
            sd.wait()
            energy = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            energies.append(energy)
            noise_chunks.append(chunk.flatten())

        # Use median (more robust than mean against spikes)
        _ambient_noise_level = float(np.median(energies))

        # Store noise profile for spectral subtraction
        if noise_chunks:
            _noise_profile = np.concatenate(noise_chunks)

        log.info("Ambient noise calibrated: %.1f RMS (%d samples), noise profile: %s",
                 _ambient_noise_level, num_chunks,
                 f"{len(_noise_profile)} samples" if _noise_profile is not None else "none")
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

    Uses multi-feature VAD with adaptive threshold:
    - Extended ambient calibration (1.0s)
    - Spectral subtraction noise reduction (when noise profile available)
    - High-pass filtering removes low-frequency noise
    - Automatic gain control for consistent recognition
    - Multi-feature VAD (energy + ZCR + spectral flatness)
    - Mic health monitoring via zero-energy detection
    - Automatic mic failover on disconnect

    Returns:
        sr.AudioData with captured speech.

    Raises:
        sr.WaitTimeoutError: No speech detected within timeout.
        sr.UnknownValueError: No audio captured.
        RuntimeError: Microphone disconnected (after failover attempt).
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
            # Try mic failover before giving up
            if failover_microphone():
                log.info("Mic failover during calibration — retrying")
                try:
                    chunk = sd.rec(chunk_size, samplerate=sample_rate,
                                   channels=1, dtype='int16',
                                   device=_mic_device_index)
                    sd.wait()
                    ambient_chunks.append(chunk)
                    continue
                except Exception:
                    pass
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
            # Try mic failover
            if failover_microphone():
                log.info("Mic failover during recording — continuing")
                continue
            _mic_healthy = False
            raise RuntimeError(f"Microphone disconnected: {e}")

        energy = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))

        # Mic health: detect zero-energy (disconnected mic)
        if energy < 1.0:
            _consecutive_zero_frames += 1
            if _consecutive_zero_frames > _MAX_ZERO_FRAMES:
                # Try failover before declaring dead
                if failover_microphone():
                    _consecutive_zero_frames = 0
                    log.info("Mic failover after zero-energy — continuing")
                    continue
                _mic_healthy = False
                log.warning("Microphone appears disconnected (zero energy for %ds)",
                            int(_consecutive_zero_frames * chunk_duration))
                raise RuntimeError("Microphone disconnected (zero energy)")
        else:
            _consecutive_zero_frames = 0
            _mic_healthy = True

        # Use multi-feature VAD instead of simple energy check
        if _is_speech_vad(chunk, energy_threshold, sample_rate):
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

    # Apply spectral subtraction (if noise profile available)
    if _noise_profile is not None and len(_noise_profile) > 512:
        audio_data = _spectral_subtract(audio_data, _noise_profile)

    # Apply noise suppression (high-pass filter)
    audio_data = _highpass_filter(audio_data, cutoff_hz=80.0, sample_rate=sample_rate)

    # Apply automatic gain control
    audio_data = _automatic_gain_control(audio_data, sample_rate=sample_rate)

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
