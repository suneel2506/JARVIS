"""
core/ai_engine.py — AI conversation engine for J.A.R.V.I.S.

Provides natural language understanding through Google Gemini.
Supports both the new google.genai SDK and the legacy google.generativeai SDK.
"""
from typing import Optional

from core.logger import get_logger

log = get_logger("core.ai_engine")

_model = None
_chat = None
_available = False
_use_legacy = False


def init_ai() -> None:
    """Initialize the Gemini AI model."""
    global _model, _chat, _available, _use_legacy
    try:
        from config.config import GEMINI_API_KEY, AI_SYSTEM_PROMPT, AI_MODEL
        if not GEMINI_API_KEY:
            log.info("No Gemini API key set — AI conversation disabled")
            log.info("Set GEMINI_API_KEY environment variable or in .env file")
            _available = False
            return

        # Try new google.genai SDK first
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            _model = client
            _chat = {"history": [], "system": AI_SYSTEM_PROMPT}
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
            system_instruction=AI_SYSTEM_PROMPT,
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


def ask(question: str) -> str:
    """
    Ask the AI a question and get a concise response.

    Args:
        question: The user's question or prompt.

    Returns:
        AI response text, or error message if unavailable.
    """
    if not _available or _model is None:
        return "AI capabilities are not enabled. Please set up a Gemini API key."

    try:
        from config.config import AI_MAX_RESPONSE_LENGTH, AI_SYSTEM_PROMPT, AI_MODEL

        prompt = f"{question}\n\n(Keep response under {AI_MAX_RESPONSE_LENGTH} characters for speech.)"

        if _use_legacy:
            response = _chat.send_message(prompt)
            text = response.text.strip()
        else:
            # New google.genai API
            full_prompt = f"System: {AI_SYSTEM_PROMPT}\n\nUser: {prompt}"
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

        log.info("AI response generated (%d chars)", len(text))
        return text
    except Exception as e:
        log.error("AI query error: %s", e)
        return "I encountered an error processing that request, sir."


def reset_conversation() -> None:
    """Reset the AI conversation history."""
    global _chat
    if _use_legacy and _model:
        _chat = _model.start_chat(history=[])
    elif not _use_legacy:
        from config.config import AI_SYSTEM_PROMPT
        _chat = {"history": [], "system": AI_SYSTEM_PROMPT}
    log.info("AI conversation reset")
