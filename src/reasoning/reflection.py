"""
Self-reflection: post-propagation compute tension, spawn meta-waves (LLM hypothesize
e.g. "merge X/Y?"), and store hypothesis nodes. Integrate after wave propagation.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.graph.cognition import EDGE_IN_WAVE, WAVE_SOURCE_REFLECTION
from src.graph.models import Edge, Node, NodeType, Wave
from src.reasoning.tension import TensionResult, compute_tension

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReflectionResult:
    meta_waves: list[Wave]
    hypothesis_nodes: list[Node]
    in_wave_edges: list[Edge]
    tension: TensionResult


def _build_positions_and_expected(
    nodes: list[Node],
    edges: list[Edge],
    *,
    cap: int = 50,
) -> tuple[dict[str, np.ndarray], dict[tuple[str, str], float]]:
    """Build positions (by node_id) and expected distances for tension. Uses node positions or index fallback."""
    node_ids = [n.node_id for n in nodes]
    if cap and len(node_ids) > cap:
        node_ids = node_ids[:cap]
    positions = {}
    for i, nid in enumerate(node_ids):
        node = next((n for n in nodes if n.node_id == nid), None)
        if node and node.position:
            positions[nid] = np.asarray(node.position[:3], dtype=np.float32)
        else:
            positions[nid] = np.array([float(i), float(i) * 0.5, 0.0], dtype=np.float32)
    expected: dict[tuple[str, str], float] = {}
    id_to_node = {n.node_id: n for n in nodes}
    for e in edges:
        if e.relation != "relates" or e.src_id not in positions or e.dst_id not in positions:
            continue
        expected[(e.src_id, e.dst_id)] = max(0.25, 1.0 / max(float(e.weight), 0.01))
    for i in range(len(node_ids) - 1):
        a, b = node_ids[i], node_ids[i + 1]
        if (a, b) not in expected:
            expected[(a, b)] = 1.0
    return positions, expected


def _hypothesize_merge_prompts(tension: TensionResult, nodes: list[Node], limit: int = 5) -> list[str]:
    """From high-tension pairs (src, dst, delta), build prompts like 'merge X/Y?' using node labels."""
    id_to_label = {n.node_id: n.label for n in nodes}
    prompts: list[str] = []
    for src, dst, delta in tension.high_tension_pairs[:limit]:
        # tension uses labels in loop.py but we may get node_ids here; support both
        src_label = id_to_label.get(src, src)
        dst_label = id_to_label.get(dst, dst)
        prompts.append(f"merge {src_label} / {dst_label}?")
    return prompts


def run_reflection(
    nodes: list[Node],
    edges: list[Edge],
    tension: TensionResult | None = None,
    *,
    llm_config_path: Path | str | None = None,
    hypothesis_limit: int = 5,
    create_meta_wave: bool = True,
) -> ReflectionResult:
    """
    Post-propagation: compute tension (if not provided), spawn meta-waves and hypothesis nodes.
    If llm_config_path is set, optionally use LLM to generate merge hypotheses; else use
    _hypothesize_merge_prompts from high-tension pairs. Returns meta_waves, hypothesis_nodes, in_wave_edges.
    """
    if tension is None:
        positions, expected = _build_positions_and_expected(nodes, edges)
        tension = compute_tension(positions, expected)

    prompts = _hypothesize_merge_prompts(tension, nodes, limit=hypothesis_limit)
    if llm_config_path:
        try:
            from src.ingestion.llm_extract import TripleExtractor
            extractor = TripleExtractor(llm_config_path)
            extended: list[str] = []
            for p in prompts:
                try:
                    terms = extractor.suggest_search_terms(p, max_terms=3)
                    if terms:
                        extended.append(p + " " + " ".join(terms[:2]))
                    else:
                        extended.append(p)
                except Exception:
                    extended.append(p)
            prompts = extended[: hypothesis_limit]
        except Exception as e:
            logger.warning("LLM reflection fallback: %s", e)

    hypothesis_nodes: list[Node] = []
    wave_id = "meta_" + hashlib.sha256(str(tension.score).encode()).hexdigest()[:14]
    for i, prompt in enumerate(prompts):
        hid = f"hypothesis_{wave_id}_{i}"
        hypothesis_nodes.append(
            Node(
                node_id=hid,
                label=prompt[:200],
                node_type=NodeType.HYPOTHESIS,
                mass=0.5,
                activation=0.5,
                metadata={"source": "reflection", "tension_score": tension.score},
            )
        )

    meta_waves: list[Wave] = []
    in_wave_edges: list[Edge] = []
    if create_meta_wave and (prompts or hypothesis_nodes):
        meta_waves.append(
            Wave(
                wave_id=wave_id,
                label="reflection: " + (prompts[0] if prompts else "meta"),
                source=WAVE_SOURCE_REFLECTION,
                intensity=float(len(hypothesis_nodes)),
                coherence=0.0,
                tension=tension.score,
                source_chunk_id=wave_id,
            )
        )
        for h in hypothesis_nodes:
            in_wave_edges.append(
                Edge(src_id=h.node_id, dst_id=wave_id, relation=EDGE_IN_WAVE, weight=0.5)
            )

    return ReflectionResult(
        meta_waves=meta_waves,
        hypothesis_nodes=hypothesis_nodes,
        in_wave_edges=in_wave_edges,
        tension=tension,
    )
