"""GET review/{period} — monthly review: income vs spend, top labels, deltas, anomalies.

Every figure is a signed, void-aware sum from :mod:`aurum.pf.ledger_view`. ``upcoming_bills``
comes from the organizer calendar (commitments the person set up), not from payee-pattern guessing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends

from ..core.dates import month_bounds, shift_period
from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from ..core.validation import validate_period
from . import goals as goals_mod
from . import labels as labels_mod
from . import ledger_view, store

router = APIRouter()


def _period_bounds(period: str) -> tuple[date, date]:
    return month_bounds(period)


def _spend_by_label(ws_id: str, period: str, currency: str | None = None) -> dict[str, Decimal]:
    """Signed spend per label name (labels resolved by ledger account; unlabeled accounts keep their name)."""
    currency = currency or store.base_currency(ws_id)
    start, end = _period_bounds(period)
    label_by_account = {lbl["account"]: lbl for lbl in labels_mod.list_labels(ws_id, include_archived=True)}
    totals: dict[str, Decimal] = {}
    for account, amount in ledger_view.sum_by_account(ws_id, start, end, "Expenses:", currency).items():
        label = label_by_account.get(account)
        if label is None:  # a sub-account of a labelled account rolls up into it
            parent = max((a for a in label_by_account if account.startswith(a + ":")), key=len, default=None)
            label = label_by_account.get(parent) if parent else None
        name = label["name"] if label else account
        totals[name] = totals.get(name, Decimal("0")) + amount
    return {k: v for k, v in totals.items() if v != 0}


def _income_expense_totals(ws_id: str, period: str, currency: str | None = None) -> tuple[Decimal, Decimal]:
    currency = currency or store.base_currency(ws_id)
    start, end = _period_bounds(period)
    income = Decimal("0")
    expense = Decimal("0")
    for _txn, p in ledger_view.live_postings(ws_id, start, end):
        assert p.amount is not None
        if p.amount.currency != currency:
            continue
        if p.account.startswith("Income:"):
            income += -p.amount.amount
        elif p.account.startswith("Expenses:"):
            expense += p.amount.amount
    return income, expense


def _prev_period(period: str) -> str:
    return shift_period(period, -1)


def _anomalies(ws_id: str, period: str, current: dict[str, Decimal] | None = None) -> list[dict]:
    """A label whose spend this month is > 2x its trailing 3-month average."""
    current = current if current is not None else _spend_by_label(ws_id, period)
    history: dict[str, list[Decimal]] = {}
    p = period
    for _ in range(3):
        p = _prev_period(p)
        for name, amt in _spend_by_label(ws_id, p).items():
            history.setdefault(name, []).append(amt)
    anomalies = []
    for name, amount in current.items():
        past = history.get(name, [])
        if not past:
            continue
        avg = sum(past, Decimal("0")) / len(past)
        if avg > 0 and amount > avg * 2:
            anomalies.append(
                {
                    "label": name,
                    "amount": str(q2(amount)),
                    "trailing_average": str(q2(avg)),
                    "ratio": str((amount / avg).quantize(Decimal("0.01"))),
                }
            )
    return anomalies


def _interest_paid(ws_id: str, period: str, currency: str | None = None) -> Decimal:
    currency = currency or store.base_currency(ws_id)
    start, end = _period_bounds(period)
    totals = ledger_view.sum_by_account(ws_id, start, end, "Expenses:", currency)
    return sum((v for k, v in totals.items() if "Interest" in k), Decimal("0"))


def upcoming_bills(ws_id: str, today: date | None = None, days: int = 30) -> list[dict]:
    """Organizer calendar items going out in the next ``days`` that are not paid/skipped. Lazy import:
    organizer imports pf lazily too, so neither package imports the other at module level."""
    today = today or date.today()
    try:
        from ..organizer import calendar_view
    except Exception:  # noqa: BLE001
        return []
    try:
        cal = calendar_view.calendar(ws_id, today, today + relativedelta(days=days), today=today)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for day in cal.get("days", []):
        for item in day.get("items", []):
            if item.get("status") in ("paid", "skipped") or item.get("kind") == "tax":
                continue  # tax deadlines are an advanced-module concern, not a personal bill
            direction = item.get("direction")
            if direction is None:
                direction = "in" if item.get("kind") == "income" else "out"
            if direction != "out":
                continue
            out.append({
                "name": item.get("name"),
                "date": item.get("date") or day.get("date"),
                "amount": item.get("amount"),
                "kind": item.get("kind"),
                "status": item.get("status"),
                "commitment_id": item.get("id") if item.get("kind") not in ("card", "loan", "tax") else None,
            })
    return sorted(out, key=lambda r: (r["date"] or "", r["name"] or ""))[:10]


def monthly_review(ws_id: str, period: str, lang: str | None = None) -> dict:
    currency = store.base_currency(ws_id)
    income, expense = _income_expense_totals(ws_id, period, currency)
    prev_period = _prev_period(period)
    prev_income, prev_expense = _income_expense_totals(ws_id, prev_period, currency)
    by_label = _spend_by_label(ws_id, period, currency)
    top_labels = sorted(by_label.items(), key=lambda kv: kv[1], reverse=True)[:10]
    goals_progress = [goals_mod.goal_with_progress(ws_id, g, lang) for g in goals_mod.list_goals(ws_id)]

    explain = Explain(summary=i18n_t("pf.review", ws_lang(ws_id, lang)))
    explain.add_step("income", q2(income))
    explain.add_step("expense", q2(expense))
    explain.add_step("net", q2(income - expense), formula="income - expense")

    return {
        "period": period,
        "currency": currency,
        "income": store.money(income, currency),
        "expense": store.money(expense, currency),
        "net": store.money(income - expense, currency),
        "vs_previous_month": {
            "income_delta": str(q2(income - prev_income)),
            "expense_delta": str(q2(expense - prev_expense)),
        },
        "top_labels": [{"label": name, "amount": str(q2(amt))} for name, amt in top_labels],
        "anomalies": _anomalies(ws_id, period, by_label),
        "goals_progress": goals_progress,
        "upcoming_bills": upcoming_bills(ws_id),
        "interest_paid": store.money(_interest_paid(ws_id, period, currency), currency),
        "explain": explain.model_dump(),
    }


@router.get("/{ws}/review/{period}")
def api_review(ws: str, period: str = Depends(validate_period), lang: str | None = None) -> dict:
    return monthly_review(ws, period, lang)
