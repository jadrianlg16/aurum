"""The one 'Disponible' (safe to spend) on a fresh workspace with exact parts."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest

from aurum.core.money import Amount
from aurum.core.workspaces import ensure_workspace
from aurum.organizer import commitments as cmt
from aurum.organizer import forecast
from aurum.organizer.models import CommitmentIn

TODAY = date(2026, 9, 15)
WS = "sts-ws"
STEP_IDS = ["liquid_balance", "until", "committed_until", "budgeted_remaining", "buffer", "safe_to_spend"]


@pytest.fixture()
def fresh(monkeypatch):
    """10,000 in checking after a 500 spend, rent 3,000 in 5 days, income 8,000 in 10 days, a 2,000
    budget with 500 spent, buffer 0 → 10,000 − 3,000 − 1,500 − 0 = 5,500."""
    monkeypatch.setenv("AURUM_TEST_CLOCK", "1")
    from aurum.pf import accounts_admin
    from aurum.pf import budgets as pf_budgets
    from aurum.pf import entries as pf_entries
    from aurum.pf import labels as pf_labels

    ensure_workspace(WS, name="Safe to spend", base_currency="MXN", language="es")
    acct = accounts_admin.create_account(
        WS, accounts_admin.AccountIn(name="Cheques", type="checking",
                                     opening_balance=Amount(amount=Decimal("10500")),
                                     opening_date=TODAY - timedelta(days=30)),
        today=TODAY,
    )
    label = pf_labels.create_label(WS, pf_labels.Label(name="Comida fuera", account="Expenses:Food:Restaurants"))
    pf_budgets.create_budget(WS, pf_budgets.Budget(label_id=label["id"], period="2026-09", amount="2000"))
    pf_entries.create_entry(
        WS, pf_entries.EntryIn(kind="expense", date=TODAY - timedelta(days=2), amount=Amount(amount=Decimal("500")),
                               account_id=acct["id"], label_id=label["id"], payee="Tacos"),
    )
    cmt.create(WS, CommitmentIn(name="Renta", kind="rent", amount=Amount(amount=Decimal("3000")), cadence="monthly",
                                next_due=TODAY + timedelta(days=5), account_id=acct["id"]), today=TODAY)
    cmt.create(WS, CommitmentIn(name="Sueldo", kind="income", amount=Amount(amount=Decimal("8000")),
                                cadence="monthly", next_due=TODAY + timedelta(days=10), account_id=acct["id"]),
               today=TODAY)
    forecast.set_buffer(WS, Decimal("0"))
    return {"account": acct, "label": label}


def test_safe_to_spend_parts_are_exact(fresh) -> None:
    result = forecast.safe_to_spend(WS, TODAY)
    assert result["amount"] == {"amount": "5500.00", "currency": "MXN"}
    assert result["until"] == (TODAY + timedelta(days=10)).isoformat()
    assert result["currency"] == "MXN"
    assert result["parts"] == {
        "balance": {"amount": "10000.00", "currency": "MXN"},
        "fixed_pending": {"amount": "3000.00", "currency": "MXN"},
        "budgets_remaining": {"amount": "1500.00", "currency": "MXN"},
        "buffer": {"amount": "0.00", "currency": "MXN"},
    }
    steps = result["explain"]["steps"]
    assert [s["label"] for s in steps] == STEP_IDS
    for step in steps:
        formula = step["formula"] or ""
        assert "Assets:" not in formula and "Σ" not in formula and "Expenses:" not in formula, formula
        assert not re.search(r"\d{4}-\d{2}-\d{2}", formula), formula
    until = next(s for s in steps if s["label"] == "until")
    assert "25 sep 2026" in until["formula"]
    final = next(s for s in steps if s["label"] == "safe_to_spend")
    assert final["formula"] == "$10,000.00 − $3,000.00 pagos fijos − $1,500.00 presupuestos − $0.00 colchón"


def test_budget_carried_by_a_commitment_is_not_double_counted(fresh) -> None:
    """A commitment on the budgeted category means the budget's remainder is already 'fixed'."""
    fresh_label = fresh["label"]
    cmt.create(WS, CommitmentIn(name="Cena semanal", amount=Amount(amount=Decimal("400")), cadence="monthly",
                                next_due=TODAY + timedelta(days=3), label_id=fresh_label["id"],
                                account_id=fresh["account"]["id"]), today=TODAY)
    result = forecast.safe_to_spend(WS, TODAY)
    assert result["parts"]["budgets_remaining"]["amount"] == "0.00"
    assert result["parts"]["fixed_pending"]["amount"] == "3400.00"
    assert result["amount"]["amount"] == "6600.00"


def test_forecast_day_zero_carries_todays_unpaid_items(fresh) -> None:
    cmt.create(WS, CommitmentIn(name="Luz", kind="utility", amount=Amount(amount=Decimal("700")), cadence="monthly",
                                next_due=TODAY, account_id=fresh["account"]["id"]), today=TODAY)
    payload = forecast.forecast(WS, days=12, today=TODAY)
    day0 = payload["series"][0]
    assert day0["date"] == TODAY.isoformat() and day0["out"]["amount"] == "700.00"
    assert Decimal(day0["balance"]["amount"]) == Decimal("10000.00") - Decimal("700")
    rent_day = payload["series"][5]
    assert rent_day["out"]["amount"] == "3000.00"
    payday = payload["series"][10]
    assert payday["in"]["amount"] == "8000.00"
    assert payload["safe_to_spend"]["amount"]["amount"] == "4800.00"  # 5500 − 700 due today


def test_summary_and_router_return_the_same_object(fresh) -> None:
    from fastapi.testclient import TestClient

    from aurum.api.app import create_app
    from aurum.organizer import summary as summary_mod

    direct = forecast.safe_to_spend(WS, TODAY)
    body = summary_mod.summary(WS, today=TODAY)["safe_to_spend"]
    assert body == direct
    client = TestClient(create_app())
    via_http = client.get(f"/api/organizer/{WS}/summary?today={TODAY.isoformat()}").json()["safe_to_spend"]
    assert via_http["amount"] == direct["amount"] and via_http["parts"] == direct["parts"]
    fc = client.get(f"/api/organizer/{WS}/forecast?days=30&today={TODAY.isoformat()}").json()
    assert fc["safe_to_spend"]["parts"]["fixed_pending"]["amount"] == "3000.00"
    buffer = client.put(f"/api/organizer/{WS}/forecast/buffer", json={"buffer": "250"}).json()
    assert buffer["buffer"] == {"amount": "250.00", "currency": "MXN"}


def test_savings_accounts_are_not_money_to_spend(fresh) -> None:
    """A savings account sits under Assets:Bank like checking, but money set aside is not
    Disponible: opening 5,000 in 'Ahorro viaje' leaves the balance and the amount as-is."""
    from aurum.pf import accounts_admin

    accounts_admin.create_account(
        WS, accounts_admin.AccountIn(name="Ahorro viaje", type="savings",
                                     opening_balance=Amount(amount=Decimal("5000")),
                                     opening_date=TODAY - timedelta(days=30)),
        today=TODAY,
    )
    result = forecast.safe_to_spend(WS, TODAY)
    assert result["parts"]["balance"] == {"amount": "10000.00", "currency": "MXN"}
    assert result["amount"] == {"amount": "5500.00", "currency": "MXN"}
    assert forecast.liquid_balance(WS) == Decimal("10000.00")
