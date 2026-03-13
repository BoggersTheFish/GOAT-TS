"""
Auto-build from text: stream mode, web_search (requests), active learning with
low-coherence trigger queries. Stream chunks in; when coherence is low, trigger
web search and ingest additional linked content.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Iterable

from src.graph.models import Edge, Node
from src.ingestion.extraction_pipeline import extract_from_texts, load_into_graph

logger = logging.getLogger(__name__)

WAVE_SOURCE_INGESTION_ONLINE = "ingestion_online"
COHERENCE_TRIGGER_THRESHOLD = 0.3


def web_search(query: str, *, max_results: int = 5, api_key: str | None = None) -> list[str]:
    """
    Web search via `requests`.

    Uses a Google Custom Search–style API when an API key is configured via
    `api_key`, `GOAT_SEARCH_API_KEY`, or `GOOGLE_API_KEY`. Returns a list of
    snippet strings and never raises on network/HTTP errors; failures are
    logged and an empty list is returned so callers can safely continue
    ingestion without external search.
    """
    if not query or not query.strip():
        return []
    try:
        import os
        import requests
        key = api_key or os.environ.get("GOAT_SEARCH_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if key:
            # Google Custom Search JSON API
            url = "https://www.googleapis.com/customsearch/v1"
            params = {"key": key, "q": query.strip()[:200], "cx": os.environ.get("GOAT_CSE_ID", ""), "num": max_results}
            r = requests.get(url, params=params, timeout=10)
            if r.ok:
                data = r.json()
                items = data.get("items", [])
                return [item.get("snippet", "") or item.get("title", "") for item in items if item.get("snippet") or item.get("title")]
        # Fallback: no-op (caller can mock or use another backend)
        return []
    except Exception as e:
        logger.warning("web_search failed: %s", e)
        return []


def compute_coherence_simple(nodes: list[Node], edges: list[Edge]) -> float:
    """Simple coherence: mean activation of nodes that have at least one edge, or 0."""
    if not nodes:
        return 0.0
    endpoint_ids = {e.src_id for e in edges} | {e.dst_id for e in edges}
    activations = [n.activation for n in nodes if n.node_id in endpoint_ids]
    return float(sum(activations) / len(activations)) if activations else 0.0


def stream_ingest(
    chunk_stream: Iterable[str],
    config_root: Path,
    *,
    live: bool = False,
    coherence_trigger: float = COHERENCE_TRIGGER_THRESHOLD,
    on_low_coherence: Callable[[str, float], list[str]] | None = None,
    web_search_max: int = 5,
) -> dict[str, int]:
    """
    Stream mode: consume chunks from chunk_stream, extract and load. When coherence
    (computed after each batch) is below coherence_trigger, run active learning:
    call on_low_coherence(last_chunk, coherence) to get extra queries, web_search each,
    and ingest the returned snippets. If on_low_coherence is None, use last chunk as query.
    """
    total_nodes = 0
    total_edges = 0
    last_chunk = ""
    batch: list[str] = []
    batch_size = 10

    for chunk in chunk_stream:
        if not (chunk and chunk.strip()):
            continue
        last_chunk = chunk.strip()
        batch.append(chunk)
        if len(batch) < batch_size:
            continue
        texts = batch
        batch = []
        nodes, edges, waves, in_wave = extract_from_texts(
            texts, config_root, use_clusters=True, min_confidence=0.5
        )
        if not nodes:
            continue
        coherence = compute_coherence_simple(nodes, edges)
        if live and nodes:
            stats = load_into_graph(
                texts, config_root, live=True, use_clusters=True,
                require_llm=False, min_confidence=0.5,
            )
            total_nodes += stats.get("nodes", 0)
            total_edges += stats.get("edges", 0) + stats.get("in_wave_edges", 0)
        if coherence < coherence_trigger and last_chunk:
            queries = on_low_coherence(last_chunk, coherence) if on_low_coherence else [last_chunk[:100]]
            for q in queries[:3]:
                snippets = web_search(q, max_results=web_search_max)
                if not snippets:
                    continue
                extra_texts = [s for s in snippets if s and len(s.strip()) > 20]
                if not extra_texts:
                    continue
                stats = load_into_graph(
                    extra_texts, config_root, live=live, use_clusters=True,
                    require_llm=False, min_confidence=0.5,
                )
                total_nodes += stats.get("nodes", 0)
                total_edges += stats.get("edges", 0) + stats.get("in_wave_edges", 0)
    if batch:
        nodes, edges, waves, in_wave = extract_from_texts(
            batch, config_root, use_clusters=True, min_confidence=0.5
        )
        if live and nodes:
            stats = load_into_graph(batch, config_root, live=True, use_clusters=True, require_llm=False, min_confidence=0.5)
            total_nodes += stats.get("nodes", 0)
            total_edges += stats.get("edges", 0) + stats.get("in_wave_edges", 0)
    return {"nodes": total_nodes, "edges": total_edges}
