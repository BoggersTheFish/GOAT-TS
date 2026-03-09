"""
Web search integration: decompose query, search (Google API/requests), extract triples,
insert linked waves. TF-IDF relevance (scikit-learn) to rank snippets.
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.ingestion.extraction_pipeline import load_into_graph
from src.ingestion.ingestion_online import web_search

logger = logging.getLogger(__name__)


def decompose_query(query: str, *, max_terms: int = 5) -> list[str]:
    """Decompose query into search terms: tokenize and filter short/stopwords."""
    stop = {"the", "a", "an", "is", "are", "what", "how", "why", "and", "or", "for"}
    terms = [t.strip().lower() for t in query.split() if t.strip() and t.strip().lower() not in stop and len(t.strip()) >= 2]
    return terms[:max_terms]


def search_and_fetch(
    query: str,
    *,
    max_results: int = 10,
    api_key: str | None = None,
) -> list[str]:
    """Decompose, run web_search for each term (or full query), return combined snippets."""
    terms = decompose_query(query)
    if not terms:
        snippets = web_search(query, max_results=max_results, api_key=api_key)
        return snippets
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        for s in web_search(t, max_results=max(3, max_results // len(terms)), api_key=api_key):
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    if not out:
        out = web_search(query, max_results=max_results, api_key=api_key)
    return out


def tfidf_relevance(snippets: list[str], query: str, *, top_k: int = 10) -> list[str]:
    """Rank snippets by TF-IDF relevance to query. Returns top_k snippets."""
    if not snippets or not query:
        return snippets[:top_k]
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        corpus = [query] + snippets
        vec = TfidfVectorizer(max_features=5000, stop_words="english")
        X = vec.fit_transform(corpus)
        from sklearn.metrics.pairwise import cosine_similarity
        sim = cosine_similarity(X[0:1], X[1:]).flatten()
        order = sim.argsort()[::-1]
        return [snippets[i] for i in order[:top_k]]
    except ImportError:
        return snippets[:top_k]
    except Exception as e:
        logger.warning("tfidf_relevance failed: %s", e)
        return snippets[:top_k]


def handle_query(
    query: str,
    config_root: Path,
    *,
    live: bool = False,
    extract_triples: bool = True,
    insert_linked_waves: bool = True,
    api_key: str | None = None,
    tfidf_top_k: int = 10,
) -> dict[str, int]:
    """
    Decompose query, search (Google API/requests), optionally run TF-IDF relevance,
    extract triples and insert as linked waves. Returns stats (nodes, edges, waves).
    """
    snippets = search_and_fetch(query, max_results=15, api_key=api_key)
    if not snippets:
        return {"nodes": 0, "edges": 0, "waves": 0}
    snippets = tfidf_relevance(snippets, query, top_k=tfidf_top_k)
    if not extract_triples or not snippets:
        return {"nodes": 0, "edges": 0, "waves": 0}
    stats = load_into_graph(
        snippets,
        config_root,
        live=live,
        use_clusters=True,
        require_llm=False,
        min_confidence=0.5,
    )
    return stats
