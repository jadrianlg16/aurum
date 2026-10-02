"""Void-aware view of the ledger (void semantics).

The ledger never erases anything: pf voids append a reversal tagged ``entry-reversal`` whose
``meta.reverses`` names the original transaction, and ``ledger/router.void_transaction`` tags the original
``voided`` and appends a ``voided-reversal``. Aggregations (budgets, review, goals, income, recurring
detection, organizer occurrence matching) must see neither the reversal nor the reversed original — this is
the ONE place that rule lives. No file is rewritten here.

    live_txns(ws_id, start, end)                       -> list[Transaction]
    live_postings(ws_id, start, end, account_prefix)   -> list[tuple[Transaction, Posting]]
    sum_by_account(ws_id, start, end, account_prefix)  -> dict[account, Decimal]  (signed sums)

Both reversal conventions date the reversal on the original's date, so a date window is self-contained:
pairing uses only the transactions inside the window (one journal load per call).

The organizer imports this module lazily (inside functions) to avoid import cycles.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from ..ledger.base import Posting, Transaction, get_ledger

REVERSAL_TAGS = frozenset({"entry-reversal", "voided-reversal"})
VOIDED_TAGS = frozenset({"voided"})
VOID_TAGS = REVERSAL_TAGS | VOIDED_TAGS


def is_live(txn: Transaction, reversed_ids: set[str]) -> bool:
    if VOID_TAGS.intersection(txn.tags):
        return False
    return not any(link in reversed_ids for link in txn.links)


def reversed_txn_ids(txns: list[Transaction]) -> set[str]:
    """Ids named by any reversal's ``meta.reverses`` (pf and ledger/router conventions)."""
    ids: set[str] = set()
    for txn in txns:
        if REVERSAL_TAGS.intersection(txn.tags):
            target = (txn.meta or {}).get("reverses") or ""
            if target:
                ids.add(target)
    return ids


def filter_live(txns: list[Transaction]) -> list[Transaction]:
    """The void filter over an already-loaded list (organizer matching may pass its own window)."""
    reversed_ids = reversed_txn_ids(txns)
    return [t for t in txns if is_live(t, reversed_ids)]


def live_txns(ws_id: str, start: date | None = None, end: date | None = None) -> list[Transaction]:
    """Transactions in the window that still count: no reversals, no reversed originals, no ``#voided``."""
    return filter_live(get_ledger().journal(ws_id, start, end))


def live_postings(
    ws_id: str,
    start: date | None = None,
    end: date | None = None,
    account_prefix: str | None = None,
) -> list[tuple[Transaction, Posting]]:
    """Signed postings of live transactions, optionally limited to accounts under ``account_prefix``
    (``"Expenses:"`` style — a prefix match on the account name). Balancing postings (amount None) are
    skipped: callers that need them should use ``txn.balanced()``."""
    out: list[tuple[Transaction, Posting]] = []
    for txn in live_txns(ws_id, start, end):
        for posting in txn.postings:
            if posting.amount is None:
                continue
            if account_prefix and not posting.account.startswith(account_prefix):
                continue
            out.append((txn, posting))
    return out


def sum_by_account(
    ws_id: str,
    start: date | None = None,
    end: date | None = None,
    account_prefix: str | None = None,
    currency: str | None = None,
) -> dict[str, Decimal]:
    """Signed sum per account over the live postings of the window (one ledger load). When ``currency``
    is given only postings in that currency count."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for _txn, posting in live_postings(ws_id, start, end, account_prefix):
        assert posting.amount is not None
        if currency and posting.amount.currency != currency:
            continue
        totals[posting.account] += posting.amount.amount
    return dict(totals)


def sum_under(totals: dict[str, Decimal], account: str) -> Decimal:
    """Σ of ``totals`` for ``account`` and every sub-account (``Expenses:Food`` covers ``Expenses:Food:X``)."""
    prefix = account + ":"
    return sum((v for k, v in totals.items() if k == account or k.startswith(prefix)), Decimal("0"))
