"""pf_goals CRUD, monthly_required, projection, emergency-fund months, debt payoff.

A goal points at a pf account (``account_id``, preferred) or, for advanced callers and the demo seeder, at a
ledger account string (``account``). ``account``/``currency`` are derived from ``pf_accounts`` when an id is
given. Progress by kind: savings/emergency/purchase = the account's balance; debt = ``target − owed``
(owed = −signed balance) clamped at 0. Stored dates that fail to parse never raise: the row carries
``target_date_invalid: true`` and no ``monthly_required``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.dates import month_bounds
from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from ..core.validation import IsoDate, parse_decimal
from ..ledger.base import get_ledger
from . import finance, ledger_view, store

router = APIRouter()

GoalKind = Literal["savings", "emergency", "debt", "purchase"]


class Goal(BaseModel):
    id: str = ""
    ws_id: str = ""
    kind: GoalKind
    name: str
    target: str
    currency: str | None = None
    target_date: IsoDate | None = None  # YYYY-MM-DD
    account: str | None = None
    account_id: str | None = None


class GoalPatch(BaseModel):
    kind: GoalKind | None = None
    name: str | None = None
    target: str | None = None
    currency: str | None = None
    target_date: IsoDate | None = None
    account: str | None = None
    account_id: str | None = None


def _row(r) -> dict:
    return store.row_to_dict(r)


def list_goals(ws_id: str) -> list[dict]:
    conn = store.db()
    rows = conn.execute("SELECT * FROM pf_goals WHERE ws_id=? ORDER BY created_at", (ws_id,)).fetchall()
    return [_row(r) for r in rows]


def get_goal(ws_id: str, goal_id: str) -> dict:
    conn = store.db()
    row = conn.execute("SELECT * FROM pf_goals WHERE ws_id=? AND id=?", (ws_id, goal_id)).fetchone()
    if row is None:
        raise KeyError(goal_id)
    return _row(row)


def _resolve_account(ws_id: str, g: Goal) -> tuple[str, str | None, str]:
    """→ (ledger account, pf account id | None, currency). KeyError when the pf account is unknown."""
    from . import accounts_admin

    if g.account_id:
        row = accounts_admin.get_row(ws_id, g.account_id)  # KeyError → 404
        return row["account"], row["id"], g.currency or row["currency"]
    if g.account:
        account = g.account.strip()
        match = next((r for r in accounts_admin.list_rows(ws_id) if r["account"] == account), None)
        return account, (match["id"] if match else None), g.currency or (match["currency"] if match else None) or store.base_currency(ws_id)
    raise ValueError("send account_id (or account)")


def _target(value: str) -> str:
    amount = parse_decimal(value, "target")
    if amount < 0:
        raise ValueError("target must be >= 0")
    return str(q2(amount))


def create_goal(ws_id: str, g: Goal) -> dict:
    account, account_id, currency = _resolve_account(ws_id, g)
    conn = store.db()
    goal_id = store.new_id("goal")
    conn.execute(
        "INSERT INTO pf_goals (id, ws_id, kind, name, target, currency, target_date, account, account_id, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (goal_id, ws_id, g.kind, g.name, _target(g.target), currency, g.target_date, account, account_id,
         datetime.now(UTC).isoformat()),
    )
    conn.commit()
    return get_goal(ws_id, goal_id)


def merge_patch(existing: dict, patch: GoalPatch) -> Goal:
    changed = patch.model_dump(exclude_unset=True)
    base = {
        "kind": existing["kind"], "name": existing["name"], "target": existing["target"],
        "currency": existing["currency"], "target_date": existing.get("target_date"),
        "account": existing["account"], "account_id": existing.get("account_id"),
    }
    if "account_id" in changed and changed["account_id"]:
        base["account"] = None  # the id wins: re-derive the ledger account
    base.update({k: v for k, v in changed.items() if k != "account" or v})
    try:
        return Goal(**base)
    except ValueError:
        # a stored target_date that no longer parses must not block an unrelated edit
        base["target_date"] = changed.get("target_date")
        return Goal(**base)


def update_goal(ws_id: str, goal_id: str, g: Goal | GoalPatch) -> dict:
    existing = get_goal(ws_id, goal_id)
    body = merge_patch(existing, g) if isinstance(g, GoalPatch) else g
    account, account_id, currency = _resolve_account(ws_id, body)
    conn = store.db()
    cur = conn.execute(
        "UPDATE pf_goals SET kind=?, name=?, target=?, currency=?, target_date=?, account=?, account_id=? "
        "WHERE ws_id=? AND id=?",
        (body.kind, body.name, _target(body.target), currency, body.target_date, account, account_id, ws_id, goal_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(goal_id)
    return get_goal(ws_id, goal_id)


def delete_goal(ws_id: str, goal_id: str) -> None:
    conn = store.db()
    cur = conn.execute("DELETE FROM pf_goals WHERE ws_id=? AND id=?", (ws_id, goal_id))
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(goal_id)


# --------------------------------------------------------------------------- progress


def _balance(ws_id: str, account: str, currency: str) -> Decimal:
    amounts = get_ledger().balances(ws_id).get(account, [])
    return sum((a.amount for a in amounts if a.currency == currency), Decimal("0"))


def _avg_monthly_spend(ws_id: str, months: int = 3, today: date | None = None) -> Decimal:
    """Average live (void-aware) Expenses per month over the trailing ``months`` full months."""
    today = today or date.today()
    start, _ = month_bounds((today.replace(day=1) - relativedelta(months=months)).strftime("%Y-%m"))
    end = today.replace(day=1) - relativedelta(days=1)
    total = sum(ledger_view.sum_by_account(ws_id, start, end, account_prefix="Expenses:").values(), Decimal("0"))
    return total / months if months else Decimal("0")


def _account_name(ws_id: str, g: dict) -> str | None:
    from . import accounts_admin

    if g.get("account_id"):
        try:
            return accounts_admin.get_row(ws_id, g["account_id"])["name"]
        except KeyError:
            return None
    match = next((r for r in accounts_admin.list_rows(ws_id) if r["account"] == g["account"]), None)
    return match["name"] if match else None


def goal_with_progress(ws_id: str, g: dict, lang: str | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    currency = g.get("currency") or store.base_currency(ws_id)
    target = Decimal(g["target"])
    signed = _balance(ws_id, g["account"], currency)
    if g["kind"] == "debt":
        owed = max(Decimal("0"), -signed)
        progress = max(Decimal("0"), target - owed)
    else:
        progress = signed
    remaining = max(Decimal("0"), target - progress)
    pct = (progress / target * 100) if target > 0 else Decimal("0")
    pct = max(Decimal("0"), pct).quantize(Decimal("0.1"))
    monthly_required = None
    target_date_invalid = False
    explain = Explain(summary=i18n_t("pf.goal_monthly_required", ws_lang(ws_id, lang)))
    if g.get("target_date"):
        try:
            target_date = date.fromisoformat(str(g["target_date"])[:10])
        except ValueError:
            target_date = None
            target_date_invalid = True
        if target_date is not None:
            months_left = max(1, (target_date.year - today.year) * 12 + (target_date.month - today.month))
            monthly_required = remaining / months_left
            explain.add_step("months_left", months_left)
            explain.add_step("monthly_required", q2(monthly_required), formula="(target - progress) / months_left")
    explain.add_step("progress", q2(progress), formula="target - owed" if g["kind"] == "debt" else "balance")
    out = {
        **g,
        "currency": currency,
        "target": store.money(target, currency),
        "account_name": _account_name(ws_id, g),
        "progress": store.money(progress, currency),
        "remaining": store.money(remaining, currency),
        "pct": float(pct),
        "monthly_required": store.money(monthly_required, currency) if monthly_required is not None else None,
        "explain": explain.model_dump(),
    }
    if target_date_invalid:
        out["target_date_invalid"] = True
    if g["kind"] == "emergency":
        avg_spend = _avg_monthly_spend(ws_id, today=today)
        out["months_of_spend_covered"] = str((progress / avg_spend).quantize(Decimal("0.01"))) if avg_spend else None
    return out


def projection(ws_id: str, goal_id: str, lang: str | None = None) -> dict:
    g = get_goal(ws_id, goal_id)
    gp = goal_with_progress(ws_id, g, lang)
    progress = Decimal(gp["progress"]["amount"])
    target = Decimal(g["target"])
    monthly = Decimal(gp["monthly_required"]["amount"]) if gp["monthly_required"] else Decimal("0")
    rows = []
    balance = progress
    today = date.today().replace(day=1)
    month = 0
    while balance < target and month < 600:
        month += 1
        balance = min(target, balance + monthly)
        rows.append({"month": (today + relativedelta(months=month)).strftime("%Y-%m"), "balance": str(q2(balance))})
        if monthly <= 0:
            break
    explain = Explain(summary=i18n_t("pf.goal_projection", ws_lang(ws_id, lang)))
    return {"goal_id": goal_id, "path": rows, "explain": explain.model_dump()}


def debt_whatif(ws_id: str, goal_id: str, extra_monthly: Decimal, lang: str | None = None) -> dict:
    """For a debt goal: interest saved by paying `extra_monthly` more, if the goal's account is a loan."""
    conn = store.db()
    g = get_goal(ws_id, goal_id)
    loan_row = conn.execute("SELECT * FROM pf_loans WHERE ws_id=? AND account=?", (ws_id, g["account"])).fetchone()
    if loan_row is None:
        return {"error": "no matching loan for this goal's account"}
    loan = store.row_to_dict(loan_row)
    principal = Decimal(loan["principal"])
    rate = Decimal(loan["annual_rate"])
    months = loan["months"]
    base = finance.build_amortization(principal, rate, months)
    payment = finance.pmt(principal, rate, months) + extra_monthly
    # simulate paying `payment` each month against the same principal/rate
    bal = principal
    r = rate / 12
    total_interest = Decimal("0")
    m = 0
    while bal > 0 and m < months * 3:
        m += 1
        interest = bal * r
        principal_part = min(bal, payment - interest)
        bal = max(Decimal("0"), bal - principal_part)
        total_interest += interest
    interest_saved = base.total_interest - total_interest
    explain = Explain(summary=i18n_t("pf.goal_debt_whatif", ws_lang(ws_id, lang)))
    explain.add_step("base_total_interest", base.total_interest)
    explain.add_step("new_total_interest", total_interest)
    explain.add_step("interest_saved", interest_saved, formula="base_total_interest - new_total_interest")
    return {
        "months_to_payoff": m,
        "months_saved": months - m,
        "interest_saved": store.money(interest_saved, loan["currency"]),
        "explain": explain.model_dump(),
    }


# --- router -----------------------------------------------------------------------------------


def _check_target_date(value: str | None) -> None:
    if value and date.fromisoformat(value) < date.today():
        raise HTTPException(
            422, [{"loc": ["body", "target_date"], "msg": "target_date must be today or later", "type": "value_error"}]
        )


@router.get("/{ws}/goals")
def api_list_goals(ws: str, lang: str | None = None) -> list[dict]:
    return [goal_with_progress(ws, g, lang) for g in list_goals(ws)]


@router.post("/{ws}/goals")
def api_create_goal(ws: str, g: Goal, lang: str | None = None) -> dict:
    _check_target_date(g.target_date)
    try:
        created = create_goal(ws, g)
    except KeyError as e:
        raise HTTPException(404, f"account {g.account_id} not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return goal_with_progress(ws, created, lang)


@router.put("/{ws}/goals/{goal_id}")
def api_update_goal(ws: str, goal_id: str, g: GoalPatch, lang: str | None = None) -> dict:
    if "target_date" in g.model_fields_set:
        _check_target_date(g.target_date)
    try:
        updated = update_goal(ws, goal_id, g)
    except KeyError as e:
        if str(e).strip("'") == goal_id:
            raise HTTPException(404, f"goal {goal_id} not found") from e
        raise HTTPException(404, f"account {g.account_id} not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return goal_with_progress(ws, updated, lang)


@router.delete("/{ws}/goals/{goal_id}")
def api_delete_goal(ws: str, goal_id: str) -> dict:
    try:
        delete_goal(ws, goal_id)
    except KeyError as e:
        raise HTTPException(404, f"goal {goal_id} not found") from e
    return {"ok": True}


@router.get("/{ws}/goals/{goal_id}/projection")
def api_projection(ws: str, goal_id: str, lang: str | None = None) -> dict:
    try:
        return projection(ws, goal_id, lang)
    except KeyError as e:
        raise HTTPException(404, f"goal {goal_id} not found") from e


class WhatIf(BaseModel):
    extra_monthly: str


@router.post("/{ws}/goals/{goal_id}/whatif")
def api_goal_whatif(ws: str, goal_id: str, body: WhatIf, lang: str | None = None) -> dict:
    try:
        return debt_whatif(ws, goal_id, Decimal(body.extra_monthly), lang)
    except KeyError as e:
        raise HTTPException(404, f"goal {goal_id} not found") from e
