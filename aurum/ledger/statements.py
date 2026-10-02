"""Statements: P&L / balance / cashflow over a ledger period.

``period`` is ``YYYY-MM`` (one month) or ``YYYY`` (a full year). Every figure comes straight from
``LedgerStore.journal``/``balances`` — no new math beyond summation, so it needs no rule citation;
``Explain`` here documents the *method*, not a statutory figure.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ..core.explain import Explain
from ..core.i18n import t
from .base import LedgerStore, Transaction

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_YEAR = re.compile(r"^\d{4}$")
_ONE_DAY = timedelta(days=1)

VALID_TYPES = ("pnl", "balance", "cashflow")


def period_bounds(period: str) -> tuple[date, date]:
    """Inclusive (start, end) for a ``YYYY-MM`` or ``YYYY`` period."""
    if _MONTH.match(period):
        year, month = (int(x) for x in period.split("-"))
        start = date(year, month, 1)
        end = date(year + (month == 12), (month % 12) + 1, 1) - _ONE_DAY
        return start, end
    if _YEAR.match(period):
        year = int(period)
        return date(year, 1, 1), date(year, 12, 31)
    raise ValueError("period must be YYYY-MM or YYYY")


def _amount_dict(value: Decimal, currency: str) -> dict[str, str]:
    return {"amount": str(value), "currency": currency}


def _section(title: str, rows: list[tuple[str, Decimal]], currency: str, label_of=lambda a: a) -> dict:
    body = [
        {"account": account, "label": label_of(account), "amount": _amount_dict(amount, currency)}
        for account, amount in sorted(rows)
    ]
    total = sum((amount for _account, amount in rows), Decimal("0"))
    return {"title": title, "rows": body, "total": _amount_dict(total, currency)}


def _pnl(txns: list[Transaction], currency: str) -> tuple[list[dict], Decimal]:
    income: dict[str, Decimal] = defaultdict(Decimal)
    expenses: dict[str, Decimal] = defaultdict(Decimal)
    for txn in txns:
        for p in txn.postings:
            if p.amount is None:
                continue
            if p.account.startswith("Income:"):
                income[p.account] += -p.amount.amount  # income postings are credits (negative)
            elif p.account.startswith("Expenses:"):
                expenses[p.account] += p.amount.amount
    income_section = _section("Income", list(income.items()), currency)
    expense_section = _section("Expenses", list(expenses.items()), currency)
    net = Decimal(income_section["total"]["amount"]) - Decimal(expense_section["total"]["amount"])
    return [income_section, expense_section], net


def _balance(store: LedgerStore, ws_id: str, as_of: date, currency: str) -> tuple[list[dict], Decimal]:
    balances = store.balances(ws_id, as_of=as_of)
    roots = {"Assets": [], "Liabilities": [], "Equity": []}
    for account, amounts in balances.items():
        root = account.split(":", 1)[0]
        if root not in roots:
            continue
        total = sum((a.amount for a in amounts if a.currency == currency), Decimal("0"))
        roots[root].append((account, total))
    sections = [_section(root, rows, currency) for root, rows in roots.items()]
    assets = Decimal(sections[0]["total"]["amount"])
    liabilities = Decimal(sections[1]["total"]["amount"])
    net = assets - liabilities
    return sections, net


def _cashflow(txns: list[Transaction], currency: str) -> tuple[list[dict], Decimal]:
    """Change in Assets:Bank:*/Assets:Cash, grouped by the *other* leg of each transaction."""
    by_counter: dict[str, Decimal] = defaultdict(Decimal)
    cash_prefixes = ("Assets:Bank:", "Assets:Cash")
    for txn in txns:
        cash_postings = [p for p in txn.postings if p.amount is not None and p.account.startswith(cash_prefixes)]
        if not cash_postings:
            continue
        cash_delta = sum((p.amount.amount for p in cash_postings), Decimal("0"))
        counters = [p.account for p in txn.postings if p.amount is not None and not p.account.startswith(cash_prefixes)]
        counter = counters[0] if counters else "Unknown"
        by_counter[counter] += cash_delta
    section = _section("Cashflow", list(by_counter.items()), currency)
    net = Decimal(section["total"]["amount"])
    return [section], net


def build_statement(
    store: LedgerStore,
    ws_id: str,
    period: str,
    stype: str,
    currency: str = "MXN",
    lang: str | None = None,
) -> dict:
    if stype not in VALID_TYPES:
        raise ValueError(f"type must be one of {VALID_TYPES}")
    start, end = period_bounds(period)

    if stype == "balance":
        sections, net = _balance(store, ws_id, end, currency)
    else:
        txns = store.journal(ws_id, start=start, end=end)
        sections, net = _pnl(txns, currency) if stype == "pnl" else _cashflow(txns, currency)

    explain = Explain(summary=t(f"ledger.statements.{stype}", lang, period=period))
    explain.add_step("period_start", start.isoformat())
    explain.add_step("period_end", end.isoformat())
    explain.add_step("net", net)

    return {
        "type": stype,
        "period": period,
        "currency": currency,
        "sections": sections,
        "net": _amount_dict(net, currency),
        "explain": explain.model_dump(mode="json"),
    }
