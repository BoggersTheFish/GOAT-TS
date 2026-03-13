"""
Stage 9: Plugin loader — config-driven optional modules.
Config key: plugins.enabled = [ "plugin_name" ] in configs/plugins.yaml.
Each plugin is a module under src/plugins/ or a dotted path; we call load_plugin(name) to get a dict of hooks.
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_loaded: dict[str, dict[str, Any]] = {}


def load_plugin(name: str, config_root: Path | None = None) -> dict[str, Any]:
    """
    Load a plugin by name. Returns a dict of optional hooks, e.g. {"on_reasoning_done": callable}.
    If the module is not found or has no PLUGIN_HOOKS, returns {}.
    """
    if name in _loaded:
        return _loaded[name]
    try:
        mod = importlib.import_module(f"src.plugins.{name}")
    except ImportError:
        try:
            mod = importlib.import_module(name)
        except ImportError as e:
            logger.debug("Plugin %s not found: %s", name, e)
            _loaded[name] = {}
            return {}
    hooks = getattr(mod, "PLUGIN_HOOKS", None)
    if not isinstance(hooks, dict):
        _loaded[name] = {}
        return {}
    _loaded[name] = hooks
    return hooks


def load_all_plugins(config_root: Path) -> list[dict[str, Any]]:
    """Load all plugins listed in configs/plugins.yaml (key: plugins.enabled)."""
    config_path = config_root / "configs" / "plugins.yaml"
    if not config_path.exists():
        return []
    try:
        from src.utils import load_yaml_config
        data = load_yaml_config(config_path)
        enabled = data.get("plugins", {}).get("enabled") or []
    except Exception:
        return []
    out = []
    for name in enabled:
        if isinstance(name, str):
            out.append(load_plugin(name, config_root))
    return out
