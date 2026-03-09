"""
Long-term self-reflection: time global waves for gaps, generate goal nodes.
Integrate into AGI loop for periodic gap detection and goal creation.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.graph.models import Node, NodeType, Wave

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WaveGap:
    """A detected gap between waves (temporal or index-based)."""
    kind: str  # "time" | "index"
    before_id: str
    after_id: str
    gap_seconds: float | None = None
    gap_index_count: int | None = None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _chunk_index(wave: Wave) -> int | None:
    """Extract numeric chunk index from source_chunk_id (e.g. doc_0 -> 0)."""
    if not wave.source_chunk_id:
        return None
    m = re.search(r"(\d+)$", wave.source_chunk_id.strip())
    return int(m.group(1)) if m else None


def detect_wave_gaps(
    waves: list[Wave],
    *,
    gap_seconds: float | None = None,
    gap_index_count: int = 5,
    now: datetime | None = None,
) -> list[WaveGap]:
    """
    Detect gaps between waves. Two modes:
    - Time: if waves have created_at, gaps where (t[i+1] - t[i]) > gap_seconds.
    - Index: order by chunk index from source_chunk_id; gaps where index diff > gap_index_count.
    Returns list of WaveGap (before_id, after_id, gap size).
    """
    gaps: list[WaveGap] = []
    if not waves:
        return gaps

    now = now or datetime.now(UTC)

    # Time-based: sort by created_at
    with_time = [(w, _parse_iso(w.created_at)) for w in waves if w.created_at]
    if with_time and gap_seconds is not None:
        with_time.sort(key=lambda x: x[1] or datetime.min.replace(tzinfo=UTC))
        for i in range(len(with_time) - 1):
            _, t0 = with_time[i]
            w1, t1 = with_time[i + 1]
            if t0 and t1:
                delta = (t1 - t0).total_seconds()
                if delta > gap_seconds:
                    gaps.append(
                        WaveGap(
                            kind="time",
                            before_id=with_time[i][0].wave_id,
                            after_id=w1.wave_id,
                            gap_seconds=delta,
                        )
                    )
        # Also gap from last wave to now
        last_w, last_t = with_time[-1]
        if last_t and (now - last_t).total_seconds() > gap_seconds:
            gaps.append(
                WaveGap(
                    kind="time",
                    before_id=last_w.wave_id,
                    after_id="",
                    gap_seconds=(now - last_t).total_seconds(),
                )
            )

    # Index-based: waves with numeric source_chunk_id
    with_idx = [(w, _chunk_index(w)) for w in waves if _chunk_index(w) is not None]
    if with_idx and gap_index_count > 0:
        with_idx.sort(key=lambda x: (x[1], x[0].wave_id))
        for i in range(len(with_idx) - 1):
            w0, idx0 = with_idx[i]
            w1, idx1 = with_idx[i + 1]
            missing = idx1 - idx0 - 1
            if missing >= gap_index_count:
                gaps.append(
                    WaveGap(
                        kind="index",
                        before_id=w0.wave_id,
                        after_id=w1.wave_id,
                        gap_index_count=missing,
                    )
                )

    return gaps


def generate_goal_nodes_for_gaps(
    gaps: list[WaveGap],
    *,
    id_to_label: dict[str, str] | None = None,
    max_goals: int = 10,
) -> list[Node]:
    """Turn wave gaps into goal nodes (node_type=GOAL) for the AGI loop to pursue."""
    id_to_label = id_to_label or {}
    goals: list[Node] = []
    for g in gaps[:max_goals]:
        if g.kind == "time":
            label = f"Fill temporal gap: {g.before_id[:12]}... -> next wave (gap {g.gap_seconds:.0f}s)"
        else:
            label = f"Fill index gap: chunks between {g.before_id[:12]}... and {g.after_id[:12]}... ({g.gap_index_count} missing)"
        goal_id = f"goal_{uuid.uuid4().hex[:12]}"
        goals.append(
            Node(
                node_id=goal_id,
                label=label,
                node_type=NodeType.GOAL,
                mass=1.0,
                activation=0.0,
                metadata={"gap_kind": g.kind, "before_id": g.before_id, "after_id": g.after_id},
            )
        )
    return goals


def run_long_term_self_reflection(
    waves: list[Wave],
    *,
    gap_seconds: float | None = 300.0,
    gap_index_count: int = 5,
    max_goal_nodes: int = 10,
    now: datetime | None = None,
) -> tuple[list[WaveGap], list[Node]]:
    """
    One-shot long-term self-reflection: detect wave gaps, return gaps and goal nodes.
    Call from AGI loop periodically (e.g. every N ticks) with client.list_waves().
    """
    gaps = detect_wave_gaps(
        waves,
        gap_seconds=gap_seconds,
        gap_index_count=gap_index_count,
        now=now,
    )
    id_to_label = {w.wave_id: w.label for w in waves}
    goal_nodes = generate_goal_nodes_for_gaps(gaps, id_to_label=id_to_label, max_goals=max_goal_nodes)
    if goal_nodes:
        logger.info("Long-term self-reflection: %d gaps -> %d goal nodes", len(gaps), len(goal_nodes))
    return gaps, goal_nodes
