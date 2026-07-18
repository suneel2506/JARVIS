"""
config/config.py — Central configuration for J.A.R.V.I.S.

Loads settings from settings.json with environment variable overrides.
All paths, API keys, theme colors, and tunable parameters are defined here.

Settings priority: Environment variables > settings.json > defaults
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
PIPER_MODEL_DIR: str = os.path.join(BASE_DIR, "model", "piper")

# Ensure directories exist
for _dir in (SCREENSHOT_DIR, LOG_DIR, DATA_DIR,
             os.path.join(BASE_DIR, "memory"),
             os.path.join(BASE_DIR, "plugins"),
             PIPER_MODEL_DIR):
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

# ─── Voice Settings ──────────────────────────────────────
_voice = _settings.get("voice", {})
WAKE_WORD: str = _voice.get("wake_words", ["hey jarvis"])[0]  # Primary for backward compat
WAKE_WORDS: list[str] = _voice.get("wake_words", ["jarvis", "hey jarvis", "okay jarvis"])
WAKE_ENGINE: str = _voice.get("wake_engine", "vosk_substring")  # openwakeword or vosk_substring
OPENWAKEWORD_MODELS: list[str] = _voice.get("openwakeword_models", ["hey_jarvis"])
LISTEN_MODE: str = _voice.get("listen_mode", "wake_word")
WAKE_SENSITIVITY: float = _voice.get("wake_sensitivity", 1.5)

# TTS Engine
TTS_ENGINE: str = _voice.get("tts_engine", "pyttsx3")  # piper or pyttsx3
TTS_RATE: int = _voice.get("tts_rate", 200)
TTS_VOLUME: float = _voice.get("tts_volume", 1.0)
PIPER_MODEL_NAME: str = _voice.get("piper_model", "en_US-lessac-medium.onnx")
PIPER_MODEL_PATH: str = os.path.join(PIPER_MODEL_DIR, PIPER_MODEL_NAME)

# Speech Recognition
LISTEN_TIMEOUT: int = _voice.get("listen_timeout", 6)
PHRASE_TIME_LIMIT: int = _voice.get("phrase_time_limit", 8)
AMBIENT_ADJUST_DURATION: float = _voice.get("ambient_adjust_duration", 0.5)
USE_VOSK_OFFLINE: bool = _voice.get("use_vosk_offline", True)
VOSK_MODEL_NAME: str = _voice.get("vosk_model", "vosk-model-small-en-us-0.15")
SLEEP_ON_IDLE_MINUTES: int = _voice.get("sleep_on_idle_minutes", 0)
PUSH_TO_TALK_KEY: str = _voice.get("push_to_talk_key", "ctrl+shift+j")

# Phase 1 — Voice System Hardening settings
MULTI_MIC_FAILOVER: bool = _voice.get("multi_mic_failover", True)
PREFERRED_MIC_INDEX: int | None = _voice.get("preferred_mic_index", None)
INTERRUPTION_ENABLED: bool = _voice.get("interruption_enabled", True)
CONFIDENCE_HIGH_THRESHOLD: float = _voice.get("confidence_high_threshold", 0.65)
CONFIDENCE_MEDIUM_THRESHOLD: float = _voice.get("confidence_medium_threshold", 0.40)
IDLE_POWER_SAVE_MINUTES: int = _voice.get("idle_power_save_minutes", 10)
VAD_MODE: str = _voice.get("vad_mode", "multi_feature")  # multi_feature or energy_only
NOISE_SUPPRESSION: str = _voice.get("noise_suppression", "spectral")  # spectral or highpass

# ─── Audio / Waveform ───────────────────────────────────
_audio = _settings.get("audio", {})
SAMPLING_RATE: int = _audio.get("sampling_rate", 16000)
FRAME_DURATION: float = _audio.get("frame_duration", 0.05)
WAVEFORM_BARS: int = _audio.get("waveform_bars", 32)

# ─── AI Engine ───────────────────────────────────────────
_ai = _settings.get("ai", {})
AI_PROVIDER: str = _ai.get("provider", "auto")  # auto, ollama, gemini
AI_MODEL: str = _ai.get("model", "gemini-2.0-flash")
OLLAMA_MODEL: str = _ai.get("ollama_model", "llama3.2")
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", _ai.get("ollama_host", "http://localhost:11434"))
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

# ─── Safety ──────────────────────────────────────────────
_safety = _settings.get("safety", {})
CONFIRM_DESTRUCTIVE: bool = _safety.get("confirm_destructive", True)
LOG_DANGEROUS_OPS: bool = _safety.get("log_dangerous_ops", True)

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


# ─── Dynamic Settings Access ───────────────────────────
def get_setting(key: str, default: Any = None) -> Any:
    """
    Get a setting value by dot-separated key path.

    Examples:
        get_setting("voice.tts_rate", 200)
        get_setting("idle_power_save_minutes", 10)

    For flat keys, searches all sections. For dotted keys,
    searches the specified section first.
    """
    if "." in key:
        section, subkey = key.split(".", 1)
        section_data = _settings.get(section, {})
        return section_data.get(subkey, default)
    else:
        # Search all sections
        for section_data in _settings.values():
            if isinstance(section_data, dict) and key in section_data:
                return section_data[key]
        return default
