"""``POST /organize``: relabel a transaction, remember the merchant, auto-label the next quick add."""

from __future__ import annotations

from datetime import timedelta

from aurum.organizer import organize

from .conftest import WS


def _label(client, name_fragment: str) -> dict:
    labels = client.get(f"/api/pf/{WS}/labels").json()
    return next(lbl for lbl in labels if name_fragment.lower() in lbl["name"].lower())


def _a_netflix_txn() -> str:
    from aurum.ledger.base import get_ledger

    for txn in get_ledger().journal(WS):
        if (txn.payee or "").startswith("NETFLIX"):
            return txn.links[0]
    raise AssertionError("no Netflix transaction in the demo ledger")


def test_relabel_moves_the_expense_posting(client) -> None:
    from aurum.ledger.base import get_ledger

    txn_id = _a_netflix_txn()
    label = _label(client, "Entretenimiento")
    other = _label(client, "Software")
    assert label["account"] != other["account"]

    r = client.post(
        f"/api/organizer/{WS}/organize",
        json={"assign": [{"txn_id": txn_id, "label_id": other["id"], "create_rule": False}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["errors"] == []
    assert body["relabelled"][0]["to"] == other["account"]

    txn = next(t for t in get_ledger().journal(WS) if txn_id in (t.links or []))
    assert any(p.account == other["account"] for p in txn.postings)


def test_create_rule_teaches_the_label_and_auto_labels_a_new_quick_add(client) -> None:
    txn_id = _a_netflix_txn()
    software = _label(client, "Software")

    r = client.post(
        f"/api/organizer/{WS}/organize",
        json={"assign": [{"txn_id": txn_id, "label_id": software["id"], "create_rule": True}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["rules"], "create_rule did not create a rule"
    assert r.json()["rules"][0]["pattern"] == "NETFLIX"

    rules = client.get(f"/api/organizer/{WS}/rules").json()
    assert [rule["pattern"] for rule in rules] == ["NETFLIX"]

    # the alias landed in pf_labels, which is what the ingest auto-label path reads
    refreshed = next(lbl for lbl in client.get(f"/api/pf/{WS}/labels").json() if lbl["id"] == software["id"])
    assert "netflix" in [a.lower() for a in refreshed["aliases"]]

    # and a brand-new quick add for the same merchant is labelled automatically
    preview = client.post(
        f"/api/organizer/{WS}/quickadd", json={"text": "netflix 219 mensual día 15"}
    ).json()
    assert preview["auto_label"]["label_id"] == software["id"]
    assert preview["auto_label"]["source"] == "rule"
    assert preview["preview"]["label_id"] == software["id"]


def test_saved_quick_add_keeps_the_auto_label(client) -> None:
    txn_id = _a_netflix_txn()
    software = _label(client, "Software")
    client.post(
        f"/api/organizer/{WS}/organize",
        json={"assign": [{"txn_id": txn_id, "label_id": software["id"], "create_rule": True}]},
    )
    saved = client.post(
        f"/api/organizer/{WS}/quickadd?save=1", json={"text": "netflix 219 mensual día 15"}
    ).json()
    assert saved["saved"] is True
    assert saved["label_id"] == software["id"]


def test_delete_rule(client) -> None:
    txn_id = _a_netflix_txn()
    software = _label(client, "Software")
    client.post(
        f"/api/organizer/{WS}/organize",
        json={"assign": [{"txn_id": txn_id, "label_id": software["id"], "create_rule": True}]},
    )
    rule_id = client.get(f"/api/organizer/{WS}/rules").json()[0]["id"]
    assert client.delete(f"/api/organizer/{WS}/rules/{rule_id}").status_code == 200
    assert client.get(f"/api/organizer/{WS}/rules").json() == []
    assert client.delete(f"/api/organizer/{WS}/rules/{rule_id}").status_code == 404


def test_unknown_txn_and_label_are_reported_not_raised(client) -> None:
    software = _label(client, "Software")
    r = client.post(
        f"/api/organizer/{WS}/organize",
        json={"assign": [
            {"txn_id": "does-not-exist", "label_id": software["id"]},
            {"txn_id": _a_netflix_txn(), "label_id": "lbl-nope"},
        ]},
    )
    assert r.status_code == 200
    assert len(r.json()["errors"]) == 2
    assert r.json()["relabelled"] == []


def test_rule_match_falls_back_to_the_pf_alias(client) -> None:
    # no organizer rule for Uber, but the default "Uber/Taxi" label carries the alias
    match = organize.apply_rules_to_quickadd(WS, "UBER TRIP 8829 CDMX")
    assert match is not None
    assert match["source"] == "alias"


def test_organize_explain_lists_every_change(client) -> None:
    txn_id = _a_netflix_txn()
    software = _label(client, "Software")
    body = client.post(
        f"/api/organizer/{WS}/organize",
        json={"assign": [{"txn_id": txn_id, "label_id": software["id"], "create_rule": True}]},
    ).json()
    labels = {s["label"] for s in body["explain"]["steps"]}
    assert {"relabelled", "rules_created", txn_id} <= labels


def test_uncategorized_list_feeds_the_plan_screen(demo) -> None:
    from aurum.organizer import plan

    start, end = plan._period_bounds("2026-09")
    rows = plan.uncategorized(WS, start - timedelta(days=120), end)
    assert all("txn_id" in r and "payee" in r and "amount" in r for r in rows)
