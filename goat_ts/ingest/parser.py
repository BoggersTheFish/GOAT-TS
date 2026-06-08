"""A deliberately bounded parser for simple candidate claims."""

from __future__ import annotations

import re

from goat_ts.core.ids import claim_id, deterministic_id
from goat_ts.core.models import CandidateClaim, RepairTarget

_SUPPORTED = ("is", "has", "uses", "supports")
_TERM = r"[A-Za-z0-9][A-Za-z0-9 _'\-]{0,79}"
_CLAIM = re.compile(
    rf"^\s*(?P<subject>{_TERM}?)\s+(?P<predicate>{'|'.join(_SUPPORTED)})\s+"
    rf"(?P<object>{_TERM}?)\s*[.!]?\s*$",
    re.IGNORECASE,
)


def parse_text(text: str) -> tuple[tuple[CandidateClaim, ...], tuple[RepairTarget, ...]]:
    candidates: list[CandidateClaim] = []
    repairs: list[RepairTarget] = []
    for raw_line in text.splitlines():
        raw = raw_line.strip()
        if not raw:
            continue
        match = _CLAIM.fullmatch(raw)
        if not match:
            repairs.append(
                RepairTarget(
                    id=deterministic_id("repair", "unsupported_or_failed_parse", raw),
                    reason="unsupported_or_failed_parse",
                    raw_text=raw,
                )
            )
            continue
        subject = " ".join(match.group("subject").split())
        predicate = match.group("predicate").casefold()
        object_ = " ".join(match.group("object").split())
        candidates.append(
            CandidateClaim(
                id=claim_id(subject, predicate, object_, raw),
                subject=subject,
                predicate=predicate,
                object=object_,
                raw_text=raw,
            )
        )
    return tuple(candidates), tuple(repairs)
