"""Research quality eval: run ``evalset.yaml`` against the corpus, score precision@1.

This does not call an LLM — it scores retrieval, not generation: for each question, does
the top *trusted* citation land on the expected ``{law, article}``? That is the number that
matters for "grounded or silent": if retrieval cannot find the right article, no amount of
generation quality fixes the answer.

``article`` comparison is normalized (lowercase, strip everything but letters/digits) so
"Artículo 113-E." and "113-E" or "Chapter 151" and "151" count as a match by substring
containment either direction.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ..corpus import cite as cite_mod
from ..corpus.search import search as corpus_search
from ..corpus.store import CorpusStore
from .router import COLLECTIONS_BY_JURISDICTION, TRUSTED_TIERS

EVALSET_PATH = Path(__file__).with_name("evalset.yaml")

_NORM = re.compile(r"[^a-z0-9]+")


def _norm(value: str) -> str:
    return _NORM.sub("", (value or "").lower())


def load_evalset() -> list[dict[str, Any]]:
    return yaml.safe_load(EVALSET_PATH.read_text(encoding="utf-8")) or []


def _article_matches(got: str, expected: str) -> bool:
    got_n, expected_n = _norm(got), _norm(expected)
    if not got_n or not expected_n:
        return False
    return expected_n in got_n or got_n in expected_n


def _law_matches(got: str, expected: str) -> bool:
    return _norm(got) == _norm(expected)


def run_eval(store: CorpusStore, *, k: int = 8) -> dict[str, Any]:
    questions = load_evalset()
    rows: list[dict[str, Any]] = []
    correct = 0
    abstained = 0

    for item in questions:
        collections = COLLECTIONS_BY_JURISDICTION.get(item["jurisdiction"], ["mx-law", "guidance"])
        hits: list[dict[str, Any]] = []
        for collection_id in collections:
            found = corpus_search(store, collection_id, item["question"], k=k)
            assert isinstance(found, list)
            hits.extend(found)
        hits.sort(key=lambda c: (-float(c.get("score") or 0.0), -float(c.get("support") or 0.0)))

        threshold = cite_mod.min_score_default()
        supported = [c for c in hits if float(c.get("support") or 0.0) >= threshold]
        trusted = [c for c in supported if str(c.get("trust_tier") or "") in TRUSTED_TIERS]

        if not trusted:
            abstained += 1
            rows.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "expected": item["expected"],
                    "got": None,
                    "abstained": True,
                    "correct": False,
                }
            )
            continue

        top = cite_mod.to_citation(trusted[0], item["question"])
        expected = item["expected"]
        is_correct = _law_matches(top["law"], expected["law"]) and _article_matches(
            top["article"], expected["article"]
        )
        if is_correct:
            correct += 1
        rows.append(
            {
                "id": item["id"],
                "question": item["question"],
                "expected": expected,
                "got": {"law": top["law"], "article": top["article"], "source_id": top["source_id"]},
                "abstained": False,
                "correct": is_correct,
            }
        )

    total = len(questions)
    return {
        "total": total,
        "correct": correct,
        "abstained": abstained,
        "precision_at_1": round(correct / total, 4) if total else 0.0,
        "rows": rows,
    }
