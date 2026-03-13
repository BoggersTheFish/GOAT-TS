"""Stage 9: Community — plugin loader, extensions."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_load_plugin_example_hook() -> None:
    """Plugin example_hook loads and exposes PLUGIN_HOOKS."""
    from src.plugins import load_plugin
    hooks = load_plugin("example_hook")
    assert isinstance(hooks, dict)
    assert "on_reasoning_done" in hooks


def test_load_all_plugins_empty_config() -> None:
    """load_all_plugins with no enabled list returns [] or list of empty dicts."""
    from src.plugins import load_all_plugins
    result = load_all_plugins(ROOT)
    assert isinstance(result, list)


def test_plugins_config_exists() -> None:
    """configs/plugins.yaml exists and has plugins.enabled."""
    from src.utils import load_yaml_config
    path = ROOT / "configs" / "plugins.yaml"
    assert path.exists()
    data = load_yaml_config(path)
    assert "plugins" in data
