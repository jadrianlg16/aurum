from __future__ import annotations

from datetime import date
from decimal import Decimal

from aurum.core.money import Amount
from aurum.holdings import limits as limits_mod
from aurum.holdings import prices as prices_mod
from aurum.holdings import symbols as symbols_mod
from aurum.holdings import trades as trades_mod


def test_symbol_seed_has_examples():
    rows = symbols_mod.list_symbols("ws1")
    syms = {r["symbol"] for r in rows}
    assert {"CETES", "VOO", "VTI", "BTC"} <= syms


def test_record_buy_writes_ledger_and_row(ledger):
    trade = trades_mod.record_trade(
        "ws1",
        when=date(2026, 1, 5),
        account="Assets:Investments:Brokerage:VOO",
        symbol="voo",
        units=Decimal("10"),
        price=Amount(amount="380.00", currency="USD"),
        fees=Amount(amount="1.00", currency="USD"),
        kind="buy",
    )
    assert trade["symbol"] == "VOO"
    assert trade["txn_id"] is not None
    journal = ledger.journal("ws1")
    assert len(journal) == 1
    accounts = {p.account for p in journal[0].postings}
    assert "Assets:Investments:Brokerage:VOO" in accounts
    assert "Assets:Bank:Brokerage" in accounts


def test_fifo_realized_gain_on_partial_sell(ledger):
    trades_mod.record_trade(
        "ws2", when=date(2026, 1, 1), account="Assets:Investments:VOO", symbol="VOO",
        units=Decimal("10"), price=Amount(amount="100", currency="USD"), fees=None, kind="buy",
    )
    trades_mod.record_trade(
        "ws2", when=date(2026, 2, 1), account="Assets:Investments:VOO", symbol="VOO",
        units=Decimal("10"), price=Amount(amount="120", currency="USD"), fees=None, kind="buy",
    )
    trades_mod.record_trade(
        "ws2", when=date(2026, 3, 1), account="Assets:Investments:VOO", symbol="VOO",
        units=Decimal("15"), price=Amount(amount="150", currency="USD"), fees=None, kind="sell",
    )
    result = trades_mod.positions("ws2")
    realized = result["realized_gains"]
    # FIFO: first 10 units from the $100 lot, next 5 from the $120 lot
    assert len(realized) == 2
    assert realized[0]["cost"] == "1000.00"
    assert realized[0]["gain"] == "500.00"
    assert realized[1]["units"] == "5"
    assert realized[1]["cost"] == "600.00"
    assert realized[1]["gain"] == "150.00"
    pos = {p["symbol"]: p for p in result["positions"]}
    assert pos["VOO"]["units"] == "5"


def test_positions_market_value_and_allocation(ledger):
    trades_mod.record_trade(
        "ws3", when=date(2026, 1, 1), account="Assets:Investments:VOO", symbol="VOO",
        units=Decimal("10"), price=Amount(amount="100", currency="USD"), fees=None, kind="buy",
    )
    prices_mod.record_price("ws3", "VOO", date(2026, 6, 1), Amount(amount="150", currency="USD"))
    result = trades_mod.positions("ws3")
    pos = result["positions"][0]
    assert pos["market_value"]["amount"] == "1500.00"
    assert pos["unrealized_gain"]["amount"] == "500.00"
    assert result["allocation"]["by_asset_class"]["equity"] == "100.00"


def test_dividend_and_interest_trades(ledger):
    trades_mod.record_trade(
        "ws4", when=date(2026, 1, 1), account="Assets:Investments:VOO", symbol="VOO",
        units=Decimal("0"), price=None, fees=None, kind="dividend",
        cash=Amount(amount="12.50", currency="USD"),
    )
    journal = ledger.journal("ws4")
    assert len(journal) == 1
    assert journal[0].meta["kind"] == "dividend"


def test_contribution_vs_limits(ledger):
    trades_mod.record_trade(
        "ws5", when=date(2026, 3, 1), account="Assets:Investments:401k", symbol="CASH",
        units=Decimal("0"), price=None, fees=None, kind="contribution",
        cash=Amount(amount="5000", currency="USD"), limit_key="401k",
    )
    result = trades_mod.contributions_vs_limits("ws5", 2026)
    by_key = {r["key"]: r for r in result["limits"]}
    assert by_key["401k"]["contributed"]["amount"] == "5000.00"
    assert Decimal(by_key["401k"]["remaining"]["amount"]) == Decimal(by_key["401k"]["limit"]["amount"]) - Decimal("5000")
    assert by_key["401k"]["verified"] is False


def test_limits_seeded():
    rows = limits_mod.list_limits("ws6", 2026)
    keys = {r["key"] for r in rows}
    assert {"401k", "ira", "hsa_self", "hsa_family", "ppr"} <= keys


def test_tax_explain_jurisdictions():
    mx = trades_mod.tax_explain("MX")
    us = trades_mod.tax_explain("US")
    assert any("LISR" in c.law for c in mx.citations)
    assert any("IRC" in c.law for c in us.citations)


def test_invalid_kind_rejected(ledger):
    import pytest

    with pytest.raises(ValueError):
        trades_mod.record_trade(
            "ws7", when=date(2026, 1, 1), account="A", symbol="X", units=Decimal("1"),
            price=None, fees=None, kind="bogus",
        )


def test_router_full_flow(client):
    r = client.post(
        "/api/holdings/wsx/trades",
        json={
            "date": "2026-01-05", "account": "Assets:Investments:VOO", "symbol": "VOO",
            "kind": "buy", "units": "5", "price": {"amount": "380.00", "currency": "USD"},
        },
    )
    assert r.status_code == 200
    r = client.post(
        "/api/holdings/wsx/prices",
        json={"symbol": "VOO", "date": "2026-06-01", "price": {"amount": "400.00", "currency": "USD"}},
    )
    assert r.status_code == 200
    r = client.get("/api/holdings/wsx")
    assert r.status_code == 200
    body = r.json()
    assert body["positions"][0]["symbol"] == "VOO"
    assert body["positions"][0]["market_value"]["amount"] == "2000.00"
    assert "tax_explain" in body
    assert "contributions" in body

    r = client.post("/api/holdings/wsx/prices/fetch", json={"symbols": ["VOO"]})
    assert r.status_code == 200
    assert "warnings" in r.json()

    r = client.get("/api/holdings/wsx/limits")
    assert r.status_code == 200
    assert len(r.json()) >= 1
