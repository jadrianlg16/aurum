"""Deny-list normalization + templating lockdown, and the runner's auth + Host headers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.demo.generate import build_demo
from aurum.workflows import runner as runner_mod
from aurum.workflows import scheduler as scheduler_mod
from aurum.workflows.deny import is_denied, normalize_api_path
from aurum.workflows.store import validate_yaml
from aurum.workflows.templating import ExprError, eval_when, render_value, resolve_path


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("/satsync/x/vault", "/satsync/x/vault"),
        ("/api/satsync/x/vault", "/satsync/x/vault"),
        ("/API//satsync/x/../x/vault?y=1", "/satsync/x/vault"),
        ("api/satsync/x/vault#frag", "/satsync/x/vault"),
        ("/api/./Insights/x", "/Insights/x"),
        ("/apix/y", "/apix/y"),
        ("/api", "/"),
        ("", "/"),
    ],
)
def test_normalize_api_path(raw, norm):
    assert normalize_api_path(raw) == norm


def test_is_denied_after_normalization():
    assert is_denied("DELETE", "/api/satsync/x/vault")
    assert is_denied("GET", "/API//satsync/x/../x/vault?y=1")
    assert is_denied("delete", "/Api/Workspaces/personal")
    assert is_denied("POST", "/api/satsync/x/sync")
    assert not is_denied("GET", "/insights/x")
    assert not is_denied("GET", "/api/workspaces")
    assert not is_denied("GET", "/satsync/x/jobs")


def test_validate_yaml_rejects_prefixed_denied_path():
    wf, errors, _ = validate_yaml(
        """
id: bad
name: Bad
steps:
  - id: leak
    method: GET
    path: /api/satsync/{{ws}}/vault
"""
    )
    assert wf is None
    assert any("denied" in e for e in errors)


def test_templating_no_getattr_and_depth_cap():
    ctx = {"steps": {"x": {"status": 200, "body": {"items": [{"n": 1}, {"n": 2}]}}}}
    assert render_value("{{ steps.x.body.items.1.n }}", ctx) == 2
    assert render_value("status={{ steps.x.status }}", ctx) == "status=200"
    for bad in (
        "{{ steps.x.body.__class__.__base__ }}",
        "{{ steps.x.body.items.__len__ }}",
        "{{ steps.x.status.real }}",
        "{{ steps.x.body.items.9.n }}",
        "{{ steps.x.body.items.n }}",
    ):
        with pytest.raises(KeyError):
            render_value(bad, ctx)
    with pytest.raises(KeyError):
        resolve_path(".".join(["a"] * 17), {"a": {}})
    with pytest.raises(ExprError):
        eval_when("steps.x.body.__class__ == 1", ctx)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("AURUM_WORKFLOWS_SCHEDULER", raising=False)
    build_demo(tmp_path / "data")
    yield TestClient(create_app())
    scheduler_mod.reset_for_tests()


def test_run_with_prefixed_denied_path_never_hits_the_vault(client, monkeypatch):
    from aurum.satsync import router as satsync_router

    def boom(*_a, **_k):
        raise AssertionError("vault endpoint was reached")

    for name in ("delete_vault", "get_vault", "vault_status", "store_vault"):
        if hasattr(satsync_router, name):
            monkeypatch.setattr(satsync_router, name, boom)
    from aurum.workflows.models import Step, WorkflowDef

    wf = WorkflowDef(id="leak", name="Leak", steps=[Step(id="v", method="DELETE", path="/api/satsync/{{ws}}/vault")])
    run = runner_mod.run_def("demo-mx", wf, {})
    assert run["status"] == "failed"
    assert run["steps"][0]["error"] == "denied path"
    assert run["steps"][0]["status_code"] is None


def test_runner_dispatches_normalized_path_with_query(client):
    from aurum.workflows.models import Step, WorkflowDef

    wf = WorkflowDef(id="q", name="Q", steps=[Step(id="h", method="GET", path="/API/./insights/{{ws}}?lang=es")])
    run = runner_mod.run_def("demo-mx", wf, {})
    assert run["status"] == "success", run
    assert run["steps"][0]["status_code"] == 200


def test_builtin_workflow_runs_with_token_and_no_allowed_hosts(client, monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    monkeypatch.delenv("AURUM_ALLOWED_HOSTS", raising=False)
    auth = {"Authorization": "Bearer s3cr3t"}
    client.get("/api/workflows/demo-mx", headers=auth)  # seed
    resp = client.post("/api/workflows/demo-mx/month-close-mx/run", json={"period": "2026-08"}, headers=auth)
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["status"] == "success", run
    assert all(s["status_code"] == 200 for s in run["steps"]), run["steps"]
