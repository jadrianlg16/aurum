"""FastAPI TestClient coverage for /api/business."""

from __future__ import annotations

from decimal import Decimal

from aurum.business.demo_biz import WS_ID


def test_business_is_mounted(client):
    assert "/api/business" in client.app.state.mounted


def test_templates_endpoint_lists_both_charts(client):
    body = client.get("/api/business/templates").json()
    names = {t["name"]: t for t in body["templates"]}
    assert set(names) == {"mx_persona_moral", "us_llc"}
    assert names["us_llc"]["currency"] == "USD"
    assert any(a.startswith("Expenses:COGS:") for a in names["mx_persona_moral"]["accounts"])


def test_apply_chart_endpoint(client):
    r = client.post("/api/business/ws-new/chart", json={"name": "us_llc"})
    assert r.status_code == 200
    body = r.json()
    assert body["currency"] == "USD"
    assert body["count"] == len(body["accounts"]) > 30


def test_apply_unknown_chart_is_404(client):
    assert client.post("/api/business/ws-new/chart", json={"name": "nope"}).status_code == 404


def test_employee_crud_masks_pii(client):
    created = client.post(
        "/api/business/ws-emp/payroll/employees",
        json={"name": "Persona Prueba", "daily_salary": "600", "sbc_daily": "640", "rfc": "FAKE800101AB1"},
    ).json()
    assert created["name"] == "P. P***"
    assert created["rfc"] == "*********1AB1"
    listed = client.get("/api/business/ws-emp/payroll/employees").json()
    assert [e["id"] for e in listed] == [created["id"]]
    gone = client.delete(f"/api/business/ws-emp/payroll/employees/{created['id']}").json()
    assert gone["active"] is False
    assert client.get("/api/business/ws-emp/payroll/employees").json() == []


def test_deleting_an_unknown_employee_is_404(client):
    assert client.delete("/api/business/ws-emp/payroll/employees/nope").status_code == 404


def test_payroll_run_endpoint_returns_totals_and_explain(client):
    client.post(
        "/api/business/ws-run/payroll/employees",
        json={"name": "Empleada Prueba", "daily_salary": "500", "sbc_daily": "530"},
    )
    r = client.post("/api/business/ws-run/payroll/run", json={"period": "2026-05"})
    assert r.status_code == 200
    body = r.json()
    assert body["employees"] == 1
    assert body["explain"]["rule_versions"] == [
        "mx.general.isr_provisional@2026.1",
        "mx.imss.employer_quotas@2026.1",
        "mx.infonavit.employer@2026.1",
        "mx.nl.isn@2026.1",
    ]
    assert Decimal(body["totals"]["employer_cost"]["amount"]) > Decimal(body["totals"]["gross"]["amount"])
    listed = client.get("/api/business/ws-run/payroll?period=2026-05").json()
    assert [row["id"] for row in listed] == [body["id"]]
    assert client.get(f"/api/business/ws-run/payroll/{body['id']}").json()["period"] == "2026-05"


def test_payroll_run_rejects_a_bad_period(client):
    assert client.post("/api/business/ws-run/payroll/run", json={"period": "May"}).status_code == 422


def test_payroll_pdf_endpoint(client):
    client.post(
        "/api/business/ws-pdf/payroll/employees", json={"name": "Empleado Prueba", "daily_salary": "400"}
    )
    run = client.post("/api/business/ws-pdf/payroll/run", json={"period": "2026-05"}).json()
    r = client.get(f"/api/business/ws-pdf/payroll/{run['id']}/draft.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "nomina-2026-05-borrador.pdf" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_pdf_for_an_unknown_run_is_404(client):
    assert client.get("/api/business/ws-pdf/payroll/nope/draft.pdf").status_code == 404


def test_invoices_endpoint(client, demo):
    body = client.get(f"/api/business/{WS_ID}/invoices?as_of=2026-06-30").json()
    assert body["counts"]["issued"] == 8
    assert len(body["aging"]) == 4
    assert body["open_invoices"][0]["age_days"] >= body["open_invoices"][-1]["age_days"]
    assert all(i["client_rfc"].startswith("*") for i in body["open_invoices"])


def test_invoices_endpoint_accepts_a_period(client, demo):
    body = client.get(f"/api/business/{WS_ID}/invoices?period=2026-05&as_of=2026-06-30").json()
    assert body["counts"]["issued"] == 3  # the three May invoices


def test_reminder_endpoint(client, demo):
    r = client.post(
        f"/api/business/{WS_ID}/invoices/remind",
        json={"uuid": "DEMO-BIZ-0000-0000-0007", "as_of": "2026-06-30"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] is False
    assert set(body["text"]) == {"es", "en"}


def test_reminder_endpoint_404(client, demo):
    r = client.post(f"/api/business/{WS_ID}/invoices/remind", json={"uuid": "nope"})
    assert r.status_code == 404


def test_kpis_endpoint(client, demo):
    body = client.get(f"/api/business/{WS_ID}/kpis?period=2026-05").json()
    assert body["currency"] == "MXN"
    assert Decimal(body["revenue"]["amount"]) > 0
    assert body["gross_margin"]["percent"]
    assert body["tax_reserve"]["explain"]["summary"]


def test_kpis_endpoint_rejects_a_bad_period(client, demo):
    assert client.get(f"/api/business/{WS_ID}/kpis?period=2026").status_code == 422


def test_constants_endpoint_exposes_verification_status(client):
    body = client.get("/api/business/constants/mx-nl").json()
    assert body["year"] == 2026
    keys = {c["key"] for c in body["constants"]}
    assert {"isn.nl.rate", "infonavit.employer", "uma.daily"} <= keys
    isn = next(c for c in body["constants"] if c["key"] == "isn.nl.rate")
    assert isn["verified"] is True
    assert isn["source_url"].startswith("https://")
    assert "imss.cesantia_vejez.employer_table_2026" in body["unverified"]
