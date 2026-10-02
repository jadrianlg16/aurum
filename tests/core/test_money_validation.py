"""aurum.core.money strict validators: ValueError (→ 422), currency ^[A-Z]{3}$."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aurum.api.app import create_app
from aurum.core.money import Amount, q2, to_decimal


def test_currency_is_upper_cased():
    assert Amount(amount="1", currency="mxn").currency == "MXN"
    assert Amount(amount="1", currency=" usd ").currency == "USD"


@pytest.mark.parametrize("currency", ["M X", "MXNN", "MX", "", "12A", None])
def test_bad_currency_rejected(currency):
    with pytest.raises(ValidationError):
        Amount(amount="1", currency=currency)


@pytest.mark.parametrize("amount", [12.5, "abc", "NaN", "Infinity", "-inf", None, True, [1]])
def test_bad_amount_is_a_validation_error_not_a_type_error(amount):
    with pytest.raises(ValidationError):
        Amount(amount=amount)


def test_to_decimal_accepts_str_int_decimal():
    assert to_decimal("12.50") == Decimal("12.50")
    assert to_decimal(3) == Decimal(3)
    assert to_decimal(Decimal("1.005")) == Decimal("1.005")
    with pytest.raises(ValueError):
        to_decimal(1.5)


def test_q2_half_up():
    assert q2("1.005") == Decimal("1.01")
    assert q2("1.004") == Decimal("1.00")
    assert q2(Decimal("-2.675")) == Decimal("-2.68")


def test_float_amount_through_the_api_is_422():
    client = TestClient(create_app())
    client.post("/api/workspaces", json={"id": "mv-ws", "name": "M", "kind": "personal", "country": "MX"})
    acct = client.post(
        "/api/pf/mv-ws/accounts",
        json={"name": "Efectivo", "type": "cash", "opening_balance": {"amount": "100", "currency": "MXN"}},
    )
    assert acct.status_code == 200, acct.text
    account_id = acct.json()["id"]
    resp = client.post(
        "/api/pf/mv-ws/entries",
        json={"kind": "expense", "date": "2026-09-01", "amount": {"amount": 12.5, "currency": "MXN"}, "account_id": account_id},
    )
    assert resp.status_code == 422, resp.text
    resp = client.post(
        "/api/pf/mv-ws/entries",
        json={"kind": "expense", "date": "2026-09-01", "amount": {"amount": "abc", "currency": "MXN"}, "account_id": account_id},
    )
    assert resp.status_code == 422, resp.text
    ok = client.post(
        "/api/pf/mv-ws/entries",
        json={"kind": "expense", "date": "2026-09-01", "amount": {"amount": "12.5", "currency": "mxn"}, "account_id": account_id},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["amount"]["currency"] == "MXN"
    from aurum.ledger.beancount_store import BeancountLedger

    main = BeancountLedger().main_path("mv-ws").read_text(encoding="utf-8")
    assert "-12.50 MXN" in main and "mxn" not in main
