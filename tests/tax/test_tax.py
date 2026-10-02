from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aurum.core.db import connect
from aurum.demo.generate import RFC, WS_ID, build_demo
from aurum.tax import sources
from aurum.tax.month_close import deadline_for, month_close
from aurum.tax.prefill import audit
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


# ------------------------------------------------------------------ deadlines


@pytest.mark.parametrize(
    ("period", "expected"),
    [("2026-08", date(2026, 9, 17)), ("2026-12", date(2027, 1, 17)), ("2026-01", date(2026, 2, 17))],
)
def test_deadline_is_the_17th_of_the_following_month(period, expected):
    assert deadline_for(period) == expected


# --------------------------------------------------------------------- audit


def test_audit_finds_every_kind_of_difference(demo):
    report = audit(WS_ID, PERIOD, rfc=RFC)
    kinds = {d.kind for d in report.diffs}
    assert kinds == {
        "pue_not_collected",
        "ppd_missing_rep",
        "deposit_without_cfdi",
        "cash_paid_expense",
        "fixed_asset_iva",
    }
    assert report.diff("pue_not_collected").amount == Decimal("13920.00")
    assert report.diff("deposit_without_cfdi").amount == Decimal("6500.00")
    assert all(d.explain.summary for d in report.diffs)
    assert all(d.explain.citations for d in report.diffs)


def test_opening_balances_are_not_flagged_as_unbacked_deposits(demo):
    report = audit(WS_ID, "2026-06", rfc=RFC)
    assert report.diff("deposit_without_cfdi") is None


def test_prefill_expected_uses_sat_rules_not_bank_reality(demo):
    report = audit(WS_ID, PERIOD, rfc=RFC)
    # SAT counts the uncollected PUE (12,000) on top of the collected one (25,000).
    assert report.prefill_income == Decimal("37000.00")
    assert report.prefill_isr == Decimal("407.00")
    assert report.prefill_iva_acreditable == Decimal("800.00")


def test_audit_without_any_data_is_empty():
    report = audit("nobody", PERIOD)
    assert report.source == "none"
    assert report.diffs == []
    assert report.prefill_income == Decimal("0")


# ---------------------------------------------------------------- month close


def test_month_close_shape_matches_the_contract(demo):
    payload = month_close(WS_ID, PERIOD, rfc=RFC)
    assert set(payload) >= {
        "period",
        "income",
        "isr",
        "iva",
        "retentions",
        "prefill_expected",
        "diffs",
        "deadline",
        "status",
        "warnings",
    }
    assert payload["status"] == "draft"
    assert payload["income"]["collected"] == {"amount": "37000.00", "currency": "MXN"}
    assert payload["isr"]["explain"]["rule_versions"] == ["mx.resico.isr_monthly@2026.1"]
    assert payload["iva"]["trasladado"]["amount"] == "5920.00"
    assert payload["retentions"]["isr"]["amount"] == "312.50"
    assert any("nunca transmite" in w for w in payload["warnings"])


def test_month_close_accepts_documents_directly():
    docs = [
        {
            "uuid": "X-1",
            "tipo": "I",
            "direction": "emitido",
            "metodo_pago": "PUE",
            "fecha": "2026-08-05",
            "subtotal": "10000.00",
            "total": "11600.00",
        }
    ]
    payload = month_close("ghost", PERIOD, documents=docs)
    assert payload["income"]["collected"]["amount"] == "10000.00"
    assert payload["isr"]["value"]["amount"] == "100.00"


# -------------------------------------------------------------------- sources


def test_sources_prefers_the_ingest_table_when_it_exists(demo):
    conn = connect()
    # The real ingest schema is applied by core.db; insert by column name so the shape may grow.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ingest_cfdi (ws_id TEXT, uuid TEXT, tipo TEXT, fecha TEXT, "
        "subtotal TEXT, total TEXT, metodo_pago TEXT, direction TEXT)"
    )
    conn.execute("DELETE FROM ingest_cfdi WHERE ws_id=?", (WS_ID,))
    base = {"ws_id", "uuid", "tipo", "fecha", "subtotal", "total", "metodo_pago", "direction"}
    info = conn.execute("PRAGMA table_info(ingest_cfdi)").fetchall()
    # fill every other NOT NULL column (no default) with a placeholder so the real schema accepts the row
    extra = {r[1]: "X" for r in info if r[3] and r[4] is None and r[1] not in base}
    names = ["ws_id", "uuid", "tipo", "fecha", "subtotal", "total", "metodo_pago", "direction", *extra]
    values = [WS_ID, "TBL-1", "I", "2026-08-03", "1000.00", "1160.00", "PUE", "emitido", *extra.values()]
    conn.execute(
        f"INSERT INTO ingest_cfdi ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",  # noqa: S608
        values,
    )
    conn.commit()
    conn.close()
    docs, source = sources.load_cfdis(WS_ID)
    assert source == "ingest_cfdi"
    assert [d["uuid"] for d in docs] == ["TBL-1"]


def test_sources_reads_demo_from_ingest_table_then_falls_back_to_fixtures(demo):
    # The demo registers its CFDIs in ingest_cfdi (demo/extras.py), so the table wins first…
    docs, source = sources.load_cfdis(WS_ID)
    assert source == "ingest_cfdi"
    assert len(docs) == 12
    # …and the fixture index is the fallback once the table is empty.
    conn = connect()
    conn.execute("DELETE FROM ingest_cfdi WHERE ws_id=?", (WS_ID,))
    conn.commit()
    conn.close()
    docs, source = sources.load_cfdis(WS_ID)
    assert source == "fixtures"
    assert len(docs) == 12


def test_sources_normalizes_alternative_column_names():
    doc = sources.normalize_cfdi(
        {"cfdi_uuid": "A", "tipo_comprobante": "I", "fecha_emision": "2026-08-01", "usocfdi": "G03"}
    )
    assert doc["uuid"] == "A"
    assert doc["tipo"] == "I"
    assert doc["uso_cfdi"] == "G03"
    assert doc["direction"] == "emitido"


def test_bank_lines_come_from_the_ledger(demo):
    lines = sources.bank_lines(WS_ID, PERIOD)
    assert {line.cfdi_uuid for line in lines} >= {"AGO-PUE-D", "REC-AGO-1", "REC-AGO-3"}
    assert any(line.cfdi_uuid is None and line.amount == Decimal("6500.00") for line in lines)


# ------------------------------------------------------------------ endpoints


def test_endpoint_returns_the_month_close(demo, client: TestClient):
    response = client.get(f"/api/tax/mx/resico/{WS_ID}/{PERIOD}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["isr"]["value"]["amount"] == "407.00"
    assert len(payload["diffs"]) == 5


def test_endpoint_rejects_a_bad_period(client: TestClient):
    assert client.get(f"/api/tax/mx/resico/{WS_ID}/2026-13").status_code == 400
    assert client.get(f"/api/tax/mx/resico/{WS_ID}/august").status_code == 400


def test_endpoint_accepts_documents_as_a_query_param(client: TestClient):
    docs = json.dumps(
        [
            {
                "uuid": "Q-1",
                "tipo": "I",
                "direction": "emitido",
                "metodo_pago": "PUE",
                "fecha": "2026-08-05",
                "subtotal": "10000.00",
                "total": "11600.00",
            }
        ]
    )
    response = client.get(f"/api/tax/mx/resico/ghost/{PERIOD}", params={"documents": docs})
    assert response.status_code == 200
    assert response.json()["income"]["collected"]["amount"] == "10000.00"
    assert client.get(f"/api/tax/mx/resico/ghost/{PERIOD}", params={"documents": "{"}).status_code == 400


def test_draft_pdf_is_watermarked_and_bilingual(demo, client: TestClient):
    response = client.get(f"/api/tax/mx/resico/{WS_ID}/{PERIOD}/draft.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "DRAFT.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")

    import pymupdf

    with pymupdf.open(stream=response.content, filetype="pdf") as doc:
        text = "\n".join(page.get_text() for page in doc)
    assert "BORRADOR" in text and "DRAFT" in text
    assert "Ingreso cobrado" in text and "Collected income" in text
    assert "nunca transmite" in text
    assert "407.00 MXN" in text
