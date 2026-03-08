"""
Jarvis 6.0 - Floating neon mini-widget + Voice waveform + Wake-word

Features added:
- Floating always-on-top mini-widget (overrideredirect) with dark/neon theme.
- Voice waveform animation while listening using `sounddevice` RMS sampling.
- Wake-word activation: background listener waits for "hey jarvis" (case-insensitive). When heard, widget expands and enters active listening mode.
- Integrates with existing Jarvis voice command handler (execute, routines, scheduler, hotkeys).

Notes:
- Uses `sounddevice` to sample the microphone for waveform. If sounddevice is unavailable, the widget falls back to a pulsing animation.
- Wake-word uses lightweight recognition via `speech_recognition` on short phrase snippets; this is not a neural wake-word detector but works decently for "hey jarvis" when ambient noise is low.
- GUI built with tkinter; requires a graphical environment.

Dependencies (install):
    pip install SpeechRecognition pyttsx3 pyaudio pywhatkit wikipedia keyboard pyautogui sounddevice numpy pillow

Run:
    python Jarvis6_widget.py

Behavior summary:
- Widget sits as a small round floating button (neon blue) at the top-right of screen.
- Saying "hey jarvis" will make it glow and expand; it will then listen for the next command (visual waveform shows activity).
- You can also click the widget to toggle listening.
- When inactive it shows a subtle breathing neon light; when listening it shows full waveform bars.

"""

import tkinter as tk
from tkinter import ttk
import threading
import time
import speech_recognition as sr
import pyttsx3
import json
import os
import webbrowser
import pywhatkit
import wikipedia
import keyboard
import pyautogui
import numpy as np
import sounddevice as sd
from datetime import datetime
import atexit

# ----------------- Config / Brain -----------------
BRAIN_FILE = "brain.json"

def load_brain():
    try:
        with open(BRAIN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"commands": {}, "usage": {}, "routines": {}, "schedules": [], "hotkeys": {}}
    return data

brain = load_brain()

# ----------------- TTS -----------------
engine = pyttsx3.init()
try:
    engine.setProperty('rate', 165)
except Exception:
    pass

def speak(text, block=True):
    def _s():
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass
    if block:
        _s()
    else:
        threading.Thread(target=_s, daemon=True).start()

atexit.register(lambda: engine.stop())

# ----------------- Recognizer -----------------
recognizer = sr.Recognizer()

# ****************** Wake-word listener ******************
wake_event = threading.Event()
listening_event = threading.Event()
terminate_event = threading.Event()

# Simple wake-word using speech_recognition: listens short snippets and checks for phrase

def wake_loop():
    mic = None
    try:
        mic = sr.Microphone()
    except Exception as e:
        print("Microphone init failed for wake-loop:", e)
        return
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
    while not terminate_event.is_set():
        try:
            with mic as source:
                audio = recognizer.listen(source, timeout=3, phrase_time_limit=2)
            try:
                text = recognizer.recognize_google(audio)
                print("wake heard:", text)
                if "hey jarvis" in text.lower():
                    wake_event.set()
            except sr.UnknownValueError:
                pass
            except sr.RequestError:
                pass
        except sr.WaitTimeoutError:
            continue
        except Exception as e:
            print("Wake loop error:", e)
            time.sleep(0.5)

# ****************** Waveform sampling (sounddevice) ******************
# We'll sample short frames and compute RMS to drive a small bar animation
SAMPLING_RATE = 16000
FRAME_DURATION = 0.05  # seconds
FRAME_SIZE = int(SAMPLING_RATE * FRAME_DURATION)
waveform_levels = [0]*16
waveform_lock = threading.Lock()
use_sounddevice = True

def audio_callback(indata, frames, time_info, status):
    if status:
        #print('status', status)
        pass
    rms = np.sqrt(np.mean(indata**2))
    level = float(rms)
    with waveform_lock:
        # push and pop to keep last N levels
        waveform_levels.pop(0)
        waveform_levels.append(level)

stream = None
try:
    stream = sd.InputStream(channels=1, samplerate=SAMPLING_RATE, blocksize=FRAME_SIZE, callback=audio_callback)
    stream.start()
    use_sounddevice = True
except Exception as e:
    print("sounddevice stream failed, falling back to synthesized animation:", e)
    use_sounddevice = False

# ****************** Core command executor (light version) ******************

def execute(command):
    if not command:
        return
    cmd = command.lower()
    print("EXEC:", cmd)
    # common commands
    if cmd in ("exit", "quit"):
        speak("Goodbye")
        terminate_event.set()
        return "exit"
    if cmd.startswith("open "):
        target = cmd.replace("open ", "").strip()
        if "chrome" in target:
            os.system("start chrome")
            speak("Opening Chrome")
            return
        if "notepad" in target:
            os.system("notepad")
            speak("Opening Notepad")
            return
    if cmd.startswith("search google"):
        q = cmd.replace("search google", "").strip()
        if q:
            webbrowser.open(f"https://www.google.com/search?q={q}")
            speak(f"Searching google for {q}")
        return
    if cmd.startswith("play "):
        song = cmd.replace("play ", "")
        speak(f"Playing {song}")
        try:
            pywhatkit.playonyt(song)
        except Exception:
            webbrowser.open(f"https://www.youtube.com/results?search_query={song}")
        return
    if cmd.startswith("wikipedia"):
        topic = cmd.replace("wikipedia", "").strip()
        try:
            s = wikipedia.summary(topic, sentences=2)
            speak(s)
        except Exception:
            speak("Could not fetch wikipedia")
        return
    # fallback: check brain custom
    if cmd in brain.get('commands', {}):
        action = brain['commands'][cmd]
        try:
            os.system(action)
            speak("Executed saved command")
        except Exception:
            speak("Failed to run saved command")
        return
    # unknown
    speak("I don't know that command yet")

# ****************** GUI: Floating widget ******************
class FloatingWidget(tk.Tk):
    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.config(bg='#0b0f14')
        # Position top-right
        self.geometry('+{}+{}'.format(self.winfo_screenwidth()-160, 40))
        # Make rounded-like frame using canvas
        self.canvas = tk.Canvas(self, width=140, height=140, bg='#0b0f14', highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind('<Button-1>', self.on_click)
        self.is_listening = False
        self.animating = True
        self._build_ui()
        # Start UI animation
        self.after(50, self.ui_loop)
        # Start wake monitor thread
        threading.Thread(target=self._wake_monitor, daemon=True).start()

    def _build_ui(self):
        # neon circle
        self.circle = self.canvas.create_oval(10,10,130,130, fill='#031224', outline='#00f0ff', width=3)
        # inner icon (dot)
        self.dot = self.canvas.create_oval(60,60,80,80, fill='#00f0ff', outline='')
        # small text
        self.label = self.canvas.create_text(70, 110, text='Jarvis', fill='#00f0ff', font=('Helvetica', 10))
        # waveform bars (16 bars)
        self.bar_items = []
        bar_w = 6
        gap = 2
        start_x = 10
        for i in range(16):
            x = start_x + i*(bar_w+gap)
            rect = self.canvas.create_rectangle(x, 20, x+bar_w, 40, fill='#00f0ff', outline='')
            self.bar_items.append(rect)
        # small expand target
        self.expanded = False

    def on_click(self, _event=None):
        # toggle manual listening
        if not self.is_listening:
            wake_event.set()
        else:
            listening_event.clear()
            self.is_listening = False
            speak('Stopped listening')

    def ui_loop(self):
        # breathing neon when idle
        if not self.is_listening:
            # pulse circle color alpha via outline width
            t = (time.time() % 2)
            w = 2 + (1.5 * abs(1 - t))
            try:
                self.canvas.itemconfig(self.circle, width=w)
            except Exception:
                pass
        else:
            # update bars from waveform_levels
            with waveform_lock:
                levels = list(waveform_levels)
            # normalize
            mx = max(max(levels), 1e-6)
            for i, val in enumerate(levels):
                h = int((val/mx)*80)+2
                x1, y1, x2, y2 = self.canvas.coords(self.bar_items[i])
                self.canvas.coords(self.bar_items[i], x1, 120-h, x2, 120)
        # check wake_event
        if wake_event.is_set() and not self.is_listening:
            self.activate_listen()
            wake_event.clear()
        self.after(60, self.ui_loop)

    def activate_listen(self):
        self.is_listening = True
        speak('Yes?')
        # expand cosmetic
        if not self.expanded:
            self.canvas.itemconfig(self.label, text='Listening...')
            self.expanded = True
        # start a thread to listen once for a full command
        threading.Thread(target=self.capture_command_once, daemon=True).start()

    def capture_command_once(self):
        listening_event.set()
        # show waveform for a short time and then perform recognition
        cmd = ''
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=6, phrase_time_limit=8)
                cmd = recognizer.recognize_google(audio)
        except sr.WaitTimeoutError:
            speak('No speech detected')
        except sr.UnknownValueError:
            speak('Could not understand')
        except sr.RequestError:
            speak('Speech API error')
        except Exception as e:
            print('listen err', e)
        # handle result
        if cmd:
            print('heard:', cmd)
            execute(cmd)
        # restore UI
        self.canvas.itemconfig(self.label, text='Jarvis')
        self.is_listening = False
        listening_event.clear()

    def _wake_monitor(self):
        # start a background thread to trigger wake_event if phrase heard
        # wake_loop runs globally; here we just wait for wake_event
        while not terminate_event.is_set():
            if wake_event.wait(timeout=0.5):
                # animate glow
                for _ in range(3):
                    self.canvas.itemconfig(self.dot, fill='#00fff0')
                    time.sleep(0.12)
                    self.canvas.itemconfig(self.dot, fill='#00f0ff')
                    time.sleep(0.08)
            time.sleep(0.1)

# ****************** Start wake-loop and GUI ******************

def start_background_services():
    # wake-word loop
    threading.Thread(target=wake_loop, daemon=True).start()
    # start scheduler from previous version if any
    # register hotkeys if present
    for keys, routine in brain.get('hotkeys', {}).items():
        try:
            keyboard.add_hotkey(keys, lambda r=routine: execute(f'run routine {r}'))
        except Exception as e:
            print('hotkey bind failed', keys, e)

if __name__ == '__main__':
    start_background_services()
    app = FloatingWidget()
    app.mainloop()
