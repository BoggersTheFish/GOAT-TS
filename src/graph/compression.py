"""
Knowledge compression: encode subgraphs with PyG GNN to vectors, archive in FAISS.
Use for long-term storage and retrieval of graph "summaries".
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import numpy as np

from src.graph.models import Edge, Node

logger = logging.getLogger(__name__)


def _build_pyg_data(
    node_ids: list[str],
    nodes: list[Node],
    edges: list[Edge],
    *,
    relation: str = "relates",
) -> object:
    """Build torch_geometric.data.Data for the subgraph. Returns None if PyG unavailable."""
    try:
        import torch
        from torch_geometric.data import Data
    except ImportError:
        return None

    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)
    if n == 0:
        return None

    xs: list[np.ndarray] = []
    for nid in node_ids:
        node = next((nd for nd in nodes if nd.node_id == nid), None)
        if node and node.embedding is not None:
            xs.append(np.asarray(node.embedding, dtype=np.float32))
        else:
            act = float(node.activation) if node else 0.0
            mass = float(node.mass) if node else 1.0
            xs.append(np.array([act, mass], dtype=np.float32))
    x = np.stack(xs)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    x_t = torch.from_numpy(x).float()

    edge_index_list: list[tuple[int, int]] = []
    for e in edges:
        if e.relation != relation:
            continue
        i = id_to_idx.get(e.src_id)
        j = id_to_idx.get(e.dst_id)
        if i is not None and j is not None:
            edge_index_list.append((i, j))
    if not edge_index_list:
        edge_index = torch.zeros((2, 0), dtype=torch.long)
    else:
        edge_index = torch.tensor(edge_index_list, dtype=torch.long).t().contiguous()

    return Data(x=x_t, edge_index=edge_index)


def subgraph_to_vector(
    nodes: list[Node],
    edges: list[Edge],
    *,
    dimension: int = 64,
    relation: str = "relates",
) -> np.ndarray | None:
    """
    Encode subgraph to a single vector using a small GNN + global pooling.
    Returns shape (dimension,) or None if PyG unavailable.
    """
    try:
        import torch
        from torch_geometric.data import Data
        from torch_geometric.nn import GATv2Conv, global_mean_pool
    except ImportError:
        logger.debug("torch_geometric not available for compression")
        return None

    node_ids = [n.node_id for n in nodes]
    data = _build_pyg_data(node_ids, nodes, edges, relation=relation)
    if data is None or not isinstance(data, Data):
        return None
    if data.x is None or data.x.shape[0] == 0:
        return None

    in_channels = data.x.shape[1]
    device = torch.device("cpu")
    data = data.to(device)

    class TinyGNN(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = GATv2Conv(in_channels, 32, heads=2)
            self.conv2 = GATv2Conv(32 * 2, dimension, heads=2)
            self.out_dim = dimension * 2

        def forward(self, x, edge_index, batch):
            x = self.conv1(x, edge_index).relu()
            x = self.conv2(x, edge_index).relu()
            x = global_mean_pool(x, batch)
            return x

    model = TinyGNN().to(device)
    batch = torch.zeros(data.x.shape[0], dtype=torch.long, device=device)
    with torch.no_grad():
        out = model(data.x, data.edge_index, batch)
    vec = out.cpu().numpy().flatten()
    if len(vec) > dimension:
        vec = vec[:dimension]
    elif len(vec) < dimension:
        vec = np.pad(vec, (0, dimension - len(vec)), mode="constant", constant_values=0.0)
    return vec.astype(np.float32)


def subgraph_id_from_nodes(node_ids: list[str]) -> str:
    """Stable id for a set of nodes (for FAISS archive key)."""
    key = "|".join(sorted(node_ids))
    return "archive_" + hashlib.sha256(key.encode()).hexdigest()[:16]


def compress_and_archive(
    nodes: list[Node],
    edges: list[Edge],
    vector_index: object,
    *,
    dimension: int = 64,
    subgraph_id: str | None = None,
) -> str | None:
    """
    Encode subgraph to vector and add to FAISS-backed vector_index (EmbeddingVectorIndex).
    Returns the id used (subgraph_id or auto-generated) or None if encoding failed.
    """
    vec = subgraph_to_vector(nodes, edges, dimension=dimension)
    if vec is None:
        return None
    if vec.shape[0] != dimension:
        vec = np.resize(vec, (dimension,)).astype(np.float32)
    node_ids = [n.node_id for n in nodes]
    sid = subgraph_id or subgraph_id_from_nodes(node_ids)
    try:
        vector_index.add([sid], vec.reshape(1, -1))
    except Exception as e:
        logger.warning("compress_and_archive: index.add failed: %s", e)
        return None
    return sid


def archive_subgraph_to_faiss(
    nodes: list[Node],
    edges: list[Edge],
    index_path: Path | None = None,
    *,
    dimension: int = 64,
) -> tuple[str | None, object]:
    """
    Encode subgraph and add to a new or existing EmbeddingVectorIndex.
    Returns (subgraph_id or None, index). If index_path is set, caller can index.save(index_path).
    """
    from src.graph.vector_index import EmbeddingVectorIndex
    index = EmbeddingVectorIndex(dimension=dimension, index_path=index_path)
    if index_path and Path(index_path).exists():
        try:
            index.load(index_path)
        except Exception as e:
            logger.debug("Could not load existing index: %s", e)
    sid = compress_and_archive(nodes, edges, index, dimension=dimension)
    return sid, index
