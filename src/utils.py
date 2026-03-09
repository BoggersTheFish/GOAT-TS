from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file into a dictionary."""
    resolved_path = Path(path)
    with resolved_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
