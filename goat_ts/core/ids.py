"""Deterministic identifiers for GOAT-TS entities."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def normalize_text(value: str) -> str:
    """Return a stable, human-text normalization used for identity."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def deterministic_id(kind: str, *parts: Any) -> str:
    """Build a deterministic UUID-shaped ID from canonical JSON."""
    payload = json.dumps(
        [normalize_text(kind), *parts],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:]}"


def node_id(label: str) -> str:
    return deterministic_id("node", normalize_text(label))


def wave_id(source: str, content: str) -> str:
    return deterministic_id("wave", normalize_text(source), content)


def claim_id(subject: str, predicate: str, object_: str, raw_text: str) -> str:
    return deterministic_id(
        "claim",
        normalize_text(subject),
        normalize_text(predicate),
        normalize_text(object_),
        raw_text.strip(),
    )
