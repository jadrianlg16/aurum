"""Turn a year of ledger postings into the inputs a US federal rule needs.

Which postings count:

* a workspace whose ``jurisdictions`` are exactly ``["US"]`` — the whole ledger;
* a mixed MX/US workspace — only what is marked US: an account with a ``US`` path segment
  (``Income:US:Consulting``), a transaction tagged ``us``, or ``meta = {"jurisdiction": "US"}``;
* a workspace with no ``US`` jurisdiction at all — nothing, and the API answers ``applicable: false``.

Cost of goods sold is split out of expenses so Schedule C line 4 and line 28 stay distinct: an account
with a ``COGS`` or ``CostOfGoodsSold`` segment is COGS, everything else under ``Expenses:`` is line 28.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..core.money import q2
from ..core.workspaces import Workspace
from ..ledger.base import LedgerStore, Transaction

COGS_SEGMENTS = {"cogs", "costofgoodssold", "cost_of_goods_sold"}
US_SEGMENT = "US"
US_TAGS = {"us", "usa", "us-tax"}


@dataclass
class ScheduleCInputs:
    year: int
    currency: str = "USD"
    gross_receipts: Decimal = Decimal("0")
    returns_and_allowances: Decimal = Decimal("0")
    cost_of_goods_sold: Decimal = Decimal("0")
    expenses: dict[str, Decimal] = field(default_factory=dict)
    income_by_account: dict[str, Decimal] = field(default_factory=dict)
    transactions: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def expenses_total(self) -> Decimal:
        return q2(sum(self.expenses.values(), Decimal("0")))

    @property
    def net(self) -> Decimal:
        return q2(
            self.gross_receipts - self.returns_and_allowances - self.cost_of_goods_sold - self.expenses_total
        )


def _is_us(txn: Transaction, account: str, us_only: bool) -> bool:
    if us_only:
        return True
    if US_SEGMENT in account.split(":"):
        return True
    if {t.lower() for t in txn.tags} & US_TAGS:
        return True
    return str(txn.meta.get("jurisdiction", "")).upper() == "US"


def _is_cogs(account: str) -> bool:
    return any(segment.lower().replace("-", "_") in COGS_SEGMENTS for segment in account.split(":"))


def collect(
    ledger: LedgerStore,
    ws: Workspace,
    year: int,
    currency: str = "USD",
) -> ScheduleCInputs:
    """Walk the year's journal and bucket Income/Expenses postings into Schedule C lines."""
    us_only = list(ws.jurisdictions) == ["US"]
    out = ScheduleCInputs(year=year, currency=currency)
    seen: set[int] = set()
    other_currencies: set[str] = set()

    for txn in ledger.journal(ws.id, start=date(year, 1, 1), end=date(year, 12, 31)):
        for posting in txn.postings:
            amount = posting.amount
            if amount is None:
                continue
            account = posting.account
            if not (account.startswith("Income:") or account.startswith("Expenses:")):
                continue
            if not _is_us(txn, account, us_only):
                continue
            if amount.currency != currency:
                other_currencies.add(amount.currency)
                continue
            seen.add(id(txn))
            value = amount.amount
            if account.startswith("Income:"):
                # Beancount income postings are negative; a refund/return is a positive income posting.
                if value <= 0:
                    out.gross_receipts += -value
                else:
                    out.returns_and_allowances += value
                out.income_by_account[account] = q2(out.income_by_account.get(account, Decimal("0")) + -value)
            elif _is_cogs(account):
                out.cost_of_goods_sold += value
            else:
                out.expenses[account] = q2(out.expenses.get(account, Decimal("0")) + value)

    out.gross_receipts = q2(out.gross_receipts)
    out.returns_and_allowances = q2(out.returns_and_allowances)
    out.cost_of_goods_sold = q2(out.cost_of_goods_sold)
    out.expenses = {k: v for k, v in sorted(out.expenses.items()) if v != 0}
    out.income_by_account = dict(sorted(out.income_by_account.items()))
    out.transactions = len(seen)

    if other_currencies:
        out.warnings.append(
            f"postings in {', '.join(sorted(other_currencies))} were skipped — US figures are {currency} only; "
            "convert them first (see /api/fx)"
        )
    if not us_only and out.transactions == 0:
        out.warnings.append(
            "no US-marked postings found: mark them with a `US` account segment (Income:US:…), the `us` tag, "
            'or meta {"jurisdiction": "US"}'
        )
    if any(v < 0 for v in out.expenses.values()):
        out.warnings.append("some expense accounts net negative for the year — check for miscoded refunds")
    return out


def expense_labels(inputs: ScheduleCInputs) -> dict[str, str]:
    """``Expenses:US:Software`` → ``Software`` for the Schedule C expense breakdown."""
    return {account: account.split(":")[-1] for account in inputs.expenses}
