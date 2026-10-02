"""Archive both ways, DELETE archives only when empty (409 + hint otherwise), PUT syncs card/loan
rows, apr_percent in/out, archived cards drop out of /credit/*, clamp_day on cut/due dates."""

from __future__ import annotations

from datetime import date

from aurum.core.money import Amount
from aurum.pf import accounts_admin, credit, entries


def test_delete_archives_when_only_opening_and_adjust_rows_exist(ledger, client):
    r = client.post("/api/pf/ws/accounts", json={
        "name": "Vieja", "type": "checking", "opening_balance": {"amount": "100", "currency": "MXN"},
    })
    acct = r.json()
    client.post(f"/api/pf/ws/accounts/{acct['id']}/adjust", json={"balance": {"amount": "150", "currency": "MXN"}})
    r = client.delete(f"/api/pf/ws/accounts/{acct['id']}")
    assert r.status_code == 200 and r.json()["archived"] is True
    assert acct["id"] not in {a["id"] for a in client.get("/api/pf/ws/accounts").json()["accounts"]}
    assert acct["id"] in {a["id"] for a in client.get("/api/pf/ws/accounts?include_archived=1").json()["accounts"]}
    r = client.put(f"/api/pf/ws/accounts/{acct['id']}", json={"archived": False})
    assert r.status_code == 200 and r.json()["archived"] is False


def test_delete_refuses_with_hint_when_movements_exist_and_voids_count_as_empty(ledger, client):
    acct = client.post("/api/pf/ws/accounts", json={"name": "Efectivo", "type": "cash"}).json()
    e = client.post("/api/pf/ws/entries", json={
        "kind": "expense", "date": "2026-09-05", "amount": {"amount": "10", "currency": "MXN"}, "account_id": acct["id"],
    }).json()
    r = client.delete(f"/api/pf/ws/accounts/{acct['id']}")
    assert r.status_code == 409 and r.json()["hint"] == "archive"
    client.delete(f"/api/pf/ws/entries/{e['id']}")
    assert client.delete(f"/api/pf/ws/accounts/{acct['id']}").status_code == 200


def test_put_syncs_card_and_loan_rows_and_apr_percent(ledger, client):
    card = client.post("/api/pf/ws/accounts", json={
        "name": "Oro", "type": "credit_card", "cut_day": 20, "due_day": 10, "apr_percent": "14",
        "credit_limit": {"amount": "30000", "currency": "MXN"},
    }).json()
    assert card["apr"] == "0.14" and card["apr_percent"] == "14"
    cards = credit.list_cards("ws")
    assert cards[0]["cut_day"] == 20 and cards[0]["limit_amount"] == "30000.00" and cards[0]["apr"] == "0.14"
    r = client.put(f"/api/pf/ws/accounts/{card['id']}", json={
        "name": "Oro Plus", "cut_day": 31, "due_day": 25, "apr": "0.2", "credit_limit": {"amount": "50000", "currency": "MXN"},
    })
    assert r.status_code == 200, r.text
    assert r.json()["apr_percent"] == "20" and r.json()["cut_day"] == 31
    cards = credit.list_cards("ws")
    assert cards[0]["name"] == "Oro Plus" and cards[0]["cut_day"] == 31 and cards[0]["due_day"] == 25
    assert cards[0]["limit_amount"] == "50000.00" and cards[0]["apr"] == "0.2"
    status = client.get("/api/pf/ws/credit/cards").json()[0]
    assert status["next_cut_date"].endswith(("-28", "-29", "-30", "-31"))
    # archiving the account hides the card from /credit/*
    client.put(f"/api/pf/ws/accounts/{card['id']}", json={"archived": True})
    assert client.get("/api/pf/ws/credit/cards").json() == []

    loan = client.post("/api/pf/ws/accounts", json={
        "name": "Auto", "type": "loan", "opening_balance": {"amount": "100000", "currency": "MXN"},
        "apr_percent": "12", "loan_months": 36,
    }).json()
    assert loan["loan_months"] == 36
    r = client.put(f"/api/pf/ws/accounts/{loan['id']}", json={"loan_months": 48, "loan_principal": {"amount": "120000", "currency": "MXN"}})
    assert r.json()["loan_months"] == 48
    row = credit.list_loans("ws")[0]
    assert row["months"] == 48 and row["principal"] == "120000.00"
    client.put(f"/api/pf/ws/accounts/{loan['id']}", json={"archived": True})
    assert client.get("/api/pf/ws/credit/loans").json() == []


def test_rename_to_an_existing_name_is_409(ledger, client):
    a = client.post("/api/pf/ws/accounts", json={"name": "A", "type": "cash"}).json()
    client.post("/api/pf/ws/accounts", json={"name": "B", "type": "checking"})
    r = client.put(f"/api/pf/ws/accounts/{a['id']}", json={"name": "b"})
    assert r.status_code == 409 and r.json()["existing_id"]


def test_next_day_uses_clamp_day():
    assert credit._next_day(date(2026, 2, 10), 31) == date(2026, 2, 28)
    assert credit._next_day(date(2026, 3, 31), 31) == date(2026, 3, 31)
    assert credit._next_day(date(2026, 1, 31), 30) == date(2026, 2, 28)
    assert credit._next_day(date(2026, 12, 20), 5) == date(2027, 1, 5)


def test_rows_expose_opening_and_ledger_account(ledger):
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(
        name="Cheques", type="checking", opening_balance=Amount(amount="500"), opening_date="2026-01-15"))
    assert acct["opening_balance"] == {"amount": "500.00", "currency": "MXN"} and acct["opening_date"] == "2026-01-15"
    assert acct["ledger_account"] == acct["account"]
    entries.create_entry("ws", entries.EntryIn(kind="expense", date="2026-02-01", amount=Amount(amount="20"), account_id=acct["id"]))
    rows = accounts_admin.list_accounts("ws")
    assert rows[0]["opening_balance"]["amount"] == "500.00" and rows[0]["balance"]["amount"] == "480.00"
