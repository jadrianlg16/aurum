"""Standard buy-vs-rent NPV/breakeven comparison.

Reuses ``aurum/pf/finance.py`` (Decimal npv, build_amortization) — no reimplementation of amortization
or discounting math. The buy side: down payment + mortgage amortization + property tax/insurance/
maintenance − (home value appreciation, realized only at horizon, minus selling costs). The rent side:
monthly rent growing with an inflation rate, with the difference vs. the buy monthly outflow invested at
an opportunity-cost discount rate. Breakeven is the month at which cumulative buy net cost first drops
below cumulative rent net cost.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from ...core.explain import Explain
from ...core.i18n import t
from ...pf.finance import build_amortization


class Inputs(BaseModel):
    home_price: str = "3000000.00"
    down_payment_pct: str = "0.20"
    mortgage_annual_rate: str = "0.11"
    mortgage_years: int = Field(20, ge=1, le=40)
    monthly_rent: str = "18000.00"
    rent_annual_growth: str = "0.05"
    home_appreciation_annual: str = "0.04"
    property_tax_insurance_monthly: str = "1500.00"
    maintenance_monthly: str = "1000.00"
    selling_cost_pct: str = "0.06"
    discount_rate_annual: str = "0.08"
    horizon_years: int = Field(10, ge=1, le=40)
    currency: str = "MXN"


def run(inputs: Inputs, lang: str = "es") -> dict:
    price = Decimal(inputs.home_price)
    down = (price * Decimal(inputs.down_payment_pct)).quantize(Decimal("0.01"))
    principal = price - down
    months = inputs.horizon_years * 12
    mortgage_months = min(months, inputs.mortgage_years * 12)
    amort = build_amortization(principal, Decimal(inputs.mortgage_annual_rate), inputs.mortgage_years * 12)

    monthly_discount = Decimal(inputs.discount_rate_annual) / 12

    buy_cum = down
    rent_cum = Decimal("0")
    rent = Decimal(inputs.monthly_rent)
    monthly_rent_growth = (1 + Decimal(inputs.rent_annual_growth)) ** (Decimal("1") / 12) - 1
    breakeven_month: int | None = None
    for m in range(1, months + 1):
        payment = amort.rows[m - 1].payment if m <= mortgage_months else Decimal("0")
        buy_outflow = payment + Decimal(inputs.property_tax_insurance_monthly) + Decimal(inputs.maintenance_monthly)
        buy_cum += buy_outflow / (1 + monthly_discount) ** m
        rent_cum += rent / (1 + monthly_discount) ** m
        rent *= 1 + monthly_rent_growth
        if breakeven_month is None and buy_cum < rent_cum:
            breakeven_month = m

    home_value_at_horizon = price * (1 + Decimal(inputs.home_appreciation_annual)) ** Decimal(inputs.horizon_years)
    selling_costs = (home_value_at_horizon * Decimal(inputs.selling_cost_pct)).quantize(Decimal("0.01"))
    remaining_balance = amort.rows[mortgage_months - 1].balance if mortgage_months <= len(amort.rows) and mortgage_months > 0 else Decimal("0")
    net_equity_at_horizon = (home_value_at_horizon - selling_costs - remaining_balance).quantize(Decimal("0.01"))
    buy_npv_cost = (buy_cum - net_equity_at_horizon / (1 + monthly_discount) ** months).quantize(Decimal("0.01"))
    rent_npv_cost = rent_cum.quantize(Decimal("0.01"))

    cheaper_key = "buy" if buy_npv_cost < rent_npv_cost else "rent"
    cheaper = t(f"plan.buy_vs_rent.cheaper.{cheaper_key}", lang)
    explain = Explain(
        summary=t(
            "plan.buy_vs_rent.summary",
            lang,
            years=inputs.horizon_years,
            buy=buy_npv_cost,
            rent=rent_npv_cost,
            currency=inputs.currency,
            cheaper=cheaper,
        ),
    )
    explain.add_step(t("plan.buy_vs_rent.step.down_payment", lang), down)
    explain.add_step(t("plan.buy_vs_rent.step.monthly_mortgage", lang), amort.payment)
    explain.add_step(t("plan.buy_vs_rent.step.home_value_horizon", lang), home_value_at_horizon.quantize(Decimal("0.01")))
    explain.add_step(t("plan.buy_vs_rent.step.selling_costs", lang), selling_costs)
    explain.add_step(t("plan.buy_vs_rent.step.remaining_balance", lang), remaining_balance.quantize(Decimal("0.01")))
    explain.add_step(t("plan.buy_vs_rent.step.net_equity", lang), net_equity_at_horizon)
    explain.add_step(t("plan.buy_vs_rent.step.buy_npv", lang), buy_npv_cost)
    explain.add_step(t("plan.buy_vs_rent.step.rent_npv", lang), rent_npv_cost)
    explain.add_step(
        t("plan.buy_vs_rent.step.breakeven_label", lang),
        str(breakeven_month) if breakeven_month is not None else t("plan.buy_vs_rent.breakeven.none", lang),
    )

    return {
        "inputs": inputs.model_dump(),
        "results": {
            "buy_npv_cost": str(buy_npv_cost),
            "rent_npv_cost": str(rent_npv_cost),
            "cheaper": cheaper_key,
            "breakeven_month": breakeven_month,
            "net_equity_at_horizon": str(net_equity_at_horizon),
        },
        "explain": explain.model_dump(),
    }


SCHEMA = Inputs.model_json_schema()
METRIC_PATH: tuple = ("results", "buy_npv_cost")  # dot-path into results, for the /sensitivity endpoint's scalar metric

__all__ = ["Inputs", "SCHEMA", "run"]
