"""Validate-then-write — the ledger is untouched on any 4xx; edits are one reversal + one txn;
bulk is all-or-nothing; missing ledger txn → 409."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aurum.core.money import Amount
from aurum.pf import accounts_admin, entries, labels, store


def _acct(ws="ws", name="Efectivo", type_="cash"):
    return accounts_admin.create_account(ws, accounts_admin.AccountIn(name=name, type=type_))


def _entry(ws, acct, amount="250", **kw):
    return entries.create_entry(
        ws, entries.EntryIn(kind="expense", date="2026-09-05", amount=Amount(amount=amount), account_id=acct["id"], **kw),
    )


def _balance(ws, acct) -> Decimal:
    return Decimal(accounts_admin.get_account(ws, acct["id"])["balance"]["amount"])


def test_put_with_bad_account_leaves_journal_and_balances_unchanged(ledger, client):
    acct = _acct()
    e = _entry("ws", acct)
    journal_before = len(ledger.journal("ws"))
    r = client.put(f"/api/pf/ws/entries/{e['id']}", json={"account_id": "nope"})
    assert r.status_code == 404
    assert len(ledger.journal("ws")) == journal_before
    assert _balance("ws", acct) == Decimal("-250")

    r = client.put(f"/api/pf/ws/entries/{e['id']}", json={"label_id": "nope"})
    assert r.status_code == 404 and len(ledger.journal("ws")) == journal_before
    r = client.put(f"/api/pf/ws/entries/{e['id']}", json={"tags": ["a b"]})
    assert r.status_code == 400 and len(ledger.journal("ws")) == journal_before


def test_valid_put_is_exactly_one_reversal_and_one_new_txn(ledger, client):
    acct = _acct()
    e = _entry("ws", acct)
    r = client.put(f"/api/pf/ws/entries/{e['id']}", json={"amount": {"amount": "300", "currency": "MXN"}})
    assert r.status_code == 200, r.text
    txns = ledger.journal("ws")
    assert len(txns) == 3
    reversal = [t for t in txns if "entry-reversal" in t.tags]
    assert len(reversal) == 1 and reversal[0].meta["reverses"] == e["txn_id"]
    assert _balance("ws", acct) == Decimal("-300")
    assert r.json()["txn_id"] != e["txn_id"]


def test_delete_twice_is_409_and_delete_after_ledger_loss_is_409(ledger, client):
    acct = _acct()
    e = _entry("ws", acct)
    assert client.delete(f"/api/pf/ws/entries/{e['id']}").status_code == 200
    assert client.delete(f"/api/pf/ws/entries/{e['id']}").status_code == 409
    assert client.put(f"/api/pf/ws/entries/{e['id']}", json={"payee": "x"}).status_code == 409

    e2 = _entry("ws", acct)
    conn = store.db()
    conn.execute("UPDATE pf_entries SET txn_id='txn-gone' WHERE id=?", (e2["id"],))
    conn.commit()
    journal_before = len(ledger.journal("ws"))
    assert client.delete(f"/api/pf/ws/entries/{e2['id']}").status_code == 409
    assert client.put(f"/api/pf/ws/entries/{e2['id']}", json={"payee": "x"}).status_code == 409
    assert len(ledger.journal("ws")) == journal_before


def test_bulk_is_all_or_nothing(ledger, client):
    acct = _acct()
    ok = {"kind": "expense", "date": "2026-09-05", "amount": {"amount": "10", "currency": "MXN"}, "account_id": acct["id"]}
    bad = {**ok, "label_id": "nope"}
    r = client.post("/api/pf/ws/entries/bulk", json={"entries": [ok, ok, bad, ok]})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == {"index": 2, "msg": "label nope not found"}
    assert ledger.journal("ws") == []
    assert client.get("/api/pf/ws/entries").json()["totals"]["count"] == 0

    r = client.post("/api/pf/ws/entries/bulk", json={"entries": [ok, ok]})
    assert r.status_code == 200 and len(r.json()["created"]) == 2
    assert _balance("ws", acct) == Decimal("-20")


def test_bulk_write_failure_reverses_what_was_written(ledger, monkeypatch):
    acct = _acct()
    ok = entries.EntryIn(kind="expense", date="2026-09-05", amount=Amount(amount="10"), account_id=acct["id"])
    calls = {"n": 0}
    real_insert = entries._insert_row

    def flaky(conn, ws_id, entry_id, p, txn_id):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("disk full")
        real_insert(conn, ws_id, entry_id, p, txn_id)

    monkeypatch.setattr(entries, "_insert_row", flaky)
    with pytest.raises(entries.BulkError) as exc:
        entries.bulk_create("ws", [ok, ok, ok])
    assert exc.value.index == 1
    assert _balance("ws", acct) == Decimal("0")
    assert entries.list_entries("ws")["totals"]["count"] == 0
    from aurum.pf import ledger_view

    assert ledger_view.live_txns("ws") == []


def test_create_failure_after_append_compensates(ledger, monkeypatch):
    acct = _acct()
    monkeypatch.setattr(entries, "_insert_row", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        _entry("ws", acct)
    assert _balance("ws", acct) == Decimal("0")
    from aurum.pf import ledger_view

    assert ledger_view.live_txns("ws") == []


def test_kind_mismatch_and_unknown_label_never_touch_the_ledger(ledger, client):
    acct = _acct()
    salary = next(x for x in labels.list_labels("ws") if x["name"] == "Sueldo/Nómina")
    r = client.post("/api/pf/ws/entries", json={
        "kind": "expense", "date": "2026-09-05", "amount": {"amount": "10", "currency": "MXN"},
        "account_id": acct["id"], "label_id": salary["id"],
    })
    assert r.status_code == 400 and "ingresos" in r.json()["detail"]
    assert ledger.journal("ws") == []
    r = client.post("/api/pf/ws/entries", json={
        "kind": "expense", "date": "2026-09-05", "amount": {"amount": "10", "currency": "MXN"},
        "account_id": acct["id"], "label_id": "lbl-nope",
    })
    assert r.status_code == 404 and ledger.journal("ws") == []


def test_helpers_for_organizer(ledger):
    acct = _acct()
    e = _entry("ws", acct, commitment_id="cmt-1", payee="Renta")
    assert entries.is_unedited("ws", e["id"]) is True
    from datetime import date

    found = entries.find_by_commitment("ws", "cmt-1", date(2026, 9, 7))
    assert found is not None and found["id"] == e["id"] and found["commitment_id"] == "cmt-1"
    assert entries.find_by_commitment("ws", "cmt-1", date(2026, 9, 20)) is None
    assert entries.list_entries("ws", commitment_id="cmt-1")["totals"]["count"] == 1
    txn = next(t for t in ledger.journal("ws") if e["txn_id"] in t.links)
    assert txn.meta["commitment_id"] == "cmt-1" and txn.meta["pf_entry_id"] == e["id"]
    entries.update_entry("ws", e["id"], entries.merge_patch(entries._fetch_row("ws", e["id"]),
                                                            entries.EntryPatch(payee="Renta depto")))
    assert entries.is_unedited("ws", e["id"]) is False
