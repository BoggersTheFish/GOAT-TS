"""Deterministic in-memory graph storage."""

from __future__ import annotations

from goat_ts.core.ids import deterministic_id, node_id, normalize_text
from goat_ts.core.models import CandidateClaim, Edge, Node, Wave


class InMemoryGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}

    def insert_claim(self, claim: CandidateClaim, wave: Wave) -> Edge:
        """Promote a candidate claim while attaching mandatory provenance."""
        source = self._upsert_node(claim.subject, wave.id)
        target = self._upsert_node(claim.object, wave.id)
        predicate = normalize_text(claim.predicate)
        edge_id = deterministic_id("edge", source.id, predicate, target.id, wave.id)
        edge = Edge(
            id=edge_id,
            source_id=source.id,
            target_id=target.id,
            predicate=predicate,
            wave_id=wave.id,
            provenance=(claim.id, wave.id),
        )
        existing = self.edges.get(edge.id)
        if existing:
            edge = Edge(
                id=existing.id,
                source_id=existing.source_id,
                target_id=existing.target_id,
                predicate=existing.predicate,
                wave_id=existing.wave_id,
                provenance=tuple(sorted(set((*existing.provenance, claim.id, wave.id)))),
            )
        self.edges[edge.id] = edge
        return edge

    def neighbors(self, source_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                edge.target_id
                for edge in self.edges.values()
                if edge.source_id == source_id
            )
        )

    def sorted_nodes(self) -> tuple[Node, ...]:
        return tuple(self.nodes[key] for key in sorted(self.nodes))

    def sorted_edges(self) -> tuple[Edge, ...]:
        return tuple(self.edges[key] for key in sorted(self.edges))

    def _upsert_node(self, label: str, wave_id: str) -> Node:
        clean_label = " ".join(label.strip().split())
        identifier = node_id(clean_label)
        existing = self.nodes.get(identifier)
        if existing:
            existing.provenance = tuple(sorted(set((*existing.provenance, wave_id))))
            return existing
        node = Node(id=identifier, label=clean_label, provenance=(wave_id,))
        self.nodes[node.id] = node
        return node
