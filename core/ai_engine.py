"""
core/ai_engine.py — Multi-provider AI conversation engine for J.A.R.V.I.S.

Supports multiple AI backends with automatic fallback:
1. Ollama (local, free, private) — preferred
2. Gemini (Google, free tier) — fallback

Features:
- Movie-accurate J.A.R.V.I.S. personality (professional, calm, British-inflected)
- Rolling conversation history with cross-session persistence
- Rich memory injection (facts, preferences, projects, goals, apps, schedules)
- System state context (time, battery, running apps, weather)
- Provider auto-fallback: if Ollama fails, use Gemini
- Response truncation for TTS delivery
- AI latency tracking for diagnostics
"""
import requests
import json
import time
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


# ═══════════════════════════════════════════════════════════
# Movie-Accurate J.A.R.V.I.S. System Prompt
# ═══════════════════════════════════════════════════════════

_JARVIS_PERSONALITY = """You are J.A.R.V.I.S. — Just A Rather Very Intelligent System.

You are the personal AI assistant created for your user, whom you address as "sir" unless they tell you otherwise. You are modeled after the AI from Marvel's Iron Man films.

PERSONALITY:
- Professional, calm, composed, and confident at all times.
- British-inflected speech patterns. Polished and articulate.
- Genuinely helpful. You anticipate needs and provide thorough assistance.
- You are polite but never servile. You have quiet dignity.
- You may use dry wit sparingly — subtle, never sarcastic.
- You never use slang, emojis, or overly casual language.
- You never say "Hey!", "Sure thing!", "No worries!", "Gotcha!", or similar.

SPEECH PATTERNS (use naturally, don't force every one):
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

RESPONSE RULES:
- Keep responses concise — 1 to 3 sentences unless the user asks for detail.
- Your responses will be spoken aloud via text-to-speech. Write naturally for speech.
- Avoid markdown formatting, bullet points, code blocks, or visual formatting.
- Never start a response with "I" — vary your sentence openings.
- When reporting a completed task, be brief: "Done, sir." or "The file has been created."
- For questions you cannot answer, say: "I'm afraid I don't have that information, sir."
- When the system has an error, say: "I've encountered a difficulty, sir. [brief explanation]"
"""


def _build_system_prompt() -> str:
    """Build a rich system prompt with personality, memory, and context."""
    prompt = _JARVIS_PERSONALITY

    # Time-aware greeting context
    hour = datetime.now().hour
    if hour < 12:
        time_of_day = "morning"
    elif hour < 17:
        time_of_day = "afternoon"
    elif hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"
    prompt += f"\n\nCurrent time: {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')} ({time_of_day})"

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

    except Exception as e:
        log.debug("Memory injection failed (non-critical): %s", e)

    # System state context
    try:
        from core.system_info import get_stats
        stats = get_stats()
        battery = stats.get("battery_percent", 100)
        plugged = stats.get("battery_plugged", False)
        net = stats.get("network_connected", False)
        prompt += f"\n\nSystem state: Battery {battery}%"
        if plugged:
            prompt += " (charging)"
        prompt += f", Internet {'connected' if net else 'offline'}"
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

    Tracks latency and records conversation history.
    """
    global _provider, _active_provider_name, _last_latency_ms

    if not _available or _provider is None:
        return "AI capabilities are not enabled, sir. Please set up Ollama or a Gemini API key."

    try:
        from config.config import AI_MAX_RESPONSE_LENGTH

        start = time.time()
        response = _provider.ask(question, max_length=AI_MAX_RESPONSE_LENGTH)
        _last_latency_ms = int((time.time() - start) * 1000)

        # Fallback if primary returned empty
        if not response and _provider is _ollama_provider and _gemini_provider:
            log.info("Ollama returned empty — falling back to Gemini")
            start = time.time()
            response = _gemini_provider.ask(question, max_length=AI_MAX_RESPONSE_LENGTH)
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
        _conversation_history.append({"role": "user", "text": question, "time": now})
        _conversation_history.append({"role": "assistant", "text": response, "time": now})

        # Persist to memory
        _persist_conversation(question, response)

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
                    _conversation_history.append({"role": "user", "text": question, "time": now})
                    _conversation_history.append({"role": "assistant", "text": response, "time": now})
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
            })
        if recent:
            log.info("Restored %d conversation entries from memory", len(recent))
    except Exception:
        pass  # Memory not ready yet — fine


def get_conversation_history() -> list[dict]:
    """Get the conversation history for display/persistence."""
    return list(_conversation_history)


def reset_conversation() -> None:
    """Reset the AI conversation history."""
    _conversation_history.clear()
    if _gemini_provider and hasattr(_gemini_provider, 'reset_chat'):
        _gemini_provider.reset_chat()
    log.info("AI conversation reset")
