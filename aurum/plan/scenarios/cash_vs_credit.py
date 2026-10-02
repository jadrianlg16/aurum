"""Cash vs. financed purchase, reusing ``aurum/pf/finance.py`` amortization."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from ...core.explain import Explain
from ...core.i18n import t
from ...pf.finance import build_amortization


class Inputs(BaseModel):
    price: str = "300000.00"
    cash_discount_pct: str = "0.05"  # paying cash often gets a discount
    annual_rate: str = "0.18"
    months: int = 24
    opportunity_cost_annual: str = "0.08"  # what the cash could otherwise earn
    currency: str = "MXN"


def run(inputs: Inputs, lang: str = "es") -> dict:
    price = Decimal(inputs.price)
    cash_price = (price * (1 - Decimal(inputs.cash_discount_pct))).quantize(Decimal("0.01"))
    amort = build_amortization(price, Decimal(inputs.annual_rate), inputs.months)

    monthly_opp = Decimal(inputs.opportunity_cost_annual) / 12
    cash_opportunity_lost = Decimal("0")
    balance = cash_price
    for _ in range(inputs.months):
        cash_opportunity_lost += balance * monthly_opp
        balance += balance * monthly_opp  # what the cash would have grown to, foregone
    cash_total_cost = (cash_price + cash_opportunity_lost).quantize(Decimal("0.01"))
    credit_total_cost = amort.total_paid.quantize(Decimal("0.01"))

    cheaper_key = "cash" if cash_total_cost < credit_total_cost else "credit"
    cheaper = t(f"plan.cash_vs_credit.cheaper.{cheaper_key}", lang)
    explain = Explain(
        summary=t(
            "plan.cash_vs_credit.summary",
            lang,
            cash_price=cash_price,
            cash_total=cash_total_cost,
            credit_total=credit_total_cost,
            currency=inputs.currency,
            cheaper=cheaper,
        ),
    )
    explain.add_step(t("plan.cash_vs_credit.step.list_price", lang), price)
    explain.add_step(t("plan.cash_vs_credit.step.cash_price", lang), cash_price)
    explain.add_step(t("plan.cash_vs_credit.step.opportunity_cost", lang), cash_opportunity_lost.quantize(Decimal("0.01")))
    explain.add_step(t("plan.cash_vs_credit.step.cash_total", lang), cash_total_cost)
    explain.add_step(t("plan.cash_vs_credit.step.monthly_payment", lang), amort.payment)
    explain.add_step(t("plan.cash_vs_credit.step.total_interest", lang), amort.total_interest.quantize(Decimal("0.01")))
    explain.add_step(t("plan.cash_vs_credit.step.credit_total", lang), credit_total_cost)

    return {
        "inputs": inputs.model_dump(),
        "results": {
            "cash_total_cost": str(cash_total_cost),
            "credit_total_cost": str(credit_total_cost),
            "cheaper": cheaper_key,
            "monthly_payment": str(amort.payment),
            "total_interest": str(amort.total_interest.quantize(Decimal("0.01"))),
        },
        "explain": explain.model_dump(),
    }


SCHEMA = Inputs.model_json_schema()
METRIC_PATH: tuple = ("results", "cash_total_cost")  # dot-path into results, for the /sensitivity endpoint's scalar metric

__all__ = ["Inputs", "SCHEMA", "run"]
