"""Plan: commitments fold into the budget row they hit; savings_rate from live expenses."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from aurum.organizer import detect, pf_bridge, plan

from .conftest import TODAY, WS

PERIOD = "2026-09"


def _accept(merchant: str):
    for candidate in detect.detect(WS, today=TODAY):
        if candidate.merchant == merchant:
            return detect.accept(WS, candidate.id, today=TODAY)
    raise AssertionError(f"{merchant} not detected")


def _rent_label() -> dict:
    from aurum.pf import labels as pf_labels

    for lbl in pf_labels.list_labels(WS):
        if lbl["account"] == "Expenses:Housing:RentMortgage":
            return lbl
    return pf_labels.create_label(WS, pf_labels.Label(name="Renta", account="Expenses:Housing:RentMortgage"))


def test_budgeted_rent_counts_once_and_nests_the_commitment(demo) -> None:
    from aurum.pf import budgets as pf_budgets

    label = _rent_label()
    pf_budgets.create_budget(WS, pf_budgets.Budget(label_id=label["id"], period=PERIOD, amount="10500"))
    rent = _accept("RENTA")
    netflix = _accept("NETFLIX")  # unbudgeted: keeps its own row

    payload = plan.build_plan(WS, PERIOD, today=TODAY)
    needs = next(g for g in payload["groups"] if g["group"] == "needs")
    assert needs["actual"]["amount"] == "10500.00"  # the 09-01 rent charge, counted once
    rows = [i for i in needs["items"] if i["label_id"] == label["id"]]
    assert len(rows) == 1
    row = rows[0]
    assert row["commitment_id"] is None and row["actual"]["amount"] == "10500.00"
    assert [c["id"] for c in row["commitments"]] == [rent.id]
    assert row["commitments"][0]["planned"]["amount"] == "10500.00"
    assert not [i for g in payload["groups"] for i in g["items"] if i["commitment_id"] == rent.id]

    wants = next(g for g in payload["groups"] if g["group"] == "wants")
    netflix_row = next(i for i in wants["items"] if i["commitment_id"] == netflix.id)
    assert netflix_row["actual"]["amount"] == "219.00" and netflix_row["commitments"] == []
    for g in payload["groups"]:
        for i in g["items"]:
            assert "commitments" in i


def test_savings_rate_uses_every_live_expense(demo) -> None:
    _accept("RENTA")
    payload = plan.build_plan(WS, PERIOD, today=TODAY)
    start, end = plan._period_bounds(PERIOD)
    txns = pf_bridge.live_txns(WS, start, end)
    expenses = sum(
        (p.amount.amount for t in txns for p in t.postings
         if p.amount is not None and p.account.startswith("Expenses:") and p.amount.amount > 0),
        Decimal("0"),
    )
    income = Decimal(payload["income_actual"]["amount"])
    assert Decimal(payload["expenses_actual"]["amount"]) == expenses.quantize(Decimal("0.01"))
    assert Decimal(payload["savings_rate"]) == ((income - expenses) / income).quantize(Decimal("0.0001"))
    assert payload["currency"] == "MXN"


def test_plan_currency_follows_the_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    from aurum.core import db

    db.reset_for_tests()
    from aurum.taxus.demo_us import build_demo_us

    build_demo_us(tmp_path / "data")
    payload = plan.build_plan("demo-us", "2026-09", today=date(2026, 9, 15))
    assert payload["currency"] == "USD"
    assert payload["income_actual"]["currency"] == "USD"
    for g in payload["groups"]:
        assert g["planned"]["currency"] == "USD"
