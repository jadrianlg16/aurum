"""Ledger write validation: validators + render-then-parse guard, against a
real BeancountLedger in tmp_path. Every rejected write leaves main.beancount byte-identical."""

from __future__ import annotations

from datetime import date

import pytest
from beancount import loader
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aurum.api.app import create_app
from aurum.core.money import Amount
from aurum.ledger.base import Posting, Transaction
from aurum.ledger.beancount_store import BeancountLedger, LedgerRenderError, TxnNotFound

INJECTED = 'Assets:Bank\noption "insert_pythonpath" "TRUE"\nplugin "beancount.plugins.auto_accounts"'


def _txn(**kw) -> Transaction:
    base = dict(
        date=date(2026, 8, 5),
        payee="ACME",
        narration="Factura",
        postings=[
            Posting(account="Assets:Bank:BBVA", amount=Amount(amount="100.00", currency="MXN")),
            Posting(account="Income:Freelance"),
        ],
    )
    base.update(kw)
    return Transaction(**base)


@pytest.fixture
def ledger(tmp_path) -> BeancountLedger:
    store = BeancountLedger(data_dir=tmp_path / "ld")
    store.append("ws1", _txn())
    return store


def _bytes(store: BeancountLedger) -> bytes:
    return store.main_path("ws1").read_bytes()


def test_injected_account_rejected_by_validator_and_file_unchanged(ledger):
    before = _bytes(ledger)
    with pytest.raises(ValidationError):
        _txn(postings=[Posting(account=INJECTED, amount=Amount(amount="1", currency="MXN")), Posting(account="Income:X")])
    # the same object built around the validator (model_construct) is caught by the write path
    bad = Posting.model_construct(account=INJECTED, amount=Amount(amount="1", currency="MXN"))
    txn = Transaction.model_construct(
        date=date(2026, 8, 5), payee=None, narration="x", postings=[bad, Posting(account="Income:X")], tags=[], links=[], meta={}
    )
    with pytest.raises(ValidationError):
        ledger.append("ws1", txn)
    assert _bytes(ledger) == before


def test_render_guard_catches_what_validators_miss(ledger, monkeypatch):
    """Force a bad render past the validators to prove the parse-back guard stands on its own."""
    before = _bytes(ledger)
    monkeypatch.setattr("aurum.ledger.beancount_store._revalidate", lambda t: t)
    bad = Posting.model_construct(account=INJECTED, amount=Amount(amount="1", currency="MXN"))
    txn = Transaction.model_construct(
        date=date(2026, 8, 5), payee=None, narration="x", postings=[bad, Posting(account="Income:X")], tags=[], links=[], meta={}
    )
    with pytest.raises(LedgerRenderError):
        ledger.append("ws1", txn)
    with pytest.raises(LedgerRenderError):
        ledger._render_checked(txn, "x")  # noqa: SLF001 - the guard on its own, no write path
    assert _bytes(ledger) == before


@pytest.mark.parametrize(
    "kw",
    [
        {"tags": ["bad tag"]},
        {"links": ["a:b"]},
        {"payee": "line\nbreak"},
        {"narration": "nul\x00"},
        {"meta": {"k": "v\nplugin \"x\""}},
    ],
)
def test_bad_fields_are_validation_errors(ledger, kw):
    before = _bytes(ledger)
    with pytest.raises(ValidationError):
        _txn(**kw)
    assert _bytes(ledger) == before


def test_lowercase_currency_is_normalised_and_accepted(ledger):
    ledger.append("ws1", _txn(postings=[
        Posting(account="Assets:Cash", amount=Amount(amount="5", currency="mxn")),
        Posting(account="Income:X"),
    ]))
    text = ledger.main_path("ws1").read_text(encoding="utf-8")
    assert "5.00 MXN" in text
    assert "mxn" not in text


def test_bad_root_account_rejected(ledger):
    with pytest.raises(ValidationError):
        _txn(postings=[Posting(account="Expenses:comida", amount=Amount(amount="1", currency="MXN")), Posting(account="Income:X")])


def test_amounts_render_quantized_half_up(ledger):
    ledger.append("ws1", _txn(postings=[
        Posting(account="Assets:Cash", amount=Amount(amount="1.005", currency="MXN")),
        Posting(account="Income:X"),
    ]))
    text = ledger.main_path("ws1").read_text(encoding="utf-8")
    assert "1.01 MXN" in text and "-1.01 MXN" in text
    assert ledger.load("ws1")[1] == []


def test_twenty_valid_appends_load_clean(ledger):
    for i in range(20):
        ledger.append("ws1", _txn(narration=f"n{i}", links=[f"l{i}"]))
    entries, errors, _ = loader.load_file(str(ledger.main_path("ws1")))
    assert errors == []
    assert sum(1 for e in entries if type(e).__name__ == "Transaction") == 21
    assert ledger.health("ws1") == {"txns": 21, "errors": [], "error_count": 0}


def test_replace_txn_and_not_found(ledger):
    txn_id = ledger.append("ws1", _txn(links=["edit-me"]))
    ledger.replace_txn("ws1", txn_id, _txn(narration="Editada", links=["edit-me"]))
    (stored,) = [t for t in ledger.journal("ws1") if "edit-me" in t.links]
    assert stored.narration == "Editada"
    with pytest.raises(TxnNotFound):
        ledger.replace_txn("ws1", "nope-id", _txn())
    with pytest.raises(TxnNotFound):
        ledger.replace_txn("ws-empty", "nope-id", _txn())


def test_load_logs_loader_errors_and_health_reports_them(ledger, caplog):
    ledger.main_path("ws1").write_text(
        ledger.main_path("ws1").read_text(encoding="utf-8") + '2026-08-06 * "x"\n  Assets:Nope  1.00 MXN\n  Income:Y  1.00 MXN\n\n',
        encoding="utf-8",
    )
    import logging

    with caplog.at_level(logging.WARNING, logger="aurum.ledger"):
        health = ledger.health("ws1")
    assert health["error_count"] >= 1
    assert health["errors"][0]["lineno"]
    assert "loaded with" in caplog.text


def test_workspace_id_validated_on_the_store(ledger):
    from aurum.core.config import InvalidWorkspaceId

    with pytest.raises(InvalidWorkspaceId):
        ledger.main_path("../x")


def test_api_rejects_injection_and_balances_unchanged():
    client = TestClient(create_app())
    body = _txn().model_dump(mode="json")
    assert client.post("/api/ledger/ws1/transactions", json=body).status_code == 200
    before = client.get("/api/ledger/ws1/balances").json()
    bad = dict(body)
    bad["postings"] = [{"account": INJECTED, "amount": {"amount": "1", "currency": "MXN"}}, {"account": "Income:X"}]
    resp = client.post("/api/ledger/ws1/transactions", json=bad)
    assert resp.status_code == 422, resp.text
    tagged = dict(body)
    tagged["tags"] = ["a b"]
    assert client.post("/api/ledger/ws1/transactions", json=tagged).status_code == 422
    assert client.get("/api/ledger/ws1/balances").json() == before
    health = client.get("/api/ledger/ws1/health").json()
    assert health == {"txns": 1, "errors": [], "error_count": 0}
