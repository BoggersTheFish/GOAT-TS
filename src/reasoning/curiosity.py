"""
Curiosity-driven exploration: entropy-based rewards, auto-query web or internal search.
Integrate into AGI loop to trigger queries when entropy is high (uncertainty) or low (boredom).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def activation_entropy(activations: dict[str, float], *, bins: int = 10) -> float:
    """
    Entropy of the activation distribution (discretized into bins).
    High entropy = more uniform (uncertain); low = peaked (confident).
    """
    if not activations:
        return 0.0
    vals = np.array(list(activations.values()), dtype=np.float64)
    vals = np.clip(vals, 0.0, 1.0)
    if vals.size == 0:
        return 0.0
    hist, _ = np.histogram(vals, bins=bins, range=(0.0, 1.0))
    probs = hist / max(hist.sum(), 1e-9)
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log(probs + 1e-12)))


def entropy_reward(entropy: float, *, target_entropy: float = 0.5, scale: float = 1.0) -> float:
    """
    Reward that encourages moving toward target_entropy (e.g. moderate uncertainty).
    reward = -scale * (entropy - target_entropy)^2
    """
    return -scale * (entropy - target_entropy) ** 2


def should_trigger_curiosity_query(
    entropy: float,
    *,
    high_threshold: float = 1.5,
    low_threshold: float = 0.3,
) -> tuple[bool, str]:
    """
    Decide whether to trigger a curiosity-driven query. Returns (trigger, reason).
    High entropy -> "explore to resolve uncertainty"; low -> "explore to avoid boredom".
    """
    if entropy >= high_threshold:
        return True, "high_uncertainty"
    if entropy <= low_threshold:
        return True, "low_diversity"
    return False, ""


def curiosity_query(
    query: str,
    config_root: Path,
    *,
    live: bool = False,
    api_key: str | None = None,
    max_results: int = 5,
) -> dict:
    """
    Run a curiosity-driven query: web search + optional extraction.
    Uses query_handler.handle_query when available.
    """
    try:
        from src.graph.query_handler import handle_query
        stats = handle_query(
            query,
            config_root,
            live=live,
            extract_triples=True,
            insert_linked_waves=True,
            api_key=api_key,
        )
        return {"triggered": True, "stats": stats, "query": query}
    except ImportError:
        logger.debug("query_handler not available for curiosity_query")
    try:
        from src.graph.query_handler import search_and_fetch
        snippets = search_and_fetch(query, max_results=max_results, api_key=api_key)
        return {"triggered": True, "snippets": len(snippets), "query": query}
    except ImportError:
        pass
    return {"triggered": False, "query": query}
