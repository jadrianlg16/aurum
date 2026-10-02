from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from aurum.core.money import Amount
from aurum.fx.rates import FxRateNotFound, cache_rate, convert, get_rate, net_worth_in


def test_same_currency_is_identity():
    assert get_rate("MXN", "MXN", date(2026, 1, 1)) == Decimal("1")


def test_no_rate_raises(fake_fx_dir):
    with pytest.raises(FxRateNotFound):
        get_rate("EUR", "JPY", date(2026, 1, 1))


def test_fixture_exact_and_nearest(fake_fx_dir):
    assert get_rate("USD", "MXN", date(2026, 1, 2)) == Decimal("17.10")
    # 2026-01-05 has no exact entry -> nearest prior (2026-01-02)
    assert get_rate("USD", "MXN", date(2026, 1, 5)) == Decimal("17.10")
    assert get_rate("USD", "MXN", date(2026, 1, 10)) == Decimal("17.35")


def test_fixture_inverse(fake_fx_dir):
    rate = get_rate("MXN", "USD", date(2026, 1, 2))
    assert rate == Decimal("1") / Decimal("17.10")


def test_cache_takes_priority(fake_fx_dir):
    cache_rate("USD", "MXN", date(2026, 1, 2), Decimal("18.00"), source="manual")
    assert get_rate("USD", "MXN", date(2026, 1, 2)) == Decimal("18.00")


def test_convert_amount(fake_fx_dir):
    amt = Amount(amount="100", currency="USD")
    converted = convert(amt, "MXN", date(2026, 1, 2))
    assert converted.currency == "MXN"
    assert converted.amount == Decimal("1710.00")


def test_convert_same_currency_quantizes():
    amt = Amount(amount="100.5", currency="MXN")
    assert convert(amt, "MXN").amount == Decimal("100.50")


def test_net_worth_in(fake_fx_dir):
    balances = {
        "Assets:Bank:Checking": [Amount(amount="1000", currency="MXN")],
        "Assets:Bank:US": [Amount(amount="100", currency="USD")],
        "Liabilities:CreditCard:Visa": [Amount(amount="200", currency="MXN")],
    }
    total = net_worth_in(balances, "MXN", date(2026, 1, 2))
    assert total.currency == "MXN"
    assert total.amount == Decimal("1000.00") + Decimal("1710.00") - Decimal("200.00")


def test_router_get_rate(client, fake_fx_dir):
    r = client.get("/api/fx/rate", params={"base": "USD", "quote": "MXN", "date": "2026-01-02"})
    assert r.status_code == 200
    assert r.json()["rate"] == "17.10"


def test_router_get_rate_404(client, fake_fx_dir):
    r = client.get("/api/fx/rate", params={"base": "EUR", "quote": "JPY", "date": "2026-01-02"})
    assert r.status_code == 404


def test_router_post_rate(client, fake_fx_dir):
    r = client.post("/api/fx/rate", json={"base": "EUR", "quote": "MXN", "date": "2026-01-02", "rate": "19.5"})
    assert r.status_code == 200
    r = client.get("/api/fx/rate", params={"base": "EUR", "quote": "MXN", "date": "2026-01-02"})
    assert r.json()["rate"] == "19.5"
