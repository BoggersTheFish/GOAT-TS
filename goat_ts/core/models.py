"""Data contracts for the v0.1 cognition pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    id: str
    label: str
    provenance: tuple[str, ...]
    activation: float = 0.0
    memory_state: str = "deep"


@dataclass(frozen=True)
class Edge:
    id: str
    source_id: str
    target_id: str
    predicate: str
    wave_id: str
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class Wave:
    id: str
    source: str
    content_hash: str


@dataclass(frozen=True)
class CandidateClaim:
    id: str
    subject: str
    predicate: str
    object: str
    raw_text: str
    parser: str = "bounded-regex-v1"


@dataclass(frozen=True)
class RepairTarget:
    id: str
    reason: str
    raw_text: str
    claim_id: str | None = None


@dataclass(frozen=True)
class Receipt:
    id: str
    version: str
    operation: str
    input: dict[str, Any]
    waves: tuple[Wave, ...] = ()
    candidates: tuple[CandidateClaim, ...] = ()
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    repair_targets: tuple[RepairTarget, ...] = ()
    activation: dict[str, float] = field(default_factory=dict)
    memory: dict[str, str] = field(default_factory=dict)
    tension: dict[str, float] = field(default_factory=dict)
