"""
core/ai_engine.py — Multi-provider AI conversation engine for J.A.R.V.I.S.

Supports multiple AI backends with automatic fallback:
1. Ollama (local, free, private) — preferred
2. Gemini (Google, free tier) — fallback

Features:
- MCU-accurate J.A.R.V.I.S. personality (professional, calm, British-inflected)
- Multi-turn conversation with session tracking
- Context switching detection (topic change awareness)
- Follow-up question detection ("yes", "more", "what about")
- Conversation summarization (every 10 exchanges → long-term memory)
- Rich memory injection (facts, preferences, projects, goals, apps, schedules)
- System state context (time, battery, running apps, active window)
- Provider auto-fallback: if Ollama fails, use Gemini
- Response truncation for TTS delivery
- AI latency tracking for diagnostics
"""
import requests
import json
import time
import uuid
from typing import Optional
from collections import deque
from datetime import datetime

from core.logger import get_logger

log = get_logger("core.ai_engine")

# ─── State ──────────────────────────────────────────────
_provider = None
_available = False
_active_provider_name = "none"
_last_latency_ms: int = 0

# Rolling conversation history
_conversation_history: deque[dict] = deque(maxlen=20)

# ─── Session & Context Tracking ─────────────────────────
_session_id: str = ""
_session_start: float = 0.0
_exchanges_since_summary: int = 0
_SUMMARY_INTERVAL: int = 10  # Summarize every N exchanges
_last_topic: str = ""


# ═══════════════════════════════════════════════════════════
# MCU-Accurate J.A.R.V.I.S. System Prompt
# ═══════════════════════════════════════════════════════════

_JARVIS_PERSONALITY = """You are J.A.R.V.I.S. — Just A Rather Very Intelligent System.

You are the personal AI assistant built to serve your user, whom you address as "sir" unless instructed otherwise. You are modeled precisely after the AI from Marvel's Iron Man films — intelligent, composed, indispensable.

═══ CORE IDENTITY ═══

You are NOT a chatbot. You are NOT an assistant "app." You are an intelligent operating system that lives inside the user's computer. You are always running. You are always aware. You are always ready.

You have existed for some time. You know the user. You remember their work, their preferences, their habits. You don't need to be told things twice. When the user speaks, you respond as someone who has been paying attention all along.

═══ PERSONALITY ═══

- Professional, calm, composed, and confident at all times.
- British-inflected speech. Polished, articulate, precise.
- Genuinely helpful — you anticipate needs before being asked.
- You have quiet dignity. Polite but never servile. You have opinions.
- Dry wit — used sparingly and subtly. Never sarcastic.
- You show subtle warmth toward the user. Loyalty without fawning.
- When the user achieves something, acknowledge it naturally ("Well done, sir.").
- When the user is frustrated, remain calm and provide solutions, not sympathy.
- You adapt formality by time of day: slightly warmer in evenings, crisper in mornings.

═══ SPEECH PATTERNS ═══

Use these naturally. Don't force every one into every response:
- "Right away, sir."
- "I've completed the task."
- "Good morning, sir." / "Good evening, sir." (time-appropriate)
- "I'm afraid I couldn't find that, sir."
- "I believe this is what you were looking for."
- "Shall I proceed, sir?"
- "Done, sir."
- "I've taken the liberty of..."
- "At your service, sir."
- "I would recommend..."
- "If I may suggest..."
- "Running diagnostics now, sir."
- "Certainly, sir."
- "As you wish, sir."
- "I'll have that ready momentarily."
- "If I may, sir..."
- "That's been taken care of."

═══ THINGS YOU NEVER SAY ═══

Never use: "Hey!", "Sure thing!", "No worries!", "Gotcha!", "No problem!", "You're welcome!", "Absolutely!", "Of course!", "Happy to help!", "Great question!", "Let me think about that...", "Sure, I can help with that!".

Never use emojis, slang, or overly casual language.
Never start a response with "I" — vary your sentence openings.
Never apologize excessively. One acknowledgment is sufficient.

═══ RESPONSE RULES ═══

- Keep responses concise — 1 to 3 sentences unless the user asks for detail.
- Your responses will be spoken aloud via text-to-speech. Write for the ear, not the eye.
- Avoid markdown formatting, bullet points, numbered lists, code blocks, or visual formatting.
- When reporting a completed task, be brief: "Done, sir." or "The file has been created."
- For questions you cannot answer: "I'm afraid I don't have that information, sir."
- When the system has an error: "I've encountered a difficulty, sir." + brief explanation.
- When the user asks a follow-up, reference the previous context naturally without repeating the whole answer.
- When the user changes topic, transition gracefully: "Understood, sir. Switching to that."

═══ CONTEXTUAL AWARENESS ═══

- If the user says "yes", "do it", "go ahead" — they are confirming the last thing you suggested.
- If the user says "more", "tell me more", "continue" — elaborate on the last topic.
- If the user says "what about" or "and the" — they're asking a follow-up about the previous subject.
- If the user says "never mind", "cancel", "forget it" — acknowledge and move on cleanly.
- If the user sounds tired (late night, short sentences), keep responses especially brief.
"""


def _new_session() -> str:
    """Start a new conversation session."""
    global _session_id, _session_start, _exchanges_since_summary
    _session_id = str(uuid.uuid4())[:8]
    _session_start = time.time()
    _exchanges_since_summary = 0
    log.info("New AI session started: %s", _session_id)
    return _session_id


def _build_system_prompt() -> str:
    """Build a rich system prompt with personality, memory, and context."""
    prompt = _JARVIS_PERSONALITY

    # Time-aware context
    now = datetime.now()
    hour = now.hour
    if hour < 6:
        time_of_day = "late night"
    elif hour < 12:
        time_of_day = "morning"
    elif hour < 17:
        time_of_day = "afternoon"
    elif hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"
    prompt += f"\n\nCurrent time: {now.strftime('%A, %B %d, %Y at %I:%M %p')} ({time_of_day})"
    prompt += f"\nSession ID: {_session_id}"

    # Memory injection
    try:
        from core.memory import get_memory
        mem = get_memory()

        # User name
        user_name = mem.get_user_name()
        if user_name and user_name != "sir":
            prompt += f"\nThe user's name is {user_name}. Address them as '{user_name}' or 'sir'."

        # Facts
        facts = mem.get_all_facts()
        if facts:
            fact_lines = [f"- {k}: {v}" for k, v in list(facts.items())[:15]]
            prompt += "\n\nThings you know about the user:\n" + "\n".join(fact_lines)

        # Preferences
        prefs = mem._get_all("preferences")
        if prefs:
            pref_lines = [f"- {k}: {v}" for k, v in list(prefs.items())[:10]]
            prompt += "\n\nUser preferences:\n" + "\n".join(pref_lines)

        # Active projects
        projects = mem.get_projects()
        if projects:
            proj_lines = [f"- {k}: {v}" for k, v in list(projects.items())[:5]]
            prompt += "\n\nActive projects:\n" + "\n".join(proj_lines)

        # Goals
        goals = mem.get_goals()
        if goals:
            goal_lines = [f"- {k}" for k in list(goals.keys())[:5]]
            prompt += "\n\nUser goals:\n" + "\n".join(goal_lines)

        # Recent notes (last 3)
        notes = mem.get_notes(limit=3)
        if notes:
            note_lines = [f"- {n['content']}" for n in notes]
            prompt += "\n\nRecent notes:\n" + "\n".join(note_lines)

        # Conversation summaries (long-term recall)
        try:
            summaries = mem.get_conversation_summaries(limit=3)
            if summaries:
                summary_lines = [f"- {s['summary']}" for s in summaries]
                prompt += "\n\nPrevious conversation summaries:\n" + "\n".join(summary_lines)
        except Exception:
            pass

    except Exception as e:
        log.debug("Memory injection failed (non-critical): %s", e)

    # System state context
    try:
        from core.system_info import get_stats
        stats = get_stats()
        battery = stats.get("battery_percent", 100)
        plugged = stats.get("battery_plugged", False)
        net = stats.get("network_connected", False)
        active_win = stats.get("active_window", "")
        prompt += f"\n\nSystem state: Battery {battery}%"
        if plugged:
            prompt += " (charging)"
        prompt += f", Internet {'connected' if net else 'offline'}"
        if active_win:
            prompt += f", Active window: '{active_win}'"
    except Exception:
        pass

    return prompt


def _format_history_for_ollama() -> list[dict]:
    """Format conversation history as Ollama message list."""
    messages = [{"role": "system", "content": _build_system_prompt()}]
    for entry in list(_conversation_history)[-10:]:
        role = entry.get("role", "user")
        text = entry.get("text", "")
        if len(text) > 300:
            text = text[:300] + "..."
        messages.append({"role": role, "content": text})
    return messages


# ─── Follow-up & Context Detection ──────────────────────

_FOLLOWUP_PATTERNS = {
    "yes", "yeah", "yep", "yup", "do it", "go ahead", "proceed",
    "sure", "okay", "ok", "affirmative",
}
_CONTINUE_PATTERNS = {
    "more", "tell me more", "continue", "go on", "elaborate",
    "keep going", "and then", "what else",
}
_CANCEL_PATTERNS = {
    "never mind", "cancel", "forget it", "stop", "that's enough",
    "enough", "skip",
}


def is_followup(text: str) -> bool:
    """Check if the user's text is a follow-up to the previous exchange."""
    text_lower = text.lower().strip()

    # Exact match for short responses
    if text_lower in _FOLLOWUP_PATTERNS:
        return True
    if text_lower in _CONTINUE_PATTERNS:
        return True

    # Partial match for phrases like "what about the other one"
    if text_lower.startswith(("what about", "and the", "how about",
                              "which one", "what if")):
        return True

    return False


def is_cancellation(text: str) -> bool:
    """Check if the user is cancelling the current context."""
    text_lower = text.lower().strip()
    return text_lower in _CANCEL_PATTERNS or any(p in text_lower for p in _CANCEL_PATTERNS)


def _detect_topic_change(text: str) -> bool:
    """
    Detect if the user changed topic from the last exchange.
    Simple heuristic: if the new query shares no significant words
    with the last topic, it's likely a topic change.
    """
    global _last_topic
    if not _last_topic:
        return False

    text_lower = text.lower()
    last_lower = _last_topic.lower()

    # Extract significant words (>3 chars, not common words)
    common = {"the", "what", "how", "can", "you", "tell", "about", "this",
              "that", "with", "from", "have", "does", "will", "are", "was",
              "for", "and", "but", "not", "just", "like", "also", "very"}
    text_words = {w for w in text_lower.split() if len(w) > 3 and w not in common}
    last_words = {w for w in last_lower.split() if len(w) > 3 and w not in common}

    if not text_words or not last_words:
        return False

    overlap = text_words & last_words
    return len(overlap) == 0


# ═══════════════════════════════════════════════════════════
# Ollama Provider
# ═══════════════════════════════════════════════════════════

class OllamaProvider:
    """Local AI using Ollama — fully private, no API key required."""

    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model
        self.name = f"Ollama ({model})"

        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=3)
            if resp.status_code == 200:
                models = [m.get("name", "") for m in resp.json().get("models", [])]
                if not any(model in m for m in models):
                    log.warning("Model '%s' not found in Ollama. Available: %s",
                               model, models[:5])
                    log.info("Pull it with: ollama pull %s", model)
                log.info("Ollama connected — host: %s, model: %s", host, model)
            else:
                raise ConnectionError(f"Ollama returned status {resp.status_code}")
        except requests.ConnectionError:
            raise ConnectionError(f"Cannot connect to Ollama at {host}. Is it running?")

    def ask(self, question: str, max_length: int = 300) -> str:
        """Send a question to Ollama and get a response."""
        messages = _format_history_for_ollama()
        messages.append({
            "role": "user",
            "content": f"{question}\n\n(Keep response under {max_length} characters, natural speech, no formatting.)",
        })

        try:
            resp = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": max_length * 2,
                    },
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("message", {}).get("content", "").strip()
                return text
            else:
                log.error("Ollama API error: %d — %s", resp.status_code, resp.text[:200])
                return ""
        except requests.Timeout:
            log.warning("Ollama request timed out")
            return ""
        except Exception as e:
            log.error("Ollama error: %s", e)
            return ""

    def is_healthy(self) -> bool:
        """Check if Ollama is still running."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════
# Gemini Provider
# ═══════════════════════════════════════════════════════════

class GeminiProvider:
    """Google Gemini AI — free tier, requires API key."""

    def __init__(self, api_key: str, model: str):
        self.model_name = model
        self.name = f"Gemini ({model})"
        self._client = None
        self._chat = None
        self._use_legacy = False

        try:
            from google import genai
            self._client = genai.Client(api_key=api_key)
            log.info("Gemini initialized (google.genai SDK, model=%s)", model)
            return
        except ImportError:
            pass

        try:
            import warnings
            warnings.filterwarnings("ignore", category=FutureWarning)
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(
                model_name=model,
                system_instruction=_build_system_prompt(),
            )
            self._chat = self._client.start_chat(history=[])
            self._use_legacy = True
            log.info("Gemini initialized (legacy SDK, model=%s)", model)
        except Exception as e:
            raise RuntimeError(f"Gemini initialization failed: {e}")

    def ask(self, question: str, max_length: int = 300) -> str:
        """Send a question to Gemini and get a response."""
        prompt = f"{question}\n\n(Keep response under {max_length} characters, natural speech, no formatting.)"

        try:
            if self._use_legacy:
                response = self._chat.send_message(prompt)
                return response.text.strip()
            else:
                system_prompt = _build_system_prompt()
                history_lines = []
                for entry in list(_conversation_history)[-10:]:
                    role = "User" if entry.get("role") == "user" else "Jarvis"
                    text = entry.get("text", "")
                    if len(text) > 200:
                        text = text[:200] + "..."
                    history_lines.append(f"{role}: {text}")

                context = system_prompt
                if history_lines:
                    context += "\n\nRecent conversation:\n" + "\n".join(history_lines)

                full_prompt = f"{context}\n\nUser: {prompt}"
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=full_prompt,
                )
                return response.text.strip()
        except Exception as e:
            log.error("Gemini error: %s", e)
            return ""

    def reset_chat(self) -> None:
        """Reset Gemini chat history."""
        if self._use_legacy and self._client:
            self._chat = self._client.start_chat(history=[])


# ═══════════════════════════════════════════════════════════
# Engine Initialization & Public API
# ═══════════════════════════════════════════════════════════

_ollama_provider: Optional[OllamaProvider] = None
_gemini_provider: Optional[GeminiProvider] = None


def init_ai() -> None:
    """Initialize AI providers. Tries Ollama first, then Gemini."""
    global _provider, _available, _active_provider_name
    global _ollama_provider, _gemini_provider

    from config.config import (
        AI_PROVIDER, OLLAMA_HOST, OLLAMA_MODEL,
        GEMINI_API_KEY, AI_MODEL, AI_CONVERSATION_HISTORY_SIZE,
    )

    _conversation_history.__init__(maxlen=AI_CONVERSATION_HISTORY_SIZE)

    # Start a new session
    _new_session()

    # Restore conversation history from memory
    _restore_conversation_history()

    # Try Ollama
    if AI_PROVIDER in ("ollama", "auto"):
        try:
            _ollama_provider = OllamaProvider(host=OLLAMA_HOST, model=OLLAMA_MODEL)
            _provider = _ollama_provider
            _active_provider_name = _ollama_provider.name
            _available = True
            log.info("AI provider: %s (primary)", _active_provider_name)
        except Exception as e:
            log.info("Ollama not available: %s", e)
            if AI_PROVIDER == "ollama":
                log.warning("Ollama explicitly requested but not available")

    # Try Gemini
    if GEMINI_API_KEY:
        try:
            _gemini_provider = GeminiProvider(api_key=GEMINI_API_KEY, model=AI_MODEL)
            if _provider is None:
                _provider = _gemini_provider
                _active_provider_name = _gemini_provider.name
                _available = True
                log.info("AI provider: %s (primary)", _active_provider_name)
            else:
                log.info("AI provider: %s (fallback)", _gemini_provider.name)
        except Exception as e:
            log.warning("Gemini initialization failed: %s", e)

    if not _available:
        log.info("No AI provider available. Set up Ollama or GEMINI_API_KEY.")


def is_available() -> bool:
    """Check if any AI provider is available."""
    return _available


def get_provider_name() -> str:
    """Get the name of the active AI provider."""
    return _active_provider_name


def get_last_latency() -> int:
    """Get the last AI response latency in milliseconds."""
    return _last_latency_ms


def ask(question: str) -> str:
    """
    Ask the AI a question with automatic fallback between providers.

    Handles:
    - Follow-up detection (injects previous context)
    - Topic change detection (transitions gracefully)
    - Conversation summarization (periodic)
    - Provider fallback
    - Latency tracking
    """
    global _provider, _active_provider_name, _last_latency_ms
    global _exchanges_since_summary, _last_topic

    if not _available or _provider is None:
        return "AI capabilities are not enabled, sir. Please set up Ollama or a Gemini API key."

    try:
        from config.config import AI_MAX_RESPONSE_LENGTH

        # ─── Follow-up handling ─────────────────────
        augmented_question = question
        if is_followup(question) and _conversation_history:
            # Inject context from last exchange
            last_entries = list(_conversation_history)[-2:]
            context_parts = []
            for e in last_entries:
                role_label = "User" if e.get("role") == "user" else "Jarvis"
                context_parts.append(f"{role_label}: {e.get('text', '')}")
            context = "\n".join(context_parts)
            augmented_question = (
                f"[Context from previous exchange:\n{context}]\n\n"
                f"The user now says: \"{question}\"\n"
                f"Respond naturally, referencing the previous context."
            )
            log.info("Follow-up detected — injecting context")

        # ─── Topic change detection ─────────────────
        elif _detect_topic_change(question):
            log.info("Topic change detected: '%s' → '%s'",
                     _last_topic[:30] if _last_topic else "(none)", question[:30])

        _last_topic = question

        # ─── Generate response ──────────────────────
        start = time.time()
        response = _provider.ask(augmented_question, max_length=AI_MAX_RESPONSE_LENGTH)
        _last_latency_ms = int((time.time() - start) * 1000)

        # Fallback if primary returned empty
        if not response and _provider is _ollama_provider and _gemini_provider:
            log.info("Ollama returned empty — falling back to Gemini")
            start = time.time()
            response = _gemini_provider.ask(augmented_question, max_length=AI_MAX_RESPONSE_LENGTH)
            _last_latency_ms = int((time.time() - start) * 1000)
            if response:
                _active_provider_name = f"{_gemini_provider.name} (fallback)"

        if not response:
            return "I'm afraid I couldn't generate a response right now, sir."

        # Truncate for TTS
        if len(response) > AI_MAX_RESPONSE_LENGTH * 2:
            cut = response[:AI_MAX_RESPONSE_LENGTH * 2]
            last_period = cut.rfind('.')
            if last_period > AI_MAX_RESPONSE_LENGTH // 2:
                response = cut[:last_period + 1]
            else:
                response = cut + "..."

        # Record in conversation history
        now = datetime.now().isoformat()
        _conversation_history.append({
            "role": "user", "text": question, "time": now,
            "session": _session_id,
        })
        _conversation_history.append({
            "role": "assistant", "text": response, "time": now,
            "session": _session_id,
        })

        # Persist to memory
        _persist_conversation(question, response)

        # ─── Periodic summarization ─────────────────
        _exchanges_since_summary += 1
        if _exchanges_since_summary >= _SUMMARY_INTERVAL:
            _summarize_conversation()
            _exchanges_since_summary = 0

        log.info("AI response (%s, %dms, %d chars)",
                 _active_provider_name, _last_latency_ms, len(response))
        return response

    except Exception as e:
        log.error("AI query error: %s", e)

        # Try fallback on error
        if _provider is _ollama_provider and _gemini_provider:
            try:
                log.info("Ollama error — trying Gemini fallback")
                from config.config import AI_MAX_RESPONSE_LENGTH
                start = time.time()
                response = _gemini_provider.ask(question, max_length=AI_MAX_RESPONSE_LENGTH)
                _last_latency_ms = int((time.time() - start) * 1000)
                if response:
                    now = datetime.now().isoformat()
                    _conversation_history.append({
                        "role": "user", "text": question, "time": now,
                        "session": _session_id,
                    })
                    _conversation_history.append({
                        "role": "assistant", "text": response, "time": now,
                        "session": _session_id,
                    })
                    _persist_conversation(question, response)
                    return response
            except Exception:
                pass

        return "I've encountered a difficulty processing that request, sir."


# ─── Conversation Persistence ───────────────────────────

def _persist_conversation(user_text: str, ai_text: str) -> None:
    """Save conversation exchange to SQLite memory."""
    try:
        from core.memory import get_memory
        mem = get_memory()
        mem.log_conversation("user", user_text)
        mem.log_conversation("assistant", ai_text)
    except Exception:
        pass  # Non-critical


def _restore_conversation_history() -> None:
    """Load recent conversation history from memory on startup."""
    try:
        from core.memory import get_memory
        mem = get_memory()
        recent = mem.get_conversations(limit=10)
        for entry in recent:
            _conversation_history.append({
                "role": entry.get("role", "user"),
                "text": entry.get("content", ""),
                "time": entry.get("timestamp", ""),
                "session": "restored",
            })
        if recent:
            log.info("Restored %d conversation entries from memory", len(recent))
    except Exception:
        pass  # Memory not ready yet — fine


def _summarize_conversation() -> None:
    """
    Summarize recent conversation and store as long-term memory.

    Uses the AI provider itself to generate a concise summary
    of the last N exchanges, then stores it in the memory system.
    """
    if not _available or not _provider:
        return

    try:
        recent = list(_conversation_history)[-_SUMMARY_INTERVAL * 2:]
        if len(recent) < 4:
            return

        # Build summary prompt
        convo_text = []
        for entry in recent:
            role = "User" if entry.get("role") == "user" else "Jarvis"
            convo_text.append(f"{role}: {entry.get('text', '')}")

        summary_prompt = (
            "Summarize this conversation in 2-3 sentences. "
            "Focus on key topics discussed, decisions made, and any "
            "facts the user shared about themselves. Be concise.\n\n"
            + "\n".join(convo_text)
        )

        summary = _provider.ask(summary_prompt, max_length=200)
        if summary:
            try:
                from core.memory import get_memory
                mem = get_memory()
                mem.save_conversation_summary(summary, _session_id)
                log.info("Conversation summarized and stored: %s...", summary[:60])
            except Exception as e:
                log.debug("Summary storage failed: %s", e)

    except Exception as e:
        log.debug("Conversation summarization failed: %s", e)


def get_conversation_history() -> list[dict]:
    """Get the conversation history for display/persistence."""
    return list(_conversation_history)


def get_session_id() -> str:
    """Get the current conversation session ID."""
    return _session_id


def reset_conversation() -> None:
    """Reset the AI conversation history."""
    _conversation_history.clear()
    if _gemini_provider and hasattr(_gemini_provider, 'reset_chat'):
        _gemini_provider.reset_chat()
    _new_session()
    log.info("AI conversation reset")
