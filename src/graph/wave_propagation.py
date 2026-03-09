"""
Multi-stage activation wave propagation: decompose input → activate seeds (1.0)
→ iterative propagate with interference (align ×1.2, oppose ×0.8). PyTorch GPU.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import numpy as np

from src.graph.constraints import cosine_similarity
from src.graph.models import Edge, Node

logger = logging.getLogger(__name__)

ALIGN_FACTOR = 1.2
OPPOSE_FACTOR = 0.8
DEFAULT_DECAY = 0.1
DEFAULT_THRESHOLD = 0.1
DEFAULT_MAX_HOPS = 5
DEFAULT_BIAS = 0.0


@dataclass(slots=True)
class WavePropagationResult:
    activations: dict[str, float]
    iterations: int
    converged: bool
    seed_ids: list[str]


def decompose_input(
    nodes: list[Node],
    input_text: str | list[str],
    *,
    relation: str = "relates",
) -> list[str]:
    """
    Decompose input into seed node ids: if input_text is str, tokenize (split on whitespace)
    and match nodes whose label contains any token (case-insensitive); if list[str], treat as
    keywords and match the same way. Returns node_ids of matching nodes.
    """
    if isinstance(input_text, str):
        keywords = [t.strip().lower() for t in input_text.split() if len(t.strip()) >= 2]
    else:
        keywords = [t.strip().lower() for t in input_text if t and len(str(t).strip()) >= 2]
    if not keywords:
        return []
    seed_ids: list[str] = []
    seen: set[str] = set()
    for n in nodes:
        lab = (n.label or "").lower()
        if any(kw in lab for kw in keywords) and n.node_id not in seen:
            seed_ids.append(n.node_id)
            seen.add(n.node_id)
    return seed_ids


def _build_adjacency_with_interference(
    node_ids: list[str],
    edges: list[Edge],
    nodes: list[Node],
    *,
    relation: str = "relates",
    align_factor: float = ALIGN_FACTOR,
    oppose_factor: float = OPPOSE_FACTOR,
) -> np.ndarray:
    """
    Build weighted adjacency with interference: adj[j,i] = weight * factor,
    where factor = align_factor if edge endpoints are aligned (e.g. cosine sim >= 0), else oppose_factor.
    Uses node embeddings when present; otherwise treats all as align.
    """
    n = len(node_ids)
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    id_to_node = {n.node_id: n for n in nodes}
    embeddings: list[np.ndarray] = []
    for nid in node_ids:
        node = id_to_node.get(nid)
        if node and node.embedding is not None:
            embeddings.append(np.asarray(node.embedding, dtype=np.float32))
        else:
            embeddings.append(np.zeros(1, dtype=np.float32))
    emb = np.stack(embeddings) if embeddings else np.zeros((n, 1), dtype=np.float32)

    adj = np.zeros((n, n), dtype=np.float32)
    for e in edges:
        if e.relation != relation:
            continue
        i = id_to_idx.get(e.src_id)
        j = id_to_idx.get(e.dst_id)
        if i is None or j is None:
            continue
        w = float(e.weight)
        if emb.shape[1] > 1:
            sim = cosine_similarity(emb[i], emb[j])
            factor = align_factor if sim >= 0.0 else oppose_factor
        else:
            factor = align_factor
        adj[j, i] = max(adj[j, i], w * factor)
        adj[i, j] = max(adj[i, j], w * factor)
    return adj


def propagate_wave(
    node_ids: list[str],
    edges: list[Edge],
    nodes: list[Node],
    seed_ids: list[str],
    *,
    max_hops: int = DEFAULT_MAX_HOPS,
    decay: float = DEFAULT_DECAY,
    threshold: float = DEFAULT_THRESHOLD,
    bias: float = DEFAULT_BIAS,
    initial_activation: float = 1.0,
    align_factor: float = ALIGN_FACTOR,
    oppose_factor: float = OPPOSE_FACTOR,
    use_torch: bool = True,
) -> WavePropagationResult:
    """
    Multi-stage: seeds at initial_activation (1.0), then iterative propagation with
    interference (align ×align_factor, oppose ×oppose_factor). PyTorch GPU when available.
    """
    if not node_ids:
        return WavePropagationResult(activations={}, iterations=0, converged=True, seed_ids=seed_ids)
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    adj = _build_adjacency_with_interference(
        node_ids, edges, nodes,
        align_factor=align_factor, oppose_factor=oppose_factor,
    )
    n = len(node_ids)

    use_torch = use_torch
    try:
        import torch
    except ImportError:
        use_torch = False

    iterations = 0
    if use_torch:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        adj_t = torch.from_numpy(adj).to(device)
        act = torch.zeros(n, dtype=torch.float32, device=device)
        for sid in seed_ids:
            idx = id_to_idx.get(sid)
            if idx is not None:
                act[idx] = initial_activation
        for iterations in range(1, max_hops + 1):
            act_prev = act.clone()
            act = (adj_t @ act) * (1.0 - decay) + bias
            for sid in seed_ids:
                idx = id_to_idx.get(sid)
                if idx is not None:
                    act[idx] = max(act[idx].item(), initial_activation)
            act[act < threshold] = 0.0
            if torch.allclose(act, act_prev, atol=1e-6):
                break
        activations = {node_ids[i]: float(act[i].item()) for i in range(n)}
    else:
        act = np.zeros(n, dtype=np.float32)
        for sid in seed_ids:
            idx = id_to_idx.get(sid)
            if idx is not None:
                act[idx] = initial_activation
        for iterations in range(1, max_hops + 1):
            act_prev = act.copy()
            act = (adj @ act) * (1.0 - decay) + bias
            for sid in seed_ids:
                idx = id_to_idx.get(sid)
                if idx is not None:
                    act[idx] = max(act[idx], initial_activation)
            act[act < threshold] = 0.0
            if np.allclose(act, act_prev, atol=1e-6):
                break
        activations = {node_ids[i]: float(act[i]) for i in range(n)}

    converged = iterations < max_hops
    return WavePropagationResult(
        activations=activations, iterations=iterations, converged=converged, seed_ids=seed_ids
    )


def run_wave_propagation(
    nodes: list[Node],
    edges: list[Edge],
    input_text: str | list[str] | None = None,
    seed_ids: list[str] | None = None,
    *,
    max_hops: int = DEFAULT_MAX_HOPS,
    decay: float = DEFAULT_DECAY,
    threshold: float = DEFAULT_THRESHOLD,
    use_torch: bool = True,
) -> tuple[list[Node], WavePropagationResult]:
    """
    Full pipeline: decompose input (if no seed_ids) → activate seeds (1.0) → propagate with interference.
    Returns (updated nodes with new activations, result).
    """
    node_ids = [n.node_id for n in nodes]
    if seed_ids is None:
        if input_text is None:
            return nodes, WavePropagationResult(
                activations={n.node_id: n.activation for n in nodes},
                iterations=0, converged=True, seed_ids=[],
            )
        seed_ids = decompose_input(nodes, input_text)
    if not seed_ids:
        return nodes, WavePropagationResult(
            activations={n.node_id: n.activation for n in nodes},
            iterations=0, converged=True, seed_ids=[],
        )
    result = propagate_wave(
        node_ids, edges, nodes, seed_ids,
        max_hops=max_hops, decay=decay, threshold=threshold, use_torch=use_torch,
    )
    out = [replace(n, activation=result.activations.get(n.node_id, n.activation)) for n in nodes]
    return out, result
