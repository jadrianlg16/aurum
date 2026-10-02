"""End-to-end tests for /api/reports against the demo-mx workspace in a temporary data dir."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.demo.generate import build_demo


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    build_demo(tmp_path / "data")
    return TestClient(create_app())


def test_mounted_includes_reports(client):
    payload = client.get("/api/mounted").json()
    assert "/api/reports" in payload["mounted"]


def test_catalog_lists_applicable_packs_for_demo_mx(client):
    payload = client.get("/api/reports/demo-mx").json()
    packs_by_id = {p["pack"]: p for p in payload["packs"]}
    assert packs_by_id["monthly-review"]["applicable"] is True
    assert packs_by_id["net-worth"]["applicable"] is True
    assert packs_by_id["mx-annual"]["applicable"] is True
    # demo-mx only declares jurisdictions=["MX"] and kind="personal"
    assert packs_by_id["us-organizer-bundle"]["applicable"] is False
    assert packs_by_id["client-pack"]["applicable"] is False


def test_unknown_workspace_catalog_has_no_packs(client):
    payload = client.get("/api/reports/nope").json()
    assert payload["packs"] == []


def test_monthly_review_preview_has_sections(client):
    payload = client.get("/api/reports/demo-mx/monthly-review/preview?period=2026-08").json()
    assert payload["workspace"] == "demo-mx"
    assert payload["period"] == "2026-08"
    assert payload["sections"]
    assert payload["title"]


def test_monthly_review_pdf_is_a_real_pdf(client):
    response = client.get("/api/reports/demo-mx/monthly-review?period=2026-08&format=pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1000


def test_monthly_review_html_carries_the_fixed_footer(client):
    response = client.get("/api/reports/demo-mx/monthly-review?period=2026-08&format=html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "decision support, not advice" in response.text
    assert "no es asesor" in response.text


def test_mx_annual_report_includes_the_known_august_isr_figure(client):
    response = client.get("/api/reports/demo-mx/mx-annual?period=2026&format=html")
    assert response.status_code == 200
    assert "407.00" in response.text
    # tax-related pack must carry the DRAFT watermark
    assert "BORRADOR" in response.text or "DRAFT" in response.text


def test_mx_annual_preview_flags_personal_deduction_candidates_or_notes_none(client):
    payload = client.get("/api/reports/demo-mx/mx-annual/preview?period=2026").json()
    assert payload["draft"] is True
    titles = [s["title"] for s in payload["sections"]]
    assert any("contador" in t.lower() for t in titles)


def test_net_worth_report_has_a_series(client):
    payload = client.get("/api/reports/demo-mx/net-worth/preview").json()
    titles = [s["title"] for s in payload["sections"]]
    assert any("Net worth" in t or "Patrimonio" in t for t in titles)


def test_us_organizer_bundle_is_not_applicable_for_demo_mx(client):
    payload = client.get("/api/reports/demo-mx/us-organizer-bundle/preview?period=2026").json()
    assert payload["warnings"]


def test_client_pack_renders_even_for_a_personal_workspace(client):
    response = client.get(
        "/api/reports/demo-mx/client-pack?period=2026-08&format=pdf&reviewer=Revisora%20Demo"
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_unknown_pack_is_404(client):
    assert client.get("/api/reports/demo-mx/not-a-pack/preview").status_code == 404


def test_archive_round_trip(client):
    created = client.post(
        "/api/reports/demo-mx/monthly-review/archive?period=2026-08&format=pdf"
    ).json()
    assert created["id"].startswith("rpt_")
    assert created["sha256"]

    listing = client.get("/api/reports/demo-mx/monthly-review/archive").json()
    assert any(row["id"] == created["id"] for row in listing)
