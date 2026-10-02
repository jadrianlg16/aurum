from __future__ import annotations

from datetime import date

from aurum.pf import accounts
from tests.pf.helpers import post


def test_get_accounts_groups_and_net_worth(ledger):
    post(ledger, "ws", date(2026, 1, 5), "Tacos", "Expenses:Food:DiningOut", "250",
         asset_account="Assets:Bank:Checking")
    out = accounts.get_accounts("ws")
    assert "bank" in out["groups"]
    assert out["net_worth"]["amount"] == "-250.00"
    assert out["net_worth"]["currency"] == "MXN"
    assert len(out["net_worth_series"]) == 12
    assert "explain" in out


def test_detect_recurring_needs_stable_cadence_and_amount(ledger):
    for m in (1, 2, 3):
        post(ledger, "ws", date(2026, m, 5), "Netflix", "Expenses:Personal:Entertainment", "199",
             asset_account="Assets:Bank:Checking")
    bills = accounts.detect_recurring("ws", today=date(2026, 4, 1))
    assert any(b["payee"] == "Netflix" for b in bills)
    netflix = next(b for b in bills if b["payee"] == "Netflix")
    assert netflix["amount"]["amount"] == "199.00"
    assert netflix["next_expected_date"] >= "2026-04-01"


def test_router_accounts_endpoint(client):
    r = client.get("/api/pf/ws/accounts")
    assert r.status_code == 200
    assert "net_worth" in r.json()
