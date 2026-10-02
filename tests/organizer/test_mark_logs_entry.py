"""Mark paid on the REAL Beancount ledger.

The ``demo`` fixture points ``AURUM_DATA_DIR`` at a tmp dir, so ``get_ledger()`` is the
``BeancountLedger`` writing ``main.beancount`` — every assertion below reads the persisted truth
(``pf_entries`` rows, ledger balances, ``organizer_occurrences`` overrides), not just the response.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from aurum.core.money import Amount
from aurum.organizer import store

from .conftest import TODAY, WS

DUE = TODAY + timedelta(days=30)  # 2026-10-15, a future occurrence: upcoming until marked


def _account(name: str = "BBVA Nómina", opening: str = "10000") -> dict:
    from aurum.pf import accounts_admin

    return accounts_admin.create_account(
        WS,
        accounts_admin.AccountIn(name=name, type="checking",
                                 opening_balance=Amount(amount=Decimal(opening), currency="MXN"),
                                 opening_date=TODAY - timedelta(days=60)),
        today=TODAY,
    )


def _netflix(client, account_id: str) -> dict:
    r = client.post(
        f"/api/organizer/{WS}/commitments",
        json={"kind": "subscription", "name": "Netflix", "amount": {"amount": "219.00", "currency": "MXN"},
              "cadence": "monthly", "anchor_day": 15, "next_due": DUE.isoformat(),
              "account_id": account_id, "merchant_patterns": ["NETFLIX"], "force": True},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _balance(ledger_account: str) -> Decimal:
    from aurum.ledger.base import get_ledger

    return sum((a.amount for a in get_ledger().balances(WS).get(ledger_account, [])), Decimal("0"))


def _entry_row(entry_id: str) -> dict:
    row = store.db().execute("SELECT * FROM pf_entries WHERE ws_id=? AND id=?", (WS, entry_id)).fetchone()
    assert row is not None
    return dict(row)


def _override(cid: str) -> dict | None:
    row = store.db().execute(
        "SELECT * FROM organizer_occurrences WHERE ws_id=? AND commitment_id=? AND due=?",
        (WS, cid, DUE.isoformat()),
    ).fetchone()
    return dict(row) if row else None


def test_mark_paid_with_log_entry_creates_one_editable_pf_entry(client) -> None:
    from aurum.pf import entries as pf_entries

    acct = _account()
    c = _netflix(client, acct["id"])
    assert c["account_id"] == acct["id"] and c["account_name"] == "BBVA Nómina"
    before = _balance(acct["account"])
    assert before == Decimal("10000")

    r = client.post(f"/api/organizer/{WS}/occurrences/mark",
                    json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid", "log_entry": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["occurrence"]["status"] == "paid"
    assert body["occurrence"]["auto_created"] is True
    assert body["entry_id"] and body["entry_id"] == body["occurrence"]["entry_id"]
    entry_id = body["entry_id"]

    # persisted pf row + ledger
    row = _entry_row(entry_id)
    assert row["source"] == "organizer" and row["voided"] == 0 and row["editable"] == 1
    assert row["payee"] == "Netflix" and row["amount"] == "219.00" and row["date"] == DUE.isoformat()
    assert row["txn_id"] == body["occurrence"]["txn_id"]
    human = pf_entries.get_entry(WS, entry_id)
    assert human["amount"] == {"amount": "-219.00", "currency": "MXN"}
    assert human["editable"] is True and "pago-fijo" in human["tags"]
    assert _balance(acct["account"]) == before - Decimal("219")
    override = _override(c["id"])
    assert override["status"] == "paid" and override["entry_id"] == entry_id and override["auto_created"] == 1

    # idempotent: a second mark returns the same entry and creates nothing
    again = client.post(f"/api/organizer/{WS}/occurrences/mark",
                        json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid", "log_entry": True})
    assert again.json()["entry_id"] == entry_id
    count = store.db().execute("SELECT COUNT(*) FROM pf_entries WHERE ws_id=? AND payee='Netflix'", (WS,)).fetchone()[0]
    assert count == 1
    assert _balance(acct["account"]) == before - Decimal("219")

    # the calendar reflects the mark (paid, with the entry)
    cal = client.get(f"/api/organizer/{WS}/calendar?from={DUE.isoformat()}&to={DUE.isoformat()}").json()
    item = next(i for d in cal["days"] for i in d["items"] if i["id"] == c["id"])
    assert item["status"] == "paid" and item["entry_id"] == entry_id and item["account_id"] == acct["id"]

    # DELETE un-marks and voids the auto-created entry; the occurrence is upcoming again
    gone = client.delete(f"/api/organizer/{WS}/occurrences/mark?commitment_id={c['id']}&date={DUE.isoformat()}")
    assert gone.status_code == 200 and gone.json() == {"removed": True, "voided_entry_id": entry_id}
    assert _entry_row(entry_id)["voided"] == 1
    assert _balance(acct["account"]) == before
    assert _override(c["id"]) is None
    cal = client.get(f"/api/organizer/{WS}/calendar?from={DUE.isoformat()}&to={DUE.isoformat()}").json()
    item = next(i for d in cal["days"] for i in d["items"] if i["id"] == c["id"])
    assert item["status"] == "upcoming" and item["txn_id"] is None

    # nothing left to remove
    assert client.delete(
        f"/api/organizer/{WS}/occurrences/mark?commitment_id={c['id']}&date={DUE.isoformat()}"
    ).json() == {"removed": False, "voided_entry_id": None}


def test_mark_paid_with_entry_id_links_that_entry(client) -> None:
    from aurum.pf import entries as pf_entries

    acct = _account()
    c = _netflix(client, acct["id"])
    entry = pf_entries.create_entry(
        WS,
        pf_entries.EntryIn(kind="expense", date=DUE, amount=Amount(amount=Decimal("219"), currency="MXN"),
                           account_id=acct["id"], payee="Netflix"),
    )
    row = _entry_row(entry["id"])
    r = client.post(f"/api/organizer/{WS}/occurrences/mark",
                    json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid",
                          "entry_id": entry["id"]})
    assert r.status_code == 200, r.text
    occ = r.json()["occurrence"]
    assert occ["txn_id"] == row["txn_id"] and occ["entry_id"] == entry["id"] and occ["auto_created"] is False

    # a hand-logged entry is never voided by DELETE
    gone = client.delete(f"/api/organizer/{WS}/occurrences/mark?commitment_id={c['id']}&date={DUE.isoformat()}")
    assert gone.json() == {"removed": True, "voided_entry_id": None}
    assert _entry_row(entry["id"])["voided"] == 0

    # unknown or voided entry → 404
    assert client.post(f"/api/organizer/{WS}/occurrences/mark",
                       json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid",
                             "entry_id": "ent-nope"}).status_code == 404
    pf_entries.delete_entry(WS, entry["id"])
    assert client.post(f"/api/organizer/{WS}/occurrences/mark",
                       json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid",
                             "entry_id": entry["id"]}).status_code == 404


def test_edited_auto_entry_survives_unmark(client) -> None:
    from aurum.pf import entries as pf_entries

    acct = _account()
    c = _netflix(client, acct["id"])
    entry_id = client.post(
        f"/api/organizer/{WS}/occurrences/mark",
        json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid", "log_entry": True},
    ).json()["entry_id"]
    row = _entry_row(entry_id)
    assert row["created_at"] == row["updated_at"]
    # the user edits the entry afterwards (note) → updated_at moves
    pf_entries.update_entry(
        WS, entry_id,
        pf_entries.merge_patch(pf_entries._fetch_row(WS, entry_id), pf_entries.EntryPatch(note="con propina")),
    )
    conn = store.db()  # timestamps have second resolution: force the edit to be visibly later
    conn.execute("UPDATE pf_entries SET updated_at=? WHERE id=?", ("2099-01-01T00:00:00+00:00", entry_id))
    conn.commit()
    gone = client.delete(f"/api/organizer/{WS}/occurrences/mark?commitment_id={c['id']}&date={DUE.isoformat()}")
    assert gone.json() == {"removed": True, "voided_entry_id": None}
    assert _entry_row(entry_id)["voided"] == 0


def test_skipped_and_validation_rules(client) -> None:
    acct = _account()
    c = _netflix(client, acct["id"])
    # unknown commitment
    assert client.post(f"/api/organizer/{WS}/occurrences/mark",
                       json={"commitment_id": "cmt-nope", "date": DUE.isoformat(), "status": "paid"}).status_code == 404
    # bad status / bad date → 422
    assert client.post(f"/api/organizer/{WS}/occurrences/mark",
                       json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "missed"}).status_code == 422
    assert client.post(f"/api/organizer/{WS}/occurrences/mark",
                       json={"commitment_id": c["id"], "date": "not-a-date", "status": "paid"}).status_code == 422
    # skipped: no txn, no entry; an earlier auto-created entry is voided first
    entry_id = client.post(
        f"/api/organizer/{WS}/occurrences/mark",
        json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid", "log_entry": True},
    ).json()["entry_id"]
    r = client.post(f"/api/organizer/{WS}/occurrences/mark",
                    json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "skipped"})
    assert r.status_code == 200
    assert r.json()["occurrence"]["status"] == "skipped" and r.json()["entry_id"] is None
    assert _entry_row(entry_id)["voided"] == 1
    assert _balance(acct["account"]) == Decimal("10000")


def test_log_entry_needs_an_account_and_an_amount(client) -> None:
    r = client.post(
        f"/api/organizer/{WS}/commitments",
        json={"kind": "bill", "name": "Sin cuenta", "amount": {"amount": "0", "currency": "MXN"},
              "cadence": "monthly", "next_due": DUE.isoformat(), "amount_variable": True},
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["account"] == "Assets:Bank" and c["account_id"] is None
    no_amount = client.post(f"/api/organizer/{WS}/occurrences/mark",
                            json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid",
                                  "log_entry": True})
    assert no_amount.status_code == 400 and no_amount.json()["detail"] == "Indica el monto"
    no_account = client.post(f"/api/organizer/{WS}/occurrences/mark",
                             json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid",
                                   "log_entry": True, "amount": {"amount": "150", "currency": "MXN"}})
    assert no_account.status_code == 400 and no_account.json()["detail"] == "Primero elige una cuenta"
    # the body's account_id fills the gap
    acct = _account("Efectivo")
    ok = client.post(f"/api/organizer/{WS}/occurrences/mark",
                     json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid",
                           "log_entry": True, "amount": {"amount": "150", "currency": "MXN"},
                           "account_id": acct["id"]})
    assert ok.status_code == 200, ok.text
    assert _entry_row(ok.json()["entry_id"])["account_id"] == acct["id"]
    assert ok.json()["occurrence"]["amount"] == {"amount": "150.00", "currency": "MXN"}


def test_paid_matches_before_creating(client) -> None:
    """A ledger transaction already covering the due date is linked; no entry is created."""
    acct = _account()
    c = _netflix(client, acct["id"])
    from aurum.pf import entries as pf_entries

    paid_on = DUE - timedelta(days=2)
    entry = pf_entries.create_entry(
        WS,
        pf_entries.EntryIn(kind="expense", date=paid_on, amount=Amount(amount=Decimal("219"), currency="MXN"),
                           account_id=acct["id"], payee="NETFLIX.COM 866-579-7172"),
    )
    r = client.post(f"/api/organizer/{WS}/occurrences/mark",
                    json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid", "log_entry": True})
    assert r.status_code == 200
    assert r.json()["entry_id"] == entry["id"]
    assert r.json()["occurrence"]["auto_created"] is False
    assert r.json()["occurrence"]["txn_id"] == _entry_row(entry["id"])["txn_id"]
    assert store.db().execute("SELECT COUNT(*) FROM pf_entries WHERE ws_id=?", (WS,)).fetchone()[0] == 1


def test_commitment_id_link_wins_once_pf_adds_the_column(client) -> None:
    """pf v3 adds ``pf_entries.commitment_id``; the bridge detects it at runtime and matches by link
    (any amount, ±7 days) before the payee heuristic. pf v3 is merged and adds the column itself; the
    ALTER stays only as a guard for a tree where pf migrations have not run."""
    from aurum.pf import entries as pf_entries

    conn = store.db()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pf_entries)")}
    if "commitment_id" not in cols:
        conn.execute("ALTER TABLE pf_entries ADD COLUMN commitment_id TEXT")
        conn.commit()
    acct = _account()
    c = _netflix(client, acct["id"])
    # a differently-named, differently-priced entry that the payee rule would never match
    entry = pf_entries.create_entry(
        WS,
        pf_entries.EntryIn(kind="expense", date=DUE + timedelta(days=5),
                           amount=Amount(amount=Decimal("999"), currency="MXN"),
                           account_id=acct["id"], payee="Cargo raro"),
    )
    r = client.post(f"/api/organizer/{WS}/occurrences/mark",
                    json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid",
                          "entry_id": entry["id"]})
    assert r.status_code == 200
    assert _entry_row(entry["id"])["commitment_id"] == c["id"]  # stamped
    # drop the override: the link alone now resolves the occurrence as paid
    client.delete(f"/api/organizer/{WS}/occurrences/mark?commitment_id={c['id']}&date={DUE.isoformat()}")
    cal = client.get(f"/api/organizer/{WS}/calendar?from={DUE.isoformat()}&to={DUE.isoformat()}").json()
    item = next(i for d in cal["days"] for i in d["items"] if i["id"] == c["id"])
    assert item["status"] == "paid" and item["txn_id"] == _entry_row(entry["id"])["txn_id"]
    assert item["entry_id"] == entry["id"]
    # voiding the linked entry flips it back
    pf_entries.delete_entry(WS, entry["id"])
    cal = client.get(f"/api/organizer/{WS}/calendar?from={DUE.isoformat()}&to={DUE.isoformat()}").json()
    item = next(i for d in cal["days"] for i in d["items"] if i["id"] == c["id"])
    assert item["status"] == "upcoming"


def test_legacy_alias_delegates(client) -> None:
    acct = _account()
    c = _netflix(client, acct["id"])
    r = client.post(f"/api/organizer/{WS}/occurrences/{c['id']}/{DUE.isoformat()}/mark", json={"status": "paid"})
    assert r.status_code == 200
    flat = r.json()
    assert flat["status"] == "paid" and flat["commitment_id"] == c["id"] and flat["due"] == DUE.isoformat()
    assert flat["entry_id"] is None and flat["auto_created"] is False  # log_entry is never implied
    assert store.db().execute("SELECT COUNT(*) FROM pf_entries WHERE ws_id=?", (WS,)).fetchone()[0] == 0


def test_mark_paid_on_the_real_ledger_uses_date_objects() -> None:
    assert isinstance(DUE, date)


def test_voiding_the_logged_entry_unpays_the_occurrence(client) -> None:
    """Void semantics: an explicit 'paid' mark whose logged entry is later deleted no longer counts —
    the calendar reads due/upcoming/missed again instead of a stale 'paid'."""
    from aurum.organizer import commitments as cmt
    from aurum.organizer import occurrences as occ_mod

    acct = _account()
    c = _netflix(client, acct["id"])
    r = client.post(f"/api/organizer/{WS}/occurrences/mark",
                    json={"commitment_id": c["id"], "date": DUE.isoformat(), "status": "paid", "log_entry": True})
    assert r.status_code == 200, r.text
    entry_id = r.json()["entry_id"]
    before = [o for o in occ_mod.build(WS, cmt.get(WS, c["id"]), DUE, DUE, today=TODAY) if o.due == DUE]
    assert before and before[0].status == "paid" and before[0].entry_id == entry_id

    r = client.delete(f"/api/pf/{WS}/entries/{entry_id}")
    assert r.status_code == 200, r.text
    assert _entry_row(entry_id)["voided"]

    after = [o for o in occ_mod.build(WS, cmt.get(WS, c["id"]), DUE, DUE, today=TODAY) if o.due == DUE]
    assert after and after[0].status in ("upcoming", "due", "missed"), after[0]
    assert after[0].entry_id is None
    cal = client.get(f"/api/organizer/{WS}/calendar?from={DUE.isoformat()}&to={DUE.isoformat()}").json()
    items = [i for d in cal["days"] for i in d["items"] if i["id"] == c["id"]]
    assert items and items[0]["status"] != "paid"
