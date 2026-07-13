"""
commands/ai.py — AI conversation and memory commands for J.A.R.V.I.S.

Routes AI-related commands through a unified interface supporting:
- Gemini (Google)
- Ollama (local)
- Memory store/recall

All AI providers are accessed through core/ai_engine.py.
Memory operations are handled through core/memory.py.
"""
from core.logger import get_logger

log = get_logger("commands.ai")


def ask_ai(question: str) -> tuple[bool, str]:
    """
    Ask the AI engine a question.

    Args:
        question: The user's question.

    Returns:
        (success, response_text)
    """
    try:
        from core.ai_engine import is_available, ask
        if not is_available():
            return False, "AI engine is not available. Please set up a Gemini API key."
        response = ask(question)
        log.info("AI query: %s → %s", question[:50], response[:50])
        return True, response
    except Exception as e:
        log.error("AI query failed: %s", e)
        return False, "I encountered an error processing that request, sir."


def reset_ai_conversation() -> tuple[bool, str]:
    """Reset the AI conversation history."""
    try:
        from core.ai_engine import reset_conversation
        reset_conversation()
        log.info("AI conversation reset")
        return True, "Conversation reset. Starting fresh, sir."
    except Exception as e:
        log.error("AI reset failed: %s", e)
        return False, "Couldn't reset the conversation."


def handle_remember(text: str) -> tuple[bool, str]:
    """
    Handle "remember" commands by storing to memory.

    Args:
        text: The full command text (e.g., "remember my college is MIT").

    Returns:
        (success, confirmation_message)
    """
    try:
        from core.memory import get_memory
        memory = get_memory()
        result = memory.parse_and_store(text)
        log.info("Memory store: %s", text[:50])
        return True, result
    except Exception as e:
        log.error("Memory store failed: %s", e)
        return False, "I couldn't save that to memory."


def handle_recall(query: str) -> tuple[bool, str]:
    """
    Try to recall information from memory.

    Args:
        query: The user's question about stored information.

    Returns:
        (success, answer) — success=False if nothing found in memory.
    """
    try:
        from core.memory import get_memory
        memory = get_memory()
        answer = memory.recall(query)
        if answer:
            log.info("Memory recall: %s → %s", query[:30], answer[:30])
            return True, answer
        return False, ""
    except Exception as e:
        log.error("Memory recall failed: %s", e)
        return False, ""


def handle_note(text: str) -> tuple[bool, str]:
    """Save a note to memory."""
    try:
        from core.memory import get_memory
        memory = get_memory()
        content = text
        for prefix in ("note ", "save note ", "note: "):
            if content.lower().startswith(prefix):
                content = content[len(prefix):]
                break
        result = memory.add_note(content.strip())
        return True, result
    except Exception as e:
        log.error("Note save failed: %s", e)
        return False, "Couldn't save that note."


def handle_show_notes() -> tuple[bool, str]:
    """Show recent notes."""
    try:
        from core.memory import get_memory
        memory = get_memory()
        notes = memory.get_notes(limit=5)
        if not notes:
            return True, "You don't have any saved notes."
        lines = []
        for note in notes:
            ts = note.get("timestamp", "")[:10]
            content = note.get("content", "")
            lines.append(f"{ts}: {content}")
        return True, "Your recent notes: " + "; ".join(lines)
    except Exception as e:
        log.error("Show notes failed: %s", e)
        return False, "Couldn't retrieve notes."


def handle_ai_command(command: str) -> tuple[bool, bool, str]:
    """
    Route AI and memory commands.

    Returns:
        (handled, success, message)
    """
    cmd = command.lower().strip()

    # Memory: remember
    if cmd.startswith(("remember ", "remember that ")):
        ok, msg = handle_remember(command)
        return True, ok, msg

    # Memory: name setting
    if cmd.startswith(("call me ", "my name is ")):
        ok, msg = handle_remember(command)
        return True, ok, msg

    # Memory: notes
    if cmd.startswith(("note ", "note: ", "save note ")):
        ok, msg = handle_note(command)
        return True, ok, msg

    if cmd in ("show notes", "my notes", "list notes", "show my notes"):
        ok, msg = handle_show_notes()
        return True, ok, msg

    if cmd in ("clear notes", "delete notes", "delete all notes"):
        try:
            from core.memory import get_memory
            msg = get_memory().clear_notes()
            return True, True, msg
        except Exception:
            return True, False, "Couldn't clear notes."

    # AI: reset conversation
    if cmd in ("reset conversation", "new conversation", "start over",
               "clear chat", "reset ai", "forget conversation"):
        ok, msg = reset_ai_conversation()
        return True, ok, msg

    # AI: explicit queries
    if cmd.startswith(("ask ", "ask jarvis ")):
        question = cmd.replace("ask jarvis ", "").replace("ask ", "").strip()
        ok, msg = ask_ai(question)
        return True, ok, msg

    if cmd.startswith(("tell me about ", "explain ")):
        question = command  # keep original case
        ok, msg = ask_ai(question)
        return True, ok, msg

    return False, False, ""
