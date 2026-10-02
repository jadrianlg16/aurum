"""GET accounts (balances + net worth) and GET recurring (bills calendar).

Net worth = Σ Assets + Σ Liabilities as signed ledger balances (liabilities are stored negative),
base-currency lots only. Recurring detection reads the void-aware view (``ledger_view``)."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter

from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from ..ledger.base import get_ledger
from . import ledger_view, store

router = APIRouter()

GROUPS: list[tuple[str, str]] = [
    ("bank", "Assets:Bank"),
    ("cash", "Assets:Cash"),
    ("investments", "Assets:Investments"),
    ("receivables", "Assets:Receivables"),
    ("credit_cards", "Liabilities:CreditCard"),
    ("loans", "Liabilities:Loan"),
]


def _group_for(account: str) -> str:
    for name, prefix in GROUPS:
        if account.startswith(prefix):
            return name
    if account.startswith("Assets:"):
        return "other_assets"
    if account.startswith("Liabilities:"):
        return "other_liabilities"
    return "other"


def _month_end(d: date) -> date:
    return d + relativedelta(day=31)


def _net_worth_from(balances: dict, currency: str) -> Decimal:
    total = Decimal("0")
    for account, amounts in balances.items():
        if account.startswith(("Assets:", "Liabilities:")):
            total += sum((a.amount for a in amounts if a.currency == currency), Decimal("0"))
    return total


def net_worth_as_of(ws_id: str, as_of: date | None = None, currency: str | None = None) -> Decimal:
    currency = currency or store.base_currency(ws_id)
    return _net_worth_from(get_ledger().balances(ws_id, as_of=as_of), currency)


def net_worth_series(ws_id: str, months: int = 12, today: date | None = None, currency: str | None = None) -> list[dict]:
    today = today or date.today()
    currency = currency or store.base_currency(ws_id)
    out = []
    for i in range(months - 1, -1, -1):
        month_date = _month_end(today - relativedelta(months=i))
        out.append({
            "month": month_date.strftime("%Y-%m"),
            "net_worth": str(q2(net_worth_as_of(ws_id, month_date, currency))),
        })
    return out


def get_accounts(ws_id: str, lang: str | None = None, include_archived: bool = False) -> dict:
    from . import accounts_admin

    currency = store.base_currency(ws_id)
    balances = get_ledger().balances(ws_id)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for account, amounts in balances.items():
        if not (account.startswith("Assets:") or account.startswith("Liabilities:")):
            continue
        grouped[_group_for(account)].append(
            {"account": account, "balances": [{"amount": str(q2(a.amount)), "currency": a.currency} for a in amounts]}
        )
    nw = _net_worth_from(balances, currency)
    explain = Explain(summary=i18n_t("pf.net_worth", ws_lang(ws_id, lang)))
    explain.add_step("net_worth", q2(nw), formula="sum(Assets) + sum(Liabilities)")

    return {
        "groups": dict(grouped),
        "accounts": accounts_admin.list_accounts(ws_id, include_archived=include_archived, balances=balances),
        "net_worth": store.money(nw, currency),
        "net_worth_series": net_worth_series(ws_id, currency=currency),
        "explain": explain.model_dump(),
    }


def detect_recurring(ws_id: str, today: date | None = None) -> list[dict]:
    """Same payee, similar amount (±15%), roughly-monthly cadence (20-40 days) → a bill w/ next date.
    Void-aware: reversed or voided transactions never count."""
    today = today or date.today()
    currency = store.base_currency(ws_id)
    by_payee: dict[str, list] = defaultdict(list)
    for t in ledger_view.live_txns(ws_id):
        if not t.payee:
            continue
        by_payee[t.payee].append(t)
    out = []
    for payee, group in by_payee.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda t: t.date)
        gaps = [(b.date - a.date).days for a, b in zip(group, group[1:], strict=False)]
        if not gaps or not all(20 <= g <= 40 for g in gaps):
            continue
        amounts = []
        for t in group:
            total = sum(
                (p.amount.amount for p in t.postings if p.amount is not None and p.account.startswith("Expenses:")),
                Decimal("0"),
            )
            if total > 0:
                amounts.append(total)
        if len(amounts) != len(group):
            continue
        avg_amount = sum(amounts, Decimal("0")) / len(amounts)
        if any(abs(a - avg_amount) > avg_amount * Decimal("0.15") for a in amounts):
            continue
        median_gap = int(statistics.median(gaps))
        last_date = group[-1].date
        next_date = last_date + relativedelta(days=median_gap)
        out.append(
            {
                "payee": payee,
                "amount": store.money(avg_amount, currency),
                "cadence_days": median_gap,
                "last_date": last_date.isoformat(),
                "next_expected_date": next_date.isoformat(),
                "occurrences": len(group),
            }
        )
    return sorted(out, key=lambda r: r["next_expected_date"])


@router.get("/{ws}/accounts")
def api_accounts(ws: str, lang: str | None = None, include_archived: bool = False) -> dict:
    return get_accounts(ws, lang, include_archived=include_archived)


@router.get("/{ws}/recurring")
def api_recurring(ws: str, lang: str | None = None) -> dict:
    bills = detect_recurring(ws)
    explain = Explain(summary=i18n_t("pf.recurring", ws_lang(ws, lang)))
    return {"bills": bills, "explain": explain.model_dump()}
