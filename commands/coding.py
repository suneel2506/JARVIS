"""
commands/coding.py — Developer assistant commands for J.A.R.V.I.S.

Git operations, script execution, project scaffolding, and IDE integration.
"""
import os
import subprocess

from core.logger import get_logger

log = get_logger("commands.coding")


def _run_shell(cmd: str, cwd: str = None) -> tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=30, cwd=cwd,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            return True, output or "Command executed successfully"
        else:
            return False, output or f"Command failed with code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 30 seconds"
    except Exception as e:
        return False, f"Error: {e}"


# ─── Git Operations ─────────────────────────────────────

def git_status() -> tuple[bool, str]:
    """Run git status in the current directory."""
    ok, output = _run_shell("git status --short")
    if ok:
        if not output:
            return True, "Working tree is clean. No changes."
        lines = output.split('\n')
        return True, f"{len(lines)} file{'s' if len(lines) != 1 else ''} changed. {output[:200]}"
    return False, output


def git_commit(message: str = "Auto-commit by JARVIS") -> tuple[bool, str]:
    """Stage all changes and commit."""
    ok1, out1 = _run_shell("git add -A")
    if not ok1:
        return False, f"Git add failed: {out1}"
    ok2, out2 = _run_shell(f'git commit -m "{message}"')
    if ok2:
        log.info("Git commit: %s", message)
        return True, f"Committed: {message}"
    return False, out2


def git_push() -> tuple[bool, str]:
    """Push to the current branch."""
    ok, output = _run_shell("git push")
    if ok:
        log.info("Git push successful")
        return True, "Pushed successfully"
    return False, output


def git_pull() -> tuple[bool, str]:
    """Pull from the remote."""
    ok, output = _run_shell("git pull")
    if ok:
        return True, "Pull completed. " + output[:100]
    return False, output


def git_log(count: int = 5) -> tuple[bool, str]:
    """Show recent git log."""
    ok, output = _run_shell(f"git log --oneline -n {count}")
    if ok:
        return True, f"Recent commits:\n{output}"
    return False, output


def git_diff() -> tuple[bool, str]:
    """Show current diff summary."""
    ok, output = _run_shell("git diff --stat")
    if ok:
        return True, output[:300] if output else "No differences"
    return False, output


def git_branch() -> tuple[bool, str]:
    """Show current branch."""
    ok, output = _run_shell("git branch --show-current")
    if ok:
        return True, f"Current branch: {output}"
    return False, output


# ─── Script Execution ───────────────────────────────────

def run_python_script(script_path: str) -> tuple[bool, str]:
    """Run a Python script."""
    if not os.path.exists(script_path):
        # Try looking in common locations
        for prefix in (".", os.path.expanduser("~"), os.path.expanduser("~/Desktop")):
            full = os.path.join(prefix, script_path)
            if os.path.exists(full):
                script_path = full
                break
        else:
            return False, f"Script not found: {script_path}"

    ok, output = _run_shell(f'python "{script_path}"')
    log.info("Ran script: %s (success=%s)", script_path, ok)
    if ok:
        return True, f"Script output: {output[:300]}"
    return False, f"Script error: {output[:300]}"


def run_command_line(cmd_text: str) -> tuple[bool, str]:
    """Run an arbitrary command and return output."""
    ok, output = _run_shell(cmd_text)
    log.info("Ran command: %s (success=%s)", cmd_text[:50], ok)
    return ok, output[:300]


# ─── Project Creation ───────────────────────────────────

def create_python_project(name: str) -> tuple[bool, str]:
    """Create a basic Python project structure."""
    base = os.path.join(os.path.expanduser("~"), "Documents", name)
    try:
        os.makedirs(os.path.join(base, "src"), exist_ok=True)
        os.makedirs(os.path.join(base, "tests"), exist_ok=True)

        # Create main.py
        with open(os.path.join(base, "src", "main.py"), "w") as f:
            f.write(f'"""\n{name} — Main entry point\n"""\n\n\ndef main():\n    print("Hello from {name}!")\n\n\nif __name__ == "__main__":\n    main()\n')

        # Create __init__.py
        with open(os.path.join(base, "src", "__init__.py"), "w") as f:
            f.write("")

        # Create requirements.txt
        with open(os.path.join(base, "requirements.txt"), "w") as f:
            f.write("# Project dependencies\n")

        # Create README
        with open(os.path.join(base, "README.md"), "w") as f:
            f.write(f"# {name}\n\nCreated by J.A.R.V.I.S.\n")

        # Create .gitignore
        with open(os.path.join(base, ".gitignore"), "w") as f:
            f.write("__pycache__/\n*.pyc\n.venv/\n.env\n")

        log.info("Created Python project: %s", base)
        return True, f"Python project created at {base}"
    except Exception as e:
        return False, f"Failed to create project: {e}"


# ─── Command Router ─────────────────────────────────────

def handle_coding_command(command: str) -> tuple[bool, bool, str]:
    """
    Route developer/coding commands.
    Returns (handled, success, message)
    """
    cmd = command.lower().strip()

    # Git operations
    if cmd in ("git status", "check git", "git changes"):
        ok, msg = git_status()
        return True, ok, msg
    if cmd.startswith("git commit"):
        msg_text = cmd.replace("git commit", "").strip()
        if not msg_text:
            msg_text = "Auto-commit by JARVIS"
        ok, msg = git_commit(msg_text)
        return True, ok, msg
    if cmd in ("git push", "push code", "push to github"):
        ok, msg = git_push()
        return True, ok, msg
    if cmd in ("git pull", "pull code", "pull from github"):
        ok, msg = git_pull()
        return True, ok, msg
    if cmd in ("git log", "show commits", "recent commits"):
        ok, msg = git_log()
        return True, ok, msg
    if cmd in ("git diff", "show diff", "show changes"):
        ok, msg = git_diff()
        return True, ok, msg
    if cmd in ("git branch", "current branch", "which branch"):
        ok, msg = git_branch()
        return True, ok, msg

    # Run scripts
    if cmd.startswith("run python ") or cmd.startswith("run script "):
        script = cmd.replace("run python ", "").replace("run script ", "").strip()
        ok, msg = run_python_script(script)
        return True, ok, msg

    if cmd.startswith("run command ") or cmd.startswith("execute "):
        shell_cmd = cmd.replace("run command ", "").replace("execute ", "").strip()
        ok, msg = run_command_line(shell_cmd)
        return True, ok, msg

    # Project creation
    if cmd.startswith("create python project ") or cmd.startswith("create project "):
        name = cmd.replace("create python project ", "").replace("create project ", "").strip()
        if name:
            ok, msg = create_python_project(name)
            return True, ok, msg

    # Open IDE
    if cmd in ("open terminal here", "open terminal", "new terminal"):
        os.system("start wt")
        return True, True, "Opening Windows Terminal"

    return False, False, ""
