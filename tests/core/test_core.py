from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core import audit
from aurum.core.money import Amount, q2
from aurum.core.workspaces import Workspace, get_workspace, list_workspaces, save_workspace
from aurum.ledger.base import Amount as LAmount
from aurum.ledger.base import InMemoryLedger, Posting, Transaction


def test_amount_refuses_float():
    with pytest.raises((TypeError, ValueError)):
        Amount(amount=1.5)


def test_amount_math_and_quantize():
    a = Amount(amount="10.005") + Amount(amount="0.10")
    assert a.quantized().amount == Decimal("10.11")
    assert q2("2.675") == Decimal("2.68")


def test_workspace_roundtrip_and_mask():
    ws = save_workspace(Workspace(id="demo-mx", name="Demo", profile={"rfc": "XAXX010101000"}))
    assert get_workspace("demo-mx").profile["rfc"] == "XAXX010101000"
    assert ws.masked()["profile"]["rfc"].endswith("1000") and ws.masked()["profile"]["rfc"].startswith("*")
    assert [w.id for w in list_workspaces()] == ["demo-mx"]


def test_audit_masks_rfc_and_is_recorded():
    audit.record("demo-mx", "test", {"rfc": "FAKE900101AB1"}, {"ok": True})
    rows = audit.recent("demo-mx")
    assert rows and "FAKE900101AB1" not in rows[0]["inputs"]


def test_inmemory_ledger_balances_posting():
    led = InMemoryLedger()
    led.append(
        "w",
        Transaction(
            date=date(2026, 8, 1),
            payee="Tacos",
            narration="comida",
            postings=[Posting(account="Expenses:Food", amount=LAmount(amount="250")), Posting(account="Assets:Cash")],
        ),
    )
    bal = led.balances("w")
    assert bal["Assets:Cash"][0].amount == Decimal("-250")
    assert bal["Expenses:Food"][0].amount == Decimal("250")


def test_app_mounts_core_and_health():
    client = TestClient(create_app())
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "/api" in client.get("/api/mounted").json()["mounted"]


# --- health: no data_dir; reports auth/bind/schema ---------------------------------------------------


def test_health_has_no_data_dir():
    client = TestClient(create_app())
    body = client.get("/api/health").json()
    assert "data_dir" not in body


def test_health_auth_defaults_to_not_required():
    client = TestClient(create_app())
    body = client.get("/api/health").json()
    assert body["auth"] == {"required": False, "source": "none"}


def test_health_auth_required_when_token_set(monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    client = TestClient(create_app())
    body = client.get("/api/health").json()
    assert body["auth"]["required"] is True
    assert body["auth"]["source"] == "env"


def test_health_bind_defaults_to_loopback():
    client = TestClient(create_app())
    assert client.get("/api/health").json()["bind"] == "127.0.0.1"


def test_health_schema_is_a_dict_of_module_versions():
    client = TestClient(create_app())
    schema = client.get("/api/health").json()["schema"]
    assert isinstance(schema, dict)


# --- Explain.Step: additive id ------------------------------------------------------------------------


def test_explain_step_id_defaults_from_label_when_it_looks_like_one():
    from aurum.core.explain import Explain

    e = Explain(summary="s")
    e.add_step("liquid_balance", "100.00")
    e.add_step("Saldo disponible", "100.00")  # not ^[a-z][a-z0-9_]*$ -> no id guess
    e.add_step("custom", "1", id="explicit")
    assert e.steps[0].id == "liquid_balance"
    assert e.steps[0].label == "liquid_balance"
    assert e.steps[1].id is None
    assert e.steps[2].id == "explicit"
