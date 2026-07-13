"""
core/mic.py — Custom microphone implementation using sounddevice.

Replaces PyAudio-dependent sr.Microphone for broad Python compatibility.
Uses energy-based voice activity detection for speech start/stop.
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


def listen_with_sounddevice(
    recognizer: sr.Recognizer,
    timeout: int = 6,
    phrase_time_limit: int = 8,
    sample_rate: int = 16000,
    energy_multiplier: float = 1.8,
    min_energy: float = 300.0,
) -> sr.AudioData:
    """
    Listen for speech using sounddevice and return an AudioData object
    compatible with speech_recognition.

    Uses energy-based voice activity detection:
    - Measures ambient noise level
    - Waits for audio above threshold (start of speech)
    - Records until silence is detected or phrase_time_limit is reached

    Args:
        recognizer: SpeechRecognition Recognizer instance.
        timeout: Seconds to wait for speech to start before giving up.
        phrase_time_limit: Maximum seconds for a single phrase.
        sample_rate: Audio sample rate in Hz.
        energy_multiplier: How much above ambient to set threshold.
        min_energy: Minimum energy threshold (prevents near-zero thresholds).

    Returns:
        sr.AudioData object containing the captured speech.

    Raises:
        sr.WaitTimeoutError: If no speech detected within timeout.
        sr.UnknownValueError: If no audio captured.
    """
    chunk_duration = 0.1  # seconds per chunk
    chunk_size = int(sample_rate * chunk_duration)

    # Measure ambient noise level
    ambient_chunks = []
    ambient_samples = int(0.5 / chunk_duration)

    for _ in range(ambient_samples):
        chunk = sd.rec(chunk_size, samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()
        ambient_chunks.append(chunk)

    ambient_data = np.concatenate(ambient_chunks)
    ambient_energy = np.sqrt(np.mean(ambient_data.astype(np.float64) ** 2))
    energy_threshold = max(ambient_energy * energy_multiplier, min_energy)

    # Wait for speech to start (or timeout)
    audio_chunks: list[np.ndarray] = []
    speech_started = False
    silence_chunks = 0
    max_silence_chunks = int(1.5 / chunk_duration)  # 1.5s of silence = end of speech
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time

        # Timeout waiting for speech to start
        if not speech_started and elapsed > timeout:
            raise sr.WaitTimeoutError("Listening timed out waiting for speech")

        # Phrase time limit
        if speech_started and elapsed > timeout + phrase_time_limit:
            break

        # Record a chunk
        chunk = sd.rec(chunk_size, samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()

        energy = np.sqrt(np.mean(chunk.astype(np.float64) ** 2))

        if energy > energy_threshold:
            if not speech_started:
                speech_started = True
            silence_chunks = 0
            audio_chunks.append(chunk)
        elif speech_started:
            silence_chunks += 1
            audio_chunks.append(chunk)  # Include trailing silence
            if silence_chunks >= max_silence_chunks:
                break  # End of speech detected

    if not audio_chunks:
        raise sr.UnknownValueError("No speech detected")

    # Combine all audio chunks into WAV format
    audio_data = np.concatenate(audio_chunks)
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())

    wav_buffer.seek(0)

    # Create AudioData from WAV
    with sr.AudioFile(wav_buffer) as source:
        audio = recognizer.record(source)

    return audio


def recognize_speech(timeout: int = 6, phrase_time_limit: int = 8) -> str:
    """
    High-level function: listen and recognize speech using the best
    available recognizer (Vosk offline → Google online).

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
        # Use the listener's unified recognition
        from core.listener import _recognize_audio
        return _recognize_audio(recognizer, audio)
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        log.warning("Speech API error: %s", e)
        return ""
    except Exception as e:
        log.error("Mic error: %s", e)
        return ""
