from datetime import date

from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.workspaces import Workspace, save_workspace
from tests.ingest.cfdi_builder import RFC_EMISOR, build_ingreso_pue_xml


def _client_with_ws() -> TestClient:
    save_workspace(Workspace(id="demo-mx", name="Demo", profile={"rfc": RFC_EMISOR}))
    return TestClient(create_app())


def test_cfdi_upload_and_list():
    client = _client_with_ws()
    xml = build_ingreso_pue_xml()
    resp = client.post(
        "/api/ingest/demo-mx/cfdi", files={"file": ("factura.xml", xml, "application/xml")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 1
    assert len(body["inbox_items"]) == 1
    assert body["inbox_items"][0]["kind"] == "cfdi"

    listed = client.get("/api/ingest/demo-mx/cfdi").json()
    assert len(listed) == 1
    assert listed[0]["uuid"] == "AAAAAAAA-1111-2222-3333-444444444444"

    listed_period = client.get("/api/ingest/demo-mx/cfdi", params={"period": "2026-08"}).json()
    assert len(listed_period) == 1
    listed_other = client.get("/api/ingest/demo-mx/cfdi", params={"period": "2026-01"}).json()
    assert listed_other == []


def test_cfdi_upload_bad_xml_400():
    client = _client_with_ws()
    resp = client.post(
        "/api/ingest/demo-mx/cfdi", files={"file": ("bad.xml", b"<oops/>", "application/xml")}
    )
    assert resp.status_code == 400


def _account(client, name="Efectivo", type_="cash") -> dict:
    r = client.post("/api/pf/demo-mx/accounts", json={"name": name, "type": type_})
    assert r.status_code == 200, r.text
    return r.json()


def test_quickadd_previews_then_commits_a_pf_entry_without_an_inbox_row():
    """Quickadd writes a real, editable movement; no inbox item."""
    client = _client_with_ws()
    cash = _account(client)
    resp = client.post("/api/ingest/demo-mx/quickadd", json={"text": "250 tacos comida"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "preview" and body["id"] is None and body["entry"] is None
    assert body["preview"]["label_name"] == "Comida fuera" and body["preview"]["account_name"] == "Efectivo"
    assert body["preview"]["amount"] == {"amount": "250.00", "currency": "MXN"}
    assert body["proposed"]["postings"][0]["account"] == cash["account"]
    assert client.get("/api/ingest/demo-mx/inbox", params={"status": "pending"}).json() == []

    resp = client.post("/api/ingest/demo-mx/quickadd", json={"text": "250 tacos comida", "commit": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "committed" and body["id"] and body["entry"]["id"] == body["id"]
    assert body["entry"]["source"] == "quickadd" and body["entry"]["editable"] is True
    assert client.get("/api/ingest/demo-mx/inbox", params={"status": "pending"}).json() == []
    balance = client.get(f"/api/pf/demo-mx/accounts/{cash['id']}").json()["balance"]
    assert balance["amount"] == "-250.00"
    page = client.get("/api/pf/demo-mx/entries").json()
    assert page["totals"]["count"] == 1 and page["entries"][0]["amount"]["amount"] == "-250.00"


def test_quickadd_without_a_resolvable_account_is_a_400_and_unknown_account_id_a_404():
    client = _client_with_ws()
    resp = client.post("/api/ingest/demo-mx/quickadd", json={"text": "250 tacos comida"})
    assert resp.status_code == 400 and "cuenta" in resp.json()["detail"].lower()
    _account(client)
    resp = client.post("/api/ingest/demo-mx/quickadd", json={"text": "250 tacos comida", "account_id": "nope"})
    assert resp.status_code == 404


def test_inbox_accept_and_reject_flow_still_works_for_other_producers():
    client = _client_with_ws()
    from aurum.core.money import Amount
    from aurum.ingest.inbox import create_inbox_item
    from aurum.ledger.base import Posting, Transaction

    txn = Transaction(
        date=date(2026, 8, 1), payee="Cine", narration="100 cine ocio",
        postings=[Posting(account="Assets:Cash", amount=Amount(amount="-100")), Posting(account="Expenses:Uncategorized")],
    )
    item = create_inbox_item("demo-mx", "bank", txn, confidence=0.6)
    pending = client.get("/api/ingest/demo-mx/inbox", params={"status": "pending"}).json()
    assert any(i["id"] == item.id for i in pending)

    bad = client.post(f"/api/ingest/demo-mx/inbox/{item.id}/accept", json={"account": "Expenses:comida\n"})
    assert bad.status_code == 400
    still = client.get("/api/ingest/demo-mx/inbox", params={"status": "pending"}).json()
    assert any(i["id"] == item.id for i in still)

    accept_resp = client.post(f"/api/ingest/demo-mx/inbox/{item.id}/accept", json={"account": "Expenses:Personal:Entertainment"})
    assert accept_resp.status_code == 200, accept_resp.text
    assert accept_resp.json()["item"]["status"] == "accepted"
    assert accept_resp.json()["item"]["proposed"]["postings"][-1]["account"] == "Expenses:Personal:Entertainment"
    assert "txn_id" in accept_resp.json()

    # accepting again is a conflict
    again = client.post(f"/api/ingest/demo-mx/inbox/{item.id}/accept")
    assert again.status_code == 409

    other = create_inbox_item("demo-mx", "bank", txn, confidence=0.6)
    rej = client.post(f"/api/ingest/demo-mx/inbox/{other.id}/reject")
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"


def test_bank_csv_upload_endpoint_requires_account_id_and_writes_entries():
    client = _client_with_ws()
    csv_bytes = b"Fecha,Concepto,Monto\n2026-08-01,OXXO,-50.00\n"
    missing = client.post(
        "/api/ingest/demo-mx/bank/csv", data={"bank": "BBVA"}, files={"file": ("mov.csv", csv_bytes, "text/csv")},
    )
    assert missing.status_code == 422
    unknown = client.post(
        "/api/ingest/demo-mx/bank/csv", data={"bank": "BBVA", "account_id": "nope"},
        files={"file": ("mov.csv", csv_bytes, "text/csv")},
    )
    assert unknown.status_code == 404
    acct = _account(client, "BBVA", "checking")
    resp = client.post(
        "/api/ingest/demo-mx/bank/csv",
        data={"bank": "BBVA", "account_id": acct["id"]},
        files={"file": ("mov.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 1 and len(body["created"]) == 1 and body["skipped_duplicates"] == 0
    assert "inbox_items" not in body
    row = client.get("/api/pf/demo-mx/entries").json()["entries"][0]
    assert row["source"] == "import" and row["amount"]["amount"] == "-50.00" and row["editable"] is True


def test_inbox_not_found_404():
    client = _client_with_ws()
    resp = client.post("/api/ingest/demo-mx/inbox/does-not-exist/accept")
    assert resp.status_code == 404
