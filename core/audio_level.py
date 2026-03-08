import sounddevice as sd
import numpy as np

level = 0.0

def audio_callback(indata, frames, time, status):
    global level
    level = np.linalg.norm(indata) * 10

def start_stream():
    stream = sd.InputStream(callback=audio_callback)
    stream.start()
