"""Deterministic JSON receipt writer."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from goat_ts.core.models import Receipt


def receipt_json(receipt: Receipt) -> str:
    return json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n"


def write_receipt(receipt: Receipt, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(receipt_json(receipt), encoding="utf-8")
    return path
