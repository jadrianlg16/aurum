"""RESICO vs Actividad Empresarial y Profesional over 12 months.

Both totals come from the rule registry — RESICO via ``mx.resico.isr_monthly`` (existing rule, no
deductions), the general regime via the new ``mx.general.isr_provisional`` (cumulative tarifa, allows
deductions). This module does no tax math of its own; it drives the two rules month by month over a
uniform income/expense mix and reports the annual totals side by side, plus a naive bisection for "what
deduction ratio would flip the answer" (the point at which the general regime's provisional total would
equal RESICO's).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from ...core.explain import Explain
from ...core.i18n import t
from ...rules.registry import load_rules, registry


class Inputs(BaseModel):
    monthly_income: str = Field("30000.00", description="Uniform monthly income (MXN, before IVA).")
    monthly_deductible_expenses: str = Field(
        "6000.00", description="Uniform monthly authorized deductions (only used by the general regime)."
    )
    months: int = Field(12, ge=1, le=12)
    currency: str = "MXN"


def _totals(income: Decimal, expenses: Decimal, months: int) -> tuple[Decimal, Decimal, list[dict]]:
    load_rules()
    resico = registry.get("mx.resico.isr_monthly")
    general = registry.get("mx.general.isr_provisional")
    resico_total = Decimal("0")
    general_total = Decimal("0")
    rows: list[dict] = []
    cum_income = Decimal("0")
    cum_expenses = Decimal("0")
    prior_general_payment = Decimal("0")
    for m in range(1, months + 1):
        cum_income += income
        cum_expenses += expenses
        r_result = resico.compute(collected_income=income)
        g_result = general.compute(
            cumulative_income=cum_income,
            cumulative_deductions=cum_expenses,
            month_number=m,
            prior_provisional_payments=prior_general_payment,
        )
        resico_total += r_result.value.amount
        general_total += g_result.value.amount
        prior_general_payment += g_result.value.amount
        rows.append(
            {
                "month": m,
                "resico_isr": str(r_result.value.amount),
                "general_provisional": str(g_result.value.amount),
            }
        )
    return resico_total, general_total, rows


def _deduction_ratio_breakeven(income: Decimal, months: int) -> Decimal | None:
    """Bisect the deduction ratio (0..0.95) at which the general regime's annual total ~= RESICO's."""
    load_rules()

    def general_total_at(ratio: Decimal) -> Decimal:
        expenses = (income * ratio).quantize(Decimal("0.01"))
        _, total, _ = _totals(income, expenses, months)
        return total

    resico_total, _, _ = _totals(income, Decimal("0"), months)
    lo, hi = Decimal("0"), Decimal("0.95")
    g_lo, g_hi = general_total_at(lo), general_total_at(hi)
    if g_lo <= resico_total:
        return Decimal("0.00")  # general already cheaper with no deductions
    if g_hi > resico_total:
        return None  # never flips even at 95% deductions
    for _ in range(24):
        mid = (lo + hi) / 2
        g_mid = general_total_at(mid)
        if g_mid > resico_total:
            lo = mid
        else:
            hi = mid
    return hi.quantize(Decimal("0.0001"))


def run(inputs: Inputs, lang: str = "es") -> dict:
    income = Decimal(inputs.monthly_income)
    expenses = Decimal(inputs.monthly_deductible_expenses)
    resico_total, general_total, rows = _totals(income, expenses, inputs.months)
    annual_income = income * inputs.months
    resico_rate = (resico_total / annual_income) if annual_income else Decimal("0")
    general_rate = (general_total / annual_income) if annual_income else Decimal("0")
    cheaper = "regime_mx.resico" if resico_total < general_total else "regime_mx.general"
    cheaper_label = t("plan.regime_mx.cheaper.resico", lang) if resico_total < general_total else t("plan.regime_mx.cheaper.general", lang)
    breakeven_ratio = _deduction_ratio_breakeven(income, inputs.months)

    explain = Explain(
        summary=t(
            "plan.regime_mx.summary",
            lang,
            resico=resico_total,
            general=general_total,
            currency=inputs.currency,
            cheaper=cheaper_label,
        ),
        rule_versions=["mx.resico.isr_monthly@2026.1", "mx.general.isr_provisional@2026.1"],
    )
    explain.add_step(t("plan.regime_mx.step.resico_isr", lang), resico_total)
    explain.add_step(t("plan.regime_mx.step.general_isr", lang), general_total)
    explain.add_step(t("plan.regime_mx.step.resico_rate", lang), f"{(resico_rate * 100).quantize(Decimal('0.01'))}%")
    explain.add_step(t("plan.regime_mx.step.general_rate", lang), f"{(general_rate * 100).quantize(Decimal('0.01'))}%")
    if breakeven_ratio is None:
        flip = t("plan.regime_mx.flip.never", lang)
    elif breakeven_ratio == 0:
        flip = t("plan.regime_mx.flip.always", lang)
    else:
        flip = t("plan.regime_mx.flip.ratio", lang, pct=(breakeven_ratio * 100).quantize(Decimal("0.01")))
    explain.add_step(t("plan.regime_mx.step.flip_label", lang), flip)

    return {
        "inputs": inputs.model_dump(),
        "results": {
            "resico": {"annual_isr": str(resico_total), "effective_rate": str(resico_rate)},
            "general": {"annual_isr": str(general_total), "effective_rate": str(general_rate)},
            "cheaper": cheaper,
            "deduction_ratio_breakeven": str(breakeven_ratio) if breakeven_ratio is not None else None,
            "months": rows,
        },
        "explain": explain.model_dump(),
    }


SCHEMA = Inputs.model_json_schema()
METRIC_PATH: tuple = ("results", "general", "annual_isr")  # dot-path into results, for the /sensitivity endpoint's scalar metric

__all__ = ["Inputs", "SCHEMA", "run"]
