"""Envelope plan: auto-plan writes pf_budgets, groups add up."""

from __future__ import annotations

from decimal import Decimal

from aurum.organizer import detect, plan

from .conftest import TODAY, WS

PERIOD = "2026-09"


def _accept_all() -> None:
    for candidate in detect.detect(WS, today=TODAY):
        detect.accept(WS, candidate.id, today=TODAY)


def test_auto_plan_writes_pf_budgets(demo) -> None:
    from aurum.pf import budgets as pf_budgets

    before = {b["label_id"] for b in pf_budgets.list_budgets(WS, PERIOD)}
    result = plan.auto_plan(WS, months=3, period=PERIOD, today=TODAY)
    assert result["written"], "auto-plan wrote nothing"
    after = pf_budgets.list_budgets(WS, PERIOD)
    assert {b["label_id"] for b in after} >= before | {w["label_id"] for w in result["written"]}
    # every written amount is the 3-month average of that label's account, floored at commitments
    start, end = plan._period_bounds(PERIOD)
    from dateutil.relativedelta import relativedelta

    spent = plan.spent_by_account(WS, start - relativedelta(months=3), start - relativedelta(days=1))
    for row in result["written"]:
        label = next(lbl for lbl in plan._labels(WS) if lbl["id"] == row["label_id"])
        expected = (spent[label["account"]] / Decimal("3")).quantize(Decimal("0.01"))
        assert Decimal(row["average"]["amount"]) == expected
        assert Decimal(row["planned"]["amount"]) >= expected


def test_auto_plan_is_idempotent(demo) -> None:
    first = plan.auto_plan(WS, months=3, period=PERIOD, today=TODAY)
    second = plan.auto_plan(WS, months=3, period=PERIOD, today=TODAY)
    assert {w["label_id"]: w["planned"]["amount"] for w in first["written"]} == \
           {w["label_id"]: w["planned"]["amount"] for w in second["written"]}

    from aurum.pf import budgets as pf_budgets

    label_ids = [b["label_id"] for b in pf_budgets.list_budgets(WS, PERIOD)]
    assert len(label_ids) == len(set(label_ids)), "auto-plan duplicated a budget row"


def test_plan_groups_and_totals(demo) -> None:
    _accept_all()
    plan.auto_plan(WS, months=3, period=PERIOD, today=TODAY)
    payload = plan.build_plan(WS, PERIOD, today=TODAY)
    assert [g["group"] for g in payload["groups"]] == ["needs", "wants", "savings", "debt"]
    for group in payload["groups"]:
        planned = sum((Decimal(i["planned"]["amount"]) for i in group["items"]), Decimal("0"))
        actual = sum((Decimal(i["actual"]["amount"]) for i in group["items"]), Decimal("0"))
        assert Decimal(group["planned"]["amount"]) == planned
        assert Decimal(group["actual"]["amount"]) == actual
        assert Decimal(group["left"]["amount"]) == planned - actual


def test_commitment_essential_decides_its_group(demo) -> None:
    _accept_all()
    payload = plan.build_plan(WS, PERIOD, today=TODAY)
    by_name = {i["name"]: g["group"] for g in payload["groups"] for i in g["items"]}
    assert by_name.get("Renta") == "needs"
    assert by_name.get("Netflix") == "wants"
    loan_items = [i["name"] for g in payload["groups"] if g["group"] == "debt" for i in g["items"]]
    assert loan_items, "the pf loan commitment must land in the debt envelope"


def test_savings_rate_and_income(demo) -> None:
    _accept_all()
    payload = plan.build_plan(WS, PERIOD, today=TODAY)
    income = Decimal(payload["income_actual"]["amount"])
    spent = sum((Decimal(g["actual"]["amount"]) for g in payload["groups"]), Decimal("0"))
    expected = ((income - spent) / income).quantize(Decimal("0.0001")) if income else Decimal("0")
    assert Decimal(payload["savings_rate"]) == expected
    assert Decimal(payload["income_expected"]["amount"]) > 0


def test_put_plan_updates_the_budget(demo) -> None:
    from aurum.pf import budgets as pf_budgets

    plan.auto_plan(WS, months=3, period=PERIOD, today=TODAY)
    row = pf_budgets.list_budgets(WS, PERIOD)[0]
    plan.put_plan(WS, [{"label_id": row["label_id"], "planned": "1234.50"}], PERIOD)
    updated = next(b for b in pf_budgets.list_budgets(WS, PERIOD) if b["label_id"] == row["label_id"])
    assert Decimal(updated["amount"]) == Decimal("1234.50")


def test_group_for_account_map() -> None:
    assert plan.group_for_account("Expenses:Housing:RentMortgage") == "needs"
    assert plan.group_for_account("Expenses:Personal:Entertainment") == "wants"
    assert plan.group_for_account("Assets:Investments:General") == "savings"
    assert plan.group_for_account("Liabilities:Loans:Auto") == "debt"


def test_router_plan_endpoints(client) -> None:
    assert client.post("/api/organizer/demo-mx/plan/auto", json={"months": 3}).status_code == 200
    payload = client.get("/api/organizer/demo-mx/plan").json()
    assert {g["group"] for g in payload["groups"]} == {"needs", "wants", "savings", "debt"}
    assert "uncategorized" in payload
    assert payload["explain"]["summary"]
