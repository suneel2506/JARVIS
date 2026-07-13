"""
core/workflow.py — Workflow chaining engine for J.A.R.V.I.S.

Enables multi-step command execution through:
1. Sequential chaining: "do X and then Y and then Z"
2. Named workflows: predefined multi-step sequences
3. AI-powered decomposition: breaking complex requests into steps
"""
import time
import threading
from typing import Optional, Callable

from core.logger import get_logger
from core.speaker import speak

log = get_logger("core.workflow")

# ─── Pre-built Workflow Templates ───────────────────────

WORKFLOW_TEMPLATES: dict[str, dict] = {
    "morning routine": {
        "description": "Start your day",
        "steps": [
            "what time is it",
            "weather",
            "news",
            "show my to do list",
        ],
    },
    "coding setup": {
        "description": "Set up for coding",
        "steps": [
            "open visual studio code",
            "open terminal here",
            "git status",
        ],
    },
    "presentation mode": {
        "description": "Prepare for a presentation",
        "steps": [
            "set brightness 100",
            "volume 50",
            "open powerpoint",
        ],
    },
    "night routine": {
        "description": "Wind down for the night",
        "steps": [
            "what time is it",
            "set brightness 20",
            "volume 20",
        ],
    },
    "system check": {
        "description": "Full system health check",
        "steps": [
            "system status",
            "cpu usage",
            "ram",
            "disk space",
            "battery",
            "check internet",
            "check ping",
        ],
    },
}


def get_workflow_templates() -> dict[str, dict]:
    """Get all available workflow templates."""
    return WORKFLOW_TEMPLATES


# ─── Multi-step Command Parsing ─────────────────────────

_CHAIN_KEYWORDS = [
    " and then ",
    " then ",
    " after that ",
    " also ",
    " followed by ",
    " next ",
]


def is_chained_command(command: str) -> bool:
    """Check if a command contains chaining keywords."""
    cmd_lower = command.lower()
    for keyword in _CHAIN_KEYWORDS:
        if keyword in cmd_lower:
            return True
    return False


def split_chained_command(command: str) -> list[str]:
    """
    Split a chained command into individual steps.
    'open chrome and then search for python tutorials' → ['open chrome', 'search for python tutorials']
    """
    import re
    # Build regex pattern from chain keywords
    pattern = '|'.join(re.escape(kw.strip()) for kw in _CHAIN_KEYWORDS)
    parts = re.split(pattern, command, flags=re.IGNORECASE)
    steps = [s.strip() for s in parts if s.strip()]
    return steps


# ─── Workflow Execution ─────────────────────────────────

_active_workflow: Optional[dict] = None
_workflow_lock = threading.Lock()


def execute_workflow(steps: list[str], executor_fn: Callable, name: str = "Custom") -> None:
    """
    Execute a sequence of commands with delays between them.

    Args:
        steps: List of command strings to execute.
        executor_fn: The execute() function from core.executor.
        name: Workflow name for logging.
    """
    global _active_workflow

    with _workflow_lock:
        _active_workflow = {
            "name": name,
            "steps": steps,
            "current": 0,
            "total": len(steps),
        }

    log.info("Starting workflow '%s' with %d steps", name, len(steps))
    speak(f"Running {name} workflow. {len(steps)} steps.")

    for i, step in enumerate(steps):
        with _workflow_lock:
            if _active_workflow is None:
                log.info("Workflow cancelled")
                speak("Workflow cancelled")
                return
            _active_workflow["current"] = i + 1

        log.info("Workflow step %d/%d: %s", i + 1, len(steps), step)
        try:
            result = executor_fn(step)
            if result == "exit":
                break
        except Exception as e:
            log.error("Workflow step failed: %s — %s", step, e)
            speak(f"Step failed: {step}")

        if i < len(steps) - 1:
            time.sleep(1.5)  # Pause between steps

    with _workflow_lock:
        _active_workflow = None

    log.info("Workflow '%s' completed", name)
    speak(f"{name} workflow completed")


def cancel_workflow() -> bool:
    """Cancel the currently running workflow."""
    global _active_workflow
    with _workflow_lock:
        if _active_workflow:
            _active_workflow = None
            return True
    return False


def get_active_workflow() -> Optional[dict]:
    """Get info about the currently running workflow."""
    with _workflow_lock:
        return dict(_active_workflow) if _active_workflow else None


# ─── Command Handler ────────────────────────────────────

def handle_workflow_command(command: str, executor_fn: Callable) -> tuple[bool, str]:
    """
    Handle workflow-related commands.

    Args:
        command: The command string.
        executor_fn: The execute() function to run steps.

    Returns:
        (handled, message)
    """
    cmd = command.lower().strip()

    # Run a named workflow template
    for name, template in WORKFLOW_TEMPLATES.items():
        if name in cmd or (cmd.startswith("run ") and name in cmd.replace("run ", "")):
            steps = template["steps"]
            threading.Thread(
                target=execute_workflow,
                args=(steps, executor_fn, name.title()),
                daemon=True,
            ).start()
            return True, f"Starting {name} workflow"

    # List available workflows
    if cmd in ("list workflows", "show workflows", "available workflows"):
        names = list(WORKFLOW_TEMPLATES.keys())
        return True, "Available workflows: " + ", ".join(names)

    # Cancel workflow
    if cmd in ("cancel workflow", "stop workflow"):
        if cancel_workflow():
            return True, "Workflow cancelled"
        return True, "No workflow is running"

    # Check if it's a chained command
    if is_chained_command(command):
        steps = split_chained_command(command)
        if len(steps) > 1:
            threading.Thread(
                target=execute_workflow,
                args=(steps, executor_fn, "Chained Command"),
                daemon=True,
            ).start()
            return True, f"Running {len(steps)} steps"

    return False, ""
