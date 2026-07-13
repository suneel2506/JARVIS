"""
core/intent.py — Natural language intent recognition for J.A.R.V.I.S.

Transforms rigid command matching into flexible intent understanding.
Instead of requiring exact "open chrome", understands:
- "Could you launch Chrome?"
- "I need my browser"
- "Start Chrome please"
- "Open the web browser for me"

Uses keyword scoring + synonym expansion — no ML required.
Falls through to AI classification for truly ambiguous commands.
"""
import re
from typing import Optional

from core.logger import get_logger

log = get_logger("core.intent")


# ═══════════════════════════════════════════════════════════
# Synonym Database
# ═══════════════════════════════════════════════════════════

# Action synonyms: different ways to say the same action
ACTION_SYNONYMS: dict[str, list[str]] = {
    "open": ["open", "launch", "start", "run", "fire up", "pull up",
             "bring up", "load", "boot", "get me", "i need", "show me",
             "can you open", "could you open", "please open", "turn on"],
    "close": ["close", "quit", "exit", "kill", "stop", "shut down",
              "terminate", "end", "shut", "turn off"],
    "search": ["search", "google", "look up", "find", "search for",
               "look for", "query", "research"],
    "play": ["play", "start playing", "put on", "listen to", "queue"],
    "pause": ["pause", "stop playing", "hold", "freeze"],
    "next": ["next", "skip", "next track", "next song"],
    "previous": ["previous", "back", "last track", "go back"],
    "volume_up": ["volume up", "louder", "turn up", "increase volume", "raise volume"],
    "volume_down": ["volume down", "quieter", "turn down", "decrease volume",
                    "lower volume", "lower the volume"],
    "mute": ["mute", "silence", "shut up", "be quiet"],
    "screenshot": ["screenshot", "screen capture", "capture screen",
                   "take a screenshot", "snap the screen", "screen grab"],
    "minimize": ["minimize", "hide", "put away", "minimize all", "clear the screen"],
    "maximize": ["maximize", "full screen", "make it bigger", "enlarge"],
    "switch": ["switch to", "go to", "jump to", "alt tab", "bring to front",
               "focus on", "activate", "show"],
    "find_file": ["find the", "locate", "where is", "show me the file",
                  "find my", "search my files", "look for the file"],
    "delete": ["delete", "remove", "trash", "get rid of", "erase"],
    "create": ["create", "make", "new", "set up", "create a"],
    "rename": ["rename", "name it", "call it", "change name"],
    "copy": ["copy", "duplicate", "make a copy"],
    "move": ["move", "transfer", "relocate", "put in"],
    "weather": ["weather", "temperature", "forecast", "how cold",
                "how hot", "is it raining", "will it rain"],
    "time": ["what time", "current time", "the time", "tell me the time"],
    "date": ["what date", "today's date", "what day", "the date"],
    "battery": ["battery", "power level", "charge", "how much battery",
                "battery status", "power status"],
    "system": ["system info", "system status", "diagnostics", "health check",
               "how's my computer", "system health"],
    "remember": ["remember", "keep in mind", "note that", "save this",
                 "don't forget", "make a note"],
    "recall": ["recall", "what do you know about", "do you remember",
               "what did i say about", "what's my"],
}

# Target synonyms: different names for the same thing
TARGET_SYNONYMS: dict[str, list[str]] = {
    "chrome": ["chrome", "google chrome", "browser", "web browser",
               "internet", "the browser", "my browser"],
    "firefox": ["firefox", "mozilla"],
    "edge": ["edge", "microsoft edge"],
    "brave": ["brave", "brave browser"],
    "vscode": ["vs code", "vscode", "visual studio code", "code editor",
               "my editor", "the editor"],
    "terminal": ["terminal", "command line", "command prompt", "cmd",
                 "powershell", "shell", "console", "windows terminal"],
    "file explorer": ["file explorer", "explorer", "files", "my files",
                      "file manager", "windows explorer"],
    "task manager": ["task manager", "processes", "running processes",
                     "running apps", "what's running"],
    "settings": ["settings", "system settings", "windows settings",
                 "control panel", "preferences"],
    "calculator": ["calculator", "calc", "the calculator"],
    "notepad": ["notepad", "text editor", "notepad++"],
    "spotify": ["spotify", "music", "music player", "my music"],
    "discord": ["discord"],
    "telegram": ["telegram"],
    "word": ["word", "microsoft word", "document editor"],
    "excel": ["excel", "spreadsheet", "microsoft excel"],
    "powerpoint": ["powerpoint", "presentation", "slides", "microsoft powerpoint"],
    "outlook": ["outlook", "email", "mail", "my email", "inbox"],
    "calendar": ["calendar", "my calendar", "schedule", "my schedule"],
    "camera": ["camera", "webcam"],
    "photos": ["photos", "gallery", "my photos", "pictures"],
    "youtube": ["youtube", "videos"],
    "github": ["github", "git", "my repositories", "repos"],
    "wikipedia": ["wikipedia", "wiki"],
    "google": ["google"],
    "stackoverflow": ["stackoverflow", "stack overflow"],
}

# Filler words to strip before intent matching
FILLER_WORDS = {
    "please", "can", "you", "could", "would", "kindly", "just",
    "maybe", "actually", "basically", "the", "a", "an", "my",
    "me", "i", "need", "want", "like", "to", "for", "it",
    "this", "that", "some", "of", "do", "go", "and", "is",
    "be", "get", "hey", "jarvis", "sir",
}


# ═══════════════════════════════════════════════════════════
# Intent Classification
# ═══════════════════════════════════════════════════════════

class Intent:
    """Represents a classified user intent."""

    def __init__(self, action: str, target: str, raw: str,
                 confidence: float = 0.0, params: Optional[dict] = None):
        self.action = action
        self.target = target
        self.raw = raw
        self.confidence = confidence
        self.params = params or {}

    def __repr__(self):
        return f"Intent(action='{self.action}', target='{self.target}', conf={self.confidence:.2f})"

    def to_command(self) -> str:
        """Convert intent back to a normalized command string."""
        if self.action == "open" and self.target:
            return f"open {self.target}"
        if self.action == "close" and self.target:
            return f"close {self.target}"
        if self.action == "search" and self.params.get("query"):
            return f"search {self.params['query']}"
        if self.action == "switch" and self.target:
            return f"switch to {self.target}"
        if self.action in ("play", "pause", "next", "previous", "mute"):
            return self.action
        if self.action in ("volume_up", "volume_down"):
            return self.action.replace("_", " ")
        if self.action == "screenshot":
            return "take screenshot"
        if self.action == "weather":
            return "weather"
        if self.action == "time":
            return "what time is it"
        if self.action == "date":
            return "what's the date"
        if self.action == "battery":
            return "battery status"
        if self.action == "system":
            return "system status"
        if self.action == "remember" and self.params.get("content"):
            return f"remember {self.params['content']}"
        if self.action == "recall" and self.params.get("query"):
            return f"recall {self.params['query']}"
        if self.action == "find_file" and self.params.get("query"):
            return f"find file {self.params['query']}"
        # Default: pass through raw command
        return self.raw


def _clean_input(text: str) -> list[str]:
    """Remove filler words and return meaningful tokens."""
    words = re.sub(r'[^\w\s]', '', text.lower()).split()
    return [w for w in words if w not in FILLER_WORDS]


def _score_match(tokens: list[str], candidates: list[str]) -> float:
    """Score how well tokens match candidate phrases."""
    text = " ".join(tokens)
    best_score = 0.0

    for candidate in candidates:
        cand_words = candidate.lower().split()
        # Exact substring match
        if candidate.lower() in text:
            score = len(cand_words) / max(len(tokens), 1)
            score = min(score * 1.5, 1.0)  # Boost exact matches
            best_score = max(best_score, score)
            continue

        # Word overlap
        overlap = sum(1 for w in cand_words if w in tokens)
        if overlap > 0:
            score = overlap / len(cand_words)
            best_score = max(best_score, score * 0.8)

    return best_score


def classify(text: str) -> Optional[Intent]:
    """
    Classify a natural language command into an Intent.

    Uses keyword scoring + synonym expansion to understand flexible phrasing.

    Returns:
        Intent object if classified with reasonable confidence, else None.
    """
    if not text or len(text.strip()) < 2:
        return None

    raw = text.lower().strip()
    tokens = _clean_input(raw)
    full_text = " ".join(tokens) if tokens else raw

    if not tokens:
        return None

    # Score each action
    best_action = None
    best_action_score = 0.0

    for action, synonyms in ACTION_SYNONYMS.items():
        score = _score_match(raw.split(), synonyms)
        if score > best_action_score:
            best_action_score = score
            best_action = action

    # Score each target
    best_target = None
    best_target_score = 0.0

    for target, synonyms in TARGET_SYNONYMS.items():
        score = _score_match(raw.split(), synonyms)
        if score > best_target_score:
            best_target_score = score
            best_target = target

    # Combined confidence
    if best_action and best_action_score > 0.3:
        confidence = (best_action_score + best_target_score) / 2 if best_target else best_action_score * 0.6

        # Extract parameters
        params = {}

        # Search queries
        if best_action == "search":
            for prefix in ("search for ", "search ", "google ", "look up ", "find "):
                if raw.startswith(prefix):
                    params["query"] = raw[len(prefix):].strip()
                    break

        # Remember content
        if best_action == "remember":
            for prefix in ("remember that ", "remember ", "note that ", "save this "):
                if raw.startswith(prefix):
                    params["content"] = raw[len(prefix):].strip()
                    break

        # Recall query
        if best_action == "recall":
            for prefix in ("what do you know about ", "do you remember ", "recall "):
                if raw.startswith(prefix):
                    params["query"] = raw[len(prefix):].strip()
                    break

        # File queries
        if best_action == "find_file":
            params["query"] = raw

        intent = Intent(
            action=best_action,
            target=best_target or "",
            raw=raw,
            confidence=confidence,
            params=params,
        )

        if confidence >= 0.4:
            log.info("Intent classified: %s (target: %s, conf: %.2f)",
                     best_action, best_target, confidence)
            return intent

    return None


def normalize_command(text: str) -> str:
    """
    Try to normalize a natural language command into a standard command.

    If intent classification succeeds, returns the normalized command string.
    Otherwise returns the original text unchanged.
    """
    intent = classify(text)
    if intent and intent.confidence >= 0.4:
        normalized = intent.to_command()
        if normalized != text.lower().strip():
            log.info("Normalized: '%s' → '%s'", text, normalized)
        return normalized
    return text.lower().strip()
