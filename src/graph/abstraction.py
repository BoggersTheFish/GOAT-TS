"""
Concept abstraction: detect dense regions (Louvain, Leiden, hierarchical on embeddings),
create super-nodes with bidirectional edges to members. Run post-consolidation.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import replace

import networkx as nx
import numpy as np

from src.graph.models import Edge, Node, NodeType

logger = logging.getLogger(__name__)

GOAT_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
EMBEDDING_DIM = 384


def _stable_id(seed: str) -> str:
    return str(uuid.uuid5(GOAT_NAMESPACE, seed.strip().lower().encode("utf-8"))).replace("-", "")[:32]


def detect_communities_louvain(
    nodes: list[Node],
    edges: list[Edge],
    *,
    relation: str = "relates",
    seed: int = 42,
) -> list[set[str]]:
    """Run Louvain on the relates subgraph; return list of community sets (node_ids)."""
    graph = nx.Graph()
    node_ids = {n.node_id for n in nodes}
    graph.add_nodes_from(node_ids)
    for e in edges:
        if e.relation != relation or e.src_id not in node_ids or e.dst_id not in node_ids:
            continue
        graph.add_edge(e.src_id, e.dst_id, weight=float(e.weight))
    try:
        communities = nx.community.louvain_communities(graph, seed=seed)
    except Exception as e:
        logger.warning("Louvain failed: %s", e)
        return []
    return list(communities)


def detect_communities_leiden(
    nodes: list[Node],
    edges: list[Edge],
    *,
    relation: str = "relates",
    seed: int = 42,
) -> list[set[str]]:
    """Run Leiden (community lib) on the relates subgraph; return list of community sets (node_ids). Fallback to Louvain if leidenalg/igraph unavailable."""
    graph = nx.Graph()
    node_ids = [n.node_id for n in nodes]
    node_set = set(node_ids)
    graph.add_nodes_from(node_ids)
    for e in edges:
        if e.relation != relation or e.src_id not in node_set or e.dst_id not in node_set:
            continue
        graph.add_edge(e.src_id, e.dst_id, weight=float(e.weight))
    try:
        import igraph as ig
        import leidenalg as la
        # NetworkX -> igraph
        id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
        edge_list = [(id_to_idx[e[0]], id_to_idx[e[1]]) for e in graph.edges()]
        g = ig.Graph(n=len(node_ids), edges=edge_list)
        partition = la.find_partition(g, la.ModularityVertexPartition, seed=seed)
        communities = [set(node_ids[i] for i in part) for part in partition]
        return communities
    except ImportError:
        return detect_communities_louvain(nodes, edges, relation=relation, seed=seed)
    except Exception as e:
        logger.warning("Leiden failed: %s; falling back to Louvain", e)
        return detect_communities_louvain(nodes, edges, relation=relation, seed=seed)


def detect_communities_hierarchical(
    nodes: list[Node],
    *,
    n_clusters: int | None = None,
    distance_threshold: float | None = None,
    embedding_dim: int = EMBEDDING_DIM,
) -> list[set[str]]:
    """Hierarchical agglomerative clustering on node embeddings; return list of community sets (node_ids)."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist
    node_ids = [n.node_id for n in nodes]
    emb = np.zeros((len(nodes), embedding_dim), dtype=np.float32)
    for i, n in enumerate(nodes):
        if n.embedding and len(n.embedding) == embedding_dim:
            emb[i] = np.asarray(n.embedding, dtype=np.float32)
        else:
            emb[i] = np.zeros(embedding_dim, dtype=np.float32)
    if len(nodes) < 2:
        return [set(node_ids)] if node_ids else []
    dist = pdist(emb, metric="cosine")
    Z = linkage(dist, method="average")
    if n_clusters is not None:
        labels = fcluster(Z, n_clusters, criterion="maxclust")
    elif distance_threshold is not None:
        labels = fcluster(Z, distance_threshold, criterion="distance")
    else:
        n_clusters = max(2, min(10, len(nodes) // 5))
        labels = fcluster(Z, n_clusters, criterion="maxclust")
    communities: dict[int, set[str]] = {}
    for i, nid in enumerate(node_ids):
        lb = int(labels[i])
        communities.setdefault(lb, set()).add(nid)
    return list(communities.values())


def create_super_nodes(
    nodes: list[Node],
    edges: list[Edge],
    *,
    relation: str = "relates",
    super_label_prefix: str = "super: ",
    weight_to_super: float = 0.8,
    seed: int = 42,
    use_leiden: bool = True,
) -> tuple[list[Node], list[Edge]]:
    """
    Detect dense regions (Leiden if use_leiden else Louvain), create one super-node per community
    with bidirectional relates edges to each member. Returns (nodes + super_nodes, edges + new_edges).
    """
    communities = (
        detect_communities_leiden(nodes, edges, relation=relation, seed=seed)
        if use_leiden
        else detect_communities_louvain(nodes, edges, relation=relation, seed=seed)
    )
    if not communities:
        return nodes, edges

    id_to_node = {n.node_id: n for n in nodes}
    new_nodes: list[Node] = list(nodes)
    new_edges: list[Edge] = list(edges)

    for idx, comm in enumerate(communities):
        if len(comm) < 2:
            continue
        super_id = _stable_id(f"super:{idx}:{sorted(comm)[:3]}")
        labels = [id_to_node[nid].label for nid in comm if nid in id_to_node]
        super_label = super_label_prefix + f"community_{idx}"  # or shorten labels
        super_node = Node(
            node_id=super_id,
            label=super_label,
            node_type=NodeType.CLUSTER,
            mass=sum(id_to_node[nid].mass for nid in comm if nid in id_to_node),
            activation=0.0,
            cluster_id=None,
            metadata={"source": "abstraction", "members": list(comm), "size": len(comm)},
        )
        new_nodes.append(super_node)
        for nid in comm:
            if nid not in id_to_node:
                continue
            new_edges.append(
                Edge(src_id=nid, dst_id=super_id, relation=relation, weight=weight_to_super)
            )
            new_edges.append(
                Edge(src_id=super_id, dst_id=nid, relation=relation, weight=weight_to_super)
            )
    return new_nodes, new_edges


def cluster_activation_patterns(
    nodes: list[Node],
    *,
    n_clusters: int | None = None,
    features: str = "activation_mass",
) -> list[set[str]]:
    """
    Cluster nodes by activation (and optionally mass) pattern. Returns list of node_id sets.
    features: "activation_mass" (activation, mass) or "activation" only.
    """
    if not nodes:
        return []
    node_ids = [n.node_id for n in nodes]
    if features == "activation_mass":
        X = np.array([[n.activation, n.mass] for n in nodes], dtype=np.float32)
    else:
        X = np.array([[n.activation] for n in nodes], dtype=np.float32)
    if n_clusters is None:
        n_clusters = max(2, min(10, len(nodes) // 5))
    try:
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=n_clusters, random_state=42)
        labels = km.fit_predict(X)
    except ImportError:
        from scipy.cluster.hierarchy import fcluster, linkage
        from scipy.spatial.distance import pdist
        Z = linkage(pdist(X), method="average")
        labels = fcluster(Z, n_clusters, criterion="maxclust") - 1
    communities: dict[int, set[str]] = {}
    for i, nid in enumerate(node_ids):
        communities.setdefault(int(labels[i]), set()).add(nid)
    return list(communities.values())


def meta_embeddings_autoencoder(
    nodes: list[Node],
    *,
    embedding_dim: int = EMBEDDING_DIM,
    latent_dim: int = 32,
    epochs: int = 20,
) -> dict[str, list[float]]:
    """
    PyTorch autoencoder on node embeddings; return node_id -> latent vector (meta-embedding).
    Nodes without embedding get zero latent. Used for higher-level concept representation.
    """
    import numpy as np
    node_ids = [n.node_id for n in nodes]
    X = np.zeros((len(nodes), embedding_dim), dtype=np.float32)
    for i, n in enumerate(nodes):
        if n.embedding and len(n.embedding) == embedding_dim:
            X[i] = np.asarray(n.embedding, dtype=np.float32)
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        logger.warning("PyTorch not available; returning zero latent for all nodes")
        return {nid: [0.0] * latent_dim for nid in node_ids}

    class AE(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc = nn.Sequential(
                nn.Linear(embedding_dim, 128),
                nn.ReLU(),
                nn.Linear(128, latent_dim),
            )
            self.dec = nn.Sequential(
                nn.Linear(latent_dim, 128),
                nn.ReLU(),
                nn.Linear(128, embedding_dim),
            )

        def forward(self, x):
            z = self.enc(x)
            return self.dec(z), z

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AE().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    x_t = torch.from_numpy(X).float().to(device)
    for _ in range(epochs):
        opt.zero_grad()
        recon, z = model(x_t)
        loss = nn.functional.mse_loss(recon, x_t)
        loss.backward()
        opt.step()
    with torch.no_grad():
        _, z = model(x_t)
        z = z.cpu().numpy()
    return {node_ids[i]: z[i].tolist() for i in range(len(node_ids))}
