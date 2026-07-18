"""
core/memory.py — Long-term memory system for J.A.R.V.I.S.

Dual-backend persistent memory with SQLite as primary and JSON for export/import.

Memory categories:
- Facts: "My college is XYZ", "I am 21 years old"
- Preferences: "I prefer dark mode", "My favorite language is Python"
- Aliases: "Call me Boss" → user nickname
- Notes: Free-form saved notes with timestamps
- Projects: Active projects with descriptions
- Goals: Personal/professional goals
- Skills: Programming languages, tools, domains

The SQLite backend provides fast full-text search across all categories.
On first run, existing brain.json data is auto-migrated to SQLite.

Usage:
    from core.memory import get_memory
    mem = get_memory()
    mem.store_fact("college", "MIT")
    answer = mem.recall("Where do I study?")  # → "Your college is MIT"
"""
import json
import os
import re
import sqlite3
import threading
from datetime import datetime
from typing import Optional

from core.logger import get_logger

log = get_logger("core.memory")


class Memory:
    """Persistent long-term memory backed by SQLite + JSON export."""

    def __init__(self, db_path: Optional[str] = None, json_path: Optional[str] = None) -> None:
        if db_path is None:
            from config.config import DATA_DIR
            db_path = os.path.join(DATA_DIR, "jarvis_memory.db")
        if json_path is None:
            from config.config import MEMORY_FILE
            json_path = json_path or MEMORY_FILE

        self._db_path = db_path
        self._json_path = json_path
        self._lock = threading.Lock()

        # Initialize SQLite
        self._init_db()

        # Auto-migrate from JSON if DB is fresh
        if self._is_empty():
            self._migrate_from_json()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        """Create the database schema."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        tags TEXT DEFAULT '',
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS conversation_summaries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        summary TEXT NOT NULL,
                        session_id TEXT DEFAULT '',
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_memory_category ON memory(category);
                    CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(category, key);
                    CREATE INDEX IF NOT EXISTS idx_notes_content ON notes(content);
                    CREATE INDEX IF NOT EXISTS idx_conv_summaries_session ON conversation_summaries(session_id);
                """)
                conn.commit()
                log.info("Memory database initialized: %s", self._db_path)
            finally:
                conn.close()

    def _is_empty(self) -> bool:
        """Check if the database has no data yet."""
        with self._lock:
            conn = self._get_conn()
            try:
                count = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
                return count == 0
            finally:
                conn.close()

    def _migrate_from_json(self) -> None:
        """Migrate existing brain.json data into SQLite."""
        if not os.path.exists(self._json_path):
            return

        try:
            with open(self._json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return

        migrated = 0
        now = datetime.now().isoformat()

        # Migrate facts
        for key, value in data.get("facts", {}).items():
            self._upsert("facts", key, str(value), now)
            migrated += 1

        # Migrate preferences
        for key, value in data.get("preferences", {}).items():
            self._upsert("preferences", key, str(value), now)
            migrated += 1

        # Migrate aliases
        for key, value in data.get("aliases", {}).items():
            self._upsert("aliases", key, str(value), now)
            migrated += 1

        # Migrate user_name
        user_name = data.get("user_name", "sir")
        self._upsert("aliases", "user_name", user_name, now)

        # Migrate notes
        for note in data.get("notes", []):
            content = note.get("content", "") if isinstance(note, dict) else str(note)
            ts = note.get("timestamp", now) if isinstance(note, dict) else now
            self._add_note_direct(content, ts)
            migrated += 1

        # Migrate projects, goals, skills if they exist
        for category in ("projects", "goals", "skills", "programming_languages"):
            items = data.get(category, {})
            if isinstance(items, dict):
                for k, v in items.items():
                    self._upsert(category, k, str(v), now)
                    migrated += 1
            elif isinstance(items, list):
                for item in items:
                    self._upsert(category, str(item), "", now)
                    migrated += 1

        if migrated > 0:
            log.info("Migrated %d entries from brain.json to SQLite", migrated)

    def _upsert(self, category: str, key: str, value: str, timestamp: str = None) -> None:
        """Insert or update a memory entry."""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                existing = conn.execute(
                    "SELECT id FROM memory WHERE category=? AND key=?",
                    (category, key.lower().strip()),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE memory SET value=?, updated_at=? WHERE id=?",
                        (value, timestamp, existing["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO memory (category, key, value, created_at, updated_at) VALUES (?,?,?,?,?)",
                        (category, key.lower().strip(), value, timestamp, timestamp),
                    )
                conn.commit()
            finally:
                conn.close()
        # Emit on event bus
        try:
            from core.event_bus import bus, Events
            bus.emit(Events.MEMORY_UPDATED, category=category, key=key)
        except Exception:
            pass

    def _get(self, category: str, key: str) -> Optional[str]:
        """Get a value from memory."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT value FROM memory WHERE category=? AND key=?",
                    (category, key.lower().strip()),
                ).fetchone()
                return row["value"] if row else None
            finally:
                conn.close()

    def _get_all(self, category: str) -> dict[str, str]:
        """Get all entries in a category."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT key, value FROM memory WHERE category=?", (category,)
                ).fetchall()
                return {r["key"]: r["value"] for r in rows}
            finally:
                conn.close()

    def _add_note_direct(self, content: str, timestamp: str) -> None:
        """Add a note directly (used during migration)."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO notes (content, created_at) VALUES (?,?)",
                    (content, timestamp),
                )
                conn.commit()
            finally:
                conn.close()

    def save(self) -> None:
        """Export memory to JSON (for backup/portability)."""
        self.export_json()

    # ─── Facts ───────────────────────────────────────────

    def store_fact(self, key: str, value: str) -> str:
        """Store a fact about the user."""
        self._upsert("facts", key, value)
        log.info("Stored fact: %s = %s", key, value)
        return f"I'll remember that your {key} is {value}."

    def get_fact(self, key: str) -> Optional[str]:
        """Retrieve a fact by key."""
        return self._get("facts", key)

    def get_all_facts(self) -> dict[str, str]:
        """Get all stored facts."""
        return self._get_all("facts")

    # ─── Preferences ─────────────────────────────────────

    def store_preference(self, key: str, value: str) -> str:
        """Store a user preference."""
        self._upsert("preferences", key, value)
        log.info("Stored preference: %s = %s", key, value)
        return f"Noted. Your {key} preference is {value}."

    def get_preference(self, key: str) -> Optional[str]:
        """Retrieve a preference."""
        return self._get("preferences", key)

    # ─── Aliases ─────────────────────────────────────────

    def set_user_name(self, name: str) -> str:
        """Set the user's preferred name/alias."""
        self._upsert("aliases", "user_name", name)
        log.info("User name set to: %s", name)
        return f"I'll call you {name} from now on."

    def get_user_name(self) -> str:
        """Get the user's preferred name."""
        name = self._get("aliases", "user_name")
        return name if name else "sir"

    def store_alias(self, key: str, value: str) -> str:
        """Store a named alias mapping."""
        self._upsert("aliases", key, value)
        return f"I'll remember that {key} means {value}."

    def get_alias(self, key: str) -> Optional[str]:
        """Retrieve an alias."""
        return self._get("aliases", key)

    # ─── Projects ────────────────────────────────────────

    def store_project(self, name: str, description: str = "") -> str:
        """Store an active project."""
        self._upsert("projects", name, description)
        return f"Project '{name}' saved."

    def get_projects(self) -> dict[str, str]:
        """Get all projects."""
        return self._get_all("projects")

    # ─── Goals ───────────────────────────────────────────

    def store_goal(self, name: str, description: str = "") -> str:
        """Store a personal/professional goal."""
        self._upsert("goals", name, description)
        return f"Goal '{name}' saved."

    def get_goals(self) -> dict[str, str]:
        """Get all goals."""
        return self._get_all("goals")

    # ─── Skills / Programming Languages ──────────────────

    def store_skill(self, name: str, level: str = "") -> str:
        """Store a skill or programming language."""
        self._upsert("skills", name, level)
        return f"Skill '{name}' noted."

    def get_skills(self) -> dict[str, str]:
        """Get all skills."""
        return self._get_all("skills")

    # ─── Notes ───────────────────────────────────────────

    def add_note(self, content: str) -> str:
        """Add a free-form note with timestamp."""
        now = datetime.now().isoformat()
        self._add_note_direct(content, now)
        log.info("Added note: %s", content[:50])
        return f"Note saved: {content}"

    def get_notes(self, limit: int = 10) -> list[dict]:
        """Get the most recent notes."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT content, created_at as timestamp FROM notes ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [{"content": r["content"], "timestamp": r["timestamp"]} for r in reversed(rows)]
            finally:
                conn.close()

    def search_notes(self, query: str) -> list[dict]:
        """Search notes by keyword."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT content, created_at as timestamp FROM notes WHERE content LIKE ?",
                    (f"%{query}%",),
                ).fetchall()
                return [{"content": r["content"], "timestamp": r["timestamp"]} for r in rows]
            finally:
                conn.close()

    def clear_notes(self) -> str:
        """Clear all notes."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM notes")
                conn.commit()
            finally:
                conn.close()
        return "All notes cleared."

    # ─── Full-text Search ────────────────────────────────

    def search(self, query: str) -> list[dict]:
        """
        Search across all memory categories.

        Returns list of dicts with: category, key, value, relevance.
        """
        results = []
        query_lower = query.lower()
        with self._lock:
            conn = self._get_conn()
            try:
                # Search memory table
                rows = conn.execute(
                    "SELECT category, key, value FROM memory WHERE key LIKE ? OR value LIKE ?",
                    (f"%{query_lower}%", f"%{query_lower}%"),
                ).fetchall()
                for r in rows:
                    results.append({
                        "category": r["category"],
                        "key": r["key"],
                        "value": r["value"],
                    })

                # Search notes
                note_rows = conn.execute(
                    "SELECT content FROM notes WHERE content LIKE ?",
                    (f"%{query_lower}%",),
                ).fetchall()
                for r in note_rows:
                    results.append({
                        "category": "notes",
                        "key": "note",
                        "value": r["content"],
                    })
            finally:
                conn.close()

        return results

    # ─── Recall (intelligent query matching) ─────────────

    def recall(self, query: str) -> Optional[str]:
        """
        Try to answer a question from stored memory.

        Matches queries like "Where do I study?" against stored facts,
        preferences, and aliases using keyword matching + SQL search.
        """
        query_lower = query.lower().strip()
        query_words = set(re.findall(r'\w+', query_lower))

        # Direct fact key match
        facts = self.get_all_facts()
        for key, value in facts.items():
            key_words = set(re.findall(r'\w+', key.lower()))
            if key_words & query_words:
                return f"Your {key} is {value}."

        # Keyword search via mapping
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
                value = self.get_fact(fact_key)
                if value:
                    return f"Your {fact_key} is {value}."

        # Search preferences
        prefs = self._get_all("preferences")
        for key, value in prefs.items():
            if key in query_lower:
                return f"Your {key} preference is {value}."

        # Search aliases
        aliases = self._get_all("aliases")
        for key, value in aliases.items():
            if key in query_lower and key != "user_name":
                return f"{key} is {value}."

        # Full-text search
        results = self.search(query)
        if results:
            r = results[0]
            if r["category"] == "notes":
                return f"I found a note: {r['value']}"
            return f"Your {r['key']} is {r['value']}."

        return None

    # ─── Parse "remember" commands ───────────────────────

    def parse_and_store(self, text: str) -> str:
        """Parse natural language 'remember' statements and store appropriately."""
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

        # "remember my project X is Y"
        project_match = re.search(r'remember\s+(?:my\s+)?project\s+(.+?)(?:\s+is\s+(.+))?$', text_lower)
        if project_match:
            name = project_match.group(1).strip()
            desc = project_match.group(2).strip() if project_match.group(2) else ""
            return self.store_project(name, desc)

        # "remember my goal is X"
        goal_match = re.search(r'remember\s+(?:my\s+)?goal\s+(?:is\s+)?(.+)', text_lower)
        if goal_match:
            return self.store_goal(goal_match.group(1).strip())

        # "remember I know X" / "remember I use X"
        skill_match = re.search(r'remember\s+(?:i\s+(?:know|use|code in|work with))\s+(.+)', text_lower)
        if skill_match:
            return self.store_skill(skill_match.group(1).strip())

        # "remember (that) my X is Y" or "remember X is Y"
        remember_match = re.search(
            r'remember\s+(?:that\s+)?(?:my\s+)?(\w+(?:\s+\w+)?)\s+is\s+(.+)',
            text_lower,
        )
        if remember_match:
            key = remember_match.group(1).strip()
            value = remember_match.group(2).strip()
            # Use original case for value
            try:
                idx = text_lower.index(value)
                original_value = text[idx:idx + len(value)]
                if original_value:
                    value = original_value
            except ValueError:
                pass
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

    # ─── Export / Import ─────────────────────────────────

    def export_json(self, filepath: str = None) -> str:
        """Export all memory to a JSON file."""
        if filepath is None:
            filepath = self._json_path

        data = {
            "facts": self.get_all_facts(),
            "preferences": self._get_all("preferences"),
            "aliases": self._get_all("aliases"),
            "projects": self.get_projects(),
            "goals": self.get_goals(),
            "skills": self.get_skills(),
            "notes": self.get_notes(limit=1000),
            "user_name": self.get_user_name(),
            "exported_at": datetime.now().isoformat(),
        }

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        log.info("Memory exported to %s", filepath)
        return f"Memory exported to {filepath}"

    def get_stats(self) -> dict:
        """Get memory statistics."""
        with self._lock:
            conn = self._get_conn()
            try:
                total = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
                notes_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
                conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
                categories = conn.execute(
                    "SELECT category, COUNT(*) as count FROM memory GROUP BY category"
                ).fetchall()
                return {
                    "total_entries": total,
                    "notes": notes_count,
                    "conversations": conv_count,
                    "categories": {r["category"]: r["count"] for r in categories},
                }
            finally:
                conn.close()

    # ─── Conversation History ────────────────────────────

    def log_conversation(self, role: str, content: str) -> None:
        """Log a conversation entry (user or assistant)."""
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO conversations (role, content, timestamp) VALUES (?,?,?)",
                    (role, content, now),
                )
                conn.commit()
            finally:
                conn.close()

    def get_conversations(self, limit: int = 20) -> list[dict]:
        """Get recent conversation entries."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT role, content, timestamp FROM conversations ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [
                    {"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]}
                    for r in reversed(rows)
                ]
            finally:
                conn.close()

    def clear_conversations(self) -> str:
        """Clear conversation history."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM conversations")
                conn.commit()
            finally:
                conn.close()
        return "Conversation history cleared."

    # ─── Conversation Summaries ──────────────────────────

    def save_conversation_summary(self, summary: str, session_id: str = "") -> None:
        """Store a conversation summary for long-term recall."""
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO conversation_summaries (summary, session_id, created_at) VALUES (?,?,?)",
                    (summary, session_id, now),
                )
                conn.commit()
            except sqlite3.OperationalError:
                # Table might not exist yet (schema migration)
                try:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS conversation_summaries (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            summary TEXT NOT NULL,
                            session_id TEXT DEFAULT '',
                            created_at TEXT NOT NULL
                        )
                    """)
                    conn.execute(
                        "INSERT INTO conversation_summaries (summary, session_id, created_at) VALUES (?,?,?)",
                        (summary, session_id, now),
                    )
                    conn.commit()
                except Exception:
                    pass
            finally:
                conn.close()
        log.info("Conversation summary saved (session: %s)", session_id[:8])

    def get_conversation_summaries(self, limit: int = 5) -> list[dict]:
        """Get recent conversation summaries for context injection."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT summary, session_id, created_at FROM conversation_summaries "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [
                    {"summary": r["summary"], "session_id": r["session_id"],
                     "created_at": r["created_at"]}
                    for r in reversed(rows)
                ]
            except sqlite3.OperationalError:
                return []  # Table doesn't exist yet
            finally:
                conn.close()

    def clear_conversation_summaries(self) -> str:
        """Clear all conversation summaries."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM conversation_summaries")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            finally:
                conn.close()
        return "Conversation summaries cleared."

    # ─── App Usage Tracking ──────────────────────────────

    def log_app_usage(self, app_name: str) -> None:
        """Record that an app was opened. Tracks frequency."""
        key = app_name.lower().strip()
        current = self._get("app_usage", key)
        count = int(current) + 1 if current else 1
        self._upsert("app_usage", key, str(count))

    def get_frequent_apps(self, limit: int = 10) -> list[tuple[str, int]]:
        """Get the most frequently opened apps."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT key, CAST(value AS INTEGER) as count FROM memory "
                    "WHERE category='app_usage' ORDER BY count DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [(r["key"], r["count"]) for r in rows]
            finally:
                conn.close()

    # ─── Site Usage Tracking ─────────────────────────────

    def log_site_usage(self, site_name: str) -> None:
        """Record that a website was visited. Tracks frequency."""
        key = site_name.lower().strip()
        current = self._get("site_usage", key)
        count = int(current) + 1 if current else 1
        self._upsert("site_usage", key, str(count))

    def get_frequent_sites(self, limit: int = 10) -> list[tuple[str, int]]:
        """Get the most frequently visited sites."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT key, CAST(value AS INTEGER) as count FROM memory "
                    "WHERE category='site_usage' ORDER BY count DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [(r["key"], r["count"]) for r in rows]
            finally:
                conn.close()

    # ─── Schedule Memory ─────────────────────────────────

    def store_schedule(self, name: str, details: str) -> str:
        """Store a persistent schedule entry."""
        self._upsert("schedules", name, details)
        return f"Schedule '{name}' saved."

    def get_schedules(self) -> dict[str, str]:
        """Get all stored schedules."""
        return self._get_all("schedules")

    def delete_schedule(self, name: str) -> str:
        """Delete a schedule entry."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM memory WHERE category='schedules' AND key=?",
                    (name.lower().strip(),),
                )
                conn.commit()
            finally:
                conn.close()
        return f"Schedule '{name}' removed."



# ─── Module-level singleton ─────────────────────────────
_memory_instance: Optional[Memory] = None


def get_memory() -> Memory:
    """Get the global Memory instance (lazy singleton)."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = Memory()
    return _memory_instance
