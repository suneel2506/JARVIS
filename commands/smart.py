"""
commands/smart.py — Smart query commands for J.A.R.V.I.S.

Time, date, weather, jokes, math, IP, system status, and conversational responses.
"""
from datetime import datetime
import random

from core.logger import get_logger

log = get_logger("commands.smart")


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


def get_system_status() -> tuple[bool, str]:
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


def get_news(topic: str = "") -> tuple[bool, str]:
    """Get latest news headlines via RSS."""
    try:
        import requests
        if topic:
            url = f"https://news.google.com/rss/search?q={topic}&hl=en"
        else:
            url = "https://news.google.com/rss?hl=en"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "JARVIS/2.0"})
        if resp.status_code == 200:
            import re as re_mod
            titles = re_mod.findall(r'<title>(.*?)</title>', resp.text)
            # Skip the first title (feed title)
            headlines = [t for t in titles[1:6] if t and 'Google News' not in t]
            if headlines:
                result = "Here are the latest headlines. " + ". ".join(headlines[:4])
                return True, result
        return False, "Couldn't fetch news right now"
    except Exception:
        return False, "News service is unavailable"


def translate_text(text: str, target_lang: str = "es") -> tuple[bool, str]:
    """Translate text using MyMemory API (free, no key needed)."""
    lang_map = {
        "spanish": "es", "french": "fr", "german": "de", "italian": "it",
        "portuguese": "pt", "chinese": "zh-CN", "japanese": "ja", "korean": "ko",
        "hindi": "hi", "arabic": "ar", "russian": "ru", "dutch": "nl",
        "turkish": "tr", "swedish": "sv", "polish": "pl", "thai": "th",
        "tamil": "ta", "telugu": "te", "bengali": "bn", "urdu": "ur",
    }
    target_lang = lang_map.get(target_lang.lower(), target_lang)
    try:
        import requests
        url = f"https://api.mymemory.translated.net/get?q={text}&langpair=en|{target_lang}"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            translated = data.get("responseData", {}).get("translatedText", "")
            if translated:
                return True, f"In {target_lang}: {translated}"
        return False, "Translation failed"
    except Exception:
        return False, "Translation service unavailable"


def define_word(word: str) -> tuple[bool, str]:
    """Get word definition using free dictionary API."""
    try:
        import requests
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data and len(data) > 0:
                meanings = data[0].get("meanings", [])
                if meanings:
                    part = meanings[0].get("partOfSpeech", "")
                    defs = meanings[0].get("definitions", [])
                    if defs:
                        definition = defs[0].get("definition", "")
                        return True, f"{word.title()} ({part}): {definition}"
        return True, f"I couldn't find a definition for '{word}'"
    except Exception:
        return False, "Dictionary service unavailable"


def get_quote() -> tuple[bool, str]:
    """Get a random inspirational quote."""
    try:
        import requests
        resp = requests.get("https://zenquotes.io/api/random", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                quote = data[0].get("q", "")
                author = data[0].get("a", "Unknown")
                return True, f'"{quote}" — {author}'
    except Exception:
        pass
    # Fallback quotes
    quotes = [
        '"The best way to predict the future is to invent it." — Alan Kay',
        '"Innovation distinguishes between a leader and a follower." — Steve Jobs',
        '"Any sufficiently advanced technology is indistinguishable from magic." — Arthur C. Clarke',
        '"Sometimes you gotta run before you can walk." — Tony Stark',
        '"The only way to do great work is to love what you do." — Steve Jobs',
    ]
    return True, random.choice(quotes)


def flip_coin() -> tuple[bool, str]:
    """Flip a coin."""
    result = random.choice(["Heads", "Tails"])
    return True, f"It's {result}!"


def roll_dice(sides: int = 6) -> tuple[bool, str]:
    """Roll a dice."""
    result = random.randint(1, sides)
    return True, f"You rolled a {result}!"


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
        city = "auto"
        if "in " in cmd:
            city = cmd.split("in ")[-1].strip()
        elif "for " in cmd:
            city = cmd.split("for ")[-1].strip()
        ok, msg = get_weather(city)
        return True, ok, msg

    # News
    if "news" in cmd or "headlines" in cmd:
        topic = ""
        for prefix in ("news about ", "news on ", "headlines about ", "headlines on "):
            if prefix in cmd:
                topic = cmd.split(prefix)[-1].strip()
                break
        ok, msg = get_news(topic)
        return True, ok, msg

    # Translate
    if "translate" in cmd:
        import re as re_mod
        # "translate hello to spanish"
        match = re_mod.search(r'translate\s+(.+?)\s+to\s+(\w+)', cmd)
        if match:
            text = match.group(1).strip()
            lang = match.group(2).strip()
            ok, msg = translate_text(text, lang)
            return True, ok, msg

    # Define
    if cmd.startswith("define ") or cmd.startswith("meaning of ") or cmd.startswith("what does ") and "mean" in cmd:
        word = cmd.replace("define ", "").replace("meaning of ", "").replace("what does ", "").replace(" mean", "").strip()
        if word:
            ok, msg = define_word(word)
            return True, ok, msg

    # Quote
    if "quote" in cmd or "inspire" in cmd or "motivation" in cmd:
        ok, msg = get_quote()
        return True, ok, msg

    # Coin flip
    if "flip" in cmd and "coin" in cmd or cmd == "heads or tails":
        ok, msg = flip_coin()
        return True, ok, msg

    # Dice
    if "roll" in cmd and ("dice" in cmd or "die" in cmd):
        ok, msg = roll_dice()
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
        return True, True, ("I am Jarvis, Just A Rather Very Intelligent System. "
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

