"""
core/ai_engine.py — Multi-provider AI conversation engine for J.A.R.V.I.S.

Supports multiple AI backends with automatic fallback:
1. Ollama (local, free, private) — preferred
2. Gemini (Google, free tier) — fallback

Features:
- Rolling conversation history for context-aware responses
- Memory injection — user facts/preferences are prepended to each call
- Dynamic system prompt with personality and temporal awareness
- Provider auto-fallback: if Ollama is not running, use Gemini
- Response truncation optimized for TTS delivery
"""
import requests
import json
from typing import Optional
from collections import deque
from datetime import datetime

from core.logger import get_logger

log = get_logger("core.ai_engine")

# ─── State ──────────────────────────────────────────────
_provider = None
_available = False
_active_provider_name = "none"

# Rolling conversation history
_conversation_history: deque[dict] = deque(maxlen=20)


# ═══════════════════════════════════════════════════════════
# System Prompt Builder
# ═══════════════════════════════════════════════════════════

def _build_system_prompt() -> str:
    """Build a dynamic system prompt with memory injection."""
    from config.config import AI_SYSTEM_PROMPT, AI_MEMORY_INJECTION

    prompt = AI_SYSTEM_PROMPT

    if AI_MEMORY_INJECTION:
        try:
            from core.brain import get_brain_data
            brain = get_brain_data()

            # Inject user facts
            facts = brain.get("facts", {})
            if facts:
                fact_lines = [f"- {k}: {v}" for k, v in list(facts.items())[:10]]
                prompt += "\n\nThings you know about the user:\n" + "\n".join(fact_lines)

            # Inject preferences
            prefs = brain.get("preferences", {})
            if prefs:
                pref_lines = [f"- {k}: {v}" for k, v in list(prefs.items())[:10]]
                prompt += "\n\nUser preferences:\n" + "\n".join(pref_lines)

            # Inject current context
            prompt += f"\n\nCurrent date and time: {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}"
        except Exception as e:
            log.debug("Memory injection failed (non-critical): %s", e)

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
    """
    Local AI using Ollama — fully private, no API key required.
    Connects to Ollama's REST API at http://localhost:11434.
    """

    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model
        self.name = f"Ollama ({model})"

        # Verify Ollama is running
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
            "content": f"{question}\n\n(Keep response under {max_length} characters for speech.)",
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
    """
    Google Gemini AI — free tier, requires API key.
    Supports both new google.genai SDK and legacy google.generativeai.
    """

    def __init__(self, api_key: str, model: str):
        self.model_name = model
        self.name = f"Gemini ({model})"
        self._client = None
        self._chat = None
        self._use_legacy = False

        # Try new google.genai SDK first
        try:
            from google import genai
            self._client = genai.Client(api_key=api_key)
            log.info("Gemini initialized (google.genai SDK, model=%s)", model)
            return
        except ImportError:
            pass

        # Fallback to legacy SDK
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
        prompt = f"{question}\n\n(Keep response under {max_length} characters for speech.)"

        try:
            if self._use_legacy:
                response = self._chat.send_message(prompt)
                return response.text.strip()
            else:
                # New SDK with context
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
    """
    Initialize AI providers based on configuration.
    Tries Ollama first (local), then Gemini (cloud fallback).
    """
    global _provider, _available, _active_provider_name
    global _ollama_provider, _gemini_provider

    from config.config import (
        AI_PROVIDER, OLLAMA_HOST, OLLAMA_MODEL,
        GEMINI_API_KEY, AI_MODEL, AI_CONVERSATION_HISTORY_SIZE,
    )

    # Update history size
    _conversation_history.__init__(maxlen=AI_CONVERSATION_HISTORY_SIZE)

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

    # Try Gemini (as primary or fallback)
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
        log.info("  Ollama: Install from ollama.ai, then 'ollama pull llama3.2'")
        log.info("  Gemini: Set GEMINI_API_KEY environment variable")


def is_available() -> bool:
    """Check if any AI provider is available."""
    return _available


def get_provider_name() -> str:
    """Get the name of the active AI provider."""
    return _active_provider_name


def ask(question: str) -> str:
    """
    Ask the AI a question with automatic fallback between providers.

    Args:
        question: The user's question or prompt.

    Returns:
        AI response text, or error message if unavailable.
    """
    global _provider, _active_provider_name

    if not _available or _provider is None:
        return "AI capabilities are not enabled. Set up Ollama or a Gemini API key."

    try:
        from config.config import AI_MAX_RESPONSE_LENGTH

        response = _provider.ask(question, max_length=AI_MAX_RESPONSE_LENGTH)

        # If primary provider returned empty, try fallback
        if not response and _provider is _ollama_provider and _gemini_provider:
            log.info("Ollama returned empty — falling back to Gemini")
            response = _gemini_provider.ask(question, max_length=AI_MAX_RESPONSE_LENGTH)
            if response:
                _active_provider_name = f"{_gemini_provider.name} (fallback)"

        if not response:
            return "I couldn't generate a response right now, sir."

        # Truncate overly long responses for TTS
        if len(response) > AI_MAX_RESPONSE_LENGTH * 2:
            cut = response[:AI_MAX_RESPONSE_LENGTH * 2]
            last_period = cut.rfind('.')
            if last_period > AI_MAX_RESPONSE_LENGTH // 2:
                response = cut[:last_period + 1]
            else:
                response = cut + "..."

        # Record in conversation history
        _conversation_history.append({
            "role": "user", "text": question,
            "time": datetime.now().isoformat(),
        })
        _conversation_history.append({
            "role": "assistant", "text": response,
            "time": datetime.now().isoformat(),
        })

        log.info("AI response (%s, %d chars)", _active_provider_name, len(response))
        return response
    except Exception as e:
        log.error("AI query error: %s", e)

        # Try fallback on error
        if _provider is _ollama_provider and _gemini_provider:
            try:
                log.info("Ollama error — trying Gemini fallback")
                from config.config import AI_MAX_RESPONSE_LENGTH
                response = _gemini_provider.ask(question, max_length=AI_MAX_RESPONSE_LENGTH)
                if response:
                    _conversation_history.append({"role": "user", "text": question, "time": datetime.now().isoformat()})
                    _conversation_history.append({"role": "assistant", "text": response, "time": datetime.now().isoformat()})
                    return response
            except Exception:
                pass

        return "I encountered an error processing that request, sir."


def get_conversation_history() -> list[dict]:
    """Get the conversation history for display/persistence."""
    return list(_conversation_history)


def reset_conversation() -> None:
    """Reset the AI conversation history."""
    _conversation_history.clear()
    if _gemini_provider and hasattr(_gemini_provider, 'reset_chat'):
        _gemini_provider.reset_chat()
    log.info("AI conversation reset")
