"""Hygiene: 422 bounds, duplicate guard, review, test clock, quickadd 400 (items 11–12)."""

from __future__ import annotations

from datetime import date

from .conftest import TODAY, WS

BASE = {"name": "Predial", "amount": {"amount": "2400", "currency": "MXN"}, "cadence": "quarterly"}


def test_bounds_are_422_not_500(client) -> None:
    for bad in (
        {"anchor_day": -5}, {"anchor_day": 0}, {"anchor_day": 32}, {"weekday": 9}, {"weekday": -1},
        {"interval_days": 0}, {"amount": {"amount": "-1", "currency": "MXN"}}, {"name": ""},
        {"cadence": "fortnightly"}, {"next_due": "2026-13-01"},
    ):
        r = client.post(f"/api/organizer/{WS}/commitments", json={**BASE, **bad})
        assert r.status_code == 422, (bad, r.text)
    ok = client.post(f"/api/organizer/{WS}/commitments", json={**BASE, "anchor_day": 31, "weekday": 6})
    assert ok.status_code == 200, ok.text
    cid = ok.json()["id"]
    for bad in ({"anchor_day": 40}, {"interval_days": -3}, {"amount": {"amount": "-9", "currency": "MXN"}}):
        assert client.put(f"/api/organizer/{WS}/commitments/{cid}", json=bad).status_code == 422, bad


def test_duplicate_guard_409_unless_forced(client) -> None:
    first = client.post(f"/api/organizer/{WS}/commitments", json={**BASE, "merchant_patterns": ["PREDIAL MUNICIPAL"]})
    assert first.status_code == 200
    dup = client.post(f"/api/organizer/{WS}/commitments", json={**BASE, "name": "predial"})
    assert dup.status_code == 409
    assert dup.json()["detail"] == {"code": "duplicate", "existing_id": first.json()["id"], "existing_name": "Predial"}
    shared_pattern = client.post(
        f"/api/organizer/{WS}/commitments",
        json={**BASE, "name": "Impuesto predial", "merchant_patterns": ["predial municipal"]},
    )
    assert shared_pattern.status_code == 409
    forced = client.post(f"/api/organizer/{WS}/commitments", json={**BASE, "force": True})
    assert forced.status_code == 200 and forced.json()["id"] != first.json()["id"]
    assert "force" not in forced.json()
    # a cancelled twin does not block re-creation
    client.delete(f"/api/organizer/{WS}/commitments/{forced.json()['id']}")
    client.delete(f"/api/organizer/{WS}/commitments/{first.json()['id']}")
    assert client.post(f"/api/organizer/{WS}/commitments", json=BASE).status_code == 200
    # quickadd?save=1 goes through the same guard
    assert client.post(f"/api/organizer/{WS}/quickadd?save=1", json={"text": "predial 2400 trimestral"}).status_code == 409
    assert client.post(f"/api/organizer/{WS}/quickadd?save=1",
                       json={"text": "predial 2400 trimestral", "force": True}).status_code == 200
    # the trial 'Max' seeded by the demo is live too
    assert client.post(f"/api/organizer/{WS}/quickadd?save=1", json={"text": "max 249 mensual"}).status_code == 409


def test_review_endpoint(client) -> None:
    cid = client.post(f"/api/organizer/{WS}/commitments", json=BASE).json()["id"]
    r = client.post(f"/api/organizer/{WS}/commitments/{cid}/review")
    assert r.status_code == 200 and r.json() == {"reviewed_at": TODAY.isoformat()}
    assert client.get(f"/api/organizer/{WS}/commitments/{cid}").json()["reviewed_at"] == TODAY.isoformat()
    assert client.post(f"/api/organizer/{WS}/commitments/nope/review").status_code == 404


def test_quickadd_without_an_amount_is_400(client) -> None:
    for save in (0, 1):
        r = client.post(f"/api/organizer/{WS}/quickadd?save={save}", json={"text": "netflix mensual"})
        assert r.status_code == 400
        assert r.json()["detail"] == 'Falta el monto (p. ej. "netflix 219 mensual")'


def test_plan_period_is_validated(client) -> None:
    assert client.get(f"/api/organizer/{WS}/plan?period=2026-13").status_code == 422
    assert client.get(f"/api/organizer/{WS}/plan?period=2026-09").status_code == 200


def test_today_is_only_accepted_with_the_test_clock(demo, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from aurum.api.app import create_app

    raw = TestClient(create_app())
    monkeypatch.delenv("AURUM_TEST_CLOCK", raising=False)
    r = raw.get(f"/api/organizer/{WS}/summary?today=2026-09-15")
    assert r.status_code == 422
    assert r.json()["detail"] == "today is only accepted when AURUM_TEST_CLOCK=1"
    assert raw.get(f"/api/organizer/{WS}/summary").status_code == 200
    monkeypatch.setenv("AURUM_TEST_CLOCK", "1")
    assert raw.get(f"/api/organizer/{WS}/summary?today=2026-09-15").status_code == 200
    assert raw.get(f"/api/organizer/{WS}/summary?today=nope").status_code == 422


def test_test_clock_beats_the_wall_clock(client, monkeypatch) -> None:
    from aurum.organizer import router as org_router
    from aurum.organizer import summary as summary_mod

    monkeypatch.setattr(org_router, "wall_today", lambda: date(2029, 1, 1))
    via_http = client.get(f"/api/organizer/{WS}/summary?today={TODAY.isoformat()}").json()
    direct = summary_mod.summary(WS, today=TODAY)
    assert via_http["next_7_days"] == direct["next_7_days"]
    assert via_http["safe_to_spend"]["amount"] == direct["safe_to_spend"]["amount"]
    assert via_http["safe_to_spend"]["until"] == direct["safe_to_spend"]["until"]
    assert via_http["alerts_count"] == direct["alerts_count"]


def test_calendar_and_forecast_caps(client) -> None:
    assert client.get(f"/api/organizer/{WS}/calendar?from=2026-01-01&to=2028-01-01").status_code == 200
    assert client.get(f"/api/organizer/{WS}/calendar?from=2026-01-01&to=2028-01-02").status_code == 422
    assert client.get(f"/api/organizer/{WS}/calendar?to=nope").status_code == 422
    assert client.get(f"/api/organizer/{WS}/forecast?days=0").status_code == 422
