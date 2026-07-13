"""
core/logger.py — Centralized logging for J.A.R.V.I.S.

Provides structured logging with:
- Console output with colored formatting
- Rotating file handler for persistent logs
- Separate conversation log
- Separate error log

Usage:
    from core.logger import get_logger
    log = get_logger(__name__)
    log.info("System initialized")
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional

_initialized = False
_conversation_logger: Optional[logging.Logger] = None

# ANSI color codes for console output
_COLORS = {
    "DEBUG": "\033[36m",     # Cyan
    "INFO": "\033[32m",      # Green
    "WARNING": "\033[33m",   # Yellow
    "ERROR": "\033[31m",     # Red
    "CRITICAL": "\033[35m",  # Magenta
    "RESET": "\033[0m",
}


class _ColoredFormatter(logging.Formatter):
    """Formatter that adds ANSI colors to console output."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, _COLORS["RESET"])
        reset = _COLORS["RESET"]
        record.levelname = f"{color}{record.levelname:<8}{reset}"
        record.name = f"\033[90m{record.name}\033[0m"
        return super().format(record)


def _init_logging() -> None:
    """Initialize the logging system. Called once on first use."""
    global _initialized, _conversation_logger
    if _initialized:
        return

    from config.config import LOG_DIR
    os.makedirs(LOG_DIR, exist_ok=True)

    root_logger = logging.getLogger("jarvis")
    root_logger.setLevel(logging.DEBUG)

    # ─── Console Handler ────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_fmt = _ColoredFormatter(
        fmt="%(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    root_logger.addHandler(console_handler)

    # ─── Main File Handler (rotating) ───────────────────
    main_log_path = os.path.join(LOG_DIR, "jarvis.log")
    file_handler = RotatingFileHandler(
        main_log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    root_logger.addHandler(file_handler)

    # ─── Error File Handler ─────────────────────────────
    error_log_path = os.path.join(LOG_DIR, "errors.log")
    error_handler = RotatingFileHandler(
        error_log_path, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_fmt)
    root_logger.addHandler(error_handler)

    # ─── Conversation Logger ────────────────────────────
    _conversation_logger = logging.getLogger("jarvis.conversation")
    _conversation_logger.setLevel(logging.INFO)
    _conversation_logger.propagate = False

    conv_log_path = os.path.join(LOG_DIR, "conversations.log")
    conv_handler = RotatingFileHandler(
        conv_log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    conv_fmt = logging.Formatter(
        fmt="%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    conv_handler.setFormatter(conv_fmt)
    _conversation_logger.addHandler(conv_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger under the 'jarvis' hierarchy.

    Args:
        name: Module name, typically __name__. If it doesn't start with 'jarvis.',
              it will be prefixed automatically.

    Returns:
        Configured logging.Logger instance.
    """
    _init_logging()
    if not name.startswith("jarvis."):
        name = f"jarvis.{name}"
    return logging.getLogger(name)


def log_conversation(user_input: str, response: str) -> None:
    """
    Log a conversation exchange to the dedicated conversation log.

    Args:
        user_input: What the user said or typed.
        response: What JARVIS responded.
    """
    _init_logging()
    if _conversation_logger:
        _conversation_logger.info("USER: %s", user_input)
        _conversation_logger.info("JARVIS: %s", response)


def log_command(command: str, result: str) -> None:
    """
    Log a command execution to the conversation log.

    Args:
        command: The command that was executed.
        result: The result/response of the command.
    """
    _init_logging()
    if _conversation_logger:
        _conversation_logger.info("CMD: %s → %s", command, result)
