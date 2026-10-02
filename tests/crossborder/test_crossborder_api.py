"""End-to-end tests for /api/crossborder."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.workspaces import Workspace, get_workspace, save_workspace
from aurum.taxus.demo_us import build_demo_us

PROFILE = {
    "days_mx": 200,
    "days_us": 150,
    "days_us_prior_1": 150,
    "days_us_prior_2": 150,
    "home_mx": True,
    "home_us": True,
    "citizenship": ["US"],
    "filing_status": "single",
    "main_professional_center": "MX",
    "foreign_accounts": [
        {"country": "MX", "institution": "Banco Demo", "max_balance_usd": "14000"},
    ],
    "income_sources": [{"country": "MX", "kind": "self_employment", "amount": "60000"}],
    "days_abroad_for_feie": 340,
    "foreign_tax_paid_usd": "5000",
    "treaty_permanent_home": "MX",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    save_workspace(Workspace(id="xb", name="Cross-border", jurisdictions=["MX", "US"]))
    return TestClient(create_app())


def test_profile_round_trips_through_the_workspace_file(client):
    response = client.put("/api/crossborder/xb/profile", json=PROFILE)
    assert response.status_code == 200
    assert response.json()["crossborder"]["days_mx"] == 200
    assert get_workspace("xb").profile["crossborder"]["days_us"] == 150
    assert client.get("/api/crossborder/xb/profile").json()["crossborder"]["citizenship"] == ["US"]


def test_profile_validation_rejects_bad_input(client):
    assert client.put("/api/crossborder/xb/profile", json={"days_us": 900}).status_code == 422
    assert client.put("/api/crossborder/xb/profile", json={"treaty_permanent_home": "CA"}).status_code == 422
    assert client.put("/api/crossborder/xb/profile", json={"mx_source_income_share": "2"}).status_code == 422
    assert client.put("/api/crossborder/xb/profile", json={"filing_status": "widower"}).status_code == 422


def test_profile_on_an_unknown_workspace_is_404(client):
    assert client.put("/api/crossborder/nope/profile", json=PROFILE).status_code == 404
    assert client.get("/api/crossborder/nope/assessment").status_code == 404


def test_assessment_needs_a_profile_first(client):
    response = client.get("/api/crossborder/xb/assessment")
    assert response.status_code == 404
    assert "PUT" in response.json()["detail"]


def test_assessment_composes_every_rule_and_raises_the_expected_flags(client):
    client.put("/api/crossborder/xb/profile", json=PROFILE)
    payload = client.get("/api/crossborder/xb/assessment?lang=en").json()

    assert payload["residency"]["us"] is True
    assert payload["residency"]["mx"] is True
    assert payload["residency"]["dual"] is True
    # 150 + 150/3 + 150/6 = 225
    assert payload["residency"]["weighted_us_days"]["amount"] == "225.00"

    assert payload["treaty"]["applies"] is True
    assert payload["treaty"]["resolved_at_step"] == 1
    assert len(payload["treaty"]["checklist"]) == 5

    assert payload["fbar"]["required"] is True
    assert payload["fbar"]["aggregate"]["amount"] == "14000.00"
    assert payload["fbar"]["threshold"] == "10000"

    options = {o["option"] for o in payload["feie_vs_ftc"]["options"]}
    assert options == {"FEIE", "FTC"}

    blob = " ".join(payload["flags"])
    assert "FBAR likely required" in blob
    assert "dual residency" in blob
    assert "treaty tie-breaker" in blob
    assert "FEIE vs FTC" in blob
    assert "explore with a preparer" in blob.lower()

    for section in ("residency", "treaty", "fbar", "feie_vs_ftc"):
        explain = payload[section]["explain"]
        assert explain["rule_versions"]
        assert explain["citations"]
        assert explain["steps"]
    assert "decides nothing" in payload["disclaimer"]


def test_no_foreign_accounts_means_no_fbar_flag(client):
    client.put("/api/crossborder/xb/profile", json={**PROFILE, "foreign_accounts": []})
    payload = client.get("/api/crossborder/xb/assessment").json()
    assert payload["fbar"]["required"] is False
    assert not any("FBAR likely required" in f for f in payload["flags"])


def test_exactly_ten_thousand_does_not_trip_the_threshold(client):
    client.put(
        "/api/crossborder/xb/profile",
        json={**PROFILE, "foreign_accounts": [{"country": "MX", "max_balance_usd": "10000"}]},
    )
    payload = client.get("/api/crossborder/xb/assessment").json()
    assert payload["fbar"]["required"] is False


def test_a_non_us_person_is_not_dual_and_has_no_fbar_duty(client):
    client.put(
        "/api/crossborder/xb/profile",
        json={
            **PROFILE,
            "citizenship": ["MX"],
            "days_us": 10,
            "days_us_prior_1": 10,
            "days_us_prior_2": 10,
        },
    )
    payload = client.get("/api/crossborder/xb/assessment").json()
    assert payload["residency"]["us"] is False
    assert payload["fbar"]["required"] is False
    assert payload["treaty"]["applies"] is False


def test_the_demo_workspace_is_a_dual_residency_case(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    build_demo_us(tmp_path / "data")
    payload = TestClient(create_app()).get("/api/crossborder/demo-us/assessment?lang=en").json()
    assert payload["residency"]["dual"] is True
    assert payload["fbar"]["required"] is True
    assert payload["fbar"]["aggregate"]["amount"] == "16700.00"
    assert any("FBAR likely required" in f for f in payload["flags"])
    assert any("treaty tie-breaker" in f for f in payload["flags"])


def test_unverified_constants_are_reported(client):
    client.put("/api/crossborder/xb/profile", json=PROFILE)
    payload = client.get("/api/crossborder/xb/assessment").json()
    assert "xb.mx.residency_cff9" in payload["unverified_constants"]
    assert "xb.treaty.article_4" in payload["unverified_constants"]
