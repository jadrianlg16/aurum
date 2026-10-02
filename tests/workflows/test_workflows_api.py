"""End-to-end tests for /api/workflows against the demo-mx workspace in a temporary data dir."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.db import connect
from aurum.demo.generate import build_demo
from aurum.workflows import scheduler as scheduler_mod
from aurum.workflows.cron import CronError, parse
from aurum.workflows.templating import ExprError, eval_when, render_value


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("AURUM_WORKFLOWS_SCHEDULER", raising=False)
    build_demo(tmp_path / "data")
    yield TestClient(create_app())
    scheduler_mod.reset_for_tests()


def test_mounted_includes_workflows(client):
    payload = client.get("/api/mounted").json()
    assert "/api/workflows" in payload["mounted"]


def test_catalog_lists_endpoints_and_excludes_denylist(client):
    payload = client.get("/api/workflows/catalog").json()
    paths = {(e["method"], e["path"]) for e in payload["endpoints"]}
    assert any(p.startswith("/api/insights") for _m, p in paths)
    assert not any("/vault" in p for _m, p in paths)
    assert not any(m == "DELETE" and p.startswith("/api/workspaces") for m, p in paths)
    assert payload["deny_list"]


def test_list_seeds_builtin_workflows(client):
    payload = client.get("/api/workflows/demo-mx").json()
    ids = {w["id"] for w in payload}
    assert {"month-close-mx", "weekly-review", "us-quarterly", "law-watch"} <= ids


def test_get_workflow_definition(client):
    client.get("/api/workflows/demo-mx")  # trigger seeding
    payload = client.get("/api/workflows/demo-mx/month-close-mx").json()
    assert payload["valid"] is True
    assert payload["definition"]["id"] == "month-close-mx"
    assert len(payload["definition"]["steps"]) == 4


def test_create_rejects_denylisted_step(client):
    bad_yaml = """
id: bad
name: Bad workflow
steps:
  - id: nuke
    method: DELETE
    path: /workspaces/demo-mx
"""
    resp = client.post("/api/workflows/demo-mx", json={"yaml": bad_yaml})
    assert resp.status_code == 400
    assert "denied" in str(resp.json()).lower()


def test_create_rejects_invalid_yaml(client):
    resp = client.post("/api/workflows/demo-mx", json={"yaml": "not: [valid"})
    assert resp.status_code == 400


def test_month_close_mx_end_to_end(client):
    client.get("/api/workflows/demo-mx")  # seed
    resp = client.post(
        "/api/workflows/demo-mx/month-close-mx/run",
        json={"period": "2026-08"},
    )
    assert resp.status_code == 200
    run = resp.json()
    assert run["status"] == "success", run
    assert run["workflow_id"] == "month-close-mx"
    step_ids = [s["step_id"] for s in run["steps"]]
    assert step_ids == ["tax_close", "insights", "archive_report", "digest"]
    for step in run["steps"]:
        assert step["status_code"] == 200, step

    # a run row + step rows + audit row + a report archive row all exist
    runs = client.get("/api/workflows/demo-mx/month-close-mx/runs").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"

    archived = client.get("/api/reports/demo-mx/monthly-review/archive").json()
    assert len(archived) == 1
    assert archived[0]["period"] == "2026-08"

    conn = connect()
    try:
        audit_rows = conn.execute(
            "SELECT * FROM core_audit WHERE ws_id=? AND action=?",
            ("demo-mx", "workflows.month-close-mx.run"),
        ).fetchall()
    finally:
        conn.close()
    assert len(audit_rows) == 1


def test_run_detail_endpoint(client):
    client.get("/api/workflows/demo-mx")
    run = client.post("/api/workflows/demo-mx/law-watch/run", json={}).json()
    detail = client.get(f"/api/workflows/demo-mx/law-watch/runs/{run['id']}").json()
    assert detail["id"] == run["id"]
    assert detail["steps"]


def test_schedule_roundtrip_and_gate(client):
    client.get("/api/workflows/demo-mx")
    resp = client.post(
        "/api/workflows/demo-mx/weekly-review/schedule", json={"cron": "0 8 * * 0"}
    )
    assert resp.status_code == 200
    assert resp.json()["gated"] is True  # AURUM_WORKFLOWS_SCHEDULER not set

    status = client.get("/api/workflows/demo-mx/weekly-review/schedule").json()
    assert status["schedule"] == "0 8 * * 0"

    resp = client.delete("/api/workflows/demo-mx/weekly-review/schedule")
    assert resp.json()["schedule"] is None


def test_schedule_rejects_bad_cron(client):
    client.get("/api/workflows/demo-mx")
    resp = client.post("/api/workflows/demo-mx/weekly-review/schedule", json={"cron": "bogus"})
    assert resp.status_code == 400


def test_propose_offline_fallback_matches_month_close(client, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("no llm reachable in tests")

    monkeypatch.setattr("aurum.llm.structured.generate_text", _boom)
    resp = client.post(
        "/api/workflows/demo-mx/propose",
        json={"description": "close the mexican tax month and archive the review"},
    )
    payload = resp.json()
    assert payload["source"] == "offline-fallback"
    assert payload["valid"] is True
    assert "month-close-mx" in payload["yaml"]


def test_propose_never_saves(client, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr("aurum.llm.structured.generate_text", _boom)
    client.post("/api/workflows/demo-mx/propose", json={"description": "weekly budget check"})
    ids = {w["id"] for w in client.get("/api/workflows/demo-mx").json()}
    assert "weekly-budget-check" not in ids


def test_deleting_unknown_workflow_404s(client):
    resp = client.delete("/api/workflows/demo-mx/does-not-exist")
    assert resp.status_code == 404


def test_scheduler_tick_runs_due_workflow(client):
    client.get("/api/workflows/demo-mx")
    client.post("/api/workflows/demo-mx/law-watch/schedule", json={"cron": "* * * * *"})
    from datetime import UTC, datetime

    ran = scheduler_mod.get_scheduler().tick(now=datetime.now(UTC))
    assert any(r["id"] == "law-watch" for r in ran)


# --------------------------------------------------------------------------- unit tests


def test_cron_parse_and_match():
    schedule = parse("0 8 * * 0")
    from datetime import datetime

    sunday_8am = datetime(2026, 9, 6, 8, 0)  # a Sunday
    assert sunday_8am.weekday() == 6
    assert schedule.matches(sunday_8am)
    assert not schedule.matches(datetime(2026, 9, 6, 9, 0))


def test_cron_rejects_bad_expression():
    with pytest.raises(CronError):
        parse("* * *")
    with pytest.raises(CronError):
        parse("99 * * * *")


def test_when_expression_evaluator():
    ctx = {"steps": {"a": {"status": 200, "body": {"x": [1, 2, 3]}}}}
    assert eval_when("steps.a.status == 200", ctx) is True
    assert eval_when("steps.a.status != 200", ctx) is False
    assert eval_when("len(steps.a.body.x) > 0 and not False", ctx) is True
    with pytest.raises(ExprError):
        eval_when("__import__('os')", ctx)


def test_render_value_templating():
    ctx = {"ws": "demo-mx", "period": "2026-08", "steps": {}}
    assert render_value("/insights/{{ ws }}?period={{ period }}", ctx) == "/insights/demo-mx?period=2026-08"
    assert render_value("{{ period }}", ctx) == "2026-08"
