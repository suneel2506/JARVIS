"""
commands/web.py — Web utility commands for J.A.R.V.I.S.

Handles general web searches and site-specific commands.
Browser navigation is handled by commands/browser.py.
Media playback is handled by commands/media.py.
"""
import webbrowser

from core.logger import get_logger

log = get_logger("commands.web")


def search_web(query: str) -> tuple[bool, str]:
    """Search the web using Google (general fallback)."""
    if not query:
        return False, "What should I search for?"
    url = f"https://www.google.com/search?q={query}"
    webbrowser.open(url)
    log.info("Web search: %s", query)
    return True, f"Searching the web for {query}"


def open_website(url: str) -> tuple[bool, str]:
    """Open a direct URL."""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        webbrowser.open(url)
        log.info("Opened URL: %s", url)
        return True, f"Opening {url}"
    except Exception as e:
        log.error("Failed to open URL %s: %s", url, e)
        return False, f"Couldn't open {url}"


def handle_web_command(command: str) -> tuple[bool, bool, str]:
    """
    Route general web search commands.

    Returns:
        (handled, success, message)
    """
    cmd = command.lower().strip()

    # General search ("search for X", "search X")
    if cmd.startswith("search for ") or cmd.startswith("search "):
        query = cmd.replace("search for ", "").replace("search ", "").strip()
        # Don't handle if it's a specific platform search
        if any(query.startswith(p) for p in ("google ", "youtube ", "github ", "stackoverflow ")):
            return False, False, ""
        ok, msg = search_web(query)
        return True, ok, msg

    # Open website
    if cmd.startswith("open website ") or cmd.startswith("go to "):
        url = cmd.replace("open website ", "").replace("go to ", "").strip()
        # Only handle if it looks like a URL
        if "." in url:
            ok, msg = open_website(url)
            return True, ok, msg

    return False, False, ""
