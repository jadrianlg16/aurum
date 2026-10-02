"""One nudge per bill: the organizer is the only 'bill due' producer; dismissals route to it."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.demo.generate import WS_ID, build_demo
from aurum.insights import engine
from aurum.insights.engine import build_insights

TODAY = date(2026, 9, 15)


@pytest.fixture()
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    build_demo(tmp_path / "data")
    from aurum.organizer.demo_org import seed_demo_org

    seed_demo_org(WS_ID, today=TODAY)
    return WS_ID


def _accept_netflix():
    from aurum.organizer import detect

    for candidate in detect.detect(WS_ID, today=TODAY):
        if candidate.merchant == "NETFLIX":
            return detect.accept(WS_ID, candidate.id, today=TODAY)
    raise AssertionError("Netflix not detected")


def test_recurring_bill_due_producer_is_gone() -> None:
    assert not hasattr(engine, "_recurring_insights")


def test_exactly_one_netflix_nudge(demo, monkeypatch) -> None:
    netflix = _accept_netflix()
    monkeypatch.setattr("aurum.organizer.alerts.date", _FrozenDate)
    insights = build_insights(WS_ID, "2026-09")
    netflix_nudges = [i for i in insights if "Netflix" in i.title]
    kinds = sorted(i.kind for i in netflix_nudges)
    assert len(netflix_nudges) == 1, kinds
    assert kinds == ["organizer_price_increase"]
    only = netflix_nudges[0]
    assert only.id.startswith("org-price_increase-")
    assert only.actions[0].label == "Ver Mi dinero"
    assert not [i for i in insights if i.kind == "recurring_bill_due"]
    # every organizer-born insight keeps the alert id
    from aurum.organizer import alerts as alerts_mod

    alert_ids = {a.id for a in alerts_mod.compute_alerts(WS_ID, TODAY)}
    org_ids = {i.id for i in insights if i.kind.startswith("organizer_")}
    assert org_ids <= alert_ids
    assert netflix.id  # accepted commitment exists


class _FrozenDate(date):
    @classmethod
    def today(cls):
        return TODAY


def test_dismissing_via_insights_hides_the_organizer_alert(demo, monkeypatch) -> None:
    from aurum.organizer import alerts as alerts_mod

    _accept_netflix()
    monkeypatch.setattr("aurum.organizer.alerts.date", _FrozenDate)
    monkeypatch.setenv("AURUM_TEST_CLOCK", "1")
    client = TestClient(create_app())
    listed = client.get(f"/api/insights/{WS_ID}", params={"period": "2026-09"}).json()
    target = next(i for i in listed if i["id"].startswith("org-price_increase-"))
    r = client.post(f"/api/insights/{WS_ID}/{target['id']}/dismiss")
    assert r.status_code == 200
    # gone from both surfaces, recorded in the organizer's table, never in insights_dismissed
    assert target["id"] not in {i["id"] for i in client.get(f"/api/insights/{WS_ID}", params={"period": "2026-09"}).json()}
    assert target["id"] not in {a.id for a in alerts_mod.compute_alerts(WS_ID, TODAY)}
    assert target["id"] not in {
        a["id"] for a in client.get(f"/api/organizer/{WS_ID}/alerts?today={TODAY.isoformat()}").json()
    }
    from aurum.core.db import connect

    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM organizer_dismissed_alerts WHERE ws_id=? AND alert_id=?",
                        (WS_ID, target["id"])).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM insights_dismissed WHERE ws_id=? AND insight_id=?",
                        (WS_ID, target["id"])).fetchone()[0] == 0
