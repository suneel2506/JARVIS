"""
config/__init__.py — Re-export all configuration for backward compatibility.

Usage:
    from config import GEMINI_API_KEY, THEME, WAKE_WORD
    from config.config import Settings
"""
from config.config import *  # noqa: F401,F403
