"""
core/memory.py — Long-term memory system for J.A.R.V.I.S.

Stores and retrieves persistent user information:
- Facts: "My college is XYZ", "I am 21 years old"
- Preferences: "I prefer dark mode", "My favorite language is Python"
- Aliases: "Call me Boss" → user nickname
- Notes: Free-form saved notes with timestamps

Usage:
    from core.memory import Memory
    mem = Memory()
    mem.store_fact("college", "MIT")
    answer = mem.recall("Where do I study?")  # → "Your college is MIT"
"""
import json
import os
import re
import threading
from datetime import datetime
from typing import Optional

from core.logger import get_logger

log = get_logger("core.memory")


class Memory:
    """Persistent long-term memory backed by a JSON file."""

    def __init__(self, filepath: Optional[str] = None) -> None:
        if filepath is None:
            from config.config import MEMORY_FILE
            filepath = MEMORY_FILE
        self._filepath = filepath
        self._lock = threading.Lock()
        self._data = self._load()

    def _default_data(self) -> dict:
        """Default memory structure."""
        return {
            "facts": {},
            "preferences": {},
            "aliases": {},
            "notes": [],
            "user_name": "sir",
        }

    def _load(self) -> dict:
        """Load memory from disk."""
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = self._default_data()
            self._save_data(data)
            log.info("Created new memory file at %s", self._filepath)
        for key, default in self._default_data().items():
            data.setdefault(key, default)
        return data

    def _save_data(self, data: Optional[dict] = None) -> None:
        """Save memory to disk (thread-safe)."""
        if data is None:
            data = self._data
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
                with open(self._filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception as e:
                log.error("Failed to save memory: %s", e)

    def save(self) -> None:
        """Public save method."""
        self._save_data()

    # ─── Facts ───────────────────────────────────────────

    def store_fact(self, key: str, value: str) -> str:
        """
        Store a fact about the user.

        Args:
            key: Fact category (e.g., "college", "name", "birthday").
            value: The fact value.

        Returns:
            Confirmation message.
        """
        key = key.lower().strip()
        self._data["facts"][key] = value
        self._save_data()
        log.info("Stored fact: %s = %s", key, value)
        return f"I'll remember that your {key} is {value}."

    def get_fact(self, key: str) -> Optional[str]:
        """Retrieve a fact by key."""
        return self._data["facts"].get(key.lower().strip())

    def get_all_facts(self) -> dict[str, str]:
        """Get all stored facts."""
        return dict(self._data["facts"])

    # ─── Preferences ─────────────────────────────────────

    def store_preference(self, key: str, value: str) -> str:
        """Store a user preference."""
        key = key.lower().strip()
        self._data["preferences"][key] = value
        self._save_data()
        log.info("Stored preference: %s = %s", key, value)
        return f"Noted. Your {key} preference is {value}."

    def get_preference(self, key: str) -> Optional[str]:
        """Retrieve a preference."""
        return self._data["preferences"].get(key.lower().strip())

    # ─── Aliases ─────────────────────────────────────────

    def set_user_name(self, name: str) -> str:
        """Set the user's preferred name/alias."""
        self._data["user_name"] = name
        self._save_data()
        log.info("User name set to: %s", name)
        return f"I'll call you {name} from now on."

    def get_user_name(self) -> str:
        """Get the user's preferred name."""
        return self._data.get("user_name", "sir")

    def store_alias(self, key: str, value: str) -> str:
        """Store a named alias mapping."""
        key = key.lower().strip()
        self._data["aliases"][key] = value
        self._save_data()
        return f"I'll remember that {key} means {value}."

    def get_alias(self, key: str) -> Optional[str]:
        """Retrieve an alias."""
        return self._data["aliases"].get(key.lower().strip())

    # ─── Notes ───────────────────────────────────────────

    def add_note(self, content: str) -> str:
        """Add a free-form note with timestamp."""
        note = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        self._data["notes"].append(note)
        self._save_data()
        log.info("Added note: %s", content[:50])
        return f"Note saved: {content}"

    def get_notes(self, limit: int = 10) -> list[dict]:
        """Get the most recent notes."""
        return self._data["notes"][-limit:]

    def search_notes(self, query: str) -> list[dict]:
        """Search notes by keyword."""
        query_lower = query.lower()
        return [n for n in self._data["notes"] if query_lower in n["content"].lower()]

    def clear_notes(self) -> str:
        """Clear all notes."""
        self._data["notes"] = []
        self._save_data()
        return "All notes cleared."

    # ─── Recall (intelligent query matching) ─────────────

    def recall(self, query: str) -> Optional[str]:
        """
        Try to answer a question from stored memory.

        Matches queries like "Where do I study?" against stored facts,
        preferences, and aliases using keyword matching.

        Args:
            query: Natural language question.

        Returns:
            Answer string if found, None otherwise.
        """
        query_lower = query.lower().strip()
        query_words = set(re.findall(r'\w+', query_lower))

        # Direct fact key match
        for key, value in self._data["facts"].items():
            key_words = set(re.findall(r'\w+', key.lower()))
            if key_words & query_words:
                return f"Your {key} is {value}."

        # Keyword search across all facts
        _question_to_fact_map = {
            "name": ["name", "who am i", "my name"],
            "college": ["college", "university", "school", "study", "studying"],
            "age": ["age", "old", "born"],
            "birthday": ["birthday", "born", "birth"],
            "city": ["city", "live", "location", "where", "hometown"],
            "job": ["job", "work", "occupation", "profession"],
            "email": ["email", "mail"],
            "phone": ["phone", "number", "mobile", "call"],
        }

        for fact_key, triggers in _question_to_fact_map.items():
            if any(t in query_lower for t in triggers):
                value = self._data["facts"].get(fact_key)
                if value:
                    return f"Your {fact_key} is {value}."

        # Search preferences
        for key, value in self._data["preferences"].items():
            if key in query_lower:
                return f"Your {key} preference is {value}."

        # Search aliases
        for key, value in self._data["aliases"].items():
            if key in query_lower:
                return f"{key} is {value}."

        # Search notes
        matching_notes = self.search_notes(query)
        if matching_notes:
            latest = matching_notes[-1]
            return f"I found a note: {latest['content']}"

        return None

    # ─── Parse "remember" commands ───────────────────────

    def parse_and_store(self, text: str) -> str:
        """
        Parse natural language "remember" statements and store appropriately.

        Handles patterns like:
        - "remember my college is MIT"
        - "remember that I like Python"
        - "my name is Tony"
        - "call me Boss"
        - "note: buy groceries"

        Args:
            text: The raw text from the user.

        Returns:
            Confirmation message.
        """
        text_lower = text.lower().strip()

        # "call me X" or "my name is X"
        name_match = re.search(r'(?:call me|my name is)\s+(.+)', text_lower)
        if name_match:
            name = name_match.group(1).strip().title()
            return self.set_user_name(name)

        # "note: X" or "note X" or "save note X"
        note_match = re.search(r'(?:note[:\s]+|save note\s+)(.+)', text_lower)
        if note_match:
            return self.add_note(note_match.group(1).strip())

        # "remember (that) my X is Y" or "remember X is Y"
        remember_match = re.search(
            r'remember\s+(?:that\s+)?(?:my\s+)?(\w+(?:\s+\w+)?)\s+is\s+(.+)',
            text_lower
        )
        if remember_match:
            key = remember_match.group(1).strip()
            value = remember_match.group(2).strip()
            # Use original case for value
            original_value = text[text_lower.index(value):text_lower.index(value) + len(value)]
            if original_value:
                value = original_value
            return self.store_fact(key, value)

        # "remember X" (store as a note)
        simple_match = re.search(r'remember\s+(.+)', text_lower)
        if simple_match:
            return self.add_note(simple_match.group(1).strip())

        # "I like X" or "I prefer X"
        pref_match = re.search(r'i (?:like|prefer|love)\s+(.+)', text_lower)
        if pref_match:
            value = pref_match.group(1).strip()
            return self.store_preference("likes", value)

        return self.add_note(text)


# ─── Module-level singleton ─────────────────────────────
_memory_instance: Optional[Memory] = None


def get_memory() -> Memory:
    """Get the global Memory instance (lazy singleton)."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = Memory()
    return _memory_instance
