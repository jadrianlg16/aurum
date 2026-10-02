"""Retirement Monte Carlo band (p10/p50/p90) via aurum/plan/engine.py."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from ...core.explain import Explain
from ...core.i18n import t
from ..engine import run_monte_carlo_retirement


class Inputs(BaseModel):
    starting_balance: str = "200000.00"
    monthly_contribution: str = "8000.00"
    expected_annual_return: str = "0.07"
    annual_volatility: str = "0.15"
    inflation_annual: str = "0.045"
    horizon_years: int = Field(25, ge=1, le=60)
    iterations: int = Field(2000, ge=100, le=20000)
    seed: int = 42
    currency: str = "MXN"


def run(inputs: Inputs, lang: str = "es") -> dict:
    result = run_monte_carlo_retirement(
        starting_balance=float(inputs.starting_balance),
        monthly_contribution=float(inputs.monthly_contribution),
        expected_annual_return=float(inputs.expected_annual_return),
        annual_volatility=float(inputs.annual_volatility),
        inflation_annual=float(inputs.inflation_annual),
        horizon_years=inputs.horizon_years,
        iterations=inputs.iterations,
        seed=inputs.seed,
    )
    explain = Explain(
        summary=t(
            "plan.retirement.summary",
            lang,
            years=inputs.horizon_years,
            iterations=inputs.iterations,
            seed=inputs.seed,
            p50=result.ending_balance.p50,
            currency=inputs.currency,
            p10=result.ending_balance.p10,
            p90=result.ending_balance.p90,
        ),
    )
    explain.add_step(t("plan.retirement.step.starting_balance", lang), inputs.starting_balance)
    explain.add_step(t("plan.retirement.step.monthly_contribution", lang), inputs.monthly_contribution)
    explain.add_step(t("plan.retirement.step.expected_return", lang), f"{Decimal(inputs.expected_annual_return) * 100}%")
    explain.add_step(t("plan.retirement.step.volatility", lang), f"{Decimal(inputs.annual_volatility) * 100}%")
    explain.add_step(t("plan.retirement.step.p10", lang), result.ending_balance.p10)
    explain.add_step(t("plan.retirement.step.p50", lang), result.ending_balance.p50)
    explain.add_step(t("plan.retirement.step.p90", lang), result.ending_balance.p90)
    explain.add_step(t("plan.retirement.step.mean", lang), result.ending_balance.mean)
    explain.add_step(t("plan.retirement.step.success_rate", lang), f"{result.success_rate}%")

    return {
        "inputs": inputs.model_dump(),
        "results": {
            "p10": str(result.ending_balance.p10),
            "p50": str(result.ending_balance.p50),
            "p90": str(result.ending_balance.p90),
            "mean": str(result.ending_balance.mean),
            "success_rate_pct": str(result.success_rate),
            "iterations": result.iterations,
            "seed": result.seed,
        },
        "explain": explain.model_dump(),
    }


SCHEMA = Inputs.model_json_schema()
METRIC_PATH: tuple = ("results", "p50")  # dot-path into results, for the /sensitivity endpoint's scalar metric

__all__ = ["Inputs", "SCHEMA", "run"]
