"""
Goal generation: from tensions produce prioritized questions for the AGI loop to pursue.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.reasoning.tension import TensionResult


@dataclass(slots=True)
class PrioritizedQuestion:
    """A question with priority score (higher = more important)."""
    question: str
    priority: float
    source: str  # e.g. "tension_pair"
    ref_src: str | None = None
    ref_dst: str | None = None


def tensions_to_prioritized_questions(
    tension: TensionResult,
    *,
    id_to_label: dict[str, str] | None = None,
    max_questions: int = 10,
    min_tension_delta: float = 0.0,
) -> list[PrioritizedQuestion]:
    """
    Convert high-tension pairs into prioritized questions. Priority = tension delta (higher = more urgent).
    id_to_label maps node_id -> label for readable questions.
    """
    id_to_label = id_to_label or {}
    out: list[PrioritizedQuestion] = []
    for src, dst, delta in tension.high_tension_pairs:
        if delta < min_tension_delta:
            continue
        if len(out) >= max_questions:
            break
        src_label = id_to_label.get(src, src)
        dst_label = id_to_label.get(dst, dst)
        question = (
            f"What explains the tension or conflict between {src_label} and {dst_label}?"
        )
        out.append(
            PrioritizedQuestion(
                question=question,
                priority=float(delta),
                source="tension_pair",
                ref_src=src,
                ref_dst=dst,
            )
        )
    return out


def goals_from_tension(
    tension: TensionResult,
    *,
    id_to_label: dict[str, str] | None = None,
    top_k: int = 5,
) -> list[str]:
    """
    Return a list of question strings (for curiosity/query_handler) from tension.
    Sorted by priority descending.
    """
    pq = tensions_to_prioritized_questions(
        tension,
        id_to_label=id_to_label,
        max_questions=top_k,
    )
    return [q.question for q in pq]
