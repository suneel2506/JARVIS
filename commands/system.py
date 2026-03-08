import os
from speaker import speak

def shutdown_jarvis():
    speak("Shutting down. Goodbye.")
    return "EXIT"

def open_chrome():
    speak("Opening Chrome")
    os.system("start chrome")

def open_notepad():
    speak("Opening Notepad")
    os.system("notepad")
