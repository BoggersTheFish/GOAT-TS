"""
Example plugin: exposes a no-op hook for testing the plugin loader.
"""
from __future__ import annotations

PLUGIN_HOOKS = {
    "on_reasoning_done": lambda result: None,
}
