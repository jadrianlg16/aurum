"""Avalanche vs snowball debt payoff order.

Avalanche: pay minimums everywhere, throw every extra peso/dollar at the highest-APR debt first.
Snowball: same mechanic, but order by smallest balance first. Both simulate month by month (the same
interest-then-principal mechanic as ``aurum/pf/finance.py``'s amortization) with a shared
``extra_monthly_payment`` snowballing onto the next debt once one is paid off.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from ...core.explain import Explain
from ...core.i18n import t


class Debt(BaseModel):
    name: str
    balance: str
    annual_rate: str
    minimum_payment: str


class Inputs(BaseModel):
    debts: list[Debt] = Field(
        default_factory=lambda: [
            Debt(name="Tarjeta A", balance="45000", annual_rate="0.55", minimum_payment="2000"),
            Debt(name="Tarjeta B", balance="15000", annual_rate="0.38", minimum_payment="800"),
            Debt(name="Préstamo personal", balance="80000", annual_rate="0.22", minimum_payment="3500"),
        ]
    )
    extra_monthly_payment: str = "2000.00"
    currency: str = "MXN"


def _simulate(debts: list[dict], extra: Decimal, order_key) -> dict:
    debts = [dict(d) for d in debts]
    for d in debts:
        d["balance"] = Decimal(d["balance"])
        d["annual_rate"] = Decimal(d["annual_rate"])
        d["minimum_payment"] = Decimal(d["minimum_payment"])
    order = sorted(range(len(debts)), key=lambda i: order_key(debts[i]))
    month = 0
    total_interest = Decimal("0")
    payoff_month: dict[str, int] = {}
    max_months = 600
    while any(debts[i]["balance"] > 0 for i in order) and month < max_months:
        month += 1
        freed = extra
        for idx in order:
            d = debts[idx]
            if d["balance"] <= 0:
                continue
            interest = d["balance"] * d["annual_rate"] / 12
            total_interest += interest
            payment = d["minimum_payment"] + freed
            freed = Decimal("0")
            principal_paid = min(d["balance"] + interest, payment)
            d["balance"] = d["balance"] + interest - principal_paid
            if payment > (d["minimum_payment"] + interest):
                freed = payment - (d["balance"] + principal_paid - d["balance"])  # unspent overflow, rare
            if d["balance"] <= Decimal("0.005"):
                if d["name"] not in payoff_month:
                    payoff_month[d["name"]] = month
                freed += -d["balance"]  # any negative remainder rolls forward
                d["balance"] = Decimal("0")
    return {
        "months_to_debt_free": month if month < max_months else None,
        "total_interest_paid": str(total_interest.quantize(Decimal("0.01"))),
        "payoff_order": [debts[i]["name"] for i in order],
        "payoff_month_by_debt": payoff_month,
    }


def run(inputs: Inputs, lang: str = "es") -> dict:
    debts = [d.model_dump() for d in inputs.debts]
    extra = Decimal(inputs.extra_monthly_payment)

    avalanche = _simulate(debts, extra, order_key=lambda d: -d["annual_rate"])
    snowball = _simulate(debts, extra, order_key=lambda d: d["balance"])

    faster = "avalanche" if (avalanche["months_to_debt_free"] or 1e9) <= (snowball["months_to_debt_free"] or 1e9) else "snowball"
    cheaper = (
        "avalanche"
        if Decimal(avalanche["total_interest_paid"]) <= Decimal(snowball["total_interest_paid"])
        else "snowball"
    )

    explain = Explain(
        summary=t(
            "plan.debt_payoff.summary",
            lang,
            avalanche_months=avalanche["months_to_debt_free"],
            avalanche_interest=avalanche["total_interest_paid"],
            snowball_months=snowball["months_to_debt_free"],
            snowball_interest=snowball["total_interest_paid"],
            currency=inputs.currency,
            cheaper=t(f"plan.debt_payoff.cheaper.{cheaper}", lang),
        ),
    )
    explain.add_step(t("plan.debt_payoff.step.avalanche_order", lang), ", ".join(avalanche["payoff_order"]))
    explain.add_step(t("plan.debt_payoff.step.snowball_order", lang), ", ".join(snowball["payoff_order"]))
    explain.add_step(t("plan.debt_payoff.step.months_avalanche", lang), str(avalanche["months_to_debt_free"]))
    explain.add_step(t("plan.debt_payoff.step.months_snowball", lang), str(snowball["months_to_debt_free"]))
    explain.add_step(t("plan.debt_payoff.step.interest_avalanche", lang), avalanche["total_interest_paid"])
    explain.add_step(t("plan.debt_payoff.step.interest_snowball", lang), snowball["total_interest_paid"])
    explain.add_step(t("plan.debt_payoff.step.cheaper", lang), t(f"plan.debt_payoff.cheaper.{cheaper}", lang))
    explain.add_step(t("plan.debt_payoff.step.faster", lang), faster)

    return {
        "inputs": inputs.model_dump(),
        "results": {"avalanche": avalanche, "snowball": snowball, "cheaper": cheaper},
        "explain": explain.model_dump(),
    }


SCHEMA = Inputs.model_json_schema()
METRIC_PATH: tuple = ("results", "avalanche", "total_interest_paid")  # dot-path into results, for the /sensitivity endpoint's scalar metric

__all__ = ["Debt", "Inputs", "SCHEMA", "run"]
