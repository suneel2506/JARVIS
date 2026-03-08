import os
import webbrowser
import pywhatkit
import wikipedia
import pyttsx3

engine = pyttsx3.init()
engine.setProperty("rate", 165)


def speak(text):
    engine.say(text)
    engine.runAndWait()


def execute_command(command: str):
    if not command:
        return

    cmd = command.lower()
    print("⚙️ Executing:", cmd)

    if "stop listening" in cmd:
        speak("Okay, I will stop listening")
        from core.listener import stop_listening
        stop_listening()
        return

    if cmd.startswith("open "):
        app = cmd.replace("open ", "")
        if "chrome" in app:
            os.system("start chrome")
            speak("Opening Chrome")
        elif "notepad" in app:
            os.system("notepad")
            speak("Opening Notepad")
        else:
            speak("I don't know that application")
        return

    if "search google" in cmd:
        query = cmd.replace("search google", "").strip()
        webbrowser.open(f"https://www.google.com/search?q={query}")
        speak(f"Searching Google for {query}")
        return

    if cmd.startswith("play "):
        song = cmd.replace("play ", "")
        speak(f"Playing {song}")
        pywhatkit.playonyt(song)
        return

    if "wikipedia" in cmd:
        topic = cmd.replace("wikipedia", "")
        try:
            result = wikipedia.summary(topic, sentences=2)
            speak(result)
        except Exception:
            speak("Could not fetch Wikipedia result")
        return

    speak("Command not recognized yet")
