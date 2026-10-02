"""Goals point at a pf account by id; account/currency derived; progress by kind; tolerant dates."""

from __future__ import annotations

from datetime import date, timedelta

from aurum.core.money import Amount
from aurum.pf import accounts_admin, entries, goals, store


def _accounts(ws="ws"):
    checking = accounts_admin.create_account(
        ws, accounts_admin.AccountIn(name="Cheques", type="checking", opening_balance=Amount(amount="20000")))
    savings = accounts_admin.create_account(
        ws, accounts_admin.AccountIn(name="Ahorro", type="savings", opening_balance=Amount(amount="12000")))
    return checking, savings


def test_post_with_account_id_derives_account_and_progress(ledger, client):
    checking, savings = _accounts()
    next_year = (date.today() + timedelta(days=365)).isoformat()
    r = client.post("/api/pf/ws/goals", json={
        "kind": "savings", "name": "Viaje", "target": "30000", "target_date": next_year, "account_id": savings["id"],
    })
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["account"] == savings["account"] and g["account"].startswith("Assets:")
    assert g["account_id"] == savings["id"] and g["account_name"] == "Ahorro" and g["currency"] == "MXN"
    assert g["progress"]["amount"] == "12000.00" and g["pct"] == 40.0 and g["target"]["amount"] == "30000.00"
    assert g["remaining"]["amount"] == "18000.00" and g["monthly_required"]

    entries.create_entry("ws", entries.EntryIn(kind="transfer", date=date.today().isoformat(), amount=Amount(amount="2000"),
                                               account_id=checking["id"], to_account_id=savings["id"]))
    row = client.get("/api/pf/ws/goals").json()[0]
    assert row["progress"]["amount"] == "14000.00"

    assert client.post("/api/pf/ws/goals", json={"kind": "savings", "name": "x", "target": "1", "account_id": "nope"}).status_code == 404
    assert client.post("/api/pf/ws/goals", json={"kind": "savings", "name": "x", "target": "1"}).status_code == 400


def test_put_is_partial_and_account_can_change(ledger, client):
    checking, savings = _accounts()
    g = goals.create_goal("ws", goals.Goal(kind="purchase", name="Laptop", target="20000", account_id=checking["id"]))
    r = client.put(f"/api/pf/ws/goals/{g['id']}", json={"name": "Laptop nueva"})
    assert r.status_code == 200 and r.json()["name"] == "Laptop nueva" and r.json()["account_id"] == checking["id"]
    r = client.put(f"/api/pf/ws/goals/{g['id']}", json={"account_id": savings["id"]})
    assert r.json()["account"] == savings["account"] and r.json()["progress"]["amount"] == "12000.00"
    assert client.put(f"/api/pf/ws/goals/{g['id']}", json={"account_id": "nope"}).status_code == 404
    assert client.put(f"/api/pf/ws/goals/{g['id']}", json={"target_date": "1999-01-01"}).status_code == 422
    assert client.put("/api/pf/ws/goals/nope", json={"name": "x"}).status_code == 404


def test_advanced_account_string_path_still_works(ledger):
    """demo/extras.py creates goals with a ledger account string and no target_date check."""
    g = goals.create_goal("ws", goals.Goal(kind="emergency", name="Fondo", target="90000", currency="MXN",
                                           target_date="2027-06-30", account="Assets:Bank:Nu"))
    assert g["account"] == "Assets:Bank:Nu" and g["account_id"] is None
    row = goals.goal_with_progress("ws", g)
    assert row["account_name"] is None and row["progress"]["amount"] == "0.00"
    assert "months_of_spend_covered" in row
    # a matching pf account later resolves the id on the way out
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Nu", type="checking"))
    assert acct["account"] == "Assets:Bank:Nu"
    updated = goals.update_goal("ws", g["id"], goals.Goal(**{**g, "account": "Assets:Bank:Nu"}))
    assert updated["account_id"] == acct["id"]


def test_stored_bad_target_date_never_raises(ledger, client):
    checking, _ = _accounts()
    g = goals.create_goal("ws", goals.Goal(kind="savings", name="x", target="100", account_id=checking["id"]))
    conn = store.db()
    conn.execute("UPDATE pf_goals SET target_date='garbage' WHERE id=?", (g["id"],))
    conn.commit()
    r = client.get("/api/pf/ws/goals")
    assert r.status_code == 200
    row = r.json()[0]
    assert row["target_date_invalid"] is True and row["monthly_required"] is None
    # an unrelated edit still works and keeps the (bad) stored date out of the way
    assert client.put(f"/api/pf/ws/goals/{g['id']}", json={"name": "y"}).status_code == 200
