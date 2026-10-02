"""Cite or abstain.

Adapted from the citation module shared with
the author's learning-tutor project (https://github.com/jadrianlg16/learning-tutor). Aurum's corpus has no source-role
concept, so this file holds only ``cite_or_abstain`` and its supporting quote-selection logic,
and a citation is built directly as an ``aurum.core.explain.Citation``-shaped dict — no extra
lookup needed.

Abstention is on purpose: a claim the corpus does not support returns ``abstain`` with a
reason, and the caller must say so rather than assert the claim with a decorative citation.
This is what the "grounded or silent" principle (docs/ARCHITECTURE.md) means in code.
"""

from __future__ import annotations

import os
import re
from typing import Any

from . import refs as refs_mod
from .search import DEFAULT_K, content_terms, search, words
from .store import CorpusStore

QUOTE_LIMIT = 200
DEFAULT_MIN_SCORE = 0.5

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def min_score_default() -> float:
    raw = os.environ.get("AURUM_CITE_MIN_SCORE")
    if not raw:
        return DEFAULT_MIN_SCORE
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_MIN_SCORE


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(text or "") if part.strip()]


def best_quote(text: str, claim: str, limit: int = QUOTE_LIMIT) -> str:
    """The sentence of the chunk that best supports the claim, capped at ``limit`` chars."""

    terms = content_terms(claim)
    parts = sentences(text) or [text or ""]
    best = parts[0]
    best_hits = -1.0
    for part in parts:
        haystack = " ".join(words(part))
        hits = sum(1 for term in terms if term in haystack)
        # Prefer a sentence that covers more terms; break ties towards the shorter one.
        score = hits - len(part) / 10000.0
        if score > best_hits:
            best_hits = score
            best = part
    quote = " ".join(best.split())
    if len(quote) > limit:
        quote = quote[: limit - 1].rstrip() + "…"
    return quote


def _article(chunk: dict[str, Any]) -> str:
    """A chunk's own tagged article/section, falling back to the source's ``law`` label."""

    return str(chunk.get("article") or chunk.get("section") or "")


def to_citation(chunk: dict[str, Any], claim: str, *, store: CorpusStore | None = None) -> dict[str, Any]:
    """Build an ``aurum.core.explain.Citation``-shaped dict straight from a search hit.

    Field mapping: ``law`` <- source's ``law``, ``article`` <- the chunk's tagged
    article/section (see ``ingest.detect_article``), ``url`` <- the source's ``url``,
    ``effective_from``/``effective_to`` <- the source's dates (the version used, per the
    as-of behavior), ``trust_tier`` <- the source's trust tier,
    ``excerpt`` <- the best-supporting quote. Plus retrieval diagnostics (``source_id``,
    ``chunk_id``, ``score``, ``support``, ``flagged``) that are not part of ``Citation`` but
    are useful to a caller deciding whether to trust it, and ``related`` (the cross-reference
    graph) when ``store`` is given.
    """

    law = str(chunk.get("law") or "")
    article = _article(chunk)
    citation = {
        "law": law,
        "article": article,
        "url": (str(chunk.get("source_url") or "") or None),
        "effective_from": chunk.get("effective_from"),
        "effective_to": chunk.get("effective_to"),
        "trust_tier": str(chunk.get("trust_tier") or "primary"),
        "excerpt": best_quote(str(chunk.get("text") or ""), claim),
        "source_id": chunk.get("source_id"),
        "chunk_id": chunk.get("chunk_id"),
        "title": chunk.get("title"),
        "locator": chunk.get("locator") or {},
        "jurisdiction": chunk.get("jurisdiction"),
        "doc_type": chunk.get("doc_type"),
        "score": round(float(chunk.get("score") or 0.0), 6),
        "support": round(float(chunk.get("support") or 0.0), 4),
        "flagged": bool(chunk.get("flags")),
        "related": [],
    }
    if store is not None and law and article:
        citation["related"] = refs_mod.related_for(store, law, article)
    return citation


def cite_or_abstain(
    store: CorpusStore,
    claim: str,
    collection_id: str,
    *,
    k: int = 5,
    min_score: float | None = None,
    source_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Cite the corpus for ``claim`` or abstain.

    ``min_score`` thresholds ``support`` — the fraction of the claim's content words that
    appear in the chunk — not the RRF score, whose scale means nothing on its own. Default
    0.5 (``AURUM_CITE_MIN_SCORE``): at least half the claim's content words must be there.
    """

    threshold = min_score_default() if min_score is None else float(min_score)
    claim = (claim or "").strip()
    if not claim:
        return {"status": "abstain", "reason": "empty claim", "claim": claim}
    if not content_terms(claim):
        return {
            "status": "abstain",
            "reason": "claim has no content words to match against the corpus",
            "claim": claim,
        }

    hits = search(store, collection_id, claim, k=max(k, DEFAULT_K), source_id=source_id, as_of=as_of)
    assert isinstance(hits, list)
    if not hits:
        return {
            "status": "abstain",
            "reason": "no corpus material matched this claim",
            "claim": claim,
            "min_score": threshold,
        }

    supported = [chunk for chunk in hits if float(chunk.get("support") or 0.0) >= threshold]
    if not supported:
        best = max(float(chunk.get("support") or 0.0) for chunk in hits)
        return {
            "status": "abstain",
            "reason": (
                f"best corpus match supports only {best:.2f} of the claim's content words "
                f"(threshold {threshold:.2f})"
            ),
            "claim": claim,
            "min_score": threshold,
            "best_support": round(best, 4),
        }

    citations = [to_citation(chunk, claim, store=store) for chunk in supported[:k]]
    return {
        "status": "cited",
        "claim": claim,
        "min_score": threshold,
        "citations": citations,
    }
