"""Writes holdings trades into the ledger as plain Beancount transactions.

``aurum.ledger.base.Posting`` has no ``cost``/``price`` field (``aurum/ledger/beancount_store.py``'s
``_render`` only emits ``account amount``), and this module deliberately leaves ``aurum/ledger/**``
unchanged.

So this module does **not** write `{units} SYM {price}` cost-basis syntax into the shared
`main.beancount`. Instead:

- The cash/units movement is written through the normal public ``LedgerStore.append()`` API (a
  balanced ``Transaction`` of plain ``Posting``s — no cost basis, just units of the investment account
  and the offsetting cash/income account), so account balances, the journal, and net worth stay correct
  through the standard interface every other module already relies on.
- Cost-basis lot math (FIFO cost, unrealized/realized gains) is computed from ``holdings_trades`` in
  this module's own SQLite table (aurum/holdings/schema.sql), which is the actual source
  of truth for every number this module reports. This keeps computation deterministic and testable
  without needing Beancount inventory-booking semantics in the shared ledger layer.

If ``cost``/``price`` are later added to ``Posting`` in ``aurum/ledger/base.py``, this module can be
re-pointed to emit real cost-basis postings without changing any public function signature here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..core.money import Amount
from ..ledger.base import Posting, Transaction, get_ledger


def write_trade_txn(
    ws_id: str,
    *,
    when: date,
    account: str,
    symbol: str,
    kind: str,
    units: Decimal,
    price: Amount | None,
    fees: Amount | None,
    cash: Amount | None,
    counter_account: str,
    trade_id: str,
) -> str | None:
    """Append a balanced ledger transaction for one holdings trade. Returns the txn id, or None if the
    ledger write failed (never fatal — the SQLite row is still the source of truth for computation)."""
    postings: list[Posting]
    narration = f"{kind} {symbol}".strip()
    if kind == "buy":
        assert price is not None
        cost = units * price.amount
        postings = [
            Posting(account=account, amount=Amount(amount=units, currency=symbol)),
            Posting(account=counter_account, amount=Amount(amount=-cost, currency=price.currency)),
        ]
        if fees and fees.amount:
            postings.append(Posting(account="Expenses:Investments:Fees", amount=fees))
            postings[1] = Posting(
                account=counter_account, amount=Amount(amount=-(cost + fees.amount), currency=price.currency)
            )
    elif kind == "sell":
        assert price is not None
        proceeds = units * price.amount
        postings = [
            Posting(account=account, amount=Amount(amount=-units, currency=symbol)),
            Posting(account=counter_account, amount=Amount(amount=proceeds, currency=price.currency)),
        ]
        if fees and fees.amount:
            postings[1] = Posting(
                account=counter_account, amount=Amount(amount=proceeds - fees.amount, currency=price.currency)
            )
            postings.append(Posting(account="Expenses:Investments:Fees", amount=fees))
    elif kind in ("dividend", "interest"):
        assert cash is not None
        income_account = "Income:Investments:Dividends" if kind == "dividend" else "Income:Investments:Interest"
        postings = [
            Posting(account=counter_account, amount=cash),
            Posting(account=income_account, amount=Amount(amount=-cash.amount, currency=cash.currency)),
        ]
    elif kind == "contribution":
        assert cash is not None
        postings = [
            Posting(account=account, amount=cash),
            Posting(account=counter_account, amount=Amount(amount=-cash.amount, currency=cash.currency)),
        ]
    else:
        raise ValueError(f"unknown trade kind: {kind}")

    txn = Transaction(
        date=when,
        narration=narration,
        postings=postings,
        tags=["holdings"],
        links=[trade_id],
        meta={"symbol": symbol, "kind": kind, "source": "holdings"},
    )
    try:
        return get_ledger().append(ws_id, txn)
    except Exception:
        return None
