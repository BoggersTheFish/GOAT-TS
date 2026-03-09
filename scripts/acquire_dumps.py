from __future__ import annotations

import argparse
import gzip
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from tqdm import tqdm


# This URL may 404; Wikimedia dump layout changes. Use --sample to create a local sample instead.
WIKIPEDIA_ABSTRACT_URL = (
    "https://dumps.wikimedia.org/enwiki/latest/"
    "enwiki-latest-abstract1.xml.gz"
)

SAMPLE_ABSTRACTS = [
    "Python is a programming language. Python has many libraries for data science.",
    "Machine learning is a subset of artificial intelligence. It uses algorithms to learn from data.",
    "NebulaGraph is a graph database. It supports distributed storage and query.",
    "Wikipedia is an online encyclopedia. Wikipedia has articles in many languages.",
    "Docker is a containerization platform. Docker packages applications and their dependencies.",
    "Redis is an in-memory data store. Redis supports caching and message queues.",
    "Apache Spark is a distributed computing engine. Spark processes large datasets.",
    "Natural language processing deals with text and speech. NLP uses machine learning models.",
    "Knowledge graphs represent entities and relations. They are used in search and reasoning.",
    "Extraction pipelines convert text into structured data. Pipelines often use regex or LLMs.",
    "The Transformer architecture uses attention mechanisms. Transformers power many NLP models.",
    "Embeddings are vector representations of text. Embeddings enable semantic search.",
    "Triple extraction finds subject-relation-object from text. Triples build knowledge graphs.",
    "Graph databases store nodes and edges. They are optimized for relationship queries.",
    "Reasoning systems use logical or neural methods. They infer new facts from existing knowledge.",
]


def download_file(url: str, target: Path) -> None:
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)


WIKIPEDIA_API_HEADERS = {
    "User-Agent": "GOAT-ingestion/1.0 (https://github.com/; corpus ingestion)",
}

WIKIPEDIA_REST_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary"


def fetch_wikipedia_summaries(max_docs: int = 200, delay_sec: float = 0.15) -> list[str]:
    """Fetch real Wikipedia article summaries via the REST API (random main-namespace pages)."""
    session = requests.Session()
    session.headers.update(WIKIPEDIA_API_HEADERS)
    abstracts: list[str] = []
    seen_ids: set[int] = set()
    batch_size = min(50, max(10, max_docs))
    needed: int = max_docs

    with tqdm(total=max_docs, unit="summaries", desc="Fetching Wikipedia") as pbar:
        while needed > 0:
            # Get random article titles (main namespace only)
            r = session.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "random",
                    "rnnamespace": 0,
                    "rnlimit": batch_size,
                    "format": "json",
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            for item in data.get("query", {}).get("random", []):
                if len(abstracts) >= max_docs:
                    break
                title = item.get("title")
                pageid = item.get("id")
                if not title or pageid in seen_ids:
                    continue
                seen_ids.add(pageid)
                # REST summary API: title with spaces -> use underscore in path
                safe_title = title.replace(" ", "_")
                url = f"{WIKIPEDIA_REST_BASE}/{quote(safe_title, safe='')}"
                try:
                    s = session.get(url, timeout=10)
                    s.raise_for_status()
                    j = s.json()
                    extract = (j.get("extract") or "").strip()
                    if extract and len(extract) > 20:
                        abstracts.append(extract)
                        pbar.update(1)
                except Exception:
                    continue
                time.sleep(delay_sec)
            needed = max_docs - len(abstracts)
            pbar.n = len(abstracts)
            pbar.refresh()
            if needed <= 0:
                break
            time.sleep(delay_sec)
    return abstracts


def parse_abstracts_from_xml_gz(xml_gz_path: Path, max_docs: int | None = None) -> list[str]:
    """Extract abstract text from a Wikipedia abstract XML dump (gzip)."""
    abstracts: list[str] = []
    # Match <abstract>...</abstract>; content may have newlines and entities
    abstract_re = re.compile(r"<abstract>([\s\S]*?)</abstract>", re.IGNORECASE)
    decoded = b""
    with gzip.open(xml_gz_path, "rb") as f:
        for chunk in f:
            decoded += chunk
            try:
                text = decoded.decode("utf-8", errors="ignore")
            except Exception:
                continue
            for m in abstract_re.finditer(text):
                raw = m.group(1).strip()
                # Normalize: collapse whitespace, strip
                line = " ".join(raw.split())
                if line and len(line) > 10:
                    abstracts.append(line)
                    if max_docs is not None and len(abstracts) >= max_docs:
                        return abstracts
            # Keep only the tail that might start an abstract
            decoded = decoded[-4096:] if len(decoded) > 8192 else decoded
    return abstracts


def main() -> None:
    parser = argparse.ArgumentParser(description="Download seed corpus dumps.")
    parser.add_argument(
        "--output-dir",
        default="data/raw",
        help="Directory for raw corpus downloads.",
    )
    parser.add_argument(
        "--source",
        default="wikipedia-api",
        choices=["sample", "wikipedia-api", "wikipedia-sample"],
        help="Dataset source: 'wikipedia-api' = fetch real summaries via Wikipedia API; 'sample' = built-in sentences; 'wikipedia-sample' = bulk XML dump (URL may 404).",
    )
    parser.add_argument(
        "--parse",
        action="store_true",
        help="After download, parse XML to text chunks (one abstract per line).",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="Max number of abstracts (default: 200 for wikipedia-api, all for others).",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Only parse an existing dump; skip download.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    wiki_dir = output_dir / "wikipedia"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    out_txt = wiki_dir / "abstracts.txt"

    if args.source == "sample":
        count = args.max_docs if args.max_docs is not None else len(SAMPLE_ABSTRACTS)
        lines = (SAMPLE_ABSTRACTS * (1 + count // len(SAMPLE_ABSTRACTS)))[:count]
        out_txt.write_text("\n".join(lines), encoding="utf-8")
        print(f"Wrote {len(lines)} sample abstracts to {out_txt}")
        return

    if args.source == "wikipedia-api":
        max_docs = args.max_docs if args.max_docs is not None else 200
        print(f"Fetching up to {max_docs} Wikipedia article summaries (this may take a minute)...")
        abstracts = fetch_wikipedia_summaries(max_docs=max_docs)
        out_txt.write_text("\n".join(abstracts), encoding="utf-8")
        print(f"Wrote {len(abstracts)} real Wikipedia abstracts to {out_txt}")
        return

    if args.source == "wikipedia-sample":
        target_xml = wiki_dir / "enwiki-latest-abstract1.xml.gz"
        if not args.no_download:
            download_file(WIKIPEDIA_ABSTRACT_URL, target_xml)
            print(f"Downloaded {target_xml}")

        if args.parse or args.no_download:
            if not target_xml.exists():
                raise SystemExit(
                    f"Missing dump: {target_xml}. Use --source sample for a local sample, or provide the XML dump manually."
                )
            abstracts = parse_abstracts_from_xml_gz(target_xml, max_docs=args.max_docs)
            out_txt.write_text("\n".join(abstracts), encoding="utf-8")
            print(f"Wrote {len(abstracts)} abstracts to {out_txt}")


if __name__ == "__main__":
    main()
