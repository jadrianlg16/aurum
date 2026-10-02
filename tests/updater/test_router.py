from __future__ import annotations

from fastapi.testclient import TestClient

from aurum.api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_mounted_at_watch_prefix():
    app = create_app()
    assert "/api/watch" in app.state.mounted


def test_changes_seeds_fixture_on_first_access():
    client = _client()
    resp = client.get("/api/watch/changes")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    seeded = body[0]
    assert "platform_withholding" in seeded["domains"]
    assert seeded["effective_from"] == "2026-04-01"


def test_proposals_has_seeded_row():
    client = _client()
    resp = client.get("/api/watch/proposals")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert body[0]["status"] == "proposed"


def test_sources_endpoint():
    client = _client()
    resp = client.get("/api/watch/sources")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()}
    assert "dof-daily" in ids


def test_run_with_fake_dir(tmp_path, monkeypatch):
    (tmp_path / "sat-rmf.txt").write_text("Texto inicial RESICO", encoding="utf-8")
    monkeypatch.setenv("AURUM_WATCH_FAKE_DIR", str(tmp_path))
    client = _client()
    resp = client.post("/api/watch/run", json={"source_id": "sat-rmf"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ran"] == ["sat-rmf"]
    assert body["changed"] == []  # first fetch is baseline only

    (tmp_path / "sat-rmf.txt").write_text("Nueva tasa IVA de 8% para plataformas.", encoding="utf-8")
    resp2 = client.post("/api/watch/run", json={"source_id": "sat-rmf"})
    body2 = resp2.json()
    assert len(body2["changed"]) == 1


def test_seed_runs_once_under_concurrent_first_reads():
    """The Watch screen asks /changes and /proposals at the same time on first load; both
    seed. Without a lock both saw an empty table and the seeded change appeared twice."""
    import threading

    from aurum.core.db import connect
    from aurum.updater import router as watch_router

    barrier = threading.Barrier(8)

    def first_read():
        barrier.wait()
        watch_router._ensure_seed()

    threads = [threading.Thread(target=first_read) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    conn = connect()
    try:
        changes = conn.execute("SELECT COUNT(*) AS n FROM updater_changes").fetchone()["n"]
        proposals = conn.execute("SELECT COUNT(*) AS n FROM updater_proposals").fetchone()["n"]
    finally:
        conn.close()
    assert (changes, proposals) == (1, 1)
