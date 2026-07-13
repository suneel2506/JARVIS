"""
core/ai_engine.py — AI conversation engine for J.A.R.V.I.S.

Provides intelligent conversation through Google Gemini with:
- Rolling conversation history for context-aware responses
- Memory injection — user facts/preferences are prepended to each call
- Enhanced personality with wit, confidence, and emotion
- Response truncation optimized for TTS delivery

Supports both the new google.genai SDK and the legacy google.generativeai SDK.
"""
from typing import Optional
from collections import deque
from datetime import datetime

from core.logger import get_logger

log = get_logger("core.ai_engine")

_model = None
_chat = None
_available = False
_use_legacy = False

# Rolling conversation history
_conversation_history: deque[dict] = deque(maxlen=20)


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


def init_ai() -> None:
    """Initialize the Gemini AI model."""
    global _model, _chat, _available, _use_legacy
    try:
        from config.config import GEMINI_API_KEY, AI_MODEL, AI_CONVERSATION_HISTORY_SIZE
        if not GEMINI_API_KEY:
            log.info("No Gemini API key set — AI conversation disabled")
            log.info("Set GEMINI_API_KEY environment variable or in .env file")
            _available = False
            return

        # Update history size from config
        _conversation_history.__init__(maxlen=AI_CONVERSATION_HISTORY_SIZE)

        # Try new google.genai SDK first
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            _model = client
            _chat = {"history": [], "system": _build_system_prompt()}
            _available = True
            _use_legacy = False
            log.info("Gemini AI initialized (google.genai SDK, model=%s)", AI_MODEL)
            return
        except ImportError:
            pass

        # Fallback to legacy google.generativeai SDK
        import warnings
        warnings.filterwarnings("ignore", category=FutureWarning)
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _model = genai.GenerativeModel(
            model_name=AI_MODEL,
            system_instruction=_build_system_prompt(),
        )
        _chat = _model.start_chat(history=[])
        _available = True
        _use_legacy = True
        log.info("Gemini AI initialized (legacy SDK, model=%s)", AI_MODEL)
    except Exception as e:
        log.error("AI initialization failed: %s", e)
        _available = False


def is_available() -> bool:
    """Check if the AI engine is available."""
    return _available


def _format_history_context() -> str:
    """Format recent conversation history for context injection."""
    if not _conversation_history:
        return ""

    lines = []
    for entry in list(_conversation_history)[-10:]:
        role = entry.get("role", "user")
        text = entry.get("text", "")
        if len(text) > 200:
            text = text[:200] + "..."
        lines.append(f"{'User' if role == 'user' else 'Jarvis'}: {text}")

    return "\n\nRecent conversation:\n" + "\n".join(lines)


def ask(question: str) -> str:
    """
    Ask the AI a question and get a contextually-aware response.

    Injects conversation history and user memory for continuity.

    Args:
        question: The user's question or prompt.

    Returns:
        AI response text, or error message if unavailable.
    """
    if not _available or _model is None:
        return "AI capabilities are not enabled. Please set up a Gemini API key."

    try:
        from config.config import AI_MAX_RESPONSE_LENGTH, AI_MODEL

        # Build contextual prompt
        system_prompt = _build_system_prompt()
        history_context = _format_history_context()

        prompt = f"{question}\n\n(Keep response under {AI_MAX_RESPONSE_LENGTH} characters for speech.)"

        if _use_legacy:
            response = _chat.send_message(prompt)
            text = response.text.strip()
        else:
            # New google.genai API with full context
            full_prompt = f"System: {system_prompt}{history_context}\n\nUser: {prompt}"
            response = _model.models.generate_content(
                model=AI_MODEL,
                contents=full_prompt,
            )
            text = response.text.strip()

        # Truncate overly long responses for comfortable TTS
        if len(text) > AI_MAX_RESPONSE_LENGTH * 2:
            cut = text[:AI_MAX_RESPONSE_LENGTH * 2]
            last_period = cut.rfind('.')
            if last_period > AI_MAX_RESPONSE_LENGTH // 2:
                text = cut[:last_period + 1]
            else:
                text = cut + "..."

        # Record in conversation history
        _conversation_history.append({"role": "user", "text": question, "time": datetime.now().isoformat()})
        _conversation_history.append({"role": "assistant", "text": text, "time": datetime.now().isoformat()})

        log.info("AI response generated (%d chars)", len(text))
        return text
    except Exception as e:
        log.error("AI query error: %s", e)
        return "I encountered an error processing that request, sir."


def get_conversation_history() -> list[dict]:
    """Get the conversation history for display/persistence."""
    return list(_conversation_history)


def reset_conversation() -> None:
    """Reset the AI conversation history."""
    global _chat
    _conversation_history.clear()
    if _use_legacy and _model:
        _chat = _model.start_chat(history=[])
    elif not _use_legacy:
        _chat = {"history": [], "system": _build_system_prompt()}
    log.info("AI conversation reset")
