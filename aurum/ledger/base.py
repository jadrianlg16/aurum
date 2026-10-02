"""LedgerStore protocol + InMemoryLedger fake.

Every other module codes and tests against this file. ``get_ledger()`` returns the Beancount store
when it can be imported, else the in-memory fake.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

from ..core.money import Amount

ACCOUNT_ROOTS = ("Assets", "Liabilities", "Equity", "Income", "Expenses")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
TAG_RE = re.compile(r"^[A-Za-z0-9\-_/.]+$")


def validate_account(name: str) -> str:
    """A Beancount account name we are willing to render into a ledger file: one of the five roots,
    ``Root:Component[:Component...]`` per ``beancount.core.account.is_valid``, no control characters
    (a newline would inject directives). Raises ``ValueError``; returns the name unchanged."""
    from beancount.core import account as bc_account

    if not isinstance(name, str) or not name or _CONTROL.search(name) or not bc_account.is_valid(name):
        raise ValueError(f"invalid account name: {name!r}")
    if bc_account.root(1, name) not in ACCOUNT_ROOTS:
        raise ValueError(f"account must start with one of {ACCOUNT_ROOTS}: {name!r}")
    return name


def _no_control(value: str, what: str) -> str:
    if _CONTROL.search(value):
        raise ValueError(f"{what} must not contain control characters")
    return value


def validate_tag(value: str) -> str:
    r"""A tag or link the way Beancount's lexer accepts it: ``^[A-Za-z0-9\-_/.]+$``."""
    if not isinstance(value, str) or not TAG_RE.match(value):
        raise ValueError(f"invalid tag/link: {value!r} (allowed: letters, digits, - _ / .)")
    return value


class Posting(BaseModel):
    account: str
    amount: Amount | None = None  # None = balancing posting (Beancount fills it in)

    @field_validator("account")
    @classmethod
    def _account(cls, v: str) -> str:
        return validate_account(v)


class Transaction(BaseModel):
    date: date
    payee: str | None = None
    narration: str = ""
    postings: list[Posting]
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)

    @field_validator("payee")
    @classmethod
    def _payee(cls, v: str | None) -> str | None:
        return None if v is None else _no_control(v, "payee")

    @field_validator("narration")
    @classmethod
    def _narration(cls, v: str) -> str:
        return _no_control(v, "narration")

    @field_validator("tags", "links")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return [validate_tag(t) for t in v]

    @field_validator("meta")
    @classmethod
    def _meta(cls, v: dict[str, str]) -> dict[str, str]:
        # Invalid KEYS are dropped at render time (pinned by tests); VALUES must be clean here.
        for key, value in v.items():
            _no_control(str(key), "meta key")
            _no_control(str(value), "meta value")
        return v

    def balanced(self) -> list[Posting]:
        """Return postings with the single missing amount filled in (per currency)."""
        missing = [p for p in self.postings if p.amount is None]
        if not missing:
            return self.postings
        if len(missing) > 1:
            raise ValueError("at most one posting may omit its amount")
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for p in self.postings:
            if p.amount is not None:
                totals[p.amount.currency] += p.amount.amount
        if len(totals) != 1:
            raise ValueError("balancing posting requires exactly one currency among the others")
        ((currency, total),) = totals.items()
        filled = [
            Posting(account=p.account, amount=Amount(amount=-total, currency=currency))
            if p.amount is None
            else p
            for p in self.postings
        ]
        return filled


@runtime_checkable
class LedgerStore(Protocol):
    def append(self, ws_id: str, txn: Transaction) -> str: ...
    def journal(
        self,
        ws_id: str,
        start: date | None = None,
        end: date | None = None,
        account_prefix: str | None = None,
    ) -> list[Transaction]: ...
    def balances(self, ws_id: str, as_of: date | None = None) -> dict[str, list[Amount]]: ...
    def query(self, ws_id: str, bql: str) -> list[dict]: ...
    def accounts(self, ws_id: str) -> list[str]: ...


class InMemoryLedger:
    """Dict-backed fake with the same semantics as the Beancount store, for unit tests and fallbacks."""

    def __init__(self) -> None:
        self._txns: dict[str, list[Transaction]] = defaultdict(list)
        self._opened: dict[str, set[str]] = defaultdict(set)

    def open_account(self, ws_id: str, account: str) -> None:
        self._opened[ws_id].add(account)

    def append(self, ws_id: str, txn: Transaction) -> str:
        txn_id = txn.links[0] if txn.links else f"txn-{uuid.uuid4().hex[:12]}"
        stored = txn.model_copy(update={"postings": txn.balanced(), "links": txn.links or [txn_id]})
        self._txns[ws_id].append(stored)
        for p in stored.postings:
            self._opened[ws_id].add(p.account)
        return txn_id

    def journal(self, ws_id, start=None, end=None, account_prefix=None):
        out = []
        for t in self._txns[ws_id]:
            if start and t.date < start:
                continue
            if end and t.date > end:
                continue
            if account_prefix and not any(p.account.startswith(account_prefix) for p in t.postings):
                continue
            out.append(t)
        return sorted(out, key=lambda t: t.date)

    def balances(self, ws_id, as_of=None):
        totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        for t in self._txns[ws_id]:
            if as_of and t.date > as_of:
                continue
            for p in t.postings:
                assert p.amount is not None
                totals[p.account][p.amount.currency] += p.amount.amount
        return {
            acct: [Amount(amount=v, currency=c) for c, v in sorted(cur.items())]
            for acct, cur in sorted(totals.items())
        }

    def query(self, ws_id, bql):
        raise NotImplementedError("BQL needs the Beancount store")

    def accounts(self, ws_id):
        return sorted(self._opened[ws_id])


_fallback: InMemoryLedger | None = None


def get_ledger() -> LedgerStore:
    """Beancount store if it can be imported, else a process-wide InMemoryLedger."""
    global _fallback
    try:
        from .beancount_store import BeancountLedger  # type: ignore

        return BeancountLedger()
    except ImportError:
        if _fallback is None:
            _fallback = InMemoryLedger()
        return _fallback
