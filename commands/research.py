"""
commands/research.py — Internet research & summarization for J.A.R.V.I.S.

Phase 6 capabilities:
- Wikipedia quick lookup
- Dictionary/definition lookup
- URL text extraction (basic)
- Research mode (multi-source search)
- Quick facts (math, conversions, definitions)
"""
import re
import webbrowser
import urllib.parse
from typing import Optional

from core.logger import get_logger

log = get_logger("commands.research")


# ═══════════════════════════════════════════════════════════
# Wikipedia Lookup
# ═══════════════════════════════════════════════════════════

def wiki_lookup(topic: str) -> tuple[bool, str]:
    """
    Open a Wikipedia page for a topic and return a brief summary.
    Uses the Wikipedia API for a text extract.
    """
    try:
        import urllib.request
        import json

        encoded = urllib.parse.quote(topic)
        api_url = (
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        )

        req = urllib.request.Request(api_url, headers={
            "User-Agent": "JARVIS/2.0 (Voice Assistant)"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        extract = data.get("extract", "")
        title = data.get("title", topic)

        if extract:
            # Trim to ~2 sentences for voice
            sentences = extract.split(". ")
            summary = ". ".join(sentences[:3])
            if len(summary) > 300:
                summary = summary[:297] + "..."
            if not summary.endswith("."):
                summary += "."

            # Also open in browser
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
            if page_url:
                webbrowser.open(page_url)

            return True, f"{title}: {summary}"
        else:
            # Fallback: open search
            webbrowser.open(f"https://en.wikipedia.org/wiki/Special:Search/{encoded}")
            return True, f"I couldn't find a summary for '{topic}', but I've opened the search page."

    except Exception as e:
        log.error("Wikipedia lookup failed for '%s': %s", topic, e)
        webbrowser.open(f"https://en.wikipedia.org/wiki/{urllib.parse.quote(topic)}")
        return True, f"Opening Wikipedia for {topic}, sir."


# ═══════════════════════════════════════════════════════════
# Dictionary Lookup
# ═══════════════════════════════════════════════════════════

def define_word(word: str) -> tuple[bool, str]:
    """Look up a word definition using a free API."""
    try:
        import urllib.request
        import json

        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "JARVIS/2.0"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if isinstance(data, list) and data:
            entry = data[0]
            meanings = entry.get("meanings", [])
            if meanings:
                first = meanings[0]
                pos = first.get("partOfSpeech", "")
                defs = first.get("definitions", [])
                if defs:
                    definition = defs[0].get("definition", "")
                    result = f"{word.capitalize()}"
                    if pos:
                        result += f" ({pos})"
                    result += f": {definition}"
                    return True, result

        return False, f"I couldn't find a definition for '{word}', sir."

    except Exception as e:
        log.error("Dictionary lookup failed for '%s': %s", word, e)
        return False, f"Definition lookup failed for '{word}', sir."


# ═══════════════════════════════════════════════════════════
# Quick Math
# ═══════════════════════════════════════════════════════════

def quick_math(expression: str) -> tuple[bool, str]:
    """
    Evaluate a simple math expression safely.
    Supports basic arithmetic only — no exec/eval abuse.
    """
    # Sanitize: only allow digits, operators, parentheses, decimal points, spaces
    sanitized = re.sub(r'[^0-9+\-*/().%^ ]', '', expression)
    if not sanitized:
        return False, "I couldn't parse that math expression, sir."

    # Replace ^ with ** for exponentiation
    sanitized = sanitized.replace('^', '**')

    try:
        # Use compile + eval with empty globals for safety
        code = compile(sanitized, "<math>", "eval")
        # Whitelist allowed names
        allowed_names = {"__builtins__": {}}
        result = eval(code, allowed_names)

        if isinstance(result, float):
            # Clean up floating point
            if result == int(result):
                result = int(result)
            else:
                result = round(result, 6)

        return True, f"{expression} = {result}"
    except Exception:
        return False, "I couldn't calculate that, sir."


# ═══════════════════════════════════════════════════════════
# Unit Conversions
# ═══════════════════════════════════════════════════════════

_CONVERSIONS = {
    ("km", "miles"): 0.621371,
    ("miles", "km"): 1.60934,
    ("kg", "lbs"): 2.20462,
    ("lbs", "kg"): 0.453592,
    ("celsius", "fahrenheit"): lambda x: x * 9/5 + 32,
    ("fahrenheit", "celsius"): lambda x: (x - 32) * 5/9,
    ("cm", "inches"): 0.393701,
    ("inches", "cm"): 2.54,
    ("meters", "feet"): 3.28084,
    ("feet", "meters"): 0.3048,
    ("liters", "gallons"): 0.264172,
    ("gallons", "liters"): 3.78541,
}


def convert_units(expression: str) -> tuple[bool, str]:
    """Convert between units. E.g., '100 km to miles'."""
    match = re.match(
        r'([\d.]+)\s*(\w+)\s+(?:to|in|into)\s+(\w+)',
        expression.lower().strip()
    )
    if not match:
        return False, "I couldn't parse that conversion, sir."

    value = float(match.group(1))
    from_unit = match.group(2)
    to_unit = match.group(3)

    key = (from_unit, to_unit)
    if key in _CONVERSIONS:
        factor = _CONVERSIONS[key]
        if callable(factor):
            result = factor(value)
        else:
            result = value * factor
        result = round(result, 4)
        return True, f"{value} {from_unit} is {result} {to_unit}, sir."

    return False, f"I don't know how to convert {from_unit} to {to_unit}, sir."


# ═══════════════════════════════════════════════════════════
# Research Mode
# ═══════════════════════════════════════════════════════════

def research_topic(topic: str) -> tuple[bool, str]:
    """
    Open multiple research sources for a topic.
    Opens Google, Wikipedia, and relevant academic sources.
    """
    encoded = urllib.parse.quote(topic)

    urls = [
        f"https://www.google.com/search?q={encoded}",
        f"https://en.wikipedia.org/wiki/Special:Search/{encoded}",
    ]

    for url in urls:
        webbrowser.open(url)

    return True, (
        f"Research mode activated for '{topic}', sir. "
        "I've opened Google and Wikipedia. Shall I dig deeper?"
    )


# ═══════════════════════════════════════════════════════════
# Command Router
# ═══════════════════════════════════════════════════════════

def handle_research_command(cmd: str) -> tuple[bool, bool, str]:
    """
    Route research & knowledge commands.

    Returns: (handled, success, message)
    """
    # Wikipedia
    for prefix in ("wikipedia ", "wiki ", "look up ", "who is ", "who was ",
                   "what is a ", "what is an ", "what is the ", "what is ",
                   "what are ", "tell me about "):
        if cmd.startswith(prefix):
            topic = cmd[len(prefix):].strip()
            if topic:
                ok, msg = wiki_lookup(topic)
                return True, ok, msg

    # Dictionary
    for prefix in ("define ", "definition of ", "what does ", "meaning of "):
        if cmd.startswith(prefix):
            word = cmd[len(prefix):].replace(" mean", "").strip()
            if word:
                ok, msg = define_word(word)
                return True, ok, msg

    # Math
    for prefix in ("calculate ", "compute ", "math ", "solve "):
        if cmd.startswith(prefix):
            expr = cmd[len(prefix):].strip()
            ok, msg = quick_math(expr)
            return True, ok, msg

    if cmd.startswith("what is ") and any(c in cmd for c in "+-*/^%"):
        expr = cmd.replace("what is ", "").strip()
        ok, msg = quick_math(expr)
        if ok:
            return True, ok, msg

    # Conversions
    if " to " in cmd and re.search(r'\d', cmd):
        for prefix in ("convert ", ""):
            if cmd.startswith(prefix):
                expr = cmd[len(prefix):].strip() if prefix else cmd
                ok, msg = convert_units(expr)
                if ok:
                    return True, ok, msg

    # Research mode
    for prefix in ("research ", "deep search for ", "investigate "):
        if cmd.startswith(prefix):
            topic = cmd[len(prefix):].strip()
            ok, msg = research_topic(topic)
            return True, ok, msg

    return False, False, ""
