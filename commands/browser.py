"""
commands/browser.py — Browser navigation commands for J.A.R.V.I.S.

Opens specific websites, searches popular platforms, and navigates the web.
"""
import webbrowser

from core.logger import get_logger

log = get_logger("commands.browser")

# Named website shortcuts
SITES: dict[str, str] = {
    "google":        "https://www.google.com",
    "youtube":       "https://www.youtube.com",
    "github":        "https://github.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "chatgpt":       "https://chat.openai.com",
    "chat gpt":      "https://chat.openai.com",
    "reddit":        "https://www.reddit.com",
    "twitter":       "https://twitter.com",
    "linkedin":      "https://www.linkedin.com",
    "instagram":     "https://www.instagram.com",
    "facebook":      "https://www.facebook.com",
    "amazon":        "https://www.amazon.com",
    "netflix":       "https://www.netflix.com",
    "spotify web":   "https://open.spotify.com",
    "gmail":         "https://mail.google.com",
    "drive":         "https://drive.google.com",
    "google drive":  "https://drive.google.com",
    "maps":          "https://maps.google.com",
    "google maps":   "https://maps.google.com",
    "wikipedia":     "https://www.wikipedia.org",
    "whatsapp":      "https://web.whatsapp.com",
    "whatsapp web":  "https://web.whatsapp.com",
    "canva":         "https://www.canva.com",
    "figma":         "https://www.figma.com",
    "notion":        "https://www.notion.so",
}


def open_site(name: str) -> tuple[bool, str]:
    """Open a named website."""
    name_lower = name.lower().strip()
    url = SITES.get(name_lower)
    if url:
        webbrowser.open(url)
        log.info("Opened site: %s → %s", name, url)
        return True, f"Opening {name.title()}"
    return False, f"I don't have a shortcut for {name}"


def search_google(query: str) -> tuple[bool, str]:
    """Search Google for a query."""
    if not query:
        return False, "What should I search for?"
    url = f"https://www.google.com/search?q={query}"
    webbrowser.open(url)
    log.info("Google search: %s", query)
    return True, f"Searching Google for {query}"


def search_youtube(query: str) -> tuple[bool, str]:
    """Search YouTube for a query."""
    if not query:
        return False, "What should I search on YouTube?"
    url = f"https://www.youtube.com/results?search_query={query}"
    webbrowser.open(url)
    log.info("YouTube search: %s", query)
    return True, f"Searching YouTube for {query}"


def search_github(query: str) -> tuple[bool, str]:
    """Search GitHub for a query."""
    if not query:
        return False, "What should I search on GitHub?"
    url = f"https://github.com/search?q={query}"
    webbrowser.open(url)
    log.info("GitHub search: %s", query)
    return True, f"Searching GitHub for {query}"


def search_stackoverflow(query: str) -> tuple[bool, str]:
    """Search StackOverflow for a query."""
    if not query:
        return False, "What should I search on StackOverflow?"
    url = f"https://stackoverflow.com/search?q={query}"
    webbrowser.open(url)
    log.info("StackOverflow search: %s", query)
    return True, f"Searching StackOverflow for {query}"


def search_wikipedia(topic: str) -> tuple[bool, str]:
    """Look up a topic on Wikipedia and read a summary."""
    if not topic:
        return False, "What topic should I look up?"
    try:
        import wikipedia
        summary = wikipedia.summary(topic, sentences=2)
        log.info("Wikipedia lookup: %s", topic)
        return True, summary
    except Exception:
        log.warning("Wikipedia lookup failed for: %s", topic)
        return False, f"I couldn't find information about {topic} on Wikipedia"


def handle_browser_command(command: str) -> tuple[bool, bool, str]:
    """
    Route browser-related commands.

    Returns:
        (handled, success, message)
    """
    cmd = command.lower().strip()

    # "open <site>" — check browser sites
    if cmd.startswith(("open ", "launch ", "go to ")):
        for prefix in ("open ", "launch ", "go to "):
            if cmd.startswith(prefix):
                site_name = cmd[len(prefix):].strip()
                break
        ok, msg = open_site(site_name)
        if ok:
            return True, True, msg

    # "search google for X" / "google X"
    if cmd.startswith("search google ") or cmd.startswith("google "):
        query = cmd.replace("search google for ", "").replace("search google ", "").replace("google ", "").strip()
        ok, msg = search_google(query)
        return True, ok, msg

    # "search github for X"
    if "search github" in cmd or "github search" in cmd:
        query = cmd.replace("search github for ", "").replace("search github ", "").replace("github search ", "").strip()
        ok, msg = search_github(query)
        return True, ok, msg

    # "search stackoverflow for X"
    if "stackoverflow" in cmd or "stack overflow" in cmd:
        query = (cmd.replace("search stackoverflow for ", "")
                 .replace("search stackoverflow ", "")
                 .replace("search stack overflow for ", "")
                 .replace("search stack overflow ", "")
                 .replace("stackoverflow ", "")
                 .replace("stack overflow ", "").strip())
        ok, msg = search_stackoverflow(query)
        return True, ok, msg

    # "search youtube for X"
    if "search youtube" in cmd or "youtube search" in cmd:
        query = cmd.replace("search youtube for ", "").replace("search youtube ", "").replace("youtube search ", "").strip()
        ok, msg = search_youtube(query)
        return True, ok, msg

    # "wikipedia X" / "wiki X" / "who is X" / "what is X"
    if cmd.startswith(("wikipedia ", "wiki ")):
        topic = cmd.replace("wikipedia ", "").replace("wiki ", "").strip()
        ok, msg = search_wikipedia(topic)
        return True, ok, msg

    if cmd.startswith(("who is ", "what is ")):
        topic = cmd.replace("who is ", "").replace("what is ", "").strip()
        ok, msg = search_wikipedia(topic)
        return True, ok, msg

    return False, False, ""
