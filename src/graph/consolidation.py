"""
Memory consolidation: periodic merge of duplicates, prune low-mass (<0.1),
transition states. Optional Redis hot/cold tiering. Schedule with APScheduler.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Callable

from src.graph.models import Edge, MemoryState, Node
from src.memory_manager import apply_decay_and_transitions

logger = logging.getLogger(__name__)

PRUNE_MASS_THRESHOLD = 0.1
REDIS_HOT_TTL = 300
REDIS_COLD_TTL = 3600


def prune_low_mass(
    nodes: list[Node],
    edges: list[Edge],
    *,
    mass_threshold: float = PRUNE_MASS_THRESHOLD,
) -> tuple[list[Node], list[Edge]]:
    """Remove nodes with mass < mass_threshold and any edges incident to them."""
    keep_ids = {n.node_id for n in nodes if float(n.mass) >= mass_threshold}
    out_nodes = [n for n in nodes if n.node_id in keep_ids]
    out_edges = [e for e in edges if e.src_id in keep_ids and e.dst_id in keep_ids]
    return out_nodes, out_edges


def transition_states_consolidation(
    nodes: list[Node],
    *,
    active_threshold: float = 0.5,
    dormant_threshold: float = 0.1,
) -> list[Node]:
    """Apply memory state transitions (active/dormant/deep)."""
    out = []
    for n in nodes:
        a = n.activation
        if a >= active_threshold:
            state = MemoryState.ACTIVE
        elif a < dormant_threshold:
            state = MemoryState.DORMANT if n.state != MemoryState.DEEP else MemoryState.DEEP
        else:
            state = n.state
        out.append(replace(n, state=state))
    return out


def run_consolidation(
    nodes: list[Node],
    edges: list[Edge],
    *,
    merge_duplicates: bool = True,
    merge_threshold: float = 0.8,
    prune_mass: float = PRUNE_MASS_THRESHOLD,
    apply_state_transitions: bool = True,
    decay_rate: float = 0.95,
    config_path: str | None = None,
    noise_filter_min_confidence: float | None = None,
    tension_scores: dict[str, float] | None = None,
    noise_contamination: float = 0.1,
) -> tuple[list[Node], list[Edge]]:
    """
    One consolidation pass: optional noise filter (low-conf + IsolationForest on tensions),
    optional merge (via global_concept_merge), prune low-mass, apply decay and state transitions.
    Returns (updated nodes, updated edges).
    """
    if noise_filter_min_confidence is not None or tension_scores:
        try:
            from src.graph.noise_filter import apply_noise_filter
            nodes, edges = apply_noise_filter(
                nodes, edges,
                min_confidence=noise_filter_min_confidence,
                tension_scores=tension_scores,
                contamination=noise_contamination,
            )
        except Exception as e:
            logger.warning("Noise filter in consolidation failed: %s", e)
    if merge_duplicates and nodes and config_path:
        try:
            from src.graph.cluster_merge import global_concept_merge
            path = Path(config_path) if config_path else None
            nodes, all_edges = global_concept_merge(
                nodes, edges,
                similarity_threshold=merge_threshold,
                config_path=path,
            )
            edges = [e for e in all_edges if e.relation == "relates"]
        except Exception as e:
            logger.warning("Consolidation merge step failed: %s", e)

    nodes, edges = prune_low_mass(nodes, edges, mass_threshold=prune_mass)
    if apply_state_transitions:
        nodes = apply_decay_and_transitions(nodes, decay_rate=decay_rate)
        nodes = transition_states_consolidation(nodes)
    return nodes, edges


def redis_tier_activations(
    node_ids_by_tier: dict[str, list[str]],
    *,
    cache_set: Callable[[str, object, int | None], None],
    hot_ttl: int = REDIS_HOT_TTL,
    cold_ttl: int = REDIS_COLD_TTL,
) -> None:
    """
    Push node id lists to Redis for hot/cold tiering. cache_set(key, value, ttl_s).
    Expects node_ids_by_tier['hot'] and optionally node_ids_by_tier['cold'].
    """
    for tier, ids in node_ids_by_tier.items():
        if not ids:
            continue
        ttl = hot_ttl if tier == "hot" else cold_ttl
        key = f"consolidation:{tier}:nodes"
        try:
            cache_set(key, ids, ttl)
        except Exception as e:
            logger.warning("Redis tier %s failed: %s", tier, e)


def schedule_consolidation(
    interval_seconds: float,
    get_graph: Callable[[], tuple[list[Node], list[Edge]]],
    set_graph: Callable[[list[Node], list[Edge]], None],
    *,
    merge_duplicates: bool = True,
    config_path: str | None = None,
) -> object:
    """
    Return an APScheduler job (callable) that runs consolidation periodically.
    get_graph() -> (nodes, edges); set_graph(nodes, edges) to persist.
    To actually schedule: use apscheduler.schedulers.background.BackgroundScheduler
    and add_job(schedule_consolidation(...), 'interval', seconds=interval_seconds).
    """
    def job() -> None:
        try:
            nodes, edges = get_graph()
            nodes, edges = run_consolidation(
                nodes, edges,
                merge_duplicates=merge_duplicates,
                config_path=config_path,
            )
            set_graph(nodes, edges)
        except Exception as e:
            logger.exception("Scheduled consolidation failed: %s", e)

    return job
