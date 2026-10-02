"""Alerts: thresholds, dismissal and how insights re-wrap them."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from aurum.core.money import Amount
from aurum.organizer import alerts as alerts_mod
from aurum.organizer import commitments as cmt
from aurum.organizer import detect
from aurum.organizer.models import CommitmentIn

from .conftest import TODAY, WS


def _accept_all(today: date = TODAY) -> None:
    for candidate in detect.detect(WS, today=today):
        if candidate.evidence:
            detect.accept(WS, candidate.id, today=today)


def test_netflix_price_increase_199_to_219(demo) -> None:
    _accept_all()
    netflix = next(c for c in cmt.list_commitments(WS) if c.merchant_patterns == ["NETFLIX"])
    found = [
        a for a in alerts_mod.compute_alerts(WS, TODAY)
        if a.kind == "price_increase" and a.commitment_id == netflix.id
    ]
    assert len(found) == 1
    alert = found[0]
    assert alert.old_amount.amount == Decimal("199.00")
    assert alert.new_amount.amount == Decimal("219.00")
    assert alert.severity == "warn"
    steps = {s.label: s.value for s in alert.explain.steps}
    assert steps["delta"] == "20.00 MXN"
    assert steps["pct"] == "10.05"
    # 20 MXN more, 12 times a year
    assert steps["annual_impact"] == "240.00"


def test_trial_ending_alert(demo) -> None:
    trial = next(c for c in cmt.list_commitments(WS) if c.status == "trial")
    assert trial.trial_ends == TODAY + timedelta(days=5)
    found = [a for a in alerts_mod.compute_alerts(WS, TODAY) if a.kind == "trial_ending"]
    assert [a.commitment_id for a in found] == [trial.id]
    steps = {s.label: s.value for s in found[0].explain.steps}
    assert steps["days_left"] == "5"
    assert found[0].severity == "warn"


def test_trial_ending_is_urgent_within_two_days(demo) -> None:
    trial = next(c for c in cmt.list_commitments(WS) if c.status == "trial")
    found = [a for a in alerts_mod.compute_alerts(WS, TODAY + timedelta(days=4))
             if a.kind == "trial_ending" and a.commitment_id == trial.id]
    assert found[0].severity == "urgent"


def test_price_change_below_both_thresholds_is_silent(demo) -> None:
    created = cmt.create(
        WS,
        CommitmentIn(name="Cafe", amount=Amount(amount=Decimal("1000")), cadence="monthly",
                     next_due=TODAY + timedelta(days=10), merchant_patterns=["CAFE"],
                     last_seen=TODAY - timedelta(days=30)),
        today=TODAY,
    )
    # +15 MXN = 1.5%: under 2% and under 20 MXN, so nothing fires.
    cmt.record_price(WS, created.id, TODAY, Amount(amount=Decimal("1015")))
    assert not [a for a in alerts_mod.compute_alerts(WS, TODAY)
                if a.kind.startswith("price_") and a.commitment_id == created.id]
    # +25 MXN crosses the absolute threshold even though it is only 2.5%.
    cmt.record_price(WS, created.id, TODAY + timedelta(days=1), Amount(amount=Decimal("1040")))
    fired = [a for a in alerts_mod.compute_alerts(WS, TODAY)
             if a.kind == "price_increase" and a.commitment_id == created.id]
    assert len(fired) == 1


def test_price_decrease_fires_as_info(demo) -> None:
    created = cmt.create(
        WS,
        CommitmentIn(name="Gimnasio", amount=Amount(amount=Decimal("800")), cadence="monthly",
                     next_due=TODAY + timedelta(days=10), merchant_patterns=["GIMNASIO"],
                     last_seen=TODAY - timedelta(days=30)),
        today=TODAY,
    )
    cmt.record_price(WS, created.id, TODAY, Amount(amount=Decimal("600")))
    alert = next(a for a in alerts_mod.compute_alerts(WS, TODAY)
                 if a.kind == "price_decrease" and a.commitment_id == created.id)
    assert alert.severity == "info"
    assert alert.old_amount.amount == Decimal("800.00")


def test_missed_payment_after_three_days(demo) -> None:
    created = cmt.create(
        WS,
        CommitmentIn(name="Colegiatura", amount=Amount(amount=Decimal("5500")), cadence="monthly",
                     anchor_day=1, next_due=TODAY + timedelta(days=17), started=TODAY - timedelta(days=70),
                     last_seen=TODAY - timedelta(days=45), merchant_patterns=["COLEGIATURA"]),
        today=TODAY,
    )
    missed = [a for a in alerts_mod.compute_alerts(WS, TODAY)
              if a.kind == "missed_payment" and a.commitment_id == created.id]
    assert missed, "a due date 14 days in the past with no ledger match must fire"
    assert missed[0].severity == "urgent"
    assert all(a.due < TODAY - timedelta(days=3) for a in missed)


def test_upcoming_only_inside_seven_days(demo) -> None:
    near = cmt.create(WS, CommitmentIn(name="Cerca", amount=Amount(amount=Decimal("100")),
                                       cadence="monthly", next_due=TODAY + timedelta(days=6)), today=TODAY)
    far = cmt.create(WS, CommitmentIn(name="Lejos", amount=Amount(amount=Decimal("100")),
                                      cadence="monthly", next_due=TODAY + timedelta(days=9)), today=TODAY)
    upcoming = {a.commitment_id for a in alerts_mod.compute_alerts(WS, TODAY) if a.kind == "upcoming"}
    assert near.id in upcoming
    assert far.id not in upcoming


def test_annual_renewal_within_thirty_days(demo) -> None:
    created = cmt.create(
        WS,
        CommitmentIn(name="Dominio", amount=Amount(amount=Decimal("450")), cadence="annual",
                     next_due=TODAY + timedelta(days=20), started=TODAY - timedelta(days=345)),
        today=TODAY,
    )
    kinds = {a.kind for a in alerts_mod.compute_alerts(WS, TODAY) if a.commitment_id == created.id}
    assert "annual_renewal" in kinds


def test_duplicate_streaming_services(demo) -> None:
    _accept_all()
    duplicates = [a for a in alerts_mod.compute_alerts(WS, TODAY) if a.kind == "duplicate"]
    assert duplicates, "Netflix + Amazon Prime + Max all share the streaming hint"
    steps = {s.label: s.value for s in duplicates[0].explain.steps}
    assert steps["category_hint"] == "streaming"
    assert "Netflix" in steps["services"]


def test_forgotten_annual_after_eleven_months(demo) -> None:
    created = cmt.create(
        WS,
        CommitmentIn(name="Membresia", amount=Amount(amount=Decimal("2000")), cadence="annual",
                     next_due=TODAY + timedelta(days=200), started=TODAY - timedelta(days=400)),
        today=TODAY,
    )
    forgotten = [a for a in alerts_mod.compute_alerts(WS, TODAY)
                 if a.kind == "forgotten" and a.commitment_id == created.id]
    assert forgotten
    cmt.mark_reviewed(WS, created.id, TODAY)
    assert not [a for a in alerts_mod.compute_alerts(WS, TODAY)
                if a.kind == "forgotten" and a.commitment_id == created.id]


def test_dismiss_hides_an_alert_and_is_stable(demo) -> None:
    _accept_all()
    alert = alerts_mod.compute_alerts(WS, TODAY)[0]
    alerts_mod.dismiss(WS, alert.id)
    assert alert.id not in {a.id for a in alerts_mod.compute_alerts(WS, TODAY)}
    assert alert.id in {a.id for a in alerts_mod.compute_alerts(WS, TODAY, include_dismissed=True)}


def test_alert_ids_are_deterministic(demo) -> None:
    _accept_all()
    first = [a.id for a in alerts_mod.compute_alerts(WS, TODAY)]
    second = [a.id for a in alerts_mod.compute_alerts(WS, TODAY)]
    assert first == second


def test_alerts_are_localized(demo) -> None:
    _accept_all()
    es = alerts_mod.compute_alerts(WS, TODAY, lang="es")
    en = alerts_mod.compute_alerts(WS, TODAY, lang="en")
    assert [a.id for a in es] == [a.id for a in en]
    assert [a.title for a in es] != [a.title for a in en]


def test_alerts_reach_the_insights_engine(demo) -> None:
    _accept_all()
    from aurum.insights.engine import build_insights

    kinds = {i.kind for i in build_insights(WS)}
    assert any(k.startswith("organizer_") for k in kinds), sorted(kinds)


def test_insights_hook_survives_a_workspace_with_no_organizer_data(demo, monkeypatch) -> None:
    from aurum.insights import engine

    monkeypatch.setattr(
        "aurum.organizer.alerts.compute_alerts",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert engine._organizer_insights(WS, "es") == []


def test_router_alerts_and_dismiss(client) -> None:
    listed = client.get("/api/organizer/demo-mx/alerts")
    assert listed.status_code == 200
    if listed.json():
        alert_id = listed.json()[0]["id"]
        assert client.post(f"/api/organizer/demo-mx/alerts/{alert_id}/dismiss").status_code == 200
        assert alert_id not in {a["id"] for a in client.get("/api/organizer/demo-mx/alerts").json()}
