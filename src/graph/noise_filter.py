"""
Noise reduction: discard low-confidence nodes/triples; IsolationForest on tensions
to flag outliers; prune in consolidation.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from src.graph.models import Edge, Node

logger = logging.getLogger(__name__)

DEFAULT_MIN_CONFIDENCE = 0.5


def filter_low_confidence(
    nodes: list[Node],
    edges: list[Edge],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    confidence_key: str = "confidence",
) -> tuple[list[Node], list[Edge]]:
    """
    Discard nodes whose metadata confidence (or edge-incident confidence) is below threshold.
    Edges incident to removed nodes are dropped. If nodes have no confidence, keep all.
    """
    if min_confidence <= 0:
        return nodes, edges
    keep_ids: set[str] = set()
    for n in nodes:
        conf = n.metadata.get(confidence_key)
        if conf is None:
            keep_ids.add(n.node_id)
        elif float(conf) >= min_confidence:
            keep_ids.add(n.node_id)
    if not keep_ids and any(n.metadata.get(confidence_key) is not None for n in nodes):
        return [], []
    if keep_ids == set(n.node_id for n in nodes):
        return nodes, edges
    out_nodes = [n for n in nodes if n.node_id in keep_ids]
    out_edges = [e for e in edges if e.src_id in keep_ids and e.dst_id in keep_ids]
    return out_nodes, out_edges


def tension_outliers_isolation_forest(
    tension_scores: list[float],
    *,
    contamination: float = 0.1,
) -> list[bool]:
    """
    Run IsolationForest on tension scores; return list of is_inlier (True = keep, False = outlier).
    Outliers can be pruned or downweighted in consolidation.
    """
    if len(tension_scores) < 2:
        return [True] * len(tension_scores)
    try:
        from sklearn.ensemble import IsolationForest
        import numpy as np
        X = np.array(tension_scores, dtype=np.float64).reshape(-1, 1)
        clf = IsolationForest(contamination=contamination, random_state=42)
        pred = clf.fit_predict(X)
        return [bool(p == 1) for p in pred]
    except ImportError:
        return [True] * len(tension_scores)
    except Exception as e:
        logger.warning("IsolationForest failed: %s", e)
        return [True] * len(tension_scores)


def filter_tension_outliers(
    nodes: list[Node],
    edges: list[Edge],
    tension_by_node_or_wave: dict[str, float],
    *,
    contamination: float = 0.1,
) -> tuple[list[Node], list[Edge]]:
    """
    Label entities (node_id or wave_id) by tension; run IsolationForest to mark outliers;
    remove nodes (or waves) that are tension outliers. tension_by_node_or_wave: id -> tension score.
    """
    ids = list(tension_by_node_or_wave.keys())
    scores = [tension_by_node_or_wave[i] for i in ids]
    inlier = tension_outliers_isolation_forest(scores, contamination=contamination)
    keep_ids = {ids[i] for i in range(len(ids)) if inlier[i]}
    out_nodes = [n for n in nodes if n.node_id in keep_ids]
    out_edges = [e for e in edges if e.src_id in keep_ids and e.dst_id in keep_ids]
    return out_nodes, out_edges


def apply_noise_filter(
    nodes: list[Node],
    edges: list[Edge],
    *,
    min_confidence: float | None = DEFAULT_MIN_CONFIDENCE,
    tension_scores: dict[str, float] | None = None,
    contamination: float = 0.1,
) -> tuple[list[Node], list[Edge]]:
    """
    Apply low-confidence filter (when min_confidence > 0), then optionally tension
    IsolationForest outlier removal. Returns (filtered nodes, filtered edges).
    Use before or inside consolidation.
    """
    if min_confidence is not None and min_confidence > 0:
        nodes, edges = filter_low_confidence(nodes, edges, min_confidence=min_confidence)
    if tension_scores:
        nodes, edges = filter_tension_outliers(
            nodes, edges, tension_scores, contamination=contamination
        )
    return nodes, edges
