"""
config/config.py — Central configuration for J.A.R.V.I.S.

Loads settings from settings.json with environment variable overrides.
All paths, API keys, theme colors, and tunable parameters are defined here.
"""
import os
import json
from typing import Any

# ─── Paths ───────────────────────────────────────────────
BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR: str = os.path.join(BASE_DIR, "config")
SETTINGS_FILE: str = os.path.join(CONFIG_DIR, "settings.json")
BRAIN_FILE: str = os.path.join(BASE_DIR, "memory", "brain.json")
MEMORY_FILE: str = os.path.join(BASE_DIR, "memory", "brain.json")
SCREENSHOT_DIR: str = os.path.join(BASE_DIR, "data", "screenshots")
LOG_DIR: str = os.path.join(BASE_DIR, "logs")
DATA_DIR: str = os.path.join(BASE_DIR, "data")
VOSK_MODEL_PATH: str = os.path.join(BASE_DIR, "model", "vosk-model-small-en-us-0.15")

# Ensure directories exist
for _dir in (SCREENSHOT_DIR, LOG_DIR, DATA_DIR, os.path.join(BASE_DIR, "memory")):
    os.makedirs(_dir, exist_ok=True)


def _load_settings() -> dict[str, Any]:
    """Load settings from JSON file, falling back to defaults on error."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[Config] Warning: Could not load settings.json: {e}")
        return {}


_settings = _load_settings()

# ─── API Keys (from environment only — never hardcode) ───
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# ─── Voice Settings ──────────────────────────────────────
_voice = _settings.get("voice", {})
WAKE_WORD: str = _voice.get("wake_words", ["hey jarvis"])[0]  # Primary for backward compat
WAKE_WORDS: list[str] = _voice.get("wake_words", ["jarvis", "hey jarvis", "okay jarvis"])
LISTEN_MODE: str = _voice.get("listen_mode", "wake_word")  # wake_word, continuous, push_to_talk
WAKE_SENSITIVITY: float = _voice.get("wake_sensitivity", 1.5)
TTS_RATE: int = _voice.get("tts_rate", 200)
TTS_VOLUME: float = _voice.get("tts_volume", 1.0)
LISTEN_TIMEOUT: int = _voice.get("listen_timeout", 6)
PHRASE_TIME_LIMIT: int = _voice.get("phrase_time_limit", 8)
AMBIENT_ADJUST_DURATION: float = _voice.get("ambient_adjust_duration", 0.5)
USE_VOSK_OFFLINE: bool = _voice.get("use_vosk_offline", True)
VOSK_MODEL_NAME: str = _voice.get("vosk_model", "vosk-model-small-en-us-0.15")
SLEEP_ON_IDLE_MINUTES: int = _voice.get("sleep_on_idle_minutes", 0)
PUSH_TO_TALK_KEY: str = _voice.get("push_to_talk_key", "ctrl+shift+j")

# ─── Audio / Waveform ───────────────────────────────────
_audio = _settings.get("audio", {})
SAMPLING_RATE: int = _audio.get("sampling_rate", 16000)
FRAME_DURATION: float = _audio.get("frame_duration", 0.05)
WAVEFORM_BARS: int = _audio.get("waveform_bars", 32)

# ─── AI Engine ───────────────────────────────────────────
_ai = _settings.get("ai", {})
AI_PROVIDER: str = _ai.get("provider", "gemini")
AI_MODEL: str = _ai.get("model", "gemini-2.0-flash")
AI_SYSTEM_PROMPT: str = _ai.get(
    "system_prompt",
    "You are Jarvis, a brilliant AI assistant inspired by Iron Man's JARVIS. "
    "You are witty, confident, and genuinely helpful. Keep responses short (2-3 sentences) "
    "unless asked for detail. Address the user as 'sir' occasionally.",
)
AI_MAX_RESPONSE_LENGTH: int = _ai.get("max_response_length", 300)
AI_CONVERSATION_HISTORY_SIZE: int = _ai.get("conversation_history_size", 20)
AI_PERSONALITY_LEVEL: str = _ai.get("personality_level", "high")
AI_MEMORY_INJECTION: bool = _ai.get("memory_injection", True)

# ─── UI / HUD ───────────────────────────────────────────
_ui = _settings.get("ui", {})
HUD_FPS: int = _ui.get("fps", 30)
ARC_REACTOR_SIZE: int = _ui.get("arc_reactor_size", 240)
PANEL_WIDTH_RATIO: float = _ui.get("panel_width_ratio", 0.22)
HUD_FULLSCREEN: bool = _ui.get("fullscreen", True)
HUD_ALWAYS_ON_TOP: bool = _ui.get("always_on_top", False)
HUD_MINI_MODE: bool = _ui.get("mini_mode", False)

# ─── Productivity ───────────────────────────────────────
_prod = _settings.get("productivity", {})
POMODORO_WORK_MINUTES: int = _prod.get("pomodoro_work_minutes", 25)
POMODORO_BREAK_MINUTES: int = _prod.get("pomodoro_break_minutes", 5)
TODO_FILE: str = os.path.join(BASE_DIR, _prod.get("todo_file", "data/todo.json"))
REMINDERS_FILE: str = os.path.join(BASE_DIR, _prod.get("reminders_file", "data/reminders.json"))

# ─── Theme (Iron Man Cyan) ──────────────────────────────
_theme_data = _settings.get("theme", {})
THEME: dict[str, str] = {
    "bg":           _theme_data.get("bg", "#05080d"),
    "bg_panel":     _theme_data.get("bg_panel", "#0a1020"),
    "primary":      _theme_data.get("primary", "#00eaff"),
    "primary_dim":  _theme_data.get("primary_dim", "#005f6a"),
    "secondary":    _theme_data.get("secondary", "#0080ff"),
    "accent":       _theme_data.get("accent", "#00ff88"),
    "warning":      _theme_data.get("warning", "#ff6a00"),
    "danger":       _theme_data.get("danger", "#ff0040"),
    "text":         _theme_data.get("text", "#c0f0ff"),
    "text_dim":     _theme_data.get("text_dim", "#406070"),
    "glow":         _theme_data.get("glow", "#00eaff"),
    "reactor_core": _theme_data.get("reactor_core", "#80ffff"),
    "reactor_ring": _theme_data.get("reactor_ring", "#00c8e0"),
    "waveform":     _theme_data.get("waveform", "#00d4ff"),
    "radar_sweep":  _theme_data.get("radar_sweep", "#00eaff"),
    "border":       _theme_data.get("border", "#0a3040"),
}
