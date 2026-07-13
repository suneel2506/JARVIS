"""
plugins/example_plugin.py — Example J.A.R.V.I.S. plugin.

Demonstrates the plugin contract. To create your own plugin:
1. Create a .py file in the plugins/ directory
2. Define a register() function that returns a descriptor dict
3. Implement a handle(command) function for command routing

JARVIS will auto-discover and load this plugin on startup.
"""


def handle(command: str) -> tuple[bool, bool, str]:
    """
    Handle commands for this plugin.

    Args:
        command: The voice/text command to handle.

    Returns:
        (handled, success, message)
    """
    cmd = command.lower().strip()

    if cmd in ("hello plugin", "test plugin"):
        return True, True, "Hello from the example plugin! I'm working correctly."

    if cmd == "plugin info":
        return True, True, "This is the example plugin for JARVIS. Create your own plugins in the plugins folder."

    return False, False, ""


def register() -> dict:
    """
    Register this plugin with JARVIS.

    Returns a descriptor dict with:
    - name: Display name
    - description: What the plugin does
    - commands: List of example commands
    - handle: The command handler function
    """
    return {
        "name": "Example Plugin",
        "description": "Demonstrates the JARVIS plugin system",
        "commands": ["hello plugin", "test plugin", "plugin info"],
        "handle": handle,
    }
