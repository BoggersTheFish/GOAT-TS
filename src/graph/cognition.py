"""
Minimal cognition graph ontology for the Thinking Wave model.

Node types:
- node: existing concept/topic vertices (label, mass, activation, state, cluster_id).
- wave: one cognitive episode (e.g. one ingestion chunk or reasoning pass). Links concepts
  that co-occur in that episode and carries optional wave-level metrics.

Relationship types:
- relates: concept-to-concept (existing).
- in_wave: concept (node) -> wave; weight = participation strength. Links each concept
  to the wave(s) it was extracted or activated in, preserving provenance and temporal grouping.

Wave properties: label, source, intensity, coherence, tension, source_chunk_id.
- source: "ingestion" | "reasoning" (origin of the episode).
- source_chunk_id: e.g. "doc_0" for ingestion chunk index, or query id for reasoning.
"""

from __future__ import annotations

# Edge type from concept (node) to wave vertex. Used for provenance and wave-scoped retrieval.
EDGE_IN_WAVE = "in_wave"

# Source identifiers for wave nodes.
WAVE_SOURCE_INGESTION = "ingestion"
WAVE_SOURCE_REASONING = "reasoning"
WAVE_SOURCE_REFLECTION = "reflection"

# Cluster/topic nodes use this label prefix (used by cluster_merge, client).
CLUSTER_LABEL_PREFIX = "topic: "
