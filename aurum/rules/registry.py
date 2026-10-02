"""Rule registry — the core artifact.

A rule is code + citation + effective range + test vectors. Nothing else in Aurum may produce a tax
figure: models classify and explain, rules compute. ``registry.get(id, on=date)`` resolves the version
in force on a date, so a 2027 table can land next to the 2026 one without breaking history.
"""

from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from ..core.explain import Citation, Explain
from ..core.money import Amount


class RuleResult(BaseModel):
    value: Amount
    explain: Explain


@runtime_checkable
class Rule(Protocol):
    id: str
    version: str
    jurisdiction: str
    citation: Citation
    effective_from: date
    effective_to: date | None

    def compute(self, **inputs: Any) -> RuleResult: ...


class RuleNotFound(KeyError):
    pass


class Registry:
    """Rules keyed by id, each holding every version ever registered."""

    def __init__(self) -> None:
        self._rules: dict[str, list[Rule]] = {}

    def register(self, rule: Rule) -> Rule:
        versions = self._rules.setdefault(rule.id, [])
        versions[:] = [r for r in versions if r.version != rule.version] + [rule]
        versions.sort(key=lambda r: r.effective_from)
        return rule

    def get(self, rule_id: str, on: date | None = None) -> Rule:
        """The version of ``rule_id`` in force on ``on`` (default: the newest registered)."""
        if "@" in rule_id:
            rule_id, _, version = rule_id.partition("@")
            for rule in self._rules.get(rule_id, []):
                if rule.version == version:
                    return rule
            raise RuleNotFound(f"{rule_id}@{version}")
        versions = self._rules.get(rule_id)
        if not versions:
            raise RuleNotFound(rule_id)
        if on is None:
            return versions[-1]
        in_force = [
            r for r in versions if r.effective_from <= on and (r.effective_to is None or on <= r.effective_to)
        ]
        if not in_force:
            raise RuleNotFound(f"{rule_id} has no version in force on {on.isoformat()}")
        return in_force[-1]

    def list(self) -> list[Rule]:
        return [r for versions in self._rules.values() for r in versions]

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "version": r.version,
                "rule_version": f"{r.id}@{r.version}",
                "jurisdiction": r.jurisdiction,
                "effective_from": r.effective_from.isoformat(),
                "effective_to": r.effective_to.isoformat() if r.effective_to else None,
                "citation": r.citation.model_dump(mode="json"),
                "doc": (r.__doc__ or "").strip().splitlines()[0] if r.__doc__ else "",
            }
            for r in sorted(self.list(), key=lambda r: (r.id, r.version))
        ]


registry = Registry()


def load_rules() -> Registry:
    """Import every rule module so the registry is populated. Safe to call repeatedly."""
    from .mx import general as _general  # noqa: F401
    from .mx import iva as _iva  # noqa: F401
    from .mx import resico as _resico  # noqa: F401

    # These packages are optional: a missing one must not break the registry.
    for module in (
        "aurum.rules.us.federal",
        "aurum.rules.us.texas",
        "aurum.rules.crossborder.rules",
        "aurum.rules.mx.nl",
    ):
        try:
            import_module(module)
        except ModuleNotFoundError as e:  # pragma: no cover - only when a package is absent
            if e.name and module.startswith(e.name):
                continue
            raise

    return registry


__all__ = ["Registry", "Rule", "RuleNotFound", "RuleResult", "load_rules", "registry"]
