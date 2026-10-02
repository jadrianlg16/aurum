"""pf_budgets CRUD + status + carry-forward copy.

Spent figures come from :mod:`aurum.pf.ledger_view` (void-aware, signed sums) — never from a raw journal
scan. The python ``list_budgets`` keeps ``amount`` as a plain string (``organizer/plan.py`` does
``Decimal(budget["amount"])``); the HTTP layer renders Money and adds ``label_name``.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..core.dates import month_bounds, shift_period
from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from ..core.validation import Period, optional_period_q, parse_decimal, period_q
from . import labels, ledger_view, store

router = APIRouter()


class BudgetExists(Exception):
    """A budget for this (label, period) already exists → 409."""


class Budget(BaseModel):
    id: str = ""
    ws_id: str = ""
    label_id: str
    period: Period
    amount: str
    currency: str | None = None
    rollover: bool = False


class BudgetCopy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: Period = Field(alias="from")
    to: Period


def _row(r) -> dict:
    d = store.row_to_dict(r)
    d["rollover"] = bool(d["rollover"])
    return d


def _amount(b: Budget) -> str:
    """Stored as the caller's decimal string (python callers such as organizer/plan.py and insights read it
    back verbatim); the HTTP layer renders it as Money through ``store.money`` (q2)."""
    value = parse_decimal(b.amount, "amount")
    if value <= 0:
        raise ValueError("amount must be greater than zero")
    return str(value)


def list_budgets(ws_id: str, period: str | None = None) -> list[dict]:
    conn = store.db()
    if period:
        rows = conn.execute(
            "SELECT * FROM pf_budgets WHERE ws_id=? AND period=? ORDER BY period", (ws_id, period)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM pf_budgets WHERE ws_id=? ORDER BY period", (ws_id,)).fetchall()
    return [_row(r) for r in rows]


def get_budget(ws_id: str, budget_id: str) -> dict:
    conn = store.db()
    row = conn.execute("SELECT * FROM pf_budgets WHERE ws_id=? AND id=?", (ws_id, budget_id)).fetchone()
    if row is None:
        raise KeyError(budget_id)
    return _row(row)


def create_budget(ws_id: str, b: Budget) -> dict:
    labels.get_label(ws_id, b.label_id)  # KeyError → 404
    conn = store.db()
    budget_id = store.new_id("bud")
    try:
        conn.execute(
            "INSERT INTO pf_budgets (id, ws_id, label_id, period, amount, currency, rollover) "
            "VALUES (?,?,?,?,?,?,?)",
            (budget_id, ws_id, b.label_id, b.period, _amount(b), b.currency or store.base_currency(ws_id),
             int(b.rollover)),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise BudgetExists(f"a budget for label {b.label_id} in {b.period} already exists") from exc
    return get_budget(ws_id, budget_id)


def update_budget(ws_id: str, budget_id: str, b: Budget) -> dict:
    existing = get_budget(ws_id, budget_id)
    conn = store.db()
    try:
        cur = conn.execute(
            "UPDATE pf_budgets SET label_id=?, period=?, amount=?, currency=?, rollover=? WHERE ws_id=? AND id=?",
            (b.label_id, b.period, _amount(b), b.currency or existing["currency"], int(b.rollover), ws_id, budget_id),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise BudgetExists(f"a budget for label {b.label_id} in {b.period} already exists") from exc
    if cur.rowcount == 0:
        raise KeyError(budget_id)
    return get_budget(ws_id, budget_id)


def delete_budget(ws_id: str, budget_id: str) -> None:
    conn = store.db()
    cur = conn.execute("DELETE FROM pf_budgets WHERE ws_id=? AND id=?", (ws_id, budget_id))
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(budget_id)


def copy_budgets(ws_id: str, from_period: str, to_period: str) -> dict:
    """Idempotent carry-forward: rows of ``from_period`` whose label has no budget in ``to_period`` yet
    (and is not archived) are copied; the rest are counted as skipped."""
    existing = {b["label_id"] for b in list_budgets(ws_id, to_period)}
    archived = {lbl["id"] for lbl in labels.list_labels(ws_id, include_archived=True) if lbl["archived"]}
    created = skipped = 0
    for b in list_budgets(ws_id, from_period):
        if b["label_id"] in existing or b["label_id"] in archived:
            skipped += 1
            continue
        try:
            create_budget(
                ws_id,
                Budget(label_id=b["label_id"], period=to_period, amount=b["amount"], currency=b["currency"],
                       rollover=b["rollover"]),
            )
        except (BudgetExists, KeyError):
            skipped += 1
            continue
        created += 1
    return {"created": created, "skipped": skipped, "period": to_period}


# --------------------------------------------------------------------------- status


def _spent_by_account(ws_id: str, period: str, currency: str) -> dict[str, Decimal]:
    start, end = month_bounds(period)
    return ledger_view.sum_by_account(ws_id, start, end, account_prefix="Expenses:", currency=currency)


def _spent_for_account(ws_id: str, account: str, period: str, currency: str | None = None) -> Decimal:
    """Signed, void-aware spend under ``account`` (and its children) for the period."""
    currency = currency or store.base_currency(ws_id)
    return ledger_view.sum_under(_spent_by_account(ws_id, period, currency), account)


def _alert_level(pct: Decimal) -> str:
    if pct >= 100:
        return "100"
    if pct >= 80:
        return "80"
    return "none"


def _state(pct: Decimal) -> str:
    if pct >= 100:
        return "over"
    if pct >= 80:
        return "warn"
    return "ok"


def budget_status(ws_id: str, period: str, lang: str | None = None) -> dict:
    currency = store.base_currency(ws_id)
    label_by_id = {lbl["id"]: lbl for lbl in labels.list_labels(ws_id, include_archived=True)}
    prior_period = shift_period(period, -1)
    rows_in = list_budgets(ws_id, period)
    prior_rows = {b["label_id"]: b for b in list_budgets(ws_id, prior_period)}
    spent_now = _spent_by_account(ws_id, period, currency)
    spent_prior = (
        _spent_by_account(ws_id, prior_period, currency) if any(b["rollover"] for b in rows_in) else {}
    )

    rows = []
    total_budget = total_spent = total_remaining = safe_to_spend = Decimal("0")
    for b in rows_in:
        label = label_by_id.get(b["label_id"], {})
        account = label.get("account", "Expenses:Uncategorized")
        amount = Decimal(b["amount"])
        carried = Decimal("0")
        if b["rollover"]:
            prior = prior_rows.get(b["label_id"])
            if prior:
                prior_label = label_by_id.get(prior["label_id"], {})
                prior_spent = ledger_view.sum_under(spent_prior, prior_label.get("account", account))
                carried = max(Decimal("0"), Decimal(prior["amount"]) - prior_spent)
        effective = amount + carried
        spent = ledger_view.sum_under(spent_now, account)
        remaining = effective - spent
        pct = (spent / effective * 100) if effective else Decimal("0")
        pct = pct.quantize(Decimal("0.1"))
        tax = label.get("tax") or {}
        mx_tax = tax.get("MX", {}) if isinstance(tax, dict) else {}
        deductible = bool(mx_tax.get("isr_deductible") or mx_tax.get("personal_deduction"))
        deductible_share = spent if deductible else Decimal("0")
        total_budget += effective
        total_spent += spent
        total_remaining += remaining
        if remaining > 0:
            safe_to_spend += remaining
        explain = Explain(
            summary=i18n_t("pf.budget_status", ws_lang(ws_id, lang), name=label.get("name", b["label_id"]))
        )
        explain.add_step("effective_budget", q2(effective), formula="amount + carried")
        explain.add_step("spent", q2(spent))
        explain.add_step("remaining", q2(remaining), formula="effective_budget - spent")
        explain.add_step("pct", pct, formula="spent / effective_budget * 100")
        rows.append(
            {
                "budget_id": b["id"],
                "label_id": b["label_id"],
                "label_name": label.get("name"),
                "icon": label.get("icon"),
                "budget": store.money(amount, currency),
                "carried": store.money(carried, currency),
                "effective": store.money(effective, currency),
                "spent": store.money(spent, currency),
                "remaining": store.money(remaining, currency),
                "pct": float(pct),
                "state": _state(pct),
                "rollover": bool(b["rollover"]),
                # compat keys (insights/engine.py reads alert + explain)
                "alert": _alert_level(pct),
                "account": account,
                "rollover_applied": str(q2(carried)),
                "deductible_share": store.money(deductible_share, currency),
                "explain": explain.model_dump(),
            }
        )
    return {
        "period": period,
        "currency": currency,
        "budgets": rows,
        "totals": {
            "budget": store.money(total_budget, currency),
            "spent": store.money(total_spent, currency),
            "remaining": store.money(total_remaining, currency),
        },
        "has_previous": bool(prior_rows),
        "previous_period": prior_period if prior_rows else None,
        "safe_to_spend": store.money(safe_to_spend, currency),
        "explain": Explain(summary=i18n_t("pf.budget_status_all", ws_lang(ws_id, lang), period=period)).model_dump(),
    }


# --- router -----------------------------------------------------------------------------------


def _http_row(ws_id: str, b: dict, label_by_id: dict[str, dict]) -> dict:
    return {
        "id": b["id"],
        "label_id": b["label_id"],
        "label_name": label_by_id.get(b["label_id"], {}).get("name"),
        "period": b["period"],
        "amount": store.money(b["amount"], b["currency"]),
        "currency": b["currency"],
        "rollover": bool(b["rollover"]),
    }


@router.get("/{ws}/budgets")
def api_list_budgets(ws: str, period: str | None = Depends(optional_period_q)) -> list[dict]:
    label_by_id = {lbl["id"]: lbl for lbl in labels.list_labels(ws, include_archived=True)}
    return [_http_row(ws, b, label_by_id) for b in list_budgets(ws, period)]


@router.post("/{ws}/budgets")
def api_create_budget(ws: str, b: Budget) -> dict:
    try:
        created = create_budget(ws, b)
    except BudgetExists as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, f"label {b.label_id} not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    label_by_id = {lbl["id"]: lbl for lbl in labels.list_labels(ws, include_archived=True)}
    return _http_row(ws, created, label_by_id)


@router.post("/{ws}/budgets/copy")
def api_copy_budgets(ws: str, body: BudgetCopy) -> dict:
    return copy_budgets(ws, body.from_, body.to)


@router.get("/{ws}/budgets/status")
def api_budget_status(ws: str, period: str = Depends(period_q), lang: str | None = None) -> dict:
    return budget_status(ws, period, lang)


@router.put("/{ws}/budgets/{budget_id}")
def api_update_budget(ws: str, budget_id: str, b: Budget) -> dict:
    try:
        updated = update_budget(ws, budget_id, b)
    except KeyError as e:
        raise HTTPException(404, f"budget {budget_id} not found") from e
    except BudgetExists as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    label_by_id = {lbl["id"]: lbl for lbl in labels.list_labels(ws, include_archived=True)}
    return _http_row(ws, updated, label_by_id)


@router.delete("/{ws}/budgets/{budget_id}")
def api_delete_budget(ws: str, budget_id: str) -> dict:
    try:
        delete_budget(ws, budget_id)
    except KeyError as e:
        raise HTTPException(404, f"budget {budget_id} not found") from e
    return {"ok": True}


__all__ = ["Budget", "BudgetExists", "budget_status", "copy_budgets", "create_budget",
           "delete_budget", "get_budget", "list_budgets", "router", "update_budget"]
