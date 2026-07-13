"""
commands/browser.py — Browser automation commands for J.A.R.V.I.S.

Dual-backend browser automation:
- Playwright (preferred): Full browser control — fill forms, click, extract text,
  take page screenshots, scrape content, headless mode
- webbrowser (fallback): Simple URL opening when Playwright unavailable

Named website shortcuts for quick access.
"""
import webbrowser
import threading
from typing import Optional

from core.logger import get_logger

log = get_logger("commands.browser")

# ─── Named Website Shortcuts ────────────────────────────

SITES: dict[str, str] = {
    "google":        "https://www.google.com",
    "youtube":       "https://www.youtube.com",
    "github":        "https://github.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "chatgpt":       "https://chat.openai.com",
    "chat gpt":      "https://chat.openai.com",
    "gemini":        "https://gemini.google.com",
    "claude":        "https://claude.ai",
    "reddit":        "https://www.reddit.com",
    "twitter":       "https://twitter.com",
    "x":             "https://twitter.com",
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
    "leetcode":      "https://leetcode.com",
    "hackerrank":    "https://www.hackerrank.com",
    "kaggle":        "https://www.kaggle.com",
    "huggingface":   "https://huggingface.co",
    "hugging face":  "https://huggingface.co",
    "arxiv":         "https://arxiv.org",
    "medium":        "https://medium.com",
    "dev.to":        "https://dev.to",
}


# ─── Playwright Backend ─────────────────────────────────

_playwright_available = False
_pw_browser = None
_pw_page = None
_pw_lock = threading.Lock()


def _check_playwright() -> bool:
    """Check if Playwright is available."""
    global _playwright_available
    try:
        import playwright  # noqa: F401
        _playwright_available = True
        return True
    except ImportError:
        _playwright_available = False
        return False


def _get_playwright_page():
    """Get or create a Playwright browser page."""
    global _pw_browser, _pw_page

    with _pw_lock:
        if _pw_page is not None:
            try:
                _pw_page.title()
                return _pw_page
            except Exception:
                _pw_page = None
                _pw_browser = None

        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            _pw_browser = pw.chromium.launch(headless=False)
            _pw_page = _pw_browser.new_page()
            log.info("Playwright browser launched")
            return _pw_page
        except Exception as e:
            log.error("Playwright launch failed: %s", e)
            return None


def _close_playwright():
    """Close the Playwright browser."""
    global _pw_browser, _pw_page
    with _pw_lock:
        if _pw_page:
            try:
                _pw_page.close()
            except Exception:
                pass
            _pw_page = None
        if _pw_browser:
            try:
                _pw_browser.close()
            except Exception:
                pass
            _pw_browser = None


# ─── Basic Operations ───────────────────────────────────

def open_site(name: str) -> tuple[bool, str]:
    """Open a named website."""
    name_lower = name.lower().strip()
    url = SITES.get(name_lower)
    if url:
        webbrowser.open(url)
        log.info("Opened site: %s → %s", name, url)
        return True, f"Opening {name.title()}"
    return False, f"I don't have a shortcut for {name}"


def open_url(url: str) -> tuple[bool, str]:
    """Open an arbitrary URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    log.info("Opened URL: %s", url)
    return True, f"Opening {url}"


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


# ─── Playwright Advanced Operations ─────────────────────

def scrape_page(url: str) -> tuple[bool, str]:
    """
    Open a URL and extract the page text content using Playwright.
    Falls back to a simple message if Playwright is unavailable.
    """
    if not _check_playwright():
        return False, "Playwright not installed. Install with: pip install playwright && playwright install chromium"

    try:
        page = _get_playwright_page()
        if page is None:
            return False, "Could not launch browser"
        page.goto(url, timeout=15000)
        title = page.title()
        text = page.inner_text("body")
        # Truncate for speech
        if len(text) > 500:
            text = text[:500] + "..."
        log.info("Scraped page: %s (%d chars)", url, len(text))
        return True, f"Page: {title}. Content: {text}"
    except Exception as e:
        log.error("Scrape failed: %s", e)
        return False, f"Couldn't scrape the page: {e}"


def take_page_screenshot(url: str) -> tuple[bool, str]:
    """Take a screenshot of a web page using Playwright."""
    if not _check_playwright():
        return False, "Playwright not installed"

    try:
        import os
        from config.config import SCREENSHOT_DIR

        page = _get_playwright_page()
        if page is None:
            return False, "Could not launch browser"
        page.goto(url, timeout=15000)
        filename = f"page_{int(__import__('time').time())}.png"
        filepath = os.path.join(SCREENSHOT_DIR, filename)
        page.screenshot(path=filepath, full_page=True)
        log.info("Page screenshot saved: %s", filepath)
        return True, f"Screenshot saved: {filename}"
    except Exception as e:
        log.error("Page screenshot failed: %s", e)
        return False, f"Screenshot failed: {e}"


def fill_form_field(selector: str, value: str) -> tuple[bool, str]:
    """Fill a form field on the current Playwright page."""
    if not _playwright_available or _pw_page is None:
        return False, "No browser page open"
    try:
        _pw_page.fill(selector, value)
        return True, f"Filled field: {selector}"
    except Exception as e:
        return False, f"Could not fill field: {e}"


def click_element(selector: str) -> tuple[bool, str]:
    """Click an element on the current Playwright page."""
    if not _playwright_available or _pw_page is None:
        return False, "No browser page open"
    try:
        _pw_page.click(selector)
        return True, f"Clicked: {selector}"
    except Exception as e:
        return False, f"Could not click element: {e}"


def extract_text(selector: str = "body") -> tuple[bool, str]:
    """Extract text from the current Playwright page."""
    if not _playwright_available or _pw_page is None:
        return False, "No browser page open"
    try:
        text = _pw_page.inner_text(selector)
        if len(text) > 500:
            text = text[:500] + "..."
        return True, text
    except Exception as e:
        return False, f"Could not extract text: {e}"


# ─── Command Router ─────────────────────────────────────

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
        # Try as direct URL
        if "." in site_name:
            ok, msg = open_url(site_name)
            return True, ok, msg

    # "search google for X" / "google X" / "search for X"
    if cmd.startswith("search google ") or cmd.startswith("google ") or cmd.startswith("search for "):
        query = (cmd.replace("search google for ", "")
                 .replace("search google ", "")
                 .replace("google ", "")
                 .replace("search for ", "").strip())
        ok, msg = search_google(query)
        return True, ok, msg

    # "search github for X"
    if "search github" in cmd or "github search" in cmd:
        query = (cmd.replace("search github for ", "")
                 .replace("search github ", "")
                 .replace("github search ", "").strip())
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
        query = (cmd.replace("search youtube for ", "")
                 .replace("search youtube ", "")
                 .replace("youtube search ", "").strip())
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

    # "scrape <url>" — Playwright page scraping
    if cmd.startswith("scrape "):
        url = cmd.replace("scrape ", "").strip()
        if not url.startswith("http"):
            url = "https://" + url
        ok, msg = scrape_page(url)
        return True, ok, msg

    # "screenshot page <url>"
    if cmd.startswith("screenshot page ") or cmd.startswith("capture page "):
        url = cmd.replace("screenshot page ", "").replace("capture page ", "").strip()
        if not url.startswith("http"):
            url = "https://" + url
        ok, msg = take_page_screenshot(url)
        return True, ok, msg

    # "close browser"
    if cmd in ("close browser", "close playwright"):
        _close_playwright()
        return True, True, "Browser closed"

    return False, False, ""
