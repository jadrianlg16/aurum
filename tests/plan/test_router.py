"""FastAPI TestClient coverage for /api/plan."""

from __future__ import annotations

from aurum.plan.scenarios import SCENARIOS


def test_scenarios_catalog_lists_all_six(client):
    r = client.get("/api/plan/ws1/scenarios")
    assert r.status_code == 200
    body = r.json()
    ids = {item["id"] for item in body}
    assert ids == set(SCENARIOS)
    for item in body:
        assert "properties" in item["schema"]


def test_run_regime_mx_default_inputs(client):
    r = client.post("/api/plan/ws1/scenarios/regime_mx/run", json={})
    assert r.status_code == 200
    body = r.json()
    assert "resico" in body["results"]
    assert "general" in body["results"]
    assert body["results"]["cheaper"] in {"regime_mx.resico", "regime_mx.general"}
    assert body["explain"]["rule_versions"] == [
        "mx.resico.isr_monthly@2026.1",
        "mx.general.isr_provisional@2026.1",
    ]


def test_run_unknown_scenario_404(client):
    r = client.post("/api/plan/ws1/scenarios/nope/run", json={})
    assert r.status_code == 404


def test_run_bad_inputs_422(client):
    r = client.post("/api/plan/ws1/scenarios/retirement/run", json={"horizon_years": 999})
    assert r.status_code == 422


def test_run_cash_vs_credit(client):
    r = client.post("/api/plan/ws1/scenarios/cash_vs_credit/run", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["results"]["cheaper"] in {"cash", "credit"}


def test_run_buy_vs_rent(client):
    r = client.post("/api/plan/ws1/scenarios/buy_vs_rent/run", json={})
    assert r.status_code == 200
    assert body_cheaper(r) in {"buy", "rent"}


def body_cheaper(r):
    return r.json()["results"]["cheaper"]


def test_run_debt_payoff(client):
    r = client.post("/api/plan/ws1/scenarios/debt_payoff/run", json={})
    assert r.status_code == 200
    body = r.json()
    assert "avalanche" in body["results"]
    assert "snowball" in body["results"]


def test_run_entity_us(client):
    r = client.post("/api/plan/ws1/scenarios/entity_us/run", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["results"]["verified"] is False


def test_montecarlo_retirement(client):
    r = client.post(
        "/api/plan/ws1/scenarios/retirement/montecarlo",
        json={"inputs": {"horizon_years": 10}, "n": 200, "seed": 7},
    )
    assert r.status_code == 200
    body = r.json()
    assert float(body["results"]["p10"]) <= float(body["results"]["p50"]) <= float(body["results"]["p90"])


def test_sensitivity_regime_mx(client):
    r = client.post(
        "/api/plan/ws1/scenarios/regime_mx/sensitivity",
        json={"inputs": {}, "vary": ["monthly_income", "monthly_deductible_expenses"], "range_pct": 0.2},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["points"]) == 2
    assert body["points"][0]["range"] >= body["points"][1]["range"]


def test_saved_scenario_crud_and_run(client):
    r = client.post(
        "/api/plan/ws1/saved",
        json={"scenario_id": "cash_vs_credit", "name": "My purchase", "inputs": {"price": "100000"}},
    )
    assert r.status_code == 200
    saved = r.json()
    saved_id = saved["id"]
    assert saved["inputs"]["price"] == "100000"

    r = client.get("/api/plan/ws1/saved")
    assert any(s["id"] == saved_id for s in r.json())

    r = client.put(
        f"/api/plan/ws1/saved/{saved_id}",
        json={"scenario_id": "cash_vs_credit", "name": "Renamed", "inputs": {"price": "50000"}},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"

    r = client.post(f"/api/plan/ws1/saved/{saved_id}/run")
    assert r.status_code == 200
    assert "cheaper" in r.json()["results"]

    r = client.delete(f"/api/plan/ws1/saved/{saved_id}")
    assert r.status_code == 200
    r = client.get("/api/plan/ws1/saved")
    assert not any(s["id"] == saved_id for s in r.json())


def test_saved_scenario_404s(client):
    assert client.put("/api/plan/ws1/saved/nope", json={"scenario_id": "cash_vs_credit", "name": "x"}).status_code == 404
    assert client.delete("/api/plan/ws1/saved/nope").status_code == 404
    assert client.post("/api/plan/ws1/saved/nope/run").status_code == 404


def test_mounted_includes_plan():
    from aurum.api.app import create_app

    app = create_app()
    assert "/api/plan" in app.state.mounted
