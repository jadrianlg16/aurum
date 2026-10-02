"""PUT = PATCH-merge, account_id resolution, month-end anchors."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from aurum.core.money import Amount
from aurum.organizer import alerts as alerts_mod
from aurum.organizer import commitments as cmt
from aurum.organizer import occurrences, store
from aurum.organizer.models import CommitmentIn, CommitmentPatch

from .conftest import TODAY, WS


def _pf_account(name: str = "BBVA Nómina") -> dict:
    from aurum.pf import accounts_admin

    return accounts_admin.create_account(
        WS, accounts_admin.AccountIn(name=name, type="checking", opening_balance=Amount(amount=Decimal("5000"))),
        today=TODAY,
    )


def test_patch_touches_only_the_sent_fields(demo) -> None:
    c = cmt.create(
        WS,
        CommitmentIn(name="Crédito auto", kind="loan_payment", amount=Amount(amount=Decimal("4918.77")),
                     cadence="monthly", anchor_day=15, next_due=date(2026, 10, 15), started=date(2026, 1, 15),
                     linked_loan_id="loan-1", category_hint="loan", source="detected", confidence=0.95,
                     last_seen=date(2026, 9, 18), essential="debt"),
        today=TODAY,
    )
    updated = cmt.update_partial(WS, c.id, CommitmentPatch(name="Auto BBVA"), today=TODAY)
    assert updated.name == "Auto BBVA"
    for field in ("linked_loan_id", "started", "category_hint", "source", "confidence", "last_seen",
                  "anchor_day", "next_due", "essential", "amount", "kind"):
        assert getattr(updated, field) == getattr(c, field), field


def test_cadence_change_reprojects_next_due(demo) -> None:
    c = cmt.create(
        WS,
        CommitmentIn(name="Dominio", amount=Amount(amount=Decimal("450")), cadence="monthly",
                     anchor_day=3, next_due=date(2026, 10, 3)),
        today=TODAY,
    )
    annual = cmt.update_partial(WS, c.id, CommitmentPatch(cadence="annual"), today=TODAY)
    assert annual.cadence == "annual"
    # project_next(today=09-15, annual, anchor_day=3): the 3rd of this month is past → one year on
    assert annual.next_due == date(2027, 9, 3)
    # an explicit next_due in the same patch wins over the re-projection
    explicit = cmt.update_partial(
        WS, c.id, CommitmentPatch(cadence="monthly", next_due=date(2026, 11, 3)), today=TODAY,
    )
    assert explicit.next_due == date(2026, 11, 3)


def test_month_end_anchor_is_derived_and_does_not_drift(demo) -> None:
    c = cmt.create(
        WS,
        CommitmentIn(name="Fin de mes", amount=Amount(amount=Decimal("100")), cadence="monthly",
                     next_due=date(2026, 10, 31)),
        today=TODAY,
    )
    assert c.anchor_day == 31
    dues = [o.due.isoformat() for o in occurrences.build(WS, c, date(2026, 10, 1), date(2027, 1, 31), today=TODAY)]
    assert dues == ["2026-10-31", "2026-11-30", "2026-12-31", "2027-01-31"]


def test_same_day_amount_correction_leaves_no_alert(demo) -> None:
    c = cmt.create(
        WS,
        CommitmentIn(name="Spotify Duo", merchant_patterns=["SPOTIFY DUO"], amount=Amount(amount=Decimal("2190")),
                     cadence="monthly", anchor_day=20, next_due=date(2026, 9, 20)),
        today=TODAY,
    )
    fixed = cmt.update_partial(WS, c.id, CommitmentPatch(amount=Amount(amount=Decimal("219"))), today=TODAY)
    assert fixed.amount.amount == Decimal("219.00")
    prices = [(p["observed"], p["amount"]["amount"]) for p in cmt.price_history(WS, c.id)]
    assert prices == [(TODAY.isoformat(), "219.00")]
    assert not [a for a in alerts_mod.compute_alerts(WS, TODAY) if a.commitment_id == c.id and "price" in a.kind]
    # a real change on a later day is still reported
    cmt.update_partial(WS, c.id, CommitmentPatch(amount=Amount(amount=Decimal("249"))), today=TODAY + timedelta(days=3))
    kinds = {a.kind for a in alerts_mod.compute_alerts(WS, TODAY + timedelta(days=3)) if a.commitment_id == c.id}
    assert "price_increase" in kinds


def test_account_id_resolves_and_round_trips(client) -> None:
    acct = _pf_account()
    created = client.post(
        f"/api/organizer/{WS}/commitments",
        json={"name": "Renta", "kind": "rent", "amount": {"amount": "3000", "currency": "MXN"},
              "cadence": "monthly", "anchor_day": 1, "account_id": acct["id"]},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["account_id"] == acct["id"] and body["account_name"] == "BBVA Nómina"
    assert body["account"] == acct["account"]
    row = store.db().execute("SELECT account, account_id FROM organizer_commitments WHERE id=?", (body["id"],)).fetchone()
    assert (row[0], row[1]) == (acct["account"], acct["id"])

    # PATCH by name keeps account_id, started and category_hint; PATCH to a bad account_id → 404 and nothing changes
    renamed = client.put(f"/api/organizer/{WS}/commitments/{body['id']}", json={"name": "Renta depto"}).json()
    assert renamed["account_id"] == acct["id"] and renamed["name"] == "Renta depto"
    assert client.put(f"/api/organizer/{WS}/commitments/{body['id']}", json={"account_id": "acc-nope"}).status_code == 404
    assert client.get(f"/api/organizer/{WS}/commitments/{body['id']}").json()["account_id"] == acct["id"]
    assert client.post(
        f"/api/organizer/{WS}/commitments",
        json={"name": "Luz", "amount": {"amount": "500", "currency": "MXN"}, "account_id": "acc-nope"},
    ).status_code == 404

    # a ledger account name alone is reverse-looked-up (the streams path)
    by_name = cmt.create(
        WS, CommitmentIn(name="Nómina Acme", kind="income", amount=Amount(amount=Decimal("20000")),
                         cadence="monthly", anchor_day=15, account=acct["account"],
                         merchant_patterns=["Nómina Acme"]),
        today=TODAY,
    )
    assert by_name.account_id == acct["id"] and by_name.merchant_patterns == ["NOMINA ACME"]
    listed = {r["id"]: r for r in client.get(f"/api/organizer/{WS}/commitments").json()}
    assert listed[by_name.id]["account_name"] == "BBVA Nómina"


def test_full_update_wrapper_still_replaces(demo) -> None:
    c = cmt.create(WS, CommitmentIn(name="Agua", amount=Amount(amount=Decimal("380")), cadence="bimonthly",
                                    anchor_day=20, next_due=date(2026, 9, 20)), today=TODAY)
    replaced = cmt.update(WS, c.id, CommitmentIn(name="Agua y drenaje", amount=Amount(amount=Decimal("380")),
                                                 cadence="bimonthly", anchor_day=20, next_due=date(2026, 9, 20),
                                                 notes="SADM"), today=TODAY)
    assert replaced.name == "Agua y drenaje" and replaced.notes == "SADM"
