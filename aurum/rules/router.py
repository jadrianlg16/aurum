"""Rule registry endpoints, mounted at ``/api/rules``."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from .registry import RuleNotFound, load_rules, registry

router = APIRouter(tags=["rules"])


@router.get("/")
def list_rules() -> list[dict]:
    load_rules()
    return registry.describe()


@router.post("/{rule_id}/compute")
def compute(rule_id: str, inputs: dict[str, Any] | None = None, on: date | None = None) -> dict:
    load_rules()
    inputs = inputs or {}
    try:
        rule = registry.get(rule_id, on=on)
    except RuleNotFound as e:
        raise HTTPException(404, f"no rule {rule_id}") from e
    try:
        result = rule.compute(**inputs)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return result.model_dump(mode="json")
