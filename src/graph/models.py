from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np


class MemoryState(StrEnum):
    ACTIVE = "active"
    DORMANT = "dormant"
    DEEP = "deep"


class NodeType(StrEnum):
    KNOWLEDGE = "knowledge"
    QUESTION = "question"
    HYPOTHESIS = "hypothesis"
    SURPRISE = "surprise"
    EQUATION = "equation"
    CLUSTER = "cluster"
    GOAL = "goal"


@dataclass(slots=True)
class Node:
    node_id: str
    label: str
    node_type: NodeType = NodeType.KNOWLEDGE
    mass: float = 1.0
    activation: float = 0.0
    attention_weight: float = 0.0
    state: MemoryState = MemoryState.DORMANT
    cluster_id: str | None = None
    embedding: list[float] | None = None
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def embedding_array(self) -> np.ndarray | None:
        if self.embedding is None:
            return None
        return np.asarray(self.embedding, dtype=np.float32)

    def position_array(self) -> np.ndarray:
        return np.asarray(self.position, dtype=np.float32)

    def velocity_array(self) -> np.ndarray:
        return np.asarray(self.velocity, dtype=np.float32)

    def to_properties(self) -> dict[str, Any]:
        metadata = dict(self.metadata)
        metadata.setdefault("node_type", self.node_type.value)
        metadata.setdefault("attention_weight", float(self.attention_weight))
        metadata.setdefault("created_at", self.created_at)
        metadata.setdefault("position", list(self.position))
        metadata.setdefault("velocity", list(self.velocity))
        if self.embedding is not None:
            metadata.setdefault("embedding", list(self.embedding))
        return {
            "label": self.label,
            "mass": float(self.mass),
            "activation": float(self.activation),
            "state": self.state.value,
            "cluster_id": self.cluster_id or "",
            "metadata": metadata,
        }


@dataclass(slots=True)
class Edge:
    src_id: str
    dst_id: str
    relation: str = "relates"
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_properties(self) -> dict[str, Any]:
        return {
            "weight": float(self.weight),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class Wave:
    """Cognition graph: one cognitive episode (e.g. ingestion chunk or reasoning pass)."""
    wave_id: str
    label: str
    source: str  # e.g. "ingestion" | "reasoning"
    intensity: float = 0.0
    coherence: float = 0.0
    tension: float = 0.0
    source_chunk_id: str = ""
    created_at: str | None = None  # ISO datetime for long-term self-reflection gap detection

    def to_properties(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "source": self.source,
            "intensity": float(self.intensity),
            "coherence": float(self.coherence),
            "tension": float(self.tension),
            "source_chunk_id": self.source_chunk_id or "",
        }


@dataclass(slots=True)
class Triple:
    subject: str
    relation: str
    object: str
    confidence: float = 1.0
