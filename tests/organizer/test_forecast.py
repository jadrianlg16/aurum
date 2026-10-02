"""Forecast + safe-to-spend, asserted against Decimals derived from the seeded demo."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from aurum.organizer import commitments as cmt
from aurum.organizer import detect, forecast

from .conftest import TODAY, WS


def _accept_all() -> None:
    for candidate in detect.detect(WS, today=TODAY):
        if candidate.evidence:
            detect.accept(WS, candidate.id, today=TODAY)


def test_start_balance_is_the_liquid_ledger_balance(demo) -> None:
    from aurum.ledger.base import get_ledger

    expected = sum(
        (a.amount
         for account, amounts in get_ledger().balances(WS).items()
         if account.startswith(("Assets:Bank", "Assets:Cash"))
         for a in amounts),
        Decimal("0"),
    )
    payload = forecast.forecast(WS, days=90, today=TODAY)
    assert Decimal(payload["start_balance"]["amount"]) == expected
    assert expected == Decimal("261698.19")  # demo opening 55,000 + three months of demo movements


def test_safe_to_spend_components_are_exact(demo) -> None:
    _accept_all()
    result = forecast.safe_to_spend(WS, TODAY)
    steps = {s["label"]: s["value"] for s in result["explain"]["steps"]}

    # Next income after TODAY (2026-09-15) is Cliente Delta on the 20th.
    assert result["until"] == "2026-09-20"
    # Commitments falling in [2026-09-15, 2026-09-20] that are neither paid nor skipped:
    #   09-15 crédito auto 4,918.77 (the pf amortization payment, since the bank charge and the pf
    #   loan share one merchant key) + 09-20 CFE 1,120.00 + 09-20 iCloud 49.00 + 09-20 Max 249.00
    committed = Decimal("4918.77") + Decimal("1120.00") + Decimal("49.00") + Decimal("249.00")
    assert committed == Decimal("6336.77")
    assert Decimal(steps["committed_until"]) == committed

    liquid = Decimal(steps["liquid_balance"])
    buffer_value = Decimal(steps["buffer"])
    monthly = forecast.monthly_committed(cmt.list_commitments(WS))
    assert buffer_value == (monthly * Decimal("0.10")).quantize(Decimal("0.01"))

    # No budgets exist before auto-plan, so budgets_remaining is 0 and the pinned figure holds.
    assert Decimal(steps["budgeted_remaining"]) == Decimal("0")
    assert result["parts"]["fixed_pending"]["amount"] == "6336.77"
    assert result["currency"] == "MXN"
    assert [s["label"] for s in result["explain"]["steps"]] == [
        "liquid_balance", "until", "committed_until", "budgeted_remaining", "buffer", "safe_to_spend",
    ]
    assert Decimal(result["amount"]["amount"]) == liquid - committed - buffer_value
    assert Decimal(result["amount"]["amount"]) == Decimal("252925.42")


def test_explicit_buffer_overrides_the_default(demo) -> None:
    _accept_all()
    default_amount = Decimal(forecast.safe_to_spend(WS, TODAY)["amount"]["amount"])
    default_buffer, _ = forecast.effective_buffer(WS, cmt.list_commitments(WS))
    forecast.set_buffer(WS, Decimal("5000"))
    with_buffer = forecast.safe_to_spend(WS, TODAY)
    steps = {s["label"]: s["value"] for s in with_buffer["explain"]["steps"]}
    assert Decimal(steps["buffer"]) == Decimal("5000.00")
    # formulas are human sentences, the source is visible in ``parts``.
    from aurum.core.i18n import t as i18n_t

    formula = next(s["formula"] for s in with_buffer["explain"]["steps"] if s["label"] == "buffer")
    assert formula == i18n_t("organizer.step.buffer_explicit", "es")
    assert with_buffer["parts"]["buffer"]["amount"] == "5000.00"
    assert Decimal(with_buffer["amount"]["amount"]) == default_amount + default_buffer - Decimal("5000")


def test_series_is_a_running_balance(demo) -> None:
    _accept_all()
    payload = forecast.forecast(WS, days=90, today=TODAY)
    series = payload["series"]
    assert len(series) == 91
    assert series[0]["date"] == TODAY.isoformat()
    assert series[-1]["date"] == (TODAY + timedelta(days=90)).isoformat()
    balance = Decimal(payload["start_balance"]["amount"])
    for row in series:
        balance = balance + Decimal(row["in"]["amount"]) - Decimal(row["out"]["amount"])
        assert Decimal(row["balance"]["amount"]) == balance


def test_low_point_is_the_minimum_of_the_series(demo) -> None:
    _accept_all()
    payload = forecast.forecast(WS, days=90, today=TODAY)
    balances = [(Decimal(r["balance"]["amount"]), r["date"]) for r in payload["series"]]
    lowest = min(balances)
    assert Decimal(payload["low_point"]["balance"]["amount"]) == lowest[0]
    assert payload["low_point"]["date"] == lowest[1]


def test_forecast_carries_safe_to_spend_and_explain(demo) -> None:
    _accept_all()
    payload = forecast.forecast(WS, days=30, today=TODAY)
    assert payload["safe_to_spend"]["amount"] == forecast.safe_to_spend(WS, TODAY)["amount"]
    labels = {s["label"] for s in payload["explain"]["steps"]}
    assert {"start_balance", "horizon_days", "commitments_projected", "low_point"} <= labels


def test_monthly_equivalents_normalize_every_cadence(demo) -> None:
    _accept_all()
    by_name = {c.name: c for c in cmt.list_commitments(WS)}
    prime = by_name["Amazon Prime"]
    assert prime.cadence == "annual"
    assert cmt.monthly_equivalent(prime) == Decimal("74.92")     # 899 / 12
    assert cmt.annual_equivalent(prime) == Decimal("899.00")
    cfe = by_name["Cfe"]
    assert cfe.cadence == "bimonthly"
    assert cmt.monthly_equivalent(cfe) == Decimal("560.00")      # 1,120 × 6 / 12


def test_router_forecast_and_buffer(client) -> None:
    assert client.get("/api/organizer/demo-mx/forecast?days=30").status_code == 200
    assert client.get("/api/organizer/demo-mx/forecast?days=400").status_code == 200
    assert client.get("/api/organizer/demo-mx/forecast?days=401").status_code == 422
    r = client.put("/api/organizer/demo-mx/forecast/buffer", json={"buffer": "1500"})
    assert r.status_code == 200
    assert r.json()["buffer"]["amount"] == "1500.00"
    assert r.json()["buffer"]["currency"] == "MXN"
    assert r.json()["source"] == "organizer_settings.buffer"
    assert client.put("/api/organizer/demo-mx/forecast/buffer",
                      json={"buffer": "not-a-number"}).status_code == 400
