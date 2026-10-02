from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.workspaces import Workspace, save_workspace
from aurum.ledger.base import get_ledger
from aurum.ledger.statements import period_bounds


def _client() -> TestClient:
    save_workspace(Workspace(id="ws1", name="Test", base_currency="MXN"))
    return TestClient(create_app())


def _txn_body(amount: str, payee: str = "ACME", narration: str = "Factura", day: str = "2026-08-05") -> dict:
    return {
        "date": day,
        "payee": payee,
        "narration": narration,
        "postings": [
            {"account": "Assets:Bank:BBVA", "amount": {"amount": amount, "currency": "MXN"}},
            {"account": "Income:Freelance"},
        ],
    }


def test_period_bounds_month_and_year():
    assert period_bounds("2026-08") == (date(2026, 8, 1), date(2026, 8, 31))
    assert period_bounds("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert period_bounds("2026") == (date(2026, 1, 1), date(2026, 12, 31))


def test_pnl_statement():
    client = _client()
    client.post("/api/ledger/ws1/transactions", json=_txn_body("1000.00"))
    resp = client.get("/api/ledger/ws1/statements/2026-08", params={"type": "pnl"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "pnl"
    income = next(s for s in body["sections"] if s["title"] == "Income")
    assert income["total"]["amount"] == "1000.00"
    assert body["net"]["amount"] == "1000.00"
    assert body["explain"]["summary"]


def test_balance_statement():
    client = _client()
    client.post("/api/ledger/ws1/transactions", json=_txn_body("1000.00"))
    resp = client.get("/api/ledger/ws1/statements/2026-08", params={"type": "balance"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assets = next(s for s in body["sections"] if s["title"] == "Assets")
    assert assets["total"]["amount"] == "1000.00"


def test_cashflow_statement():
    client = _client()
    client.post("/api/ledger/ws1/transactions", json=_txn_body("1000.00"))
    resp = client.get("/api/ledger/ws1/statements/2026-08", params={"type": "cashflow"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["net"]["amount"] == "1000.00"


def test_statement_bad_type_400():
    client = _client()
    resp = client.get("/api/ledger/ws1/statements/2026-08", params={"type": "bogus"})
    assert resp.status_code == 400


def test_statement_bad_period_400():
    client = _client()
    resp = client.get("/api/ledger/ws1/statements/not-a-period", params={"type": "pnl"})
    assert resp.status_code == 400


def test_update_transaction_rewrites_in_place():
    client = _client()
    txn_id = client.post("/api/ledger/ws1/transactions", json=_txn_body("1000.00")).json()["id"]

    resp = client.put(f"/api/ledger/ws1/transactions/{txn_id}", json=_txn_body("1200.00", narration="Editada"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == txn_id

    journal = client.get("/api/ledger/ws1/journal").json()
    assert len(journal) == 1
    assert journal[0]["narration"] == "Editada"
    assert journal[0]["postings"][0]["amount"]["amount"] == "1200.00"
    assert journal[0]["links"] == [txn_id]


def test_update_missing_transaction_404():
    client = _client()
    resp = client.put("/api/ledger/ws1/transactions/does-not-exist", json=_txn_body("1.00"))
    assert resp.status_code == 404


def test_void_transaction_tags_and_reverses_never_erases():
    client = _client()
    txn_id = client.post("/api/ledger/ws1/transactions", json=_txn_body("1000.00")).json()["id"]

    resp = client.delete(f"/api/ledger/ws1/transactions/{txn_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == txn_id
    assert body["reversal_id"] != txn_id

    journal = client.get("/api/ledger/ws1/journal").json()
    assert len(journal) == 2  # original kept (tagged) + reversing entry — nothing erased
    original = next(t for t in journal if t["links"] == [txn_id])
    assert "voided" in original["tags"]

    reversal = next(t for t in journal if txn_id in t["links"] and t["links"] != [txn_id])
    assert "voided-reversal" in reversal["tags"]

    balances = client.get("/api/ledger/ws1/balances").json()
    bank = balances["Assets:Bank:BBVA"][0]
    assert Decimal(bank["amount"]) == Decimal("0")  # the reversal cancels the original out


def test_void_already_voided_conflict():
    client = _client()
    txn_id = client.post("/api/ledger/ws1/transactions", json=_txn_body("1000.00")).json()["id"]
    client.delete(f"/api/ledger/ws1/transactions/{txn_id}")
    resp = client.delete(f"/api/ledger/ws1/transactions/{txn_id}")
    assert resp.status_code == 409


def test_void_missing_transaction_404():
    client = _client()
    resp = client.delete("/api/ledger/ws1/transactions/does-not-exist")
    assert resp.status_code == 404


def test_edits_require_beancount_store(monkeypatch):
    from aurum.ledger.base import InMemoryLedger

    monkeypatch.setattr("aurum.ledger.router.get_ledger", lambda: InMemoryLedger())
    client = _client()
    resp = client.put("/api/ledger/ws1/transactions/whatever", json=_txn_body("1.00"))
    assert resp.status_code == 501


def test_get_ledger_is_beancount_by_default():
    from aurum.ledger.beancount_store import BeancountLedger

    assert isinstance(get_ledger(), BeancountLedger)
