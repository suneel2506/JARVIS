import speech_recognition as sr
import threading

recognizer = sr.Recognizer()
mic = sr.Microphone()

stop_listening_flag = False


def listen_continuous(on_command):
    """
    Always listens until stop_listening_flag becomes True
    Calls on_command(text) whenever speech is recognized
    """

    global stop_listening_flag
    stop_listening_flag = False

    def _listen_loop():
        global stop_listening_flag
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)

        while not stop_listening_flag:
            try:
                with mic as source:
                    audio = recognizer.listen(source, phrase_time_limit=6)

                text = recognizer.recognize_google(audio)
                print("🎧 Heard:", text)
                on_command(text)

            except sr.UnknownValueError:
                pass
            except sr.RequestError:
                print("Speech service error")
            except Exception as e:
                print("Listener error:", e)

    threading.Thread(target=_listen_loop, daemon=True).start()


def stop_listening():
    global stop_listening_flag
    stop_listening_flag = True
