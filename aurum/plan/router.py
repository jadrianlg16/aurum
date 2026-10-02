"""``/api/plan`` router: scenario catalog, run/sensitivity/montecarlo, saved CRUD."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.i18n import ws_lang
from ..pf import store
from .engine import one_way_sensitivity, run_monte_carlo_retirement
from .scenarios import SCENARIOS

router = APIRouter()


def _get_scenario(scenario_id: str):
    module = SCENARIOS.get(scenario_id)
    if module is None:
        raise HTTPException(404, f"unknown scenario '{scenario_id}'")
    return module


def _prefill_defaults(ws_id: str, scenario_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Best-effort: pull a default monthly income from the ledger for regime_mx.

    Defensive: ``aurum.ledger.base.get_ledger`` may not be wired for this workspace/environment yet, so
    any failure here just falls back to the scenario's own pydantic defaults.
    """
    if scenario_id != "regime_mx" or "monthly_income" in inputs:
        return inputs
    try:
        from ..ledger.base import get_ledger

        ledger = get_ledger()
        txns = ledger.journal(ws_id)
        income = sum(
            (-p.amount.amount for t in txns for p in t.postings if p.amount is not None and p.account.startswith("Income:")),
            start=0,
        )
        months = {t.date.strftime("%Y-%m") for t in txns} or {"1"}
        if income:
            avg = income / len(months)
            inputs = {**inputs, "monthly_income": str(round(float(avg), 2))}
    except Exception:
        pass
    return inputs


def _get_metric_path(module) -> tuple:
    return getattr(module, "METRIC_PATH", ())


def _extract(d: dict, path: tuple) -> float:
    cur: Any = d
    for key in path:
        cur = cur[key]
    return float(cur)


def _coerce_for_field(model_cls: type[BaseModel], key: str, value: Any) -> Any:
    """The sensitivity sweep perturbs numeric-looking fields as floats; scenario Inputs store money as
    strings (Decimal-safe). Cast back to the field's declared type before constructing the model."""
    field = model_cls.model_fields.get(key)
    if field is not None and field.annotation is str and isinstance(value, int | float):
        return str(value)
    if field is not None and field.annotation is int and isinstance(value, float):
        return round(value)
    return value


def _metric_fn(module):
    def fn(inputs_dict: dict[str, Any]) -> float:
        coerced = {k: _coerce_for_field(module.Inputs, k, v) for k, v in inputs_dict.items()}
        result = module.run(module.Inputs(**coerced))
        return _extract(result, _get_metric_path(module))

    return fn


@router.get("/{ws}/scenarios")
def api_list_scenarios(ws: str) -> list[dict]:
    return [
        {"id": sid, "schema": module.SCHEMA, "metric_path": list(_get_metric_path(module))}
        for sid, module in SCENARIOS.items()
    ]


@router.post("/{ws}/scenarios/{scenario_id}/run")
def api_run_scenario(ws: str, scenario_id: str, body: dict[str, Any] | None = None, lang: str | None = None) -> dict:
    module = _get_scenario(scenario_id)
    inputs_dict = _prefill_defaults(ws, scenario_id, dict(body or {}))
    try:
        inputs = module.Inputs(**inputs_dict)
    except Exception as e:  # pydantic ValidationError et al.
        raise HTTPException(422, str(e)) from e
    return module.run(inputs, lang=ws_lang(ws, lang))


class SensitivityRequest(BaseModel):
    inputs: dict[str, Any] = {}
    vary: list[str]
    range_pct: float = 0.2


@router.post("/{ws}/scenarios/{scenario_id}/sensitivity")
def api_sensitivity(ws: str, scenario_id: str, body: SensitivityRequest) -> dict:
    module = _get_scenario(scenario_id)
    if not _get_metric_path(module):
        raise HTTPException(400, f"scenario '{scenario_id}' has no sensitivity metric configured")
    inputs_dict = _prefill_defaults(ws, scenario_id, dict(body.inputs))
    try:
        module.Inputs(**inputs_dict)  # validate before sweeping
    except Exception as e:
        raise HTTPException(422, str(e)) from e
    vary = [(key, key, body.range_pct) for key in body.vary]
    points = one_way_sensitivity(inputs_dict, _metric_fn(module), vary)
    return {
        "scenario": scenario_id,
        "range_pct": body.range_pct,
        "points": [
            {
                "key": p.key,
                "label": p.label,
                "base": p.base,
                "low": p.low,
                "high": p.high,
                "range": p.range,
            }
            for p in points
        ],
    }


class MonteCarloRequest(BaseModel):
    inputs: dict[str, Any] = {}
    n: int = 2000
    seed: int = 42


@router.post("/{ws}/scenarios/{scenario_id}/montecarlo")
def api_montecarlo(ws: str, scenario_id: str, body: MonteCarloRequest, lang: str | None = None) -> dict:
    module = _get_scenario(scenario_id)
    inputs_dict = _prefill_defaults(ws, scenario_id, dict(body.inputs))
    if scenario_id == "retirement":
        inputs_dict = {**inputs_dict, "iterations": body.n, "seed": body.seed}
        try:
            inputs = module.Inputs(**inputs_dict)
        except Exception as e:
            raise HTTPException(422, str(e)) from e
        return module.run(inputs, lang=ws_lang(ws, lang))
    # generic fallback: run the engine's retirement Monte Carlo directly over numeric-looking fields
    try:
        result = run_monte_carlo_retirement(
            starting_balance=float(inputs_dict.get("starting_balance", 0) or 0),
            monthly_contribution=float(inputs_dict.get("monthly_contribution", 0) or 0),
            expected_annual_return=float(inputs_dict.get("expected_annual_return", 0.07)),
            annual_volatility=float(inputs_dict.get("annual_volatility", 0.15)),
            inflation_annual=float(inputs_dict.get("inflation_annual", 0.04)),
            horizon_years=int(inputs_dict.get("horizon_years", 10) or 10),
            iterations=body.n,
            seed=body.seed,
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(400, f"scenario '{scenario_id}' has no montecarlo-compatible inputs: {e}") from e
    return {
        "scenario": scenario_id,
        "p10": str(result.ending_balance.p10),
        "p50": str(result.ending_balance.p50),
        "p90": str(result.ending_balance.p90),
        "mean": str(result.ending_balance.mean),
        "iterations": result.iterations,
        "seed": result.seed,
    }


# --------------------------------------------------------------------------- saved scenarios CRUD


class SavedScenario(BaseModel):
    id: str = ""
    scenario_id: str
    name: str
    inputs: dict[str, Any] = {}


def _row(r) -> dict:
    d = store.row_to_dict(r)
    d["inputs"] = store.loads(d["inputs"], {})
    return d


@router.get("/{ws}/saved")
def api_list_saved(ws: str) -> list[dict]:
    conn = store.db()
    rows = conn.execute("SELECT * FROM plan_saved WHERE ws_id=? ORDER BY updated_at DESC", (ws,)).fetchall()
    return [_row(r) for r in rows]


@router.post("/{ws}/saved")
def api_create_saved(ws: str, body: SavedScenario) -> dict:
    _get_scenario(body.scenario_id)
    conn = store.db()
    saved_id = store.new_id("plan")
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO plan_saved (id, ws_id, scenario_id, name, inputs, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (saved_id, ws, body.scenario_id, body.name, json.dumps(body.inputs, ensure_ascii=False), now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM plan_saved WHERE id=?", (saved_id,)).fetchone()
    return _row(row)


@router.put("/{ws}/saved/{saved_id}")
def api_update_saved(ws: str, saved_id: str, body: SavedScenario) -> dict:
    conn = store.db()
    now = datetime.now(UTC).isoformat()
    cur = conn.execute(
        "UPDATE plan_saved SET name=?, inputs=?, updated_at=? WHERE ws_id=? AND id=?",
        (body.name, json.dumps(body.inputs, ensure_ascii=False), now, ws, saved_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"saved scenario {saved_id} not found")
    row = conn.execute("SELECT * FROM plan_saved WHERE id=?", (saved_id,)).fetchone()
    return _row(row)


@router.delete("/{ws}/saved/{saved_id}")
def api_delete_saved(ws: str, saved_id: str) -> dict:
    conn = store.db()
    cur = conn.execute("DELETE FROM plan_saved WHERE ws_id=? AND id=?", (ws, saved_id))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, f"saved scenario {saved_id} not found")
    return {"ok": True}


@router.post("/{ws}/saved/{saved_id}/run")
def api_run_saved(ws: str, saved_id: str, lang: str | None = None) -> dict:
    conn = store.db()
    row = conn.execute("SELECT * FROM plan_saved WHERE ws_id=? AND id=?", (ws, saved_id)).fetchone()
    if row is None:
        raise HTTPException(404, f"saved scenario {saved_id} not found")
    saved = _row(row)
    return api_run_scenario(ws, saved["scenario_id"], saved["inputs"], lang)
