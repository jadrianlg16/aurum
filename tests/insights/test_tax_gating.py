"""Tax nudges and the tax calendar only when the tax module is on."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.workspaces import ensure_workspace, get_workspace, save_workspace
from aurum.demo.generate import WS_ID, build_demo
from aurum.insights.engine import build_insights

TAX_KINDS = {"pue_not_collected", "deposit_without_cfdi", "cash_paid_expense", "fixed_asset_iva",
             "ppd_missing_rep", "you_may_owe", "regime_exit_risk", "us_quarterly_estimate"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    build_demo(tmp_path / "data")
    return TestClient(create_app())


def _set_tax(ws_id: str, on: bool) -> None:
    ws = get_workspace(ws_id)
    ws.modules.tax = on
    save_workspace(ws)


def test_simple_workspace_sees_no_tax_insights_or_calendar(client) -> None:
    _set_tax(WS_ID, False)  # the RESICO demo seeds with modules.tax on; this test is about the gate, not the seed
    assert get_workspace(WS_ID).ui_mode == "simple" and get_workspace(WS_ID).modules.tax is False
    kinds = {i.kind for i in build_insights(WS_ID, "2026-08")}
    assert not kinds & TAX_KINDS, kinds & TAX_KINDS
    rows = client.get(f"/api/insights/{WS_ID}/calendar", params={"from": "2026-09-01", "to": "2026-09-30"}).json()
    assert not [r for r in rows if r["kind"].startswith(("mx_", "us_"))]
    org = client.get(f"/api/organizer/{WS_ID}/calendar?from=2026-09-01&to=2026-09-30").json()
    assert not [i for d in org["days"] for i in d["items"] if i["kind"] == "tax"]
    digest = client.get(f"/api/insights/{WS_ID}/digest", params={"period": "2026-08", "format": "json"}).json()
    assert not {i["kind"] for i in digest["insights"]} & TAX_KINDS


def test_tax_module_on_brings_them_back(client) -> None:
    _set_tax(WS_ID, True)
    kinds = {i.kind for i in build_insights(WS_ID, "2026-08")}
    assert {"pue_not_collected", "you_may_owe"} <= kinds
    rows = client.get(f"/api/insights/{WS_ID}/calendar", params={"from": "2026-09-01", "to": "2026-09-30"}).json()
    assert "mx_monthly_declaration" in {r["kind"] for r in rows}
    org = client.get(f"/api/organizer/{WS_ID}/calendar?from=2026-09-01&to=2026-09-30").json()
    assert [i for d in org["days"] for i in d["items"] if i["kind"] == "tax"]
    _set_tax(WS_ID, False)
    assert not {i.kind for i in build_insights(WS_ID, "2026-08")} & TAX_KINDS


def test_advanced_mode_counts_as_on(client) -> None:
    ws = get_workspace(WS_ID)
    ws.ui_mode = "advanced"
    save_workspace(ws)
    assert "pue_not_collected" in {i.kind for i in build_insights(WS_ID, "2026-08")}


def test_mx_calendar_needs_the_mx_jurisdiction(client) -> None:
    ensure_workspace("us-only", name="US only", jurisdictions=["US"], base_currency="USD")
    _set_tax("us-only", True)
    rows = client.get("/api/insights/us-only/calendar", params={"from": "2026-09-01", "to": "2026-09-30"}).json()
    assert not [r for r in rows if r["kind"].startswith("mx_")]


def test_demo_us_never_gets_resico(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    from aurum.core import db

    db.reset_for_tests()
    from aurum.taxus.demo_us import build_demo_us

    build_demo_us(tmp_path / "data")
    _set_tax("demo-us", True)
    kinds = {i.kind for i in build_insights("demo-us", "2026-08")}
    assert "regime_exit_risk" not in kinds and "pue_not_collected" not in kinds
