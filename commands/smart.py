"""
commands/smart.py — Smart query commands for Jarvis.
Time, date, weather, jokes, math, IP, and general info.
"""
from datetime import datetime
import random


def get_time():
    """Get current time in natural language."""
    now = datetime.now()
    hour = now.strftime("%I").lstrip("0")
    minute = now.strftime("%M")
    period = now.strftime("%p")
    return True, f"It's {hour}:{minute} {period}"


def get_date():
    """Get current date in natural language."""
    now = datetime.now()
    return True, f"Today is {now.strftime('%A, %B %d, %Y')}"


def get_weather(city="auto"):
    """Get weather from wttr.in (no API key needed)."""
    try:
        import requests
        if city == "auto":
            # Auto-detect location
            url = "https://wttr.in/?format=%C+%t+%h+%w"
        else:
            url = f"https://wttr.in/{city}?format=%C+%t+%h+%w"
        resp = requests.get(url, timeout=5, headers={"User-Agent": "curl"})
        if resp.status_code == 200:
            return True, f"Current weather: {resp.text.strip()}"
        else:
            return False, "Couldn't fetch weather data"
    except Exception:
        return False, "Weather service is unavailable. Check your internet connection."


def tell_joke():
    """Tell a random joke."""
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs.",
        "I told my wife she was drawing her eyebrows too high. She looked surprised.",
        "Why don't scientists trust atoms? Because they make up everything.",
        "What do you call a fake noodle? An impasta.",
        "Why did the scarecrow win an award? Because he was outstanding in his field.",
        "I would tell you a joke about UDP, but you might not get it.",
        "There are 10 types of people in the world: those who understand binary, and those who don't.",
        "A SQL query walks into a bar, sees two tables and asks... can I JOIN you?",
        "Why do Java developers wear glasses? Because they can't C sharp.",
        "I'd tell you a chemistry joke but I know I wouldn't get a reaction.",
    ]
    return True, random.choice(jokes)


def calculate(expression):
    """Evaluate a simple math expression safely."""
    try:
        # Only allow safe characters
        allowed = set("0123456789+-*/().% ")
        if all(c in allowed for c in expression):
            result = eval(expression)
            return True, f"The answer is {result}"
        else:
            return False, "I can only handle basic math operations"
    except Exception:
        return False, "I couldn't calculate that"


def get_ip():
    """Get the current IP address."""
    try:
        import requests
        resp = requests.get("https://api.ipify.org", timeout=5)
        return True, f"Your public IP address is {resp.text}"
    except Exception:
        try:
            import socket
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            return True, f"Your local IP address is {ip}"
        except Exception:
            return False, "Couldn't determine IP address"


def get_system_status():
    """Get a brief system status report."""
    try:
        from core.system_info import get_stats
        stats = get_stats()
        msg = (
            f"System status: CPU at {stats['cpu_percent']:.0f}%, "
            f"RAM at {stats['ram_percent']:.0f}%, "
            f"Battery at {stats['battery_percent']:.0f}%"
        )
        if stats['battery_plugged']:
            msg += " and charging"
        msg += f". Network is {'connected' if stats['network_connected'] else 'disconnected'}."
        return True, msg
    except Exception:
        return False, "System monitoring not available"


def handle_smart_command(command):
    """
    Route smart query commands.
    Returns (handled: bool, success: bool, message: str)
    """
    cmd = command.lower()

    # Time
    if "time" in cmd and ("what" in cmd or "current" in cmd or "tell" in cmd or cmd.strip() == "time"):
        ok, msg = get_time()
        return True, ok, msg

    # Date
    if "date" in cmd and ("what" in cmd or "current" in cmd or "today" in cmd or cmd.strip() == "date"):
        ok, msg = get_date()
        return True, ok, msg

    if "what day" in cmd or "today" in cmd:
        ok, msg = get_date()
        return True, ok, msg

    # Weather
    if "weather" in cmd:
        # Extract city if mentioned
        city = "auto"
        if "in " in cmd:
            city = cmd.split("in ")[-1].strip()
        elif "for " in cmd:
            city = cmd.split("for ")[-1].strip()
        ok, msg = get_weather(city)
        return True, ok, msg

    # Jokes
    if "joke" in cmd or "funny" in cmd or "make me laugh" in cmd:
        ok, msg = tell_joke()
        return True, ok, msg

    # Math / Calculate
    if cmd.startswith("calculate ") or cmd.startswith("compute "):
        expr = cmd.replace("calculate ", "").replace("compute ", "").strip()
        ok, msg = calculate(expr)
        return True, ok, msg

    if "plus" in cmd or "minus" in cmd or "times" in cmd or "divided by" in cmd:
        expr = (cmd.replace("plus", "+").replace("minus", "-")
                .replace("times", "*").replace("divided by", "/")
                .replace("x", "*"))
        # Extract just the math parts
        import re
        nums = re.findall(r'[\d.+\-*/() ]+', expr)
        if nums:
            ok, msg = calculate("".join(nums).strip())
            return True, ok, msg

    # IP
    if "ip address" in cmd or "my ip" in cmd:
        ok, msg = get_ip()
        return True, ok, msg

    # System status
    if "system status" in cmd or "system report" in cmd or "diagnostics" in cmd:
        ok, msg = get_system_status()
        return True, ok, msg

    # How are you / greeting
    if any(g in cmd for g in ["how are you", "how do you do", "hello", "hi jarvis"]):
        responses = [
            "All systems operational, sir. How can I help you?",
            "I'm functioning within normal parameters. What do you need?",
            "Running at peak efficiency. What can I do for you?",
            "Online and ready, sir.",
        ]
        return True, True, random.choice(responses)

    # Who are you
    if "who are you" in cmd or "what are you" in cmd or "your name" in cmd:
        return True, True, ("I am J.A.R.V.I.S., Just A Rather Very Intelligent System. "
                           "Your personal AI assistant, sir.")

    # Thank you
    if "thank" in cmd:
        responses = [
            "You're welcome, sir.",
            "Happy to help.",
            "At your service, sir.",
            "Anytime.",
        ]
        return True, True, random.choice(responses)

    return False, False, ""
