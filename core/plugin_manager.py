"""
core/plugin_manager.py — Plugin system for J.A.R.V.I.S.

Discovers, loads, and manages plugins from the plugins/ directory.
Each plugin is a Python module with a register() function that returns
a plugin descriptor dict.

Plugin contract:
    def register() -> dict:
        return {
            "name": "My Plugin",
            "description": "Does cool things",
            "commands": ["cool stuff", "do thing"],
            "handle": handle_function,  # (cmd: str) -> (handled: bool, ok: bool, msg: str)
        }
"""
import os
import importlib
import importlib.util
import threading
from typing import Any

from core.logger import get_logger

log = get_logger("core.plugin_manager")

_plugins: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def discover_plugins(plugins_dir: str = None) -> list[str]:
    """
    Scan the plugins directory for Python modules with register() functions.

    Returns:
        List of discovered plugin names.
    """
    if plugins_dir is None:
        from config.config import BASE_DIR
        plugins_dir = os.path.join(BASE_DIR, "plugins")

    if not os.path.isdir(plugins_dir):
        os.makedirs(plugins_dir, exist_ok=True)
        log.info("Created plugins directory: %s", plugins_dir)
        return []

    discovered = []
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            plugin_name = filename[:-3]
            discovered.append(plugin_name)

    log.info("Discovered %d plugin(s): %s", len(discovered), discovered)
    return discovered


def load_plugin(name: str, plugins_dir: str = None) -> bool:
    """
    Load a single plugin by name.

    Returns:
        True if loaded successfully, False otherwise.
    """
    if plugins_dir is None:
        from config.config import BASE_DIR
        plugins_dir = os.path.join(BASE_DIR, "plugins")

    filepath = os.path.join(plugins_dir, f"{name}.py")
    if not os.path.exists(filepath):
        log.warning("Plugin file not found: %s", filepath)
        return False

    try:
        spec = importlib.util.spec_from_file_location(f"plugins.{name}", filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, 'register'):
            log.warning("Plugin '%s' has no register() function — skipped", name)
            return False

        descriptor = module.register()
        if not isinstance(descriptor, dict) or 'name' not in descriptor:
            log.warning("Plugin '%s' register() returned invalid descriptor", name)
            return False

        descriptor["module"] = module
        descriptor["enabled"] = True
        descriptor["file"] = filepath

        with _lock:
            _plugins[name] = descriptor

        log.info("Loaded plugin: %s — %s", descriptor['name'], descriptor.get('description', ''))
        return True
    except Exception as e:
        log.error("Failed to load plugin '%s': %s", name, e)
        return False


def load_all_plugins() -> int:
    """
    Discover and load all plugins.

    Returns:
        Number of successfully loaded plugins.
    """
    names = discover_plugins()
    loaded = 0
    for name in names:
        if load_plugin(name):
            loaded += 1
    return loaded


def get_plugins() -> dict[str, dict]:
    """Get all loaded plugins."""
    with _lock:
        return dict(_plugins)


def get_plugin(name: str) -> dict | None:
    """Get a specific plugin's descriptor."""
    with _lock:
        return _plugins.get(name)


def enable_plugin(name: str) -> bool:
    """Enable a plugin."""
    with _lock:
        if name in _plugins:
            _plugins[name]["enabled"] = True
            log.info("Plugin enabled: %s", name)
            return True
    return False


def disable_plugin(name: str) -> bool:
    """Disable a plugin (keeps it loaded but inactive)."""
    with _lock:
        if name in _plugins:
            _plugins[name]["enabled"] = False
            log.info("Plugin disabled: %s", name)
            return True
    return False


def unload_plugin(name: str) -> bool:
    """Completely unload a plugin."""
    with _lock:
        if name in _plugins:
            del _plugins[name]
            log.info("Plugin unloaded: %s", name)
            return True
    return False


def handle_plugin_commands(command: str) -> tuple[bool, bool, str]:
    """
    Route a command through all enabled plugins.

    Returns:
        (handled, success, message)
    """
    with _lock:
        plugins = list(_plugins.values())

    for plugin in plugins:
        if not plugin.get("enabled", True):
            continue

        handler = plugin.get("handle")
        if handler is None:
            continue

        try:
            result = handler(command)
            if result and result[0]:  # handled
                return result
        except Exception as e:
            log.error("Plugin '%s' handler error: %s", plugin.get('name', '?'), e)

    return False, False, ""


def list_plugin_info() -> str:
    """Get a human-readable summary of all plugins."""
    with _lock:
        if not _plugins:
            return "No plugins loaded"
        lines = []
        for name, p in _plugins.items():
            status = "✓" if p.get("enabled", True) else "✗"
            lines.append(f"{status} {p['name']}: {p.get('description', 'No description')}")
        return "\n".join(lines)
