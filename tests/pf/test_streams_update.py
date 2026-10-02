"""Income streams: PUT is a partial merge, in place; commitments patched not recreated; paused
on active=false; 404 with nothing changed on a bad account; history uses commitment_id links first."""

from __future__ import annotations

from datetime import date

from aurum.core.money import Amount
from aurum.organizer import commitments as org_commitments
from aurum.pf import accounts_admin, entries, labels, streams


def _account(ws="ws", name="Nómina BBVA"):
    return accounts_admin.create_account(ws, accounts_admin.AccountIn(name=name, type="checking"))


def _stream(client, acct, **over):
    body = {"name": "Nómina Acme", "source_type": "salary", "amount": {"amount": "22500", "currency": "MXN"},
            "cadence": "semimonthly", "anchor_days": [15, 30], "account_id": acct["id"]}
    body.update(over)
    r = client.post("/api/pf/ws/income/streams", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_mirrors_normalized_commitments_with_account_name(ledger, client):
    acct = _account()
    s = _stream(client, acct)
    assert s["account_name"] == "Nómina BBVA" and len(s["commitment_ids"]) == 2
    assert s["amount"] == {"amount": "22500.00", "currency": "MXN"}
    cs = [org_commitments.get("ws", cid) for cid in s["commitment_ids"]]
    assert all(c.kind == "income" and c.status == "active" for c in cs)
    # organizer.commitments.normalize_patterns stores patterns normalized, so the accented variant collapses
    assert all(c.merchant_patterns == ["NOMINA ACME"] for c in cs)


def test_put_partial_updates_in_place_and_patches_commitments(ledger, client):
    acct = _account()
    s = _stream(client, acct)
    before = [org_commitments.get("ws", cid) for cid in s["commitment_ids"]]
    r = client.put(f"/api/pf/ws/income/streams/{s['id']}", json={"amount": {"amount": "24000", "currency": "MXN"}})
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["id"] == s["id"] and after["created_at"] == s["created_at"] and after["updated_at"] >= s["updated_at"]
    assert after["commitment_ids"] == s["commitment_ids"]  # patched in place, same ids
    assert after["name"] == "Nómina Acme" and after["anchor_days"] == [15, 30]
    cs = [org_commitments.get("ws", cid) for cid in after["commitment_ids"]]
    assert all(str(c.amount.amount) == "24000.00" for c in cs)
    assert [c.next_due for c in cs] == [c.next_due for c in before]
    assert len(org_commitments.list_commitments("ws")) == 2

    # cadence change with a different spec count → old ones removed, new ones created
    r = client.put(f"/api/pf/ws/income/streams/{s['id']}", json={"cadence": "monthly", "anchor_days": [1]})
    assert r.status_code == 200 and len(r.json()["commitment_ids"]) == 1
    live = [c for c in org_commitments.list_commitments("ws") if c.status != "cancelled"]
    assert len(live) == 1


def test_bad_account_id_is_404_with_nothing_changed(ledger, client):
    acct = _account()
    s = _stream(client, acct)
    r = client.put(f"/api/pf/ws/income/streams/{s['id']}", json={"account_id": "nope"})
    assert r.status_code == 404
    again = client.get(f"/api/pf/ws/income/streams/{s['id']}").json()
    assert again["created_at"] == s["created_at"] and again["updated_at"] == s["updated_at"]
    assert all(org_commitments.get("ws", cid).status == "active" for cid in again["commitment_ids"])


def test_active_false_pauses_commitments(ledger, client):
    acct = _account()
    s = _stream(client, acct)
    r = client.put(f"/api/pf/ws/income/streams/{s['id']}", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    assert all(org_commitments.get("ws", cid).status == "paused" for cid in r.json()["commitment_ids"])
    r = client.put(f"/api/pf/ws/income/streams/{s['id']}", json={"active": True})
    assert all(org_commitments.get("ws", cid).status == "active" for cid in r.json()["commitment_ids"])


def test_label_must_be_income_and_weekday_bounds(ledger, client):
    acct = _account()
    food = next(x for x in labels.list_labels("ws") if x["name"] == "Comida fuera")
    r = client.post("/api/pf/ws/income/streams", json={
        "name": "X", "source_type": "salary", "amount": {"amount": "1", "currency": "MXN"}, "cadence": "monthly",
        "account_id": acct["id"], "label_id": food["id"]})
    assert r.status_code == 400
    salary = next(x for x in labels.list_labels("ws") if x["name"] == "Sueldo/Nómina")
    s = _stream(client, acct, cadence="weekly", weekday=4, anchor_days=[], label_id=salary["id"])
    assert s["weekday"] == 4 and s["label_id"] == salary["id"]


def test_history_prefers_entries_linked_by_commitment_id(ledger, client):
    acct = _account()
    s = _stream(client, acct, cadence="monthly", anchor_days=[15])
    cid = s["commitment_ids"][0]
    c = org_commitments.get("ws", cid)
    due = c.next_due
    entries.create_entry("ws", entries.EntryIn(kind="income", date=due.isoformat(), amount=Amount(amount="22500"),
                                               account_id=acct["id"], payee="ACME", commitment_id=cid))
    history = streams.stream_history("ws", s["id"], today=due)
    row = next(h for h in history if h["due"] == due.isoformat())
    assert row["received"] == {"amount": "22500.00", "currency": "MXN"} and row["status"] == "paid"
    assert row["entry_id"]


def test_history_covers_the_last_payday_before_the_stream_was_created(ledger, client):
    """A semimonthly stream created on the 19th mirrors commitments that already know about
    the 15th (started = last anchor on or before today), so an income entry logged for that payday
    shows up as received instead of the history being empty."""
    from datetime import date

    from aurum.organizer import occurrences as org_occ

    acct = _account()
    today = date.today()  # the API mirrors the stream with the real clock
    last_15th = streams._last_anchor_on_or_before(today, 15)
    assert last_15th <= today
    body = {"name": "Nómina Acme", "source_type": "salary", "amount": {"amount": "22500", "currency": "MXN"},
            "cadence": "semimonthly", "anchor_days": [15, 30], "account_id": acct["id"]}
    r = client.post("/api/pf/ws/income/streams", json=body)
    assert r.status_code == 200, r.text
    s = r.json()
    cs = [org_commitments.get("ws", cid) for cid in s["commitment_ids"]]
    fifteenth = next(c for c in cs if c.anchor_day == 15)
    assert org_occ.history_floor("ws", fifteenth) <= last_15th
    entries.create_entry("ws", entries.EntryIn(kind="income", date=last_15th.isoformat(), amount=Amount(amount="22500"),
                                               account_id=acct["id"], payee="ACME", commitment_id=fifteenth.id))
    history = streams.stream_history("ws", s["id"], today=today)
    row = next((h for h in history if h["due"] == last_15th.isoformat()), None)
    assert row is not None, history
    assert row["received"] == {"amount": "22500.00", "currency": "MXN"} and row["status"] == "paid"


def test_delete_stream_removes_or_cancels_commitments(ledger, client):
    acct = _account()
    s = _stream(client, acct)
    r = client.delete(f"/api/pf/ws/income/streams/{s['id']}")
    assert r.status_code == 200
    assert client.get(f"/api/pf/ws/income/streams/{s['id']}").status_code == 404
    for cid in s["commitment_ids"]:
        try:
            c = org_commitments.get("ws", cid)
        except KeyError:
            continue  # hard-deleted once organizer lands hard_delete
        assert c.status == "cancelled"


def test_today_is_a_valid_anchor_date(ledger):
    """Streams created with today's date still carry a next_expected (regression guard)."""
    acct = _account()
    s = streams.create_stream("ws", streams.IncomeStreamIn(
        name="Sueldo", source_type="salary", amount=Amount(amount="1000"), cadence="monthly", anchor_days=[1],
        account_id=acct["id"]), today=date(2026, 1, 10))
    assert s["next_expected"] == "2026-02-01"
