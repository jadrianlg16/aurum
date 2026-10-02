"""End-to-end insights checks against the demo-mx fixture."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aurum.demo.generate import WS_ID, build_demo
from aurum.insights.engine import build_insights


@pytest.fixture
def demo() -> dict:
    """demo-mx with the tax module switched on — every tax nudge is gated behind it."""
    manifest = build_demo()
    from aurum.core.workspaces import get_workspace, save_workspace

    ws = get_workspace(WS_ID)
    ws.modules.tax = True
    save_workspace(ws)
    return manifest


def test_month_close_diffs_surface_as_insights(demo):
    insights = build_insights(WS_ID, "2026-08")
    by_kind = {i.kind: i for i in insights}
    assert "pue_not_collected" in by_kind
    assert Decimal(by_kind["pue_not_collected"].amount.amount) == Decimal("13920.00")
    assert by_kind["pue_not_collected"].severity == "warn"

    assert "deposit_without_cfdi" in by_kind
    assert Decimal(by_kind["deposit_without_cfdi"].amount.amount) == Decimal("6500.00")

    assert "cash_paid_expense" in by_kind
    assert Decimal(by_kind["cash_paid_expense"].amount.amount) == Decimal("160.00")

    assert "fixed_asset_iva" in by_kind
    assert Decimal(by_kind["fixed_asset_iva"].amount.amount) == Decimal("3200.00")

    assert "ppd_missing_rep" in by_kind
    assert Decimal(by_kind["ppd_missing_rep"].amount.amount) == Decimal("9280.00")


def test_you_may_owe_insight_matches_month_close_figures(demo):
    insights = build_insights(WS_ID, "2026-08")
    owe = next(i for i in insights if i.kind == "you_may_owe")
    # August: isr 407.00 + iva payable 5120.00 (docs/demo-manifest.json EXPECTED_FIGURES)
    assert Decimal(owe.amount.amount) == Decimal("407.00") + Decimal("5120.00")
    assert owe.due_date == "2026-09-17"


def test_every_insight_carries_an_explain(demo):
    insights = build_insights(WS_ID, "2026-08")
    assert insights, "expected at least one insight for the demo workspace"
    for i in insights:
        assert i.explain.summary
        assert i.ws_id == WS_ID
        assert i.severity in ("info", "warn", "urgent")


def test_insights_are_sorted_urgent_first(demo):
    insights = build_insights(WS_ID, "2026-08")
    order = {"urgent": 0, "warn": 1, "info": 2}
    values = [order[i.severity] for i in insights]
    assert values == sorted(values)


def test_budget_alerts_use_pf_budget_status(demo):
    from datetime import date

    from aurum.core.money import Amount
    from aurum.ledger.base import Posting, Transaction, get_ledger
    from aurum.pf import budgets

    # The demo's "Súper" budget (Expenses:Food:Groceries) has no spend yet -- post one, then drop the
    # budget amount below it so the 100% alert fires.
    get_ledger().append(
        WS_ID,
        Transaction(
            date=date(2026, 8, 20), payee="Super", narration="Super",
            postings=[
                Posting(account="Expenses:Food:Groceries", amount=Amount(amount="7000")),
                Posting(account="Assets:Bank:BBVA"),
            ],
        ),
    )
    seeded = next(b for b in budgets.list_budgets(WS_ID, "2026-08") if b["amount"] == "6000")
    budgets.update_budget(
        WS_ID, seeded["id"],
        budgets.Budget(label_id=seeded["label_id"], period="2026-08", amount="6000", currency="MXN", rollover=False),
    )
    insights = build_insights(WS_ID, "2026-08")
    alert = next(i for i in insights if i.kind == "budget_alert")
    assert alert.severity == "urgent"
    # budget_status already reports pct as a percent; the sentence must show it unscaled.
    from decimal import Decimal

    from aurum.core.money import q2

    row = next(r for r in budgets.budget_status(WS_ID, "2026-08")["budgets"] if r["budget_id"] == seeded["id"])
    assert f"({q2(Decimal(str(row['pct'])))}%)" in alert.body


def test_lang_override_changes_body_text(demo):
    es = build_insights(WS_ID, "2026-08", lang="es")
    en = build_insights(WS_ID, "2026-08", lang="en")
    es_owe = next(i for i in es if i.kind == "you_may_owe")
    en_owe = next(i for i in en if i.kind == "you_may_owe")
    assert es_owe.body != en_owe.body


def test_unknown_workspace_returns_empty_list():
    assert build_insights("does-not-exist", "2026-08") == []
