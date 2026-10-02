"""Effective next_due: computed on read, lazily persisted."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from aurum.core.money import Amount
from aurum.ledger.base import Posting, Transaction, get_ledger
from aurum.organizer import alerts as alerts_mod
from aurum.organizer import commitments as cmt
from aurum.organizer import occurrences, store
from aurum.organizer.models import CommitmentIn, CommitmentPatch

from .conftest import TODAY, WS


def _yoga(stored_next_due: date = date(2026, 9, 8)):
    c = cmt.create(
        WS,
        CommitmentIn(name="Yoga Studio", merchant_patterns=["YOGA STUDIO"], kind="subscription",
                     amount=Amount(amount=Decimal("649")), cadence="monthly", anchor_day=8,
                     next_due=stored_next_due, started=date(2026, 8, 8), last_seen=date(2026, 9, 8),
                     essential="wants"),
        today=TODAY,
    )
    for when in (date(2026, 8, 8), date(2026, 9, 8)):
        get_ledger().append(
            WS,
            Transaction(
                date=when, payee="YOGA STUDIO CENTRO", narration="mensualidad",
                postings=[Posting(account="Expenses:Personal:Entertainment", amount=Amount(amount=Decimal("649"))),
                          Posting(account="Assets:Bank:BBVA", amount=Amount(amount=Decimal("-649")))],
                links=[f"yoga-{when.isoformat()}"],
            ),
        )
    return c


def _stored(cid: str) -> str:
    return store.db().execute("SELECT next_due FROM organizer_commitments WHERE id=?", (cid,)).fetchone()[0]


def test_stale_stored_next_due_rolls_forward_on_read(client) -> None:
    c = _yoga()
    assert cmt.get(WS, c.id).next_due == date(2026, 9, 8)  # library callers keep the stored value
    assert cmt.effective_next_due(WS, c, TODAY) == date(2026, 10, 8)

    row = client.get(f"/api/organizer/{WS}/commitments/{c.id}").json()
    assert row["next_due"] == "2026-10-08" and row["stored_next_due"] == "2026-09-08"
    assert [(o["due"], o["status"]) for o in row["occurrences"]] == [
        ("2026-08-08", "paid"), ("2026-09-08", "paid"),
    ]
    assert _stored(c.id) == "2026-10-08"  # lazily persisted because the stored value was in the past
    # idempotent: a second read changes nothing and the list is ordered by the effective date
    client.get(f"/api/organizer/{WS}/commitments")
    assert _stored(c.id) == "2026-10-08"
    listed = client.get(f"/api/organizer/{WS}/commitments").json()
    dues = [r["next_due"] for r in listed]
    assert dues == sorted(dues)


def test_upcoming_alert_uses_the_effective_next_due(demo) -> None:
    c = _yoga()
    # 2026-10-05: the stored 09-08 is paid and in the past; the effective 10-08 is 3 days away
    alerts = [a for a in alerts_mod.compute_alerts(WS, date(2026, 10, 5)) if a.commitment_id == c.id]
    kinds = {a.kind: a for a in alerts}
    assert "upcoming" in kinds and kinds["upcoming"].due == date(2026, 10, 8)
    assert "missed_payment" not in kinds
    assert "8 oct 2026" in kinds["upcoming"].body and "$649.00" in kinds["upcoming"].body


def test_patch_anchor_reprojects_and_september_has_one_occurrence(demo) -> None:
    c = _yoga()
    updated = cmt.update_partial(WS, c.id, CommitmentPatch(anchor_day=15), today=TODAY)
    assert updated.anchor_day == 15 and updated.next_due == date(2026, 9, 15)
    sept = occurrences.build(WS, updated, date(2026, 9, 1), date(2026, 9, 30), today=TODAY)
    assert [o.due for o in sept] == [date(2026, 9, 15)]


def test_summary_and_forecast_see_the_rolled_forward_due(demo) -> None:
    from aurum.organizer import forecast
    from aurum.organizer import summary as summary_mod

    c = _yoga()
    body = summary_mod.summary(WS, today=date(2026, 10, 5))
    upcoming = [r for r in body["next_7_days"] if r["commitment_id"] == c.id]
    assert [(r["due"], r["status"]) for r in upcoming] == [("2026-10-08", "upcoming")]
    series = forecast.forecast(WS, days=10, today=date(2026, 10, 5))["series"]
    day = next(r for r in series if r["date"] == "2026-10-08")
    assert Decimal(day["out"]["amount"]) >= Decimal("649.00")


def test_trial_becomes_active_once_the_trial_ended(client) -> None:
    trial = next(c for c in cmt.list_commitments(WS) if c.status == "trial")
    assert trial.trial_ends == TODAY + timedelta(days=5)
    after = (trial.trial_ends + timedelta(days=1)).isoformat()
    row = client.get(f"/api/organizer/{WS}/commitments/{trial.id}?today={after}").json()
    assert row["status"] == "active"
    assert cmt.get(WS, trial.id).status == "active"
