"""``/api/insights`` router, mounted end-to-end via ``aurum.api.app.create_app``."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.demo.generate import WS_ID, build_demo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    build_demo(tmp_path / "data")
    # tax nudges and the tax calendar require modules.tax on the (simple-mode) demo.
    from aurum.core.workspaces import get_workspace, save_workspace

    ws = get_workspace(WS_ID)
    ws.modules.tax = True
    save_workspace(ws)
    return TestClient(create_app())


def test_mounted_at_api_insights(client):
    mounted = client.get("/api/mounted").json()["mounted"]
    assert "/api/insights" in mounted


def test_list_insights(client):
    r = client.get(f"/api/insights/{WS_ID}", params={"period": "2026-08"})
    assert r.status_code == 200
    body = r.json()
    assert any(i["kind"] == "pue_not_collected" for i in body)
    for i in body:
        assert set(i) >= {"id", "ws_id", "kind", "severity", "title", "body", "explain", "actions"}


def test_dismiss_then_list_excludes_it(client):
    body = client.get(f"/api/insights/{WS_ID}", params={"period": "2026-08"}).json()
    target = body[0]["id"]
    r = client.post(f"/api/insights/{WS_ID}/{target}/dismiss")
    assert r.status_code == 200
    after = client.get(f"/api/insights/{WS_ID}", params={"period": "2026-08"}).json()
    assert target not in {i["id"] for i in after}
    # still there when explicitly asked for
    with_dismissed = client.get(f"/api/insights/{WS_ID}", params={"period": "2026-08", "include_dismissed": True}).json()
    assert target in {i["id"] for i in with_dismissed}


def test_digest_text(client):
    r = client.get(f"/api/insights/{WS_ID}/digest", params={"period": "2026-08"})
    assert r.status_code == 200
    assert "2026-08" in r.text


def test_digest_json(client):
    r = client.get(f"/api/insights/{WS_ID}/digest", params={"period": "2026-08", "format": "json"})
    body = r.json()
    assert body["period"] == "2026-08"
    assert "text" in body
    assert isinstance(body["insights"], list)


def test_calendar_includes_mx_monthly_deadline(client):
    r = client.get(f"/api/insights/{WS_ID}/calendar", params={"from": "2026-09-01", "to": "2026-09-30"})
    assert r.status_code == 200
    kinds = {d["kind"] for d in r.json()}
    assert "mx_monthly_declaration" in kinds
    dates = [d["date"] for d in r.json() if d["kind"] == "mx_monthly_declaration"]
    assert "2026-09-17" in dates


def test_calendar_rejects_backwards_range(client):
    r = client.get(f"/api/insights/{WS_ID}/calendar", params={"from": "2026-09-30", "to": "2026-09-01"})
    assert r.status_code == 400
