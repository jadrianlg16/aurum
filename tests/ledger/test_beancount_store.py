from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aurum.core.money import Amount
from aurum.ledger.base import LedgerStore, Posting, Transaction, get_ledger
from aurum.ledger.beancount_store import BeancountLedger
from aurum.ledger.router import router


def txn(day: str, amount: str, account: str = "Assets:Bank:BBVA", **kw) -> Transaction:
    return Transaction(
        date=date.fromisoformat(day),
        payee=kw.pop("payee", "ACME SA de CV"),
        narration=kw.pop("narration", "Factura"),
        postings=[
            Posting(account=account, amount=Amount(amount=Decimal(amount), currency="MXN")),
            Posting(account="Income:Freelance"),
        ],
        **kw,
    )


def test_implements_the_protocol():
    assert isinstance(BeancountLedger(), LedgerStore)


def test_get_ledger_returns_the_beancount_store():
    assert isinstance(get_ledger(), BeancountLedger)


def test_append_creates_files_and_opens_accounts():
    ledger = BeancountLedger()
    ledger.append("ws1", txn("2026-08-05", "11600.00"))
    assert ledger.main_path("ws1").exists()
    accounts_text = ledger.accounts_path("ws1").read_text(encoding="utf-8")
    assert "2026-08-05 open Assets:Bank:BBVA" in accounts_text
    assert "2026-08-05 open Income:Freelance" in accounts_text
    assert ledger.accounts("ws1") == ["Assets:Bank:BBVA", "Income:Freelance"]


def test_ledger_loads_without_errors_and_balances():
    ledger = BeancountLedger()
    ledger.append("ws1", txn("2026-08-05", "11600.00"))
    ledger.append("ws1", txn("2026-08-20", "5800.00"))
    _entries, errors = ledger.load("ws1")
    assert errors == []
    balances = ledger.balances("ws1")
    assert balances["Assets:Bank:BBVA"][0].amount == Decimal("17400.00")
    assert balances["Income:Freelance"][0].amount == Decimal("-17400.00")


def test_an_earlier_transaction_moves_the_open_directive_back():
    ledger = BeancountLedger()
    ledger.append("ws1", txn("2026-08-05", "1000.00"))
    ledger.append("ws1", txn("2026-06-01", "500.00"))
    assert "2026-06-01 open Assets:Bank:BBVA" in ledger.accounts_path("ws1").read_text(encoding="utf-8")
    assert ledger.load("ws1")[1] == []


def test_meta_tags_and_links_round_trip():
    ledger = BeancountLedger()
    t = txn(
        "2026-08-05",
        "11600.00",
        tags=["resico"],
        links=["cfdi-1"],
        meta={"cfdi_uuid": "AAAA-BBBB", "label": "freelance", "bad key!": "dropped"},
    )
    assert ledger.append("ws1", t) == "cfdi-1"
    (stored,) = ledger.journal("ws1")
    assert stored.tags == ["resico"]
    assert stored.links == ["cfdi-1"]
    assert stored.meta["cfdi_uuid"] == "AAAA-BBBB"
    assert "bad key!" not in stored.meta
    assert stored.payee == "ACME SA de CV"


def test_balancing_posting_is_filled_in():
    ledger = BeancountLedger()
    ledger.append("ws1", txn("2026-08-05", "11600.00"))
    (stored,) = ledger.journal("ws1")
    amounts = {p.account: p.amount.amount for p in stored.postings if p.amount}
    assert amounts["Income:Freelance"] == Decimal("-11600.00")


def test_journal_filters():
    ledger = BeancountLedger()
    ledger.append("ws1", txn("2026-07-05", "100.00"))
    ledger.append("ws1", txn("2026-08-05", "200.00", account="Assets:Cash"))
    assert len(ledger.journal("ws1", start=date(2026, 8, 1))) == 1
    assert len(ledger.journal("ws1", end=date(2026, 7, 31))) == 1
    assert len(ledger.journal("ws1", account_prefix="Assets:Cash")) == 1
    assert len(ledger.journal("ws1", account_prefix="Assets:")) == 2


def test_balances_as_of():
    ledger = BeancountLedger()
    ledger.append("ws1", txn("2026-07-05", "100.00"))
    ledger.append("ws1", txn("2026-08-05", "200.00"))
    assert ledger.balances("ws1", as_of=date(2026, 7, 31))["Assets:Bank:BBVA"][0].amount == Decimal("100.00")


def test_query_via_beanquery():
    ledger = BeancountLedger()
    ledger.append("ws1", txn("2026-08-05", "11600.00"))
    rows = ledger.query("ws1", "SELECT account, sum(position) AS bal GROUP BY account ORDER BY account")
    assert [r["account"] for r in rows] == ["Assets:Bank:BBVA", "Income:Freelance"]
    assert all(isinstance(r["bal"], str) for r in rows)


def test_unknown_workspace_reads_empty():
    ledger = BeancountLedger()
    assert ledger.journal("nope") == []
    assert ledger.balances("nope") == {}
    assert ledger.accounts("nope") == []
    assert ledger.query("nope", "SELECT account") == []


def test_template_opens_the_resico_chart_of_accounts():
    ledger = BeancountLedger()
    opened = ledger.apply_template("ws1")
    assert "Assets:Taxes:IVA-Acreditable" in opened
    assert "Liabilities:Taxes:IVA-Trasladado" in opened
    assert "Expenses:Taxes:ISR" in opened
    assert "Equity:Opening" in opened
    ledger.apply_template("ws1")  # idempotent
    assert ledger.load("ws1")[1] == []
    assert len(ledger.accounts("ws1")) == len(opened)


def test_concurrent_appends_are_all_recorded():
    ledger = BeancountLedger()
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            ledger.append("ws1", txn("2026-08-05", "100.00", links=[f"t{i}"]))
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert ledger.load("ws1")[1] == []
    assert len(ledger.journal("ws1")) == 12


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/ledger")
    return TestClient(app)


def test_endpoints(client: TestClient):
    body = txn("2026-08-05", "11600.00", meta={"label": "freelance"}).model_dump(mode="json")
    posted = client.post("/api/ledger/ws1/transactions", json=body)
    assert posted.status_code == 200
    assert posted.json()["id"]

    journal = client.get("/api/ledger/ws1/journal")
    assert journal.status_code == 200
    assert journal.json()[0]["postings"][0]["amount"]["amount"] == "11600.00"

    balances = client.get("/api/ledger/ws1/balances").json()
    assert balances["Assets:Bank:BBVA"][0] == {"amount": "11600.00", "currency": "MXN"}

    assert client.get("/api/ledger/ws1/accounts").json() == ["Assets:Bank:BBVA", "Income:Freelance"]

    rows = client.post("/api/ledger/ws1/query", json={"bql": "SELECT account GROUP BY account"})
    assert rows.status_code == 200
    assert len(rows.json()) == 2

    assert client.post("/api/ledger/ws1/query", json={"bql": "NOT BQL"}).status_code == 400


def test_journal_endpoint_filters(client: TestClient):
    client.post("/api/ledger/ws1/transactions", json=txn("2026-07-05", "100.00").model_dump(mode="json"))
    client.post("/api/ledger/ws1/transactions", json=txn("2026-08-05", "200.00").model_dump(mode="json"))
    got = client.get("/api/ledger/ws1/journal", params={"start": "2026-08-01"}).json()
    assert len(got) == 1
