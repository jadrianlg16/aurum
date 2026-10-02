"""Ordinary bad input is a 4xx by construction, and the ledger is byte-identical afterwards."""

from __future__ import annotations

import pytest

from aurum.pf import labels


def _acct(client, ws, name="Efectivo", type_="cash"):
    r = client.post(f"/api/pf/{ws}/accounts", json={"name": name, "type": type_})
    assert r.status_code == 200, r.text
    return r.json()


def _journal_len(ledger, ws):
    return len(ledger.journal(ws))


def _entry(acct, **over):
    body = {"kind": "expense", "date": "2026-09-05", "amount": {"amount": "12.50", "currency": "MXN"},
            "account_id": acct["id"]}
    body.update(over)
    return body


CASES = [
    ("amount float", lambda a, b: _entry(a, amount={"amount": 12.5, "currency": "MXN"}), 422),
    ("amount text", lambda a, b: _entry(a, amount={"amount": "abc", "currency": "MXN"}), 422),
    ("amount zero", lambda a, b: _entry(a, amount={"amount": "0", "currency": "MXN"}), 422),
    ("amount negative", lambda a, b: _entry(a, amount={"amount": "-5", "currency": "MXN"}), 422),
    ("bad date", lambda a, b: _entry(a, date="2026-13-40"), 422),
    ("bad kind", lambda a, b: _entry(a, kind="gift"), 422),
    ("tag with space", lambda a, b: _entry(a, tags=["a b"]), 400),
    ("currency too long", lambda a, b: _entry(a, amount={"amount": "1", "currency": "PESOS"}), 422),
    ("unknown account", lambda a, b: _entry(a, account_id="nope"), 404),
    ("unknown label", lambda a, b: _entry(a, label_id="nope"), 404),
    ("transfer to self", lambda a, b: _entry(a, kind="transfer", to_account_id=a["id"]), 400),
    ("transfer without destination", lambda a, b: _entry(a, kind="transfer"), 400),
    ("transfer to archived", lambda a, b: _entry(a, kind="transfer", to_account_id=b["id"]), 400),
    ("splits on transfer", lambda a, b: _entry(a, kind="transfer", to_account_id=b["id"],
                                               splits=[{"label_id": "x", "amount": {"amount": "12.50", "currency": "MXN"}}]), 400),
    ("split without label", lambda a, b: _entry(a, splits=[{"amount": {"amount": "12.50", "currency": "MXN"}}]), 422),
    ("splits do not sum", lambda a, b: _entry(a, splits=[
        {"label_id": "LBL", "amount": {"amount": "5", "currency": "MXN"}},
        {"label_id": "LBL", "amount": {"amount": "5", "currency": "MXN"}}]), 400),
    ("bad source", lambda a, b: _entry(a, source="telegram"), 422),
]


@pytest.mark.parametrize("name,make,status", CASES, ids=[c[0] for c in CASES])
def test_entries_4xx_table(ledger, client, name, make, status):
    acct = _acct(client, "ws")
    archived = _acct(client, "ws", "Vieja", "checking")
    assert client.put(f"/api/pf/ws/accounts/{archived['id']}", json={"archived": True}).status_code == 200
    lbl = next(x for x in labels.list_labels("ws") if x["name"] == "Comida fuera")
    body = make(acct, archived)
    if body.get("splits"):
        for sp in body["splits"]:
            if sp.get("label_id") == "LBL":
                sp["label_id"] = lbl["id"]
    before = _journal_len(ledger, "ws")
    r = client.post("/api/pf/ws/entries", json=body)
    assert r.status_code == status, (name, r.text)
    assert _journal_len(ledger, "ws") == before, name
    assert client.get("/api/pf/ws/entries").json()["totals"]["count"] == 0


def test_lowercase_currency_is_upper_cased_into_the_ledger(ledger, client):
    acct = _acct(client, "ws")
    r = client.post("/api/pf/ws/entries", json=_entry(acct, amount={"amount": "10", "currency": "mxn"}))
    assert r.status_code == 200, r.text
    assert r.json()["amount"]["currency"] == "MXN"
    txn = ledger.journal("ws")[0]
    assert {p.amount.currency for p in txn.postings if p.amount} == {"MXN"}


def test_query_and_other_routes_4xx(ledger, client):
    acct = _acct(client, "ws")
    assert client.get("/api/pf/ws/entries?from=abc").status_code == 422
    assert client.get("/api/pf/ws/entries?limit=501").status_code == 422
    assert client.get("/api/pf/ws/entries?limit=0").status_code == 422
    assert client.get("/api/pf/ws/entries?cursor=%%%").status_code == 400
    assert client.get("/api/pf/ws/review/2026-13").status_code == 422
    assert client.get("/api/pf/ws/budgets/status?period=2026-9").status_code == 422
    assert client.post("/api/pf/ws/goals", json={"kind": "foo", "name": "x", "target": "1", "account_id": acct["id"]}).status_code == 422
    assert client.post("/api/pf/ws/goals", json={"kind": "savings", "name": "x", "target": "1", "account_id": "nope"}).status_code == 404
    assert client.post("/api/pf/ws/goals", json={"kind": "savings", "name": "x", "target": "1", "account_id": acct["id"],
                                                 "target_date": "2000-01-01"}).status_code == 422
    assert client.post("/api/pf/ws/accounts", json={"name": "\n", "type": "cash"}).status_code == 422
    assert client.post("/api/pf/ws/accounts", json={"name": "x" * 81, "type": "cash"}).status_code == 422
    assert client.post("/api/pf/ws/accounts", json={"name": "Ok", "type": "checking", "currency": "pesos"}).status_code == 422
    assert client.post("/api/pf/ws/accounts", json={"name": "Ok", "type": "credit_card", "cut_day": 32}).status_code == 422
    assert client.post("/api/pf/ws/labels", json={"name": "Gimnasio", "kind": "expense", "account": "Expenses:comida"}).status_code == 400
    assert client.post("/api/pf/ws/labels", json={"name": "Gimnasio", "kind": "transfer"}).status_code == 400
    assert client.post("/api/pf/ws/income/streams", json={
        "name": "Sueldo", "source_type": "salary", "amount": {"amount": "1", "currency": "MXN"}, "cadence": "monthly",
        "anchor_days": [32], "account_id": acct["id"]}).status_code == 422
    assert client.post("/api/pf/ws/income/streams", json={
        "name": "Sueldo", "source_type": "salary", "amount": {"amount": "1", "currency": "MXN"}, "cadence": "weekly",
        "weekday": 7, "account_id": acct["id"]}).status_code == 422
    assert client.post("/api/pf/ws/credit/cards/card-x/msi", json={
        "card_id": "card-x", "purchase": "TV", "amount": "600", "months": 0, "started": "2026-06-01"}).status_code == 422
    assert ledger.journal("ws") == []
