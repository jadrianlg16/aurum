from __future__ import annotations

from datetime import date

from aurum.pf import accounts_admin


def test_create_account_with_opening_balance_shows_in_ledger(ledger):
    acct = accounts_admin.create_account(
        "ws",
        accounts_admin.AccountIn(
            name="BBVA Nómina", type="checking", institution="BBVA",
            opening_balance={"amount": "1500.00", "currency": "MXN"},
            opening_date=date(2026, 1, 1),
        ),
    )
    assert acct["account"] == "Assets:Bank:BbvaNomina"
    assert acct["balance"]["amount"] == "1500.00"
    assert acct["archived"] is False


def test_create_account_twice_is_a_409_with_the_existing_id(ledger, client):
    """A duplicate name is a 409 carrying the existing id."""
    first = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="BBVA Nómina", type="checking"))
    try:
        accounts_admin.create_account("ws", accounts_admin.AccountIn(name="bbva nómina", type="savings"))
        raised = None
    except accounts_admin.AccountExists as e:
        raised = e
    assert raised is not None and raised.existing_id == first["id"]
    rows = accounts_admin.list_accounts("ws")
    assert sum(1 for r in rows if r["account"] == first["account"]) == 1
    r = client.post("/api/pf/ws/accounts", json={"name": "BBVA Nómina", "type": "checking"})
    assert r.status_code == 409 and r.json()["existing_id"] == first["id"]


def test_different_names_never_collide_on_the_same_ledger_account(ledger):
    a = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Fondo!", type="savings"))
    b = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Fondo?", type="savings"))
    assert a["account"] != b["account"]


def test_cash_account_uses_the_plain_assets_cash_leaf(ledger):
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Efectivo", type="cash"))
    assert acct["account"] == "Assets:Cash"


def test_update_account_renames_without_touching_ledger_account(ledger):
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Santander", type="checking"))
    updated = accounts_admin.update_account("ws", acct["id"], accounts_admin.AccountUpdate(name="Santander Débito"))
    assert updated["name"] == "Santander Débito"
    assert updated["account"] == acct["account"]


def test_adjust_account_posts_a_reconciling_entry(ledger):
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Cuenta", type="checking"))
    adjusted = accounts_admin.adjust_account(
        "ws", acct["id"], accounts_admin.AdjustBody(balance={"amount": "300.00", "currency": "MXN"})
    )
    assert adjusted["balance"]["amount"] == "300.00"


def test_delete_refuses_when_account_has_movements(ledger):
    from aurum.core.money import Amount
    from aurum.ledger.base import Posting, Transaction

    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Con movimientos", type="checking"))
    ledger.append(
        "ws",
        Transaction(
            date=date.today(), payee="Tienda", narration="Tienda",
            postings=[
                Posting(account="Expenses:Other", amount=Amount(amount="50")),
                Posting(account=acct["account"]),
            ],
        ),
    )
    try:
        accounts_admin.delete_account("ws", acct["id"])
        raised = False
    except accounts_admin.AccountHasMovements:
        raised = True
    assert raised


def test_delete_archives_when_no_movements(ledger):
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Vacía", type="checking"))
    result = accounts_admin.delete_account("ws", acct["id"])
    assert result["archived"] is True
    assert acct["id"] not in [a["id"] for a in accounts_admin.list_accounts("ws")]


def test_router_create_and_get_account(client):
    r = client.post("/api/pf/ws/accounts", json={"name": "Efectivo diario", "type": "cash"})
    assert r.status_code == 200
    body = r.json()
    assert body["account"] == "Assets:Cash"
    r2 = client.get(f"/api/pf/ws/accounts/{body['id']}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Efectivo diario"


def test_router_accounts_summary_includes_friendly_rows(client):
    client.post("/api/pf/ws/accounts", json={"name": "Cuenta A", "type": "checking"})
    r = client.get("/api/pf/ws/accounts")
    assert r.status_code == 200
    body = r.json()
    assert "accounts" in body
    assert any(a["name"] == "Cuenta A" for a in body["accounts"])
