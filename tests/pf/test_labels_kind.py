"""Categories carry kind + archived; POST derives the ledger account server-side; DELETE refuses in-use."""

from __future__ import annotations

import pytest

from aurum.core.money import Amount
from aurum.pf import accounts_admin, entries, labels


def test_seeds_have_kinds_and_income_seeds_exist(ledger):
    rows = labels.list_labels("ws", kind="income")
    assert {r["name"] for r in rows} >= {"Sueldo/Nómina", "Renta cobrada", "Intereses", "Dividendos", "Otros ingresos"}
    assert all(r["account"].startswith("Income:") for r in rows)
    expense = labels.list_labels("ws", kind="expense")
    assert all(r["account"].startswith("Expenses:") for r in expense)
    transfer = labels.list_labels("ws", kind="transfer")
    assert {r["name"] for r in transfer} == {"Ahorro/Inversión", "Transferencia"}


def test_post_derives_account_and_validates_grammar(ledger, client):
    r = client.post("/api/pf/ws/labels", json={"name": "Gimnasio", "kind": "expense"})
    assert r.status_code == 200, r.text
    gym = r.json()
    assert gym["account"] == "Expenses:Gimnasio" and gym["kind"] == "expense" and ":" not in gym["name"]
    # same name again → suffix, never a collision
    r = client.post("/api/pf/ws/labels", json={"name": "Gimnasio", "kind": "expense"})
    assert r.json()["account"] == "Expenses:Gimnasio2"
    # parent nests under the parent's account and inherits its kind
    r = client.post("/api/pf/ws/labels", json={"name": "Yoga", "parent": gym["id"]})
    assert r.status_code == 200 and r.json()["account"] == "Expenses:Gimnasio:Yoga" and r.json()["kind"] == "expense"
    r = client.post("/api/pf/ws/labels", json={"name": "Propinas", "kind": "income"})
    assert r.json()["account"] == "Income:Propinas"
    # explicit account (advanced) must be valid Beancount grammar and match the kind
    assert client.post("/api/pf/ws/labels", json={"name": "X", "account": "Expenses:comida"}).status_code == 400
    assert client.post("/api/pf/ws/labels", json={"name": "X", "kind": "income", "account": "Expenses:Food"}).status_code == 400
    assert client.post("/api/pf/ws/labels", json={"name": "X", "parent": "nope", "kind": "expense"}).status_code == 404
    assert client.post("/api/pf/ws/labels", json={"name": "Acentuado ñ", "kind": "expense"}).json()["account"] == "Expenses:AcentuadoN"


def test_kind_mismatch_on_entries_and_archive_hides_from_pickers(ledger, client):
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Efectivo", type="cash"))
    food = next(x for x in labels.list_labels("ws") if x["name"] == "Comida fuera")
    r = client.post("/api/pf/ws/entries", json={
        "kind": "income", "date": "2026-09-05", "amount": {"amount": "10", "currency": "MXN"},
        "account_id": acct["id"], "label_id": food["id"],
    })
    assert r.status_code == 400 and "gastos" in r.json()["detail"]
    r = client.put(f"/api/pf/ws/labels/{food['id']}", json={"archived": True})
    assert r.status_code == 200 and r.json()["archived"] is True
    assert food["id"] not in {x["id"] for x in client.get("/api/pf/ws/labels?kind=expense").json()}
    assert food["id"] in {x["id"] for x in client.get("/api/pf/ws/labels?include_archived=1").json()}
    r = client.put(f"/api/pf/ws/labels/{food['id']}", json={"archived": False, "icon": "🌮", "aliases": ["taquería"]})
    assert r.json()["archived"] is False and r.json()["icon"] == "🌮" and r.json()["aliases"] == ["taquería"]


def test_delete_refuses_when_used_by_a_live_entry_or_split(ledger, client):
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Efectivo", type="cash"))
    food = next(x for x in labels.list_labels("ws") if x["name"] == "Comida fuera")
    e = entries.create_entry("ws", entries.EntryIn(kind="expense", date="2026-09-05", amount=Amount(amount="10"),
                                                   account_id=acct["id"], label_id=food["id"]))
    assert client.delete(f"/api/pf/ws/labels/{food['id']}").status_code == 409
    entries.delete_entry("ws", e["id"])
    assert client.delete(f"/api/pf/ws/labels/{food['id']}").status_code == 200

    super_ = next(x for x in labels.list_labels("ws") if x["name"] == "Súper")
    ropa = next(x for x in labels.list_labels("ws") if x["name"] == "Ropa")
    entries.create_entry("ws", entries.EntryIn(
        kind="expense", date="2026-09-05", amount=Amount(amount="10"), account_id=acct["id"],
        splits=[entries.SplitIn(label_id=super_["id"], amount=Amount(amount="4")),
                entries.SplitIn(label_id=ropa["id"], amount=Amount(amount="6"))],
    ))
    with pytest.raises(labels.LabelInUse):
        labels.delete_label("ws", ropa["id"])


def test_match_label_is_whole_word_and_accent_insensitive(ledger):
    assert labels.match_label("ws", "viaje a europa 900")["name"] == "Viajes"
    assert labels.match_label("ws", "250 tacos comida")["name"] == "Comida fuera"
    assert labels.match_label("ws", "Ropa nueva")["name"] == "Ropa"
    assert labels.match_label("ws", "europa")  is None
    assert labels.match_label("ws", "SÚPER del domingo")["name"] == "Súper"
    assert labels.match_label("ws", "nómina quincena", kind="income")["name"] == "Sueldo/Nómina"


def test_organize_style_full_label_update_keeps_working(ledger):
    """organizer/organize.py rebuilds a Label with only the original fields to teach an alias."""
    food = next(x for x in labels.list_labels("ws") if x["name"] == "Comida fuera")
    body = labels.Label(name=food["name"], aliases=[*food["aliases"], "taqueria el primo"], account=food["account"],
                        icon=food["icon"], tax=food["tax"], sort=food["sort"])
    updated = labels.update_label("ws", food["id"], body)
    assert "taqueria el primo" in updated["aliases"] and updated["kind"] == "expense" and updated["archived"] is False
