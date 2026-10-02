from __future__ import annotations

from aurum.creditreport import store
from aurum.creditreport.parser import parse_pdf_bytes, parse_text


def test_parse_text_labeled_blocks():
    report = parse_text(
        "SCORE: 720\n\nOTORGANTE: BANCO XYZ\nLIMITE DE CREDITO: $50,000.00\n"
        "SALDO ACTUAL: $12,345.00\nESTATUS DE CUENTA: AL CORRIENTE\nFECHA DE APERTURA: 15/03/2020\n"
    )
    assert report.score == {"value": 720, "bureau": "Buró de Crédito"}
    assert len(report.accounts) == 1
    acct = report.accounts[0]
    assert acct["grantor"] == "BANCO XYZ"
    assert acct["limit"] == "50000.00"
    assert acct["balance"] == "12345.00"
    assert acct["status"] == "AL CORRIENTE"
    assert acct["opened"] == "15/03/2020"
    assert report.warnings == []


def test_parse_pdf_bytes(sample_report_pdf):
    report = parse_pdf_bytes(sample_report_pdf)
    assert report.score["value"] == 720
    assert len(report.accounts) == 2
    grantors = {a["grantor"] for a in report.accounts}
    assert "BANCO XYZ SA" in grantors
    assert "FINANCIERA ABC" in grantors


def test_parse_low_confidence_document(blank_pdf):
    report = parse_pdf_bytes(blank_pdf)
    assert report.accounts == []
    assert any("no accounts" in w for w in report.warnings)
    assert any("no score" in w for w in report.warnings)


def test_store_roundtrip(sample_report_pdf):
    report = parse_pdf_bytes(sample_report_pdf)
    saved = store.save_import("ws-a", "report.pdf", report)
    assert saved["score"]["value"] == 720
    fetched = store.get_import("ws-a", saved["id"])
    assert fetched["id"] == saved["id"]
    latest = store.latest_import("ws-a")
    assert latest["id"] == saved["id"]


def test_explain_score_factors():
    explain = store.explain_score_factors()
    assert explain.citations
    assert any("Buró" in c.law or "CONDUSEF" in c.law for c in explain.citations)


def test_router_import_and_get(client, sample_report_pdf):
    r = client.post(
        "/api/creditreport/ws-b/import",
        files={"file": ("report.pdf", sample_report_pdf, "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["score"]["value"] == 720
    assert len(body["accounts"]) == 2

    r = client.get("/api/creditreport/ws-b")
    assert r.status_code == 200
    assert r.json()["latest"]["id"] == body["id"]

    r = client.get("/api/creditreport/ws-b/explain")
    assert r.status_code == 200
    assert "summary" in r.json()


def test_router_rejects_non_pdf(client):
    r = client.post(
        "/api/creditreport/wsC/import",
        files={"file": ("report.txt", b"not a pdf", "text/plain")},
    )
    assert r.status_code == 400
