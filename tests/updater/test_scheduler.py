from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.updater import scheduler as scheduler_mod
from aurum.updater import tracker


@pytest.fixture(autouse=True)
def _reset_scheduler():
    scheduler_mod.reset_for_tests()
    yield
    scheduler_mod.reset_for_tests()


def _client() -> TestClient:
    return TestClient(create_app())


# --- new US/TX triage domains ------------------------------------------


def test_new_us_domains_are_registered():
    from aurum.updater.triage import DOMAIN_KEYWORDS

    for domain in ("se_tax", "sales_tax", "fbar", "feie", "standard_deduction", "franchise_tax"):
        assert domain in DOMAIN_KEYWORDS


def test_detect_domains_finds_se_tax():
    from aurum.updater.triage import detect_domains

    assert "se_tax" in detect_domains("This page explains the self-employment tax and Schedule SE.")


def test_us_tx_sources_present_in_registry():
    ids = {s["id"] for s in tracker.load_sources()}
    for expected in (
        "irs-standard-deduction",
        "irs-se-tax",
        "tx-comptroller-franchise",
        "tx-comptroller-sales",
        "fincen-fbar",
        "irs-feie",
    ):
        assert expected in ids


# --- GET /sources/{id}/history ------------------------------------------


def test_source_history_empty_before_any_run():
    client = _client()
    resp = client.get("/api/watch/sources/dof-daily/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_id"] == "dof-daily"
    assert body["snapshots"] == []
    assert body["changes"] == []


def test_source_history_after_a_run(tmp_path, monkeypatch):
    (tmp_path / "sat-rmf.txt").write_text("Texto inicial", encoding="utf-8")
    monkeypatch.setenv("AURUM_WATCH_FAKE_DIR", str(tmp_path))
    client = _client()
    client.post("/api/watch/run", json={"source_id": "sat-rmf"})

    (tmp_path / "sat-rmf.txt").write_text("Nueva tasa 8% para plataformas.", encoding="utf-8")
    client.post("/api/watch/run", json={"source_id": "sat-rmf"})

    resp = client.get("/api/watch/sources/sat-rmf/history")
    body = resp.json()
    assert len(body["snapshots"]) == 2
    assert len(body["changes"]) == 1


# --- POST /schedule -------------------------------------------------------


def test_schedule_is_gated_off_by_default(monkeypatch):
    monkeypatch.delenv("AURUM_WATCH_SCHEDULER", raising=False)
    client = _client()
    resp = client.post("/api/watch/schedule", json={"enabled": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["gated"] is True
    assert scheduler_mod.get_scheduler().status()["running"] is False


def test_schedule_starts_when_env_gate_is_set(monkeypatch, tmp_path):
    # AURUM_WATCH_FAKE_DIR keeps the background thread's first tick offline (it fires a real
    # tick() immediately on start, and sat-rmf has no snapshot yet so it is due right away).
    (tmp_path / "sat-rmf.txt").write_text("texto", encoding="utf-8")
    monkeypatch.setenv("AURUM_WATCH_FAKE_DIR", str(tmp_path))
    monkeypatch.setenv("AURUM_WATCH_SCHEDULER", "1")
    client = _client()
    resp = client.post("/api/watch/schedule", json={"enabled": True, "sources": ["sat-rmf"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["gated"] is False
    assert scheduler_mod.get_scheduler().status()["running"] is True

    resp2 = client.post("/api/watch/schedule", json={"enabled": False})
    assert resp2.json()["enabled"] is False
    assert scheduler_mod.get_scheduler().status()["running"] is False


def test_schedule_status_endpoint():
    client = _client()
    resp = client.get("/api/watch/schedule")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False, "sources": None, "running": False}


# --- Scheduler.tick() with a fake fetcher and a fake clock ----------------


def test_scheduler_tick_runs_only_due_sources():
    sch = scheduler_mod.Scheduler()
    sch.sources = ["dof-daily", "sat-rmf"]  # limit to two sources, both `daily`/`weekly`

    # No snapshot yet for either -> both are due on the first tick.
    ran = sch.tick(fetcher=tracker.FakeFetcher({"dof-daily": "a", "sat-rmf": "b"}))
    assert set(ran) == {"dof-daily", "sat-rmf"}

    # Immediately after: neither is due yet (their cadence has not elapsed).
    ran_again = sch.tick(fetcher=tracker.FakeFetcher({"dof-daily": "a", "sat-rmf": "b"}))
    assert ran_again == []

    # Fast-forward past dof-daily's 24h cadence but not sat-rmf's 7-day one.
    future = datetime.now(UTC) + timedelta(hours=25)
    ran_later = sch.tick(fetcher=tracker.FakeFetcher({"dof-daily": "a", "sat-rmf": "b"}), now=future)
    assert ran_later == ["dof-daily"]
