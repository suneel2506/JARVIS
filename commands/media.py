"""
commands/media.py — Media playback and volume control for J.A.R.V.I.S.

Controls system media playback (play/pause/next/previous) and volume
via keyboard media keys for maximum compatibility.
"""
import webbrowser

from core.logger import get_logger

log = get_logger("commands.media")


def _press_media_key(key: str, description: str) -> tuple[bool, str]:
    """Press a media key using the keyboard module."""
    try:
        import keyboard
        keyboard.press_and_release(key)
        log.info("Media key pressed: %s", key)
        return True, description
    except Exception as e:
        log.error("Failed to press media key %s: %s", key, e)
        return False, f"Couldn't {description.lower()}: {e}"


def play_pause() -> tuple[bool, str]:
    """Toggle play/pause on current media."""
    return _press_media_key("play/pause media", "Play/Pause toggled")


def next_track() -> tuple[bool, str]:
    """Skip to next track."""
    return _press_media_key("next track", "Skipped to next track")


def previous_track() -> tuple[bool, str]:
    """Go to previous track."""
    return _press_media_key("previous track", "Went to previous track")


def stop_media() -> tuple[bool, str]:
    """Stop media playback."""
    return _press_media_key("stop media", "Media stopped")


def volume_up(steps: int = 5) -> tuple[bool, str]:
    """Increase system volume."""
    try:
        import keyboard
        for _ in range(steps):
            keyboard.press_and_release("volume up")
        log.info("Volume increased by %d steps", steps)
        return True, "Volume up"
    except Exception as e:
        log.error("Volume up failed: %s", e)
        return False, f"Couldn't increase volume: {e}"


def volume_down(steps: int = 5) -> tuple[bool, str]:
    """Decrease system volume."""
    try:
        import keyboard
        for _ in range(steps):
            keyboard.press_and_release("volume down")
        log.info("Volume decreased by %d steps", steps)
        return True, "Volume down"
    except Exception as e:
        log.error("Volume down failed: %s", e)
        return False, f"Couldn't decrease volume: {e}"


def volume_mute() -> tuple[bool, str]:
    """Toggle mute."""
    return _press_media_key("volume mute", "Volume muted")


def play_on_youtube(query: str) -> tuple[bool, str]:
    """Play something on YouTube."""
    if not query:
        return False, "What should I play?"
    try:
        import pywhatkit
        pywhatkit.playonyt(query)
        log.info("Playing on YouTube: %s", query)
        return True, f"Playing {query} on YouTube"
    except Exception:
        url = f"https://www.youtube.com/results?search_query={query}"
        webbrowser.open(url)
        log.info("YouTube search fallback: %s", query)
        return True, f"Searching YouTube for {query}"


def handle_media_command(command: str) -> tuple[bool, bool, str]:
    """
    Route media-related commands.

    Returns:
        (handled, success, message)
    """
    cmd = command.lower().strip()

    # Play on YouTube
    if cmd.startswith("play "):
        query = cmd[5:].strip()
        ok, msg = play_on_youtube(query)
        return True, ok, msg

    # Play/Pause
    if cmd in ("pause", "resume", "play", "play pause", "pause music", "resume music"):
        ok, msg = play_pause()
        return True, ok, msg

    # Next
    if cmd in ("next", "next track", "next song", "skip", "skip track"):
        ok, msg = next_track()
        return True, ok, msg

    # Previous
    if cmd in ("previous", "previous track", "previous song", "go back"):
        ok, msg = previous_track()
        return True, ok, msg

    # Stop
    if cmd in ("stop music", "stop media", "stop playing"):
        ok, msg = stop_media()
        return True, ok, msg

    # Volume
    if any(phrase in cmd for phrase in ("volume up", "louder", "increase volume", "turn up")):
        ok, msg = volume_up()
        return True, ok, msg

    if any(phrase in cmd for phrase in ("volume down", "quieter", "decrease volume", "turn down")):
        ok, msg = volume_down()
        return True, ok, msg

    if "mute" in cmd:
        ok, msg = volume_mute()
        return True, ok, msg

    return False, False, ""
