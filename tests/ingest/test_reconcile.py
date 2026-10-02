from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.db import connect
from aurum.core.workspaces import Workspace, save_workspace


def _client() -> TestClient:
    save_workspace(Workspace(id="ws1", name="Test", base_currency="MXN"))
    return TestClient(create_app())


def _insert_bank_line(ws: str, day: str, amount: str, description: str = "line", bank: str = "bbva") -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO ingest_bank_lines (ws_id, bank, date, description, amount, currency, hash, imported_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ws, bank, day, description, amount, "MXN", f"hash-{day}-{amount}-{description}", datetime.now(UTC).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _insert_cfdi(uuid: str, ws: str, direction: str, day: str, total: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO ingest_cfdi (uuid, ws_id, tipo, direction, fecha, emisor_rfc, receptor_rfc, subtotal, "
            "total, moneda, json, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (uuid, ws, "I", direction, day, "AAA010101AAA", "BBB010101BBB", total, total, "MXN", "{}",
             datetime.now(UTC).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def test_reconcile_suggests_cfdi_for_inflow():
    client = _client()
    line_id = _insert_bank_line("ws1", "2026-08-05", "1000.00", description="DEPOSITO")
    _insert_cfdi("uuid-1", "ws1", "emitido", "2026-08-06T00:00:00", "1000.00")

    resp = client.get("/api/ingest/ws1/reconcile", params={"period": "2026-08"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unmatched_bank"] == 1
    assert body["unmatched_cfdi"] == ["uuid-1"]
    line = next(bl for bl in body["bank_lines"] if bl["id"] == line_id)
    assert line["suggestions"] and line["suggestions"][0]["cfdi_uuid"] == "uuid-1"
    assert line["suggestions"][0]["score"] > 0


def test_reconcile_suggests_cfdi_recibido_for_outflow():
    client = _client()
    _insert_bank_line("ws1", "2026-08-10", "-500.00", description="PAGO PROVEEDOR")
    _insert_cfdi("uuid-2", "ws1", "recibido", "2026-08-11T00:00:00", "500.00")

    body = client.get("/api/ingest/ws1/reconcile", params={"period": "2026-08"}).json()
    line = body["bank_lines"][0]
    assert line["suggestions"][0]["cfdi_uuid"] == "uuid-2"


def test_reconcile_no_suggestion_outside_tolerance():
    client = _client()
    _insert_bank_line("ws1", "2026-08-05", "1000.00")
    _insert_cfdi("uuid-3", "ws1", "emitido", "2026-08-20T00:00:00", "1000.00")  # 15 days away, out of ±3

    body = client.get("/api/ingest/ws1/reconcile", params={"period": "2026-08"}).json()
    assert body["bank_lines"][0]["suggestions"] == []
    assert body["unmatched_cfdi"] == ["uuid-3"]


def test_match_and_unmatch_roundtrip():
    client = _client()
    line_id = _insert_bank_line("ws1", "2026-08-05", "1000.00")
    _insert_cfdi("uuid-4", "ws1", "emitido", "2026-08-05T00:00:00", "1000.00")

    resp = client.post("/api/ingest/ws1/reconcile/match", json={"bank_line_id": line_id, "cfdi_uuid": "uuid-4"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["cfdi_uuid"] == "uuid-4"

    body = client.get("/api/ingest/ws1/reconcile", params={"period": "2026-08"}).json()
    assert body["unmatched_bank"] == 0
    assert body["unmatched_cfdi"] == []
    line = body["bank_lines"][0]
    assert line["cfdi_uuid"] == "uuid-4"
    assert line["suggestions"] == []  # already matched, no suggestions offered

    unmatch_resp = client.post("/api/ingest/ws1/reconcile/unmatch", json={"bank_line_id": line_id})
    assert unmatch_resp.status_code == 200
    assert unmatch_resp.json()["cfdi_uuid"] is None

    body_again = client.get("/api/ingest/ws1/reconcile", params={"period": "2026-08"}).json()
    assert body_again["unmatched_bank"] == 1


def test_match_missing_bank_line_404():
    client = _client()
    resp = client.post("/api/ingest/ws1/reconcile/match", json={"bank_line_id": 999, "cfdi_uuid": "x"})
    assert resp.status_code == 404


def test_unmatch_missing_bank_line_404():
    client = _client()
    resp = client.post("/api/ingest/ws1/reconcile/unmatch", json={"bank_line_id": 999})
    assert resp.status_code == 404


def test_reconcile_bad_period_400():
    client = _client()
    resp = client.get("/api/ingest/ws1/reconcile", params={"period": "not-a-period"})
    assert resp.status_code == 400


def test_reconcile_matches_ledger_transaction():
    client = _client()
    line_id = _insert_bank_line("ws1", "2026-08-05", "1000.00", description="DEPOSITO")
    client.post(
        "/api/ledger/ws1/transactions",
        json={
            "date": "2026-08-05",
            "payee": "ACME",
            "narration": "Factura",
            "postings": [
                {"account": "Assets:Bank:BBVA", "amount": {"amount": "1000.00", "currency": "MXN"}},
                {"account": "Income:Freelance"},
            ],
        },
    )
    body = client.get("/api/ingest/ws1/reconcile", params={"period": "2026-08"}).json()
    line = next(bl for bl in body["bank_lines"] if bl["id"] == line_id)
    assert any(s["txn_id"] for s in line["suggestions"])
