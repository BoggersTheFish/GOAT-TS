"""
Stage 7: Connectors for external streams — RSS, generic web APIs, URL lists.
All functions return list[str] (chunk text) and never raise on network errors (log and return []).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def fetch_urls(urls: list[str], *, timeout: int = 10) -> list[str]:
    """
    Fetch raw text from a list of URLs. Each URL body is one chunk.
    Requires requests. Returns [] on failure.
    """
    if not urls:
        return []
    try:
        import requests
    except ImportError:
        logger.warning("requests not available for fetch_urls")
        return []
    chunks: list[str] = []
    for url in urls[:50]:
        try:
            r = requests.get(url.strip(), timeout=timeout)
            if r.ok and r.text:
                chunks.append(r.text[:50000])
        except Exception as e:
            logger.debug("fetch_urls %s: %s", url[:50], e)
    return chunks


def rss_feed_to_chunks(feed_url: str, *, max_entries: int = 20) -> list[str]:
    """
    Parse an RSS/Atom feed URL and return a list of text chunks (title + description per entry).
    Uses feedparser if available; else requests + xml.etree. Returns [] on failure.
    """
    if not feed_url or not feed_url.strip():
        return []
    try:
        import requests
        resp = requests.get(feed_url.strip(), timeout=10)
        if not resp.ok:
            return []
        raw = resp.text
    except Exception as e:
        logger.warning("rss_feed_to_chunks fetch failed: %s", e)
        return []

    # Try feedparser first
    try:
        import feedparser
        parsed = feedparser.parse(raw)
        chunks: list[str] = []
        for entry in (parsed.get("entries") or [])[:max_entries]:
            title = getattr(entry, "title", "") or ""
            summary = entry.get("summary", "") or entry.get("description", "") or ""
            chunks.append(f"{title}\n{summary}".strip() or "(no content)")
        return chunks
    except ImportError:
        pass

    # Fallback: minimal Atom parsing
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/elements/1.1/"}
        chunks = []
        for entry in root.findall(".//atom:entry", ns)[:max_entries]:
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns) or entry.find("atom:content", ns)
            title = (title_el.text or "").strip() if title_el is not None else ""
            summary = (summary_el.text or "").strip() if summary_el is not None else ""
            chunks.append(f"{title}\n{summary}".strip() or "(no content)")
        return chunks
    except Exception as e:
        logger.debug("rss_feed_to_chunks parse failed: %s", e)
        return []


def load_sources_config(config_path: Path) -> dict[str, Any]:
    """Load configs/ingestion_sources.yaml if present; else return {}."""
    path = config_path / "configs" / "ingestion_sources.yaml"
    if not path.exists():
        return {}
    try:
        from src.utils import load_yaml_config
        return load_yaml_config(path)
    except Exception:
        return {}
