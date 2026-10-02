"""Compose the US annual payload from the ledger and the ``us.*`` rules.

Nothing here computes a tax figure — every number comes out of :mod:`aurum.rules.us` with its explain
attached. This module reads the ledger, reads the workspace profile, calls the rules in order (Schedule
C → SE tax → income tax → estimates) and assembles the response payload.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..core.i18n import ws_lang
from ..core.money import Amount, q2
from ..core.workspaces import Workspace, WorkspaceNotFound, get_workspace
from ..ledger.base import LedgerStore, get_ledger
from ..rules.registry import load_rules, registry
from ..rules.us import constants_2026 as K
from ..rules.us.federal import dec, normalize_status
from . import inputs as ledger_inputs

CURRENCY = "USD"
DISCLAIMER = (
    "This is an organizer, not a tax return. Aurum never files, signs or transmits anything to the IRS "
    "or the Texas Comptroller. Every figure is an estimate from your ledger — take it to a licensed "
    "preparer."
)


def us_profile(ws: Workspace) -> dict[str, Any]:
    """Workspace profile fields the US rules read, with defaults."""
    profile = dict(ws.profile or {})
    us = dict(profile.get("us") or {})
    merged = {**profile, **us}
    return {
        "filing_status": normalize_status(merged.get("filing_status")),
        "entity_type": str(merged.get("entity_type") or "sole_proprietorship"),
        "business_type": str(merged.get("business_type") or "other"),
        "state": str(merged.get("state") or ""),
        "wages": dec(merged.get("wages")),
        "other_income": dec(merged.get("other_income")),
        "itemized_deductions": None if merged.get("itemized_deductions") is None else dec(merged["itemized_deductions"]),
        "prior_year_tax": None if merged.get("prior_year_tax") is None else dec(merged["prior_year_tax"]),
        "prior_year_agi": None if merged.get("prior_year_agi") is None else dec(merged["prior_year_agi"]),
        "withholding": dec(merged.get("withholding")),
        "local_sales_tax_rate": merged.get("local_sales_tax_rate"),
    }


def _amount(value: Decimal) -> dict[str, str]:
    return Amount(amount=q2(value), currency=CURRENCY).model_dump(mode="json")


def not_applicable(ws_id: str, year: int, reason: str) -> dict[str, Any]:
    return {
        "workspace": ws_id,
        "year": year,
        "applicable": False,
        "reason": reason,
        "currency": CURRENCY,
        "disclaimer": DISCLAIMER,
        "warnings": [reason],
    }


def annual(ws_id: str, year: int, ledger: LedgerStore | None = None, lang: str | None = None) -> dict[str, Any]:
    """``GET /api/tax/us/{ws}/{year}`` — Schedule C, SE tax, income tax and the quarterly estimate."""
    load_rules()
    try:
        ws = get_workspace(ws_id)
    except WorkspaceNotFound:
        return not_applicable(ws_id, year, f"workspace {ws_id} does not exist")
    if "US" not in ws.jurisdictions:
        return not_applicable(
            ws_id,
            year,
            f"no US profile: workspace {ws_id} declares jurisdictions {ws.jurisdictions}. "
            "Add 'US' to the workspace to see US figures.",
        )

    resolved_lang = ws_lang(ws_id, lang)
    store = ledger or get_ledger()
    collected = ledger_inputs.collect(store, ws, year, currency=CURRENCY)
    profile = us_profile(ws)
    warnings = list(collected.warnings)

    sched = registry.get("us.fed.schedule_c_net").compute(
        gross_receipts=collected.gross_receipts,
        returns_and_allowances=collected.returns_and_allowances,
        cost_of_goods_sold=collected.cost_of_goods_sold,
        expenses={
            label: collected.expenses[account]
            for account, label in ledger_inputs.expense_labels(collected).items()
        },
        currency=CURRENCY,
        lang=resolved_lang,
    )
    net = sched.value.amount

    se = registry.get("us.fed.se_tax").compute(
        net_profit=net,
        filing_status=profile["filing_status"],
        wages=profile["wages"],
        currency=CURRENCY,
        lang=resolved_lang,
    )
    deductible_half = _se_deductible_half(net, profile)

    tax = registry.get("us.fed.income_tax").compute(
        filing_status=profile["filing_status"],
        schedule_c_net=net,
        other_income=profile["other_income"],
        se_tax_deduction=deductible_half,
        itemized_deductions=profile["itemized_deductions"],
        currency=CURRENCY,
        lang=resolved_lang,
    )

    total_tax = q2(tax.value.amount + se.value.amount)
    quarterly = registry.get("us.fed.quarterly_estimate").compute(
        current_year_tax=total_tax,
        filing_status=profile["filing_status"],
        prior_year_tax=profile["prior_year_tax"],
        prior_year_agi=profile["prior_year_agi"],
        withholding=profile["withholding"],
        currency=CURRENCY,
        lang=resolved_lang,
    )

    if profile["prior_year_tax"] is None:
        warnings.append(
            "no prior-year tax on the workspace profile — the estimate uses only the 90%-of-this-year leg; "
            "add `prior_year_tax` and `prior_year_agi` for the safe harbour"
        )
    unverified = [c.key for c in K.unverified()]

    return {
        "workspace": ws_id,
        "year": year,
        "applicable": True,
        "currency": CURRENCY,
        "profile": {
            "filing_status": profile["filing_status"],
            "entity_type": profile["entity_type"],
            "business_type": profile["business_type"],
            "state": profile["state"],
        },
        "schedule_c": {
            "gross_receipts": _amount(collected.gross_receipts),
            "returns_and_allowances": _amount(collected.returns_and_allowances),
            "cost_of_goods_sold": _amount(collected.cost_of_goods_sold),
            "expenses": _amount(collected.expenses_total),
            "expenses_by_account": {a: _amount(v) for a, v in collected.expenses.items()},
            "income_by_account": {a: _amount(v) for a, v in collected.income_by_account.items()},
            "transactions": collected.transactions,
            "net": sched.value.model_dump(mode="json"),
            "explain": sched.explain.model_dump(mode="json"),
        },
        "se_tax": {
            "value": se.value.model_dump(mode="json"),
            "deductible_half": _amount(deductible_half),
            "explain": se.explain.model_dump(mode="json"),
        },
        "income_tax": {
            "value": tax.value.model_dump(mode="json"),
            "explain": tax.explain.model_dump(mode="json"),
        },
        "total_tax": _amount(total_tax),
        "quarterly": {
            "due_dates": [d.isoformat() for d in K.ESTIMATE_DUE_DATES.value],
            "amount_each": quarterly.value.model_dump(mode="json"),
            "explain": quarterly.explain.model_dump(mode="json"),
        },
        "organizer_url": f"/api/tax/us/{ws_id}/{year}/organizer.pdf",
        "tx_franchise_url": f"/api/tax/us/{ws_id}/{year}/tx-franchise",
        "unverified_constants": unverified,
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
        "status": "draft",
    }


def _se_deductible_half(net_profit: Decimal, profile: dict[str, Any]) -> Decimal:
    from ..rules.us.federal import self_employment_tax

    return self_employment_tax(net_profit, profile["filing_status"], profile["wages"]).deductible_half


def tx_franchise(ws_id: str, year: int, ledger: LedgerStore | None = None, lang: str | None = None) -> dict[str, Any]:
    """``GET /api/tax/us/{ws}/{year}/tx-franchise`` — no-tax-due check on the year's revenue."""
    load_rules()
    try:
        ws = get_workspace(ws_id)
    except WorkspaceNotFound:
        return not_applicable(ws_id, year, f"workspace {ws_id} does not exist")
    if "US" not in ws.jurisdictions:
        return not_applicable(ws_id, year, f"no US profile: workspace {ws_id} is {ws.jurisdictions}-only")

    resolved_lang = ws_lang(ws_id, lang)
    profile = us_profile(ws)
    collected = ledger_inputs.collect(ledger or get_ledger(), ws, year, currency=CURRENCY)
    result = registry.get("us.tx.franchise_no_tax_due").compute(
        total_revenue=collected.gross_receipts,
        entity_type=profile["entity_type"],
        business_type=profile["business_type"],
        cost_of_goods_sold=collected.cost_of_goods_sold,
        currency=CURRENCY,
        lang=resolved_lang,
    )
    warnings = list(collected.warnings)
    if profile["state"].upper() not in {"TX", ""}:
        warnings.append(
            f"the workspace state is {profile['state']}, not TX — the Texas franchise tax may not apply at all"
        )
    return {
        "workspace": ws_id,
        "year": year,
        "applicable": True,
        "currency": CURRENCY,
        "entity_type": profile["entity_type"],
        "business_type": profile["business_type"],
        "total_revenue": _amount(collected.gross_receipts),
        "no_tax_due_threshold": _amount(K.TX_NO_TAX_DUE_THRESHOLD.value),
        "no_tax_due": result.value.amount == 0,
        "tax": result.value.model_dump(mode="json"),
        "explain": result.explain.model_dump(mode="json"),
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
    }
