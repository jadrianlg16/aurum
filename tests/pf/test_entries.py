from __future__ import annotations

from datetime import date
from decimal import Decimal

from aurum.core.money import Amount
from aurum.ledger.base import Posting, Transaction
from aurum.pf import accounts_admin, entries, labels


def _account(ws, name="Cuenta", type_="checking", opening=None):
    body = accounts_admin.AccountIn(name=name, type=type_, opening_balance=opening)
    return accounts_admin.create_account(ws, body)


def _label(ws, name="Comida fuera") -> str:
    return next(x for x in labels.list_labels(ws) if x["name"] == name)["id"]


def _rows(ws, **kw) -> list[dict]:
    return entries.list_entries(ws, **kw)["entries"]


def _balance(ws, account_id) -> Decimal:
    return Decimal(accounts_admin.get_account(ws, account_id)["balance"]["amount"])


def test_log_a_coffee_end_to_end(ledger):
    """The non-negotiable: fresh workspace, one account, one expense, balance changes."""
    acct = _account("ws", "Efectivo", "cash")
    entry = entries.create_entry(
        "ws",
        entries.EntryIn(
            kind="expense", date=date(2026, 1, 5), amount=Amount(amount="55.00"),
            account_id=acct["id"], payee="Café", note="Cafecito",
        ),
    )
    assert entry["amount"] == {"amount": "-55.00", "currency": "MXN"}
    assert entry["editable"] is True
    assert "postings" not in entry
    balance = accounts_admin.get_account("ws", acct["id"])["balance"]
    assert balance["amount"] == "-55.00"


def test_income_entry_is_positive(ledger):
    acct = _account("ws")
    entry = entries.create_entry(
        "ws", entries.EntryIn(kind="income", date=date(2026, 1, 5), amount=Amount(amount="1000"), account_id=acct["id"])
    )
    assert entry["amount"]["amount"] == "1000.00"
    assert _balance("ws", acct["id"]) == Decimal("1000")


def test_transfer_moves_money_between_two_accounts(ledger):
    a = _account("ws", "A", opening=Amount(amount="500"))
    b = _account("ws", "B")
    entries.create_entry(
        "ws",
        entries.EntryIn(
            kind="transfer", date=date(2026, 1, 5), amount=Amount(amount="200"),
            account_id=a["id"], to_account_id=b["id"],
        ),
    )
    assert _balance("ws", a["id"]) == Decimal("300")
    assert _balance("ws", b["id"]) == Decimal("200")


def test_splits_must_sum_to_amount(ledger):
    acct = _account("ws")
    try:
        entries.create_entry(
            "ws",
            entries.EntryIn(
                kind="expense", date=date(2026, 1, 5), amount=Amount(amount="100"), account_id=acct["id"],
                splits=[
                    entries.SplitIn(label_id=_label("ws"), amount=Amount(amount="40")),
                    entries.SplitIn(label_id=_label("ws", "Súper"), amount=Amount(amount="50")),
                ],
            ),
        )
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_split_expense_creates_one_row_per_split_and_balances(ledger):
    acct = _account("ws")
    entry = entries.create_entry(
        "ws",
        entries.EntryIn(
            kind="expense", date=date(2026, 1, 5), amount=Amount(amount="100"), account_id=acct["id"],
            splits=[
                entries.SplitIn(label_id=_label("ws"), amount=Amount(amount="40"), note="parte 1"),
                entries.SplitIn(label_id=_label("ws", "Súper"), amount=Amount(amount="60"), note="parte 2"),
            ],
        ),
    )
    assert len(entry["splits"]) == 2
    assert _balance("ws", acct["id"]) == Decimal("-100")


def test_edit_rewrites_the_ledger_without_erasing_history(ledger):
    acct = _account("ws")
    entry = entries.create_entry(
        "ws", entries.EntryIn(kind="expense", date=date(2026, 1, 5), amount=Amount(amount="50"), account_id=acct["id"])
    )
    before_txns = len(ledger.journal("ws"))
    updated = entries.update_entry(
        "ws", entry["id"],
        entries.EntryIn(kind="expense", date=date(2026, 1, 5), amount=Amount(amount="80"), account_id=acct["id"]),
    )
    assert updated["amount"]["amount"] == "-80.00"
    assert _balance("ws", acct["id"]) == Decimal("-80")
    # a reversal + a new transaction were appended, nothing rewritten in place
    assert len(ledger.journal("ws")) == before_txns + 2


def test_delete_voids_and_hides_from_list(ledger):
    acct = _account("ws")
    entry = entries.create_entry(
        "ws", entries.EntryIn(kind="expense", date=date(2026, 1, 5), amount=Amount(amount="50"), account_id=acct["id"])
    )
    entries.delete_entry("ws", entry["id"])
    assert _balance("ws", acct["id"]) == Decimal("0")
    ids = [e["id"] for e in _rows("ws")]
    assert entry["id"] not in ids


def test_bulk_create(ledger):
    acct = _account("ws")
    created = entries.bulk_create(
        "ws",
        [
            entries.EntryIn(kind="expense", date=date(2026, 1, 5), amount=Amount(amount="10"), account_id=acct["id"]),
            entries.EntryIn(kind="expense", date=date(2026, 1, 6), amount=Amount(amount="20"), account_id=acct["id"]),
        ],
    )
    assert len(created["created"]) == 2 and created["errors"] == []
    assert _balance("ws", acct["id"]) == Decimal("-30")


def test_foreign_entries_from_another_subsystem_are_visible_but_not_editable(ledger):
    acct = _account("ws", opening=Amount(amount="0"))
    # simulate a CFDI/payroll write straight to the ledger, bypassing pf.entries entirely
    ledger.append(
        "ws",
        Transaction(
            date=date(2026, 1, 10), payee="Nómina", narration="Pago de nómina",
            postings=[
                Posting(account=acct["account"], amount=Amount(amount="5000")),
                Posting(account="Income:Salary"),
            ],
            tags=["payroll"],
        ),
    )
    rows = _rows("ws")
    foreign = [r for r in rows if r["source"] == "payroll"]
    assert len(foreign) == 1
    assert foreign[0]["editable"] is False
    assert foreign[0]["non_editable_reason"]
    assert foreign[0]["amount"]["amount"] == "5000.00"
    assert foreign[0]["account_id"] == acct["id"]


def test_get_entries_never_exposes_postings(ledger):
    acct = _account("ws")
    entries.create_entry(
        "ws", entries.EntryIn(kind="expense", date=date(2026, 1, 5), amount=Amount(amount="50"), account_id=acct["id"])
    )
    for row in _rows("ws"):
        assert "postings" not in row
        assert "debit" not in row and "credit" not in row


def test_router_create_list_edit_delete(client):
    acct = client.post("/api/pf/ws/accounts", json={"name": "Cuenta", "type": "checking"}).json()
    created = client.post(
        "/api/pf/ws/entries",
        json={"kind": "expense", "date": "2026-01-05", "amount": {"amount": "40", "currency": "MXN"},
              "account_id": acct["id"], "payee": "Tacos"},
    )
    assert created.status_code == 200
    entry_id = created.json()["id"]

    listed = client.get("/api/pf/ws/entries")
    assert listed.status_code == 200
    page = listed.json()
    assert set(page) == {"entries", "next_cursor", "totals"}
    assert any(e["id"] == entry_id for e in page["entries"])
    assert page["totals"]["out"]["amount"] == "40.00" and page["totals"]["count"] == 1

    updated = client.put(
        f"/api/pf/ws/entries/{entry_id}",
        json={"kind": "expense", "date": "2026-01-05", "amount": {"amount": "45", "currency": "MXN"},
              "account_id": acct["id"], "payee": "Tacos"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"]["amount"] == "-45.00"

    deleted = client.delete(f"/api/pf/ws/entries/{entry_id}")
    assert deleted.status_code == 200
    listed2 = client.get("/api/pf/ws/entries")
    assert all(e["id"] != entry_id for e in listed2.json()["entries"])


def test_put_accepts_a_partial_body_and_keeps_the_rest(client, ledger):
    ws = "ws"
    acct = client.post(f"/api/pf/{ws}/accounts", json={"name": "Efectivo", "type": "cash"}).json()
    created = client.post(
        f"/api/pf/{ws}/entries",
        json={"kind": "expense", "date": "2026-09-07", "amount": {"amount": "250.00", "currency": "MXN"},
              "account_id": acct["id"], "payee": "Tacos El Primo", "note": "comida"},
    ).json()
    r = client.put(f"/api/pf/{ws}/entries/{created['id']}", json={"amount": {"amount": "300.00", "currency": "MXN"}})
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["amount"]["amount"] == "-300.00"
    assert row["payee"] == "Tacos El Primo" and row["note"] == "comida" and row["account_id"] == acct["id"]
