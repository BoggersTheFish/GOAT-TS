"""
Node importance weighting: dynamic mass (from gravity/activation), high-mass pull
(update pos/vel via gravity), and GAT (PyG GraphAttentionLayer) for edge evolution.
"""
from __future__ import annotations

import logging
from dataclasses import replace

import numpy as np

from src.graph.models import Edge, Node

logger = logging.getLogger(__name__)

# Dynamic mass: mass = max(min_mass, base * (1 + activation_scale * activation))
MIN_MASS = 0.1
DEFAULT_ACTIVATION_SCALE = 0.5


def update_mass_from_activation(
    nodes: list[Node],
    *,
    min_mass: float = MIN_MASS,
    activation_scale: float = DEFAULT_ACTIVATION_SCALE,
) -> list[Node]:
    """
    Dynamic mass from activation: mass = max(min_mass, base_mass * (1 + activation_scale * activation)).
    High activation -> higher mass -> stronger pull in gravity.
    """
    out: list[Node] = []
    for n in nodes:
        base = max(min_mass, float(n.mass))
        new_mass = max(min_mass, base * (1.0 + activation_scale * float(n.activation)))
        out.append(replace(n, mass=new_mass))
    return out


def evolve_edges_with_gat(
    node_ids: list[str],
    edges: list[Edge],
    nodes: list[Node],
    *,
    in_channels: int | None = None,
    hidden_channels: int = 32,
    out_channels: int = 1,
    heads: int = 4,
    relation: str = "relates",
    evolution_scale: float = 0.1,
) -> list[Edge]:
    """
    Use PyG GAT to compute node importance and evolve edge weights:
    new_weight = old_weight * (1 + evolution_scale * (importance_src + importance_dst)).
    Falls back to identity (return edges unchanged) if torch_geometric is not installed.
    """
    try:
        import torch
        from torch_geometric.data import Data
        from torch_geometric.nn import GATv2Conv
    except ImportError:
        logger.debug("torch_geometric not available; skipping GAT edge evolution")
        return list(edges)

    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)
    if n == 0:
        return list(edges)

    # Node features: embedding if present, else [activation, mass]
    xs: list[np.ndarray] = []
    for nid in node_ids:
        node = next((nd for nd in nodes if nd.node_id == nid), None)
        if node and node.embedding is not None:
            xs.append(np.asarray(node.embedding, dtype=np.float32))
        else:
            xs.append(np.array([node.activation if node else 0.0, node.mass if node else 1.0], dtype=np.float32))
    x = np.stack(xs)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    feat_dim = x.shape[1]
    if in_channels is None:
        in_channels = feat_dim

    edge_index_list: list[tuple[int, int]] = []
    edge_weights: list[float] = []
    for e in edges:
        if e.relation != relation:
            continue
        i = id_to_idx.get(e.src_id)
        j = id_to_idx.get(e.dst_id)
        if i is not None and j is not None:
            edge_index_list.append((i, j))
            edge_weights.append(float(e.weight))
    if not edge_index_list:
        return list(edges)

    edge_index = torch.tensor(edge_index_list, dtype=torch.long).t().contiguous()
    edge_attr = torch.tensor(edge_weights, dtype=torch.float32).unsqueeze(1)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    x_t = torch.from_numpy(x).float().to(device)
    if x_t.size(1) != in_channels:
        # Pad or project to in_channels
        if x_t.size(1) < in_channels:
            x_t = torch.nn.functional.pad(x_t, (0, in_channels - x_t.size(1)))
        else:
            x_t = x_t[:, :in_channels]
    edge_index = edge_index.to(device)
    edge_attr = edge_attr.to(device)
    data = Data(x=x_t, edge_index=edge_index, edge_attr=edge_attr)

    try:
        conv = GATv2Conv(
            in_channels=in_channels,
            out_channels=out_channels,
            heads=heads,
            edge_dim=1,
        ).to(device)
        with torch.no_grad():
            importance = conv(data.x, data.edge_index, data.edge_attr)
        # Multi-head: (n, out_channels * heads) -> mean over heads -> (n,)
        if importance.dim() == 2 and importance.size(1) > 1:
            importance = importance.mean(dim=1)
        importance = importance.cpu().numpy().flatten()
    except Exception as e:
        logger.warning("GAT forward failed: %s; returning edges unchanged", e)
        return list(edges)

    # importance may be per-edge or per-node; GATv2Conv returns node-level output
    # So we have one importance per node. Evolve edge weight by (imp_src + imp_dst)
    imp_min = float(np.min(importance)) if importance.size else 0.0
    imp_max = float(np.max(importance)) if importance.size else 1.0
    if imp_max - imp_min > 1e-9:
        importance = (importance - imp_min) / (imp_max - imp_min)
    else:
        importance = np.ones_like(importance)
    id_to_imp = {node_ids[i]: float(importance[i]) for i in range(n)}

    new_edges: list[Edge] = []
    for e in edges:
        if e.relation != relation:
            new_edges.append(e)
            continue
        imp_src = id_to_imp.get(e.src_id, 0.5)
        imp_dst = id_to_imp.get(e.dst_id, 0.5)
        delta = evolution_scale * (imp_src + imp_dst)
        new_w = max(0.01, float(e.weight) * (1.0 + delta))
        new_edges.append(replace(e, weight=new_w))
    return new_edges


def apply_importance_weighting(
    nodes: list[Node],
    edges: list[Edge],
    *,
    update_mass: bool = True,
    evolve_edges_gat: bool = True,
    activation_scale: float = DEFAULT_ACTIVATION_SCALE,
    evolution_scale: float = 0.1,
) -> tuple[list[Node], list[Edge]]:
    """
    Apply dynamic mass (from activation) and optional GAT-based edge evolution.
    Integrate into loop after gravity: call update_mass_from_activation, then
    (optionally) evolve_edges_with_gat. Returns (updated nodes, updated edges).
    """
    if update_mass:
        nodes = update_mass_from_activation(nodes, activation_scale=activation_scale)
    node_ids = [n.node_id for n in nodes]
    if evolve_edges_gat:
        edges = evolve_edges_with_gat(
            node_ids, edges, nodes, evolution_scale=evolution_scale
        )
    return nodes, edges
