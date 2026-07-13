"""
commands/communication.py — Communication app launcher for J.A.R.V.I.S.

Social media, messaging, email, and collaboration tools.
"""
import os
import webbrowser

from core.logger import get_logger

log = get_logger("commands.communication")

# Communication apps and their launch methods
COMM_APPS: dict[str, dict] = {
    # Messaging
    "whatsapp": {"url": "https://web.whatsapp.com", "app": "start whatsapp:"},
    "telegram": {"url": "https://web.telegram.org", "app": "start telegram:"},
    "discord": {"url": "https://discord.com/app", "app": "start discord:"},
    "slack": {"url": "https://app.slack.com", "app": "start slack:"},
    "signal": {"url": "https://signal.org", "app": "start signal:"},
    "teams": {"url": "https://teams.microsoft.com", "app": "start msteams:"},
    "zoom": {"url": "https://zoom.us/join", "app": "start zoommtg:"},
    "skype": {"url": "https://web.skype.com", "app": "start skype:"},

    # Email
    "gmail": {"url": "https://mail.google.com"},
    "outlook": {"url": "https://outlook.live.com", "app": "start outlook"},
    "yahoo mail": {"url": "https://mail.yahoo.com"},
    "protonmail": {"url": "https://mail.proton.me"},

    # Social Media
    "twitter": {"url": "https://twitter.com"},
    "x": {"url": "https://x.com"},
    "instagram": {"url": "https://www.instagram.com"},
    "facebook": {"url": "https://www.facebook.com"},
    "linkedin": {"url": "https://www.linkedin.com"},
    "reddit": {"url": "https://www.reddit.com"},
    "pinterest": {"url": "https://www.pinterest.com"},
    "tiktok": {"url": "https://www.tiktok.com"},
    "snapchat": {"url": "https://www.snapchat.com"},
    "threads": {"url": "https://www.threads.net"},

    # Collaboration
    "notion": {"url": "https://www.notion.so"},
    "trello": {"url": "https://trello.com"},
    "asana": {"url": "https://app.asana.com"},
    "jira": {"url": "https://www.atlassian.com/software/jira"},
    "figma": {"url": "https://www.figma.com"},
    "miro": {"url": "https://miro.com"},

    # AI
    "chatgpt": {"url": "https://chat.openai.com"},
    "claude": {"url": "https://claude.ai"},
    "gemini": {"url": "https://gemini.google.com"},
    "perplexity": {"url": "https://www.perplexity.ai"},

    # Cloud / Productivity
    "google drive": {"url": "https://drive.google.com"},
    "google docs": {"url": "https://docs.google.com"},
    "google sheets": {"url": "https://sheets.google.com"},
    "dropbox": {"url": "https://www.dropbox.com"},
    "onedrive": {"url": "https://onedrive.live.com"},
}


def open_communication_app(app_name: str) -> tuple[bool, str]:
    """Open a communication/social app by name."""
    app_lower = app_name.lower().strip()

    for key, config in COMM_APPS.items():
        if key in app_lower or app_lower in key:
            # Try native app first
            if "app" in config:
                try:
                    os.system(config["app"])
                    log.info("Opened native app: %s", key)
                    return True, f"Opening {key.title()}"
                except Exception:
                    pass

            # Fall back to web
            if "url" in config:
                webbrowser.open(config["url"])
                log.info("Opened in browser: %s", key)
                return True, f"Opening {key.title()} in browser"

    return False, f"I don't know how to open {app_name}"


def compose_email() -> tuple[bool, str]:
    """Open Gmail compose window."""
    webbrowser.open("https://mail.google.com/mail/u/0/#inbox?compose=new")
    return True, "Opening Gmail compose window"


def handle_communication_command(command: str) -> tuple[bool, bool, str]:
    """
    Route communication commands.
    Returns (handled, success, message)
    """
    cmd = command.lower().strip()

    # Compose email
    if "compose email" in cmd or "write email" in cmd or "new email" in cmd or "send email" in cmd:
        ok, msg = compose_email()
        return True, ok, msg

    # Check if command mentions a known communication app
    for key in COMM_APPS:
        if key in cmd:
            ok, msg = open_communication_app(key)
            return True, ok, msg

    return False, False, ""
