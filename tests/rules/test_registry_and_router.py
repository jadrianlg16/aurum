from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aurum.core.explain import Citation
from aurum.core.money import Amount
from aurum.rules.mx.iva import classify_iva
from aurum.rules.mx.resico import IsrMonthlyRule, classify_income, period_bounds
from aurum.rules.registry import Registry, Rule, RuleNotFound, RuleResult, load_rules, registry
from aurum.rules.router import router


def test_rules_satisfy_the_protocol():
    load_rules()
    # Alongside the us.* and xb.* rules, the MX four must still all be there.
    assert len(registry.list()) >= 4
    for rule in registry.list():
        assert isinstance(rule, Rule)
        assert rule.citation.law
        assert rule.effective_from <= date(2026, 1, 1)


def test_get_by_explicit_version_and_by_date():
    load_rules()
    assert registry.get("mx.resico.isr_monthly@2026.1").version == "2026.1"
    assert registry.get("mx.resico.isr_monthly", on=date(2026, 8, 31)).version == "2026.1"
    with pytest.raises(RuleNotFound):
        registry.get("mx.resico.isr_monthly", on=date(2020, 1, 1))
    with pytest.raises(RuleNotFound):
        registry.get("mx.nope")
    with pytest.raises(RuleNotFound):
        registry.get("mx.resico.isr_monthly@1999.9")


def test_a_second_version_supersedes_by_effective_date():
    local = Registry()

    class V2(IsrMonthlyRule):
        version = "2027.1"
        effective_from = date(2027, 1, 1)

    local.register(IsrMonthlyRule())
    local.register(V2())
    assert local.get("mx.resico.isr_monthly", on=date(2026, 6, 1)).version == "2026.1"
    assert local.get("mx.resico.isr_monthly", on=date(2027, 6, 1)).version == "2027.1"
    assert len(local.list()) == 2


def test_registering_the_same_version_twice_replaces_it():
    local = Registry()
    local.register(IsrMonthlyRule())
    local.register(IsrMonthlyRule())
    assert len(local.list()) == 1


def test_rule_result_serializes_money_as_strings():
    result = RuleResult(
        value=Amount(amount=Decimal("1.5"), currency="MXN"),
        explain=__import__("aurum.core.explain", fromlist=["Explain"]).Explain(summary="x"),
    )
    assert result.model_dump(mode="json")["value"]["amount"] == "1.5"


def test_citations_carry_a_trust_tier_and_effective_date():
    load_rules()
    citation = registry.get("mx.resico.isr_monthly").citation
    assert isinstance(citation, Citation)
    assert citation.law == "LISR" and citation.article == "113-E"
    assert citation.trust_tier == "primary"
    assert citation.effective_from == date(2026, 1, 1)
    assert citation.url


def test_period_bounds():
    assert period_bounds("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert period_bounds("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))


def test_floats_are_refused():
    with pytest.raises(TypeError):
        registry.get("mx.resico.isr_monthly").compute(collected_income=1000.5)


def test_negative_income_is_refused():
    with pytest.raises(ValueError):
        registry.get("mx.resico.isr_monthly").compute(collected_income="-1")


def test_ppd_paid_by_rep_is_not_reported_missing():
    docs = [
        {
            "uuid": "PPD",
            "tipo": "I",
            "direction": "emitido",
            "metodo_pago": "PPD",
            "fecha": "2026-08-01",
            "subtotal": "1000.00",
            "total": "1160.00",
        },
        {
            "uuid": "REP",
            "tipo": "P",
            "direction": "emitido",
            "fecha": "2026-08-20",
            "pagos": [{"fecha_pago": "2026-08-20", "monto": "1160.00", "uuid_relacionado": "PPD"}],
        },
    ]
    result = classify_income(docs, "2026-08")
    assert result.collected == Decimal("1000.00")
    assert result.excluded == []


def test_rfc_scopes_which_emitidos_are_ours():
    docs = [
        {
            "uuid": "MINE",
            "tipo": "I",
            "direction": "emitido",
            "emisor_rfc": "XAXX010101000",
            "metodo_pago": "PUE",
            "fecha": "2026-08-01",
            "subtotal": "1000.00",
            "total": "1160.00",
        },
        {
            "uuid": "THEIRS",
            "tipo": "I",
            "direction": "emitido",
            "emisor_rfc": "OTRO010101AAA",
            "metodo_pago": "PUE",
            "fecha": "2026-08-01",
            "subtotal": "9000.00",
            "total": "10440.00",
        },
    ]
    assert classify_income(docs, "2026-08", ws_rfc="XAXX010101000").collected == Decimal("1000.00")


def test_iva_credit_requires_the_receptor_rfc_to_match():
    docs = [
        {
            "uuid": "R1",
            "tipo": "I",
            "direction": "recibido",
            "receptor_rfc": "OTRO010101AAA",
            "metodo_pago": "PUE",
            "forma_pago": "03",
            "uso_cfdi": "G03",
            "fecha": "2026-08-01",
            "subtotal": "1000.00",
            "total": "1160.00",
        }
    ]
    result = classify_iva(docs, "2026-08", rfc="XAXX010101000")
    assert result.acreditable == Decimal("0")
    assert result.excluded[0]["reason"] == "rfc_mismatch"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/rules")
    return TestClient(app)


def test_list_endpoint(client: TestClient):
    rows = client.get("/api/rules/").json()
    assert {
        "mx.resico.isr_monthly",
        "mx.resico.income_cash_basis",
        "mx.resico.retention_pm",
        "mx.iva.monthly",
    } <= {r["id"] for r in rows}
    assert all(r["citation"]["law"] for r in rows)
    assert all(r["version"] == "2026.1" for r in rows)


def test_compute_endpoint(client: TestClient):
    response = client.post("/api/rules/mx.resico.isr_monthly/compute", json={"collected_income": "40000.00"})
    assert response.status_code == 200
    body = response.json()
    assert body["value"] == {"amount": "440.00", "currency": "MXN"}
    assert body["explain"]["rule_versions"] == ["mx.resico.isr_monthly@2026.1"]
    assert body["explain"]["citations"][0]["article"] == "113-E"


def test_compute_endpoint_errors(client: TestClient):
    assert client.post("/api/rules/nope/compute", json={}).status_code == 404
    assert client.post("/api/rules/mx.resico.isr_monthly/compute", json={}).status_code == 400
