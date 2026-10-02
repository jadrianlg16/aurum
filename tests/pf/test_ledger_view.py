"""pf.ledger_view: reversals and reversed originals never count (void semantics)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from aurum.core.money import Amount
from aurum.ledger.base import InMemoryLedger, Posting, Transaction
from aurum.pf import ledger_view


def _txn(day: int, amount: str, links: list[str], tags: list[str] | None = None, meta: dict | None = None):
    return Transaction(
        date=date(2026, 9, day),
        payee="tacos",
        narration="comida",
        postings=[
            Posting(account="Expenses:Food", amount=Amount(amount=Decimal(amount), currency="MXN")),
            Posting(account="Assets:Cash", amount=Amount(amount=-Decimal(amount), currency="MXN")),
        ],
        tags=tags or [],
        links=links,
        meta=meta or {},
    )


def test_live_view_excludes_pf_reversal_and_its_original(monkeypatch):
    ledger = InMemoryLedger()
    monkeypatch.setattr(ledger_view, "get_ledger", lambda: ledger)
    ledger.append("ws", _txn(1, "250", ["txn-a"]))
    ledger.append("ws", _txn(2, "300", ["txn-b"]))
    # pf-style void of txn-a: reversal tagged entry-reversal, meta.reverses = txn-a, original untouched
    ledger.append("ws", _txn(1, "-250", ["txn-a-rev"], tags=["entry-reversal"], meta={"reverses": "txn-a"}))

    live = ledger_view.live_txns("ws")
    assert [t.links[0] for t in live] == ["txn-b"]
    postings = ledger_view.live_postings("ws", account_prefix="Expenses:")
    assert [(p.account, p.amount.amount) for _, p in postings] == [("Expenses:Food", Decimal("300"))]


def test_live_view_excludes_router_void_convention(monkeypatch):
    ledger = InMemoryLedger()
    monkeypatch.setattr(ledger_view, "get_ledger", lambda: ledger)
    ledger.append("ws", _txn(3, "100", ["txn-c"], tags=["voided"]))
    ledger.append(
        "ws", _txn(3, "-100", ["txn-c-void-1", "txn-c"], tags=["voided-reversal"], meta={"reverses": "txn-c"})
    )
    ledger.append("ws", _txn(4, "50", ["txn-d"]))
    assert [t.links[0] for t in ledger_view.live_txns("ws")] == ["txn-d"]


def test_window_pairs_reversal_on_the_originals_date(monkeypatch):
    """Both reversal conventions date the reversal on the original's date, so a window is self-contained
    and costs one journal load."""
    ledger = InMemoryLedger()
    monkeypatch.setattr(ledger_view, "get_ledger", lambda: ledger)
    ledger.append("ws", _txn(1, "250", ["txn-a"]))
    ledger.append("ws", _txn(1, "-250", ["txn-a-rev"], tags=["entry-reversal"], meta={"reverses": "txn-a"}))
    ledger.append("ws", _txn(9, "80", ["txn-b"]))
    live = ledger_view.live_txns("ws", date(2026, 9, 1), date(2026, 9, 2))
    assert live == []
    totals = ledger_view.sum_by_account("ws", date(2026, 9, 1), date(2026, 9, 30), "Expenses:")
    assert totals == {"Expenses:Food": Decimal("80")}
    assert ledger_view.sum_under(totals, "Expenses") == Decimal("80")
