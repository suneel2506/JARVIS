import os

def open_chrome():
    os.system("start chrome")

def open_notepad():
    os.system("notepad")

def shutdown_jarvis():
    return "EXIT"

COMMANDS = {
    "open chrome": open_chrome,
    "open notepad": open_notepad,
    "shutdown jarvis": shutdown_jarvis
}

def execute(text):
    for key, func in COMMANDS.items():
        if key in text:
            return func()
