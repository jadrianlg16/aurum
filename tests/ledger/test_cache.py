"""aurum.ledger.cache: one parse per file state, invalidated on writes and
on external edits, bypassed with AURUM_LEDGER_CACHE=0."""

from __future__ import annotations

import os
import time
from datetime import date

import pytest
from beancount import loader as bc_loader

from aurum.core.money import Amount
from aurum.ledger import beancount_store, cache
from aurum.ledger.base import Posting, Transaction
from aurum.ledger.beancount_store import BeancountLedger


def _txn(n: int) -> Transaction:
    return Transaction(
        date=date(2026, 8, 5),
        narration=f"n{n}",
        links=[f"l{n}"],
        postings=[
            Posting(account="Assets:Bank:BBVA", amount=Amount(amount="100.00", currency="MXN")),
            Posting(account="Income:Freelance"),
        ],
    )


@pytest.fixture
def counted(monkeypatch):
    calls = {"n": 0}
    real = bc_loader.load_file

    def wrapped(path, *a, **kw):
        calls["n"] += 1
        return real(path, *a, **kw)

    monkeypatch.setattr(beancount_store.loader, "load_file", wrapped)
    return calls


def _bump_mtime(path) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000))


def test_cache_serves_repeated_reads_and_invalidates_on_write(tmp_path, counted):
    ledger = BeancountLedger(data_dir=tmp_path / "ld")
    ledger.append("ws1", _txn(1))
    for _ in range(10):
        ledger.journal("ws1")
    assert counted["n"] == 1
    ledger.balances("ws1")
    ledger.accounts("ws1")
    assert counted["n"] == 1

    ledger.append("ws1", _txn(2))
    assert len(ledger.journal("ws1")) == 2
    assert counted["n"] == 2

    # external edit: content change + mtime bump (Windows mtime granularity is coarse)
    main = ledger.main_path("ws1")
    main.write_text(main.read_text(encoding="utf-8") + ledger._render(_txn(3), "l3"), encoding="utf-8")  # noqa: SLF001
    _bump_mtime(main)
    assert len(ledger.journal("ws1")) == 3
    assert counted["n"] == 3
    assert cache.size() == 1


def test_replace_txn_invalidates(tmp_path, counted):
    ledger = BeancountLedger(data_dir=tmp_path / "ld")
    ledger.append("ws1", _txn(1))
    ledger.journal("ws1")
    ledger.replace_txn("ws1", "l1", _txn(1).model_copy(update={"narration": "edited"}))
    time.sleep(0.01)
    assert ledger.journal("ws1")[0].narration == "edited"
    assert counted["n"] == 2


def test_cache_opt_out(tmp_path, counted, monkeypatch):
    monkeypatch.setenv("AURUM_LEDGER_CACHE", "0")
    ledger = BeancountLedger(data_dir=tmp_path / "ld")
    ledger.append("ws1", _txn(1))
    for _ in range(10):
        ledger.journal("ws1")
    assert counted["n"] == 10
    assert cache.size() == 0


def test_cache_is_keyed_on_the_resolved_path(tmp_path, counted):
    a = BeancountLedger(data_dir=tmp_path / "a")
    b = BeancountLedger(data_dir=tmp_path / "b")
    a.append("ws1", _txn(1))
    b.append("ws1", _txn(2))
    b.append("ws1", _txn(3))
    assert len(a.journal("ws1")) == 1
    assert len(b.journal("ws1")) == 2
    assert cache.size() == 2
    cache.clear()
    assert cache.size() == 0
