from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aurum.core.workspaces import Workspace, save_workspace
from aurum.demo.generate import WS_ID, build_demo
from aurum.tax.month_close import month_close
from aurum.tax.router import router

PERIOD = "2026-08"


@pytest.fixture
def demo() -> dict:
    return build_demo()


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/tax")
    return TestClient(app)


def test_month_close_summary_localizes(demo):
    es = month_close(WS_ID, PERIOD, lang="es")
    en = month_close(WS_ID, PERIOD, lang="en")
    assert "Prellenado" in es["prefill_expected"]["explain"]["summary"]
    assert "prefill" in en["prefill_expected"]["explain"]["summary"].lower()
    # numbers and shape stay identical regardless of language
    assert es["isr"]["value"] == en["isr"]["value"]
    assert es["prefill_expected"]["income"] == en["prefill_expected"]["income"]
    assert [d["kind"] for d in es["diffs"]] == [d["kind"] for d in en["diffs"]]
    for d_es, d_en in zip(es["diffs"], en["diffs"], strict=True):
        assert d_es["amount"] == d_en["amount"]


def test_month_close_default_warning_is_spanish(demo):
    payload = month_close(WS_ID, PERIOD)
    assert any("Borrador" in w for w in payload["warnings"])


def test_router_resico_endpoint_respects_workspace_language(demo):
    save_workspace(Workspace(id=WS_ID, name="Demo", language="en"))
    app = FastAPI()
    app.include_router(router, prefix="/api/tax")
    client = TestClient(app)
    resp = client.get(f"/api/tax/mx/resico/{WS_ID}/{PERIOD}")
    assert resp.status_code == 200, resp.text
    assert "prefill" in resp.json()["prefill_expected"]["explain"]["summary"].lower()


def test_router_resico_endpoint_lang_query_overrides_workspace(demo, client):
    resp = client.get(f"/api/tax/mx/resico/{WS_ID}/{PERIOD}", params={"lang": "en"})
    assert resp.status_code == 200, resp.text
    assert "prefill" in resp.json()["prefill_expected"]["explain"]["summary"].lower()
