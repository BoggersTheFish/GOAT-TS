from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.graph.models import Triple
from src.utils import load_yaml_config


PROMPT_TEMPLATE = """
Extract factual triples from the following text.
Return each triple on its own line in the format:
subject | relation | object

Text:
{text}
""".strip()


QUERY_CONTEXT_PROMPT = """The user is searching a knowledge graph with the query: "{query}".
Suggest 5-10 additional search terms or short phrases that could help find relevant nodes.
Consider different meanings (e.g. a phrase might be a band name or a religious concept), related entities, and broader or narrower terms.
Return only a JSON array of strings, e.g. ["term1", "term2"].""".strip()


@dataclass(slots=True)
class ExtractionResult:
    triples: list[Triple]
    raw_response: str


class TripleExtractor:
    """Best-effort extractor with transformer and regex fallbacks."""

    def __init__(self, config_path: str | Path = "configs/llm.yaml") -> None:
        self.config = load_yaml_config(config_path)["llm"]
        self._pipeline = None

    def _build_pipeline(self) -> None:
        if self._pipeline is not None:
            return
        if not self.config.get("enable_model_inference", False):
            self._pipeline = False
            return

        try:
            from transformers import pipeline
        except ImportError:
            self._pipeline = False
            return

        device = self.config.get("device", "cpu")
        pipeline_device = 0 if device in {"cuda", "gpu"} else -1
        self._pipeline = pipeline(
            "text2text-generation",
            model=self.config["model_name"],
            device=pipeline_device,
        )

    def _extract_with_model(self, text: str) -> ExtractionResult | None:
        self._build_pipeline()
        if self._pipeline is False:
            return None

        prompt = PROMPT_TEMPLATE.format(text=text)
        output = self._pipeline(prompt, max_new_tokens=128, truncation=True)
        raw = output[0]["generated_text"]
        triples = self._parse_response(raw)
        if not triples:
            return None
        return ExtractionResult(triples=triples, raw_response=raw)

    def _extract_with_regex(self, text: str) -> ExtractionResult:
        sentence_pattern = re.compile(r"([A-Z][A-Za-z0-9_\- ]+?)\s+(is|has|uses|contains|supports)\s+([^\.]+)")
        triples: list[Triple] = []
        for subject, relation, obj in sentence_pattern.findall(text):
            triples.append(
                Triple(
                    subject=subject.strip(),
                    relation=relation.strip(),
                    object=obj.strip(),
                    confidence=0.5,
                )
            )

        return ExtractionResult(triples=triples, raw_response="regex-fallback")

    def _parse_response(self, raw_response: str) -> list[Triple]:
        triples: list[Triple] = []
        for line in raw_response.splitlines():
            if "|" not in line:
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 3:
                continue
            triples.append(Triple(subject=parts[0], relation=parts[1], object=parts[2]))
        return triples

    def extract(self, text: str) -> ExtractionResult:
        model_result = self._extract_with_model(text)
        if model_result is not None:
            return model_result
        return self._extract_with_regex(text)

    def extract_batch(self, chunks: Iterable[str]) -> list[ExtractionResult]:
        return [self.extract(chunk) for chunk in chunks]

    def suggest_search_terms(self, query: str, max_terms: int = 10) -> list[str]:
        """Use the LLM to suggest additional seed terms for graph lookup (e.g. alternative meanings, related concepts)."""
        self._build_pipeline()
        if self._pipeline is False:
            return []

        prompt = QUERY_CONTEXT_PROMPT.format(query=query.strip())
        try:
            output = self._pipeline(prompt, max_new_tokens=150, truncation=True)
            raw = output[0]["generated_text"]
        except Exception:
            return []

        # Parse JSON array from response (model may wrap in text)
        terms: list[str] = []
        raw_clean = raw.strip()
        # Find first [...] in response
        start = raw_clean.find("[")
        if start == -1:
            return []
        depth = 0
        end = -1
        for i in range(start, len(raw_clean)):
            if raw_clean[i] == "[":
                depth += 1
            elif raw_clean[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == -1:
            return []
        try:
            parsed = json.loads(raw_clean[start:end])
            if isinstance(parsed, list):
                for x in parsed:
                    if isinstance(x, str) and len(x.strip()) >= 2:
                        terms.append(x.strip())
        except json.JSONDecodeError:
            return []

        # Normalize: alphanumeric + spaces, take token-like or short phrases
        out = []
        for t in terms[: max_terms * 2]:
            if len(out) >= max_terms:
                break
            # Allow words and short phrases
            clean = re.sub(r"[^\w\s\-]", "", t).strip()
            if len(clean) >= 2 and clean.lower() not in {s.lower() for s in out}:
                out.append(clean)
        return out[:max_terms]
