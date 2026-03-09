"""
Prediction: forward-simulate waves for forecasts, LLM textual from subgraphs.
Free-energy style: predict activations, compute error, optional backprop to edges.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.activation import activate_and_propagate, propagate_spreading_activation
from src.graph.models import Edge, Node

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PredictionResult:
    forecast_text: str
    simulated_activations: dict[str, float]
    subgraph_node_ids: list[str]


@dataclass(slots=True)
class PredictiveActivationResult:
    predicted_activations: dict[str, float]
    actual_activations: dict[str, float]
    errors: dict[str, float]
    free_energy: float


def _build_adjacency(node_ids: list[str], edges: list[Edge]) -> np.ndarray:
    n = len(node_ids)
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    adj = np.zeros((n, n), dtype=np.float32)
    for e in edges:
        if e.relation != "relates":
            continue
        i, j = id_to_idx.get(e.src_id), id_to_idx.get(e.dst_id)
        if i is not None and j is not None:
            w = float(e.weight)
            adj[j, i] = max(adj[j, i], w)
            adj[i, j] = max(adj[i, j], w)
    return adj


def predict_activations(
    node_ids: list[str],
    edges: list[Edge],
    current_activations: dict[str, float],
    *,
    decay: float = 0.1,
    bias: float = 0.0,
) -> dict[str, float]:
    """One-step prediction: act_pred = (adj @ act) * (1 - decay) + bias."""
    if not node_ids:
        return {}
    adj = _build_adjacency(node_ids, edges)
    n = len(node_ids)
    act = np.array([current_activations.get(nid, 0.0) for nid in node_ids], dtype=np.float32)
    act_next = (adj @ act) * (1.0 - decay) + bias
    return {node_ids[i]: float(act_next[i]) for i in range(n)}


def predictive_activation_error(
    nodes: list[Node],
    edges: list[Edge],
    seed_ids: list[str],
    *,
    decay: float = 0.1,
    threshold: float = 0.1,
) -> PredictiveActivationResult:
    """
    Free-energy style: predict next activations from current state, run one propagation
    step to get actual, compute error = actual - predicted. free_energy = 0.5 * sum(err^2).
    """
    node_ids = [n.node_id for n in nodes]
    current_activations = {n.node_id: n.activation for n in nodes}
    predicted = predict_activations(node_ids, edges, current_activations, decay=decay)
    result = propagate_spreading_activation(
        node_ids, edges, seed_ids,
        max_hops=1, decay=decay, threshold=threshold,
    )
    actual = result.activations
    errors = {nid: actual.get(nid, 0.0) - predicted.get(nid, 0.0) for nid in node_ids}
    free_energy = 0.5 * sum(e * e for e in errors.values())
    return PredictiveActivationResult(
        predicted_activations=predicted,
        actual_activations=actual,
        errors=errors,
        free_energy=free_energy,
    )


def backprop_errors_to_edges(
    edges: list[Edge],
    errors: dict[str, float],
    *,
    lr: float = 0.01,
    relation: str = "relates",
) -> list[Edge]:
    """
    Simple backprop: scale edge weight by (1 - lr * (|error_src| + |error_dst|)) to
    reduce contribution of high-error endpoints. Returns new edges with updated weights.
    """
    from dataclasses import replace
    out = []
    for e in edges:
        if e.relation != relation:
            out.append(e)
            continue
        err_src = abs(errors.get(e.src_id, 0.0))
        err_dst = abs(errors.get(e.dst_id, 0.0))
        scale = max(0.01, 1.0 - lr * (err_src + err_dst))
        new_w = max(0.01, float(e.weight) * scale)
        out.append(replace(e, weight=new_w))
    return out


def forward_simulate(
    nodes: list[Node],
    edges: list[Edge],
    seed_ids: list[str],
    *,
    steps: int = 3,
    decay: float = 0.1,
    threshold: float = 0.1,
    top_k_seeds: int = 20,
) -> tuple[list[Node], dict[str, float]]:
    """
    Forward-simulate propagation for `steps` steps; return (updated nodes with final
    activations, activations dict). Each step re-seeds from top-k activated nodes.
    """
    current = list(nodes)
    for _ in range(max(1, steps)):
        current, result = activate_and_propagate(
            current, edges, seed_ids,
            max_hops=5, decay=decay, threshold=threshold,
        )
        sorted_ids = sorted(result.activations.items(), key=lambda x: -x[1])
        seed_ids = [nid for nid, _ in sorted_ids[:top_k_seeds] if result.activations.get(nid, 0) >= threshold]
        if not seed_ids:
            seed_ids = [nid for nid, _ in sorted_ids[:5]]
    return current, result.activations


def subgraph_to_text(nodes: list[Node], edges: list[Edge], node_ids: list[str], *, max_labels: int = 30) -> str:
    """Summarize subgraph as text for LLM: node labels and edge count."""
    id_set = set(node_ids)
    labels = [n.label for n in nodes if n.node_id in id_set][:max_labels]
    edge_count = sum(1 for e in edges if e.src_id in id_set and e.dst_id in id_set)
    return f"Concepts: {', '.join(labels)}. Edges in subgraph: {edge_count}."


def llm_forecast_from_subgraph(
    nodes: list[Node],
    edges: list[Edge],
    subgraph_node_ids: list[str],
    *,
    llm_config_path: str | Path | None = None,
    prompt_prefix: str = "Given the following concept subgraph, give a one-sentence forecast: ",
) -> str:
    """Build text summary of subgraph and call LLM for a short forecast. Returns forecast string."""
    summary = subgraph_to_text(nodes, edges, subgraph_node_ids)
    prompt = prompt_prefix + summary
    if llm_config_path is None:
        return f"[no LLM] Subgraph: {summary[:200]}..."
    try:
        from src.ingestion.llm_extract import TripleExtractor
        extractor = TripleExtractor(llm_config_path)
        extractor._build_pipeline()
        if getattr(extractor, "_pipeline", None) and extractor._pipeline is not False:
            out = extractor._pipeline(prompt, max_new_tokens=80, truncation=True)
            return (out[0].get("generated_text") or "").strip() or summary[:200]
    except Exception as e:
        logger.warning("LLM forecast failed: %s", e)
    return f"[fallback] Subgraph: {summary[:200]}..."


def run_prediction(
    nodes: list[Node],
    edges: list[Edge],
    seed_ids: list[str],
    *,
    forward_steps: int = 3,
    llm_config_path: str | Path | None = None,
) -> PredictionResult:
    """
    Forward-simulate propagation, collect activated subgraph, generate LLM forecast.
    """
    updated, activations = forward_simulate(
        nodes, edges, seed_ids, steps=forward_steps,
    )
    threshold = 0.1
    subgraph_node_ids = [nid for nid, a in activations.items() if a >= threshold]
    forecast_text = llm_forecast_from_subgraph(
        updated, edges, subgraph_node_ids, llm_config_path=llm_config_path,
    )
    return PredictionResult(
        forecast_text=forecast_text,
        simulated_activations=activations,
        subgraph_node_ids=subgraph_node_ids,
    )
