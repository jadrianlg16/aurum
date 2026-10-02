"""Every rule ships YAML test vectors; this runs all of them."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from aurum.rules.registry import load_rules, registry

VECTOR_DIR = Path(__file__).resolve().parents[2] / "aurum" / "rules" / "vectors"


def _load_vectors() -> list[tuple[str, str, dict]]:
    cases: list[tuple[str, str, dict]] = []
    for path in sorted(VECTOR_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        rule_id = doc["rule"]
        version = doc["version"]
        for case in doc["cases"]:
            cases.append((f"{rule_id}@{version}", case["name"], case))
    return cases


VECTORS = _load_vectors()


def test_every_registered_rule_has_vectors():
    load_rules()
    with_vectors = {p.stem for p in VECTOR_DIR.glob("*.yaml")}
    missing = {r.id for r in registry.list()} - with_vectors
    assert not missing, f"rules without test vectors: {sorted(missing)}"


def test_vectors_were_found():
    assert len(VECTORS) >= 20


@pytest.mark.parametrize(
    ("rule_ref", "name", "case"),
    VECTORS,
    ids=[f"{ref}:{name}" for ref, name, _ in VECTORS],
)
def test_vector(rule_ref: str, name: str, case: dict):
    load_rules()
    rule = registry.get(rule_ref)
    result = rule.compute(**case["inputs"])
    expected = case["expect"]
    assert result.value.amount == Decimal(expected["amount"]), name
    assert result.value.currency == expected.get("currency", "MXN")
    assert result.explain.rule_versions == [rule_ref]
    assert result.explain.citations, "every figure carries a citation"
    if "explain_contains" in case:
        assert case["explain_contains"] in result.explain.summary
    if "steps_contain" in case:
        blob = " ".join(f"{s.label} {s.formula or ''} {s.value}" for s in result.explain.steps)
        assert case["steps_contain"] in blob
