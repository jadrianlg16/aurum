"""Simulation engine for the plan module.

Adapted from ``monteCarlo.js``, ``sensitivity.js`` and ``depreciation.js`` in
the author's financial-sim project (https://github.com/jadrianlg16/financial-sim). That reference JS is domain-specific (a ride-share car simulator) and its Monte Carlo loop is
UNSEEDED (``Math.random()``), so there is no seeded-RNG algorithm in the JS to port verbatim. What *is*
ported bit-for-bit is the machinery that any seeded Monte Carlo needs and that the JS file exercises
structurally:

* the percentile helper ``q = (arr, p) => arr[Math.floor(arr.length * p)]`` (monteCarlo.js:71), and
* the Box-Muller normal transform used by ``randomNormal`` (monteCarlo.js:5-8), plugged into a seeded
  PRNG (mulberry32, a standard public-domain generator) so runs are reproducible and cross-checkable
  between the two languages — see ``tests/plan/test_engine.py`` for the exact ``node -e`` invocation
  that proves the Python port produces bit-identical uniforms/normals to a JS mulberry32 + Box-Muller
  implementation for seed 42.

``depreciated_value`` is a direct, faithful port of ``depreciation.js`` (declining / straight / realistic
methods) — floats throughout, matching the JS's float arithmetic; callers quantize to Decimal at the
boundary. ``one_way_sensitivity`` generalizes ``sensitivity.js``: vary one field by ±range_pct around its
base value, measure a scalar objective, report the delta. ``compare_scenarios`` generalizes
``compare.js``'s "several full configs side by side" idea into a jurisdiction-agnostic table builder.

Floats are fine inside simulation loops; callers quantize reported summary Decimals.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENT = Decimal("0.01")


def q2(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- seeded RNG (mulberry32)


def mulberry32(seed: int) -> Callable[[], float]:
    """A seeded PRNG yielding uniforms in [0, 1), bit-identical to the standard JS mulberry32.

    Public-domain algorithm (not from the reference JS, which uses unseeded ``Math.random()``); implemented
    with the same 32-bit wraparound arithmetic as the JS version so both sides can be cross-checked.
    """
    state = {"a": seed & 0xFFFFFFFF}

    def next_() -> float:
        state["a"] = (state["a"] + 0x6D2B79F5) & 0xFFFFFFFF
        a = state["a"]
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t2 = t
        t = (t2 + (((t2 ^ (t2 >> 7)) * (61 | t2)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        t ^= t2
        t &= 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return next_


def box_muller(u: float, v: float) -> float:
    """Standard normal sample from two uniforms — same formula as monteCarlo.js's ``randomNormal``."""
    return math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)


def random_normal(rng: Callable[[], float], mean: float, std: float) -> float:
    u = 0.0
    while u == 0.0:
        u = rng()
    v = 0.0
    while v == 0.0:
        v = rng()
    return mean + std * box_muller(u, v)


def percentile(sorted_values: list[float], p: float) -> float:
    """``q(arr, p)`` from monteCarlo.js:71 — ``arr[floor(len*p)]``, NaN (here: 0.0) if empty."""
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, math.floor(len(sorted_values) * p))
    return sorted_values[idx]


# --------------------------------------------------------------------------- generic Monte Carlo


@dataclass
class MonteCarloBand:
    p10: Decimal
    p50: Decimal
    p90: Decimal
    mean: Decimal


@dataclass
class MonteCarloResult:
    iterations: int
    seed: int
    ending_balance: MonteCarloBand
    success_rate: Decimal  # fraction of paths that never went negative before the horizon
    paths_sample: list[list[float]] = field(default_factory=list)


def run_monte_carlo_retirement(
    *,
    starting_balance: float,
    monthly_contribution: float,
    expected_annual_return: float,
    annual_volatility: float,
    inflation_annual: float,
    horizon_years: int,
    iterations: int = 2000,
    seed: int = 42,
    sample_paths: int = 0,
) -> MonteCarloResult:
    """Contributions + expected return + volatility + inflation through the horizon.

    Structure mirrors ``runMonteCarlo`` in monteCarlo.js: per-iteration jitter of the return around its
    mean (Box-Muller normal, same as the JS's ``randomNormal``), simulate month by month, collect an
    ending-balance distribution, then take p10/p50/p90 via the same ``q`` percentile helper.
    """
    rng = mulberry32(seed)
    months = max(1, horizon_years * 12)
    monthly_return_mean = expected_annual_return / 12.0
    monthly_vol = annual_volatility / math.sqrt(12.0)
    monthly_inflation = inflation_annual / 12.0

    endings: list[float] = []
    successes = 0
    paths: list[list[float]] = []
    for i in range(iterations):
        balance = starting_balance
        contribution = monthly_contribution
        never_negative = True
        path: list[float] = [balance]
        for _m in range(months):
            r = random_normal(rng, monthly_return_mean, monthly_vol)
            balance = balance * (1.0 + r) + contribution
            contribution *= 1.0 + monthly_inflation
            if balance < 0:
                never_negative = False
                balance = 0.0
            if sample_paths and i < sample_paths:
                path.append(balance)
        endings.append(balance)
        if never_negative:
            successes += 1
        if sample_paths and i < sample_paths:
            paths.append(path)

    endings_sorted = sorted(endings)
    mean = sum(endings_sorted) / len(endings_sorted) if endings_sorted else 0.0
    return MonteCarloResult(
        iterations=iterations,
        seed=seed,
        ending_balance=MonteCarloBand(
            p10=q2(percentile(endings_sorted, 0.10)),
            p50=q2(percentile(endings_sorted, 0.50)),
            p90=q2(percentile(endings_sorted, 0.90)),
            mean=q2(mean),
        ),
        success_rate=q2(Decimal(successes) / Decimal(iterations) * 100) if iterations else Decimal("0.00"),
        paths_sample=paths,
    )


# --------------------------------------------------------------------------- one-way sensitivity


@dataclass
class SensitivityPoint:
    key: str
    label: str
    delta_pct: float
    base: float
    low: float
    high: float
    range: float


def one_way_sensitivity(
    inputs: dict[str, Any],
    metric_fn: Callable[[dict[str, Any]], float],
    vary: list[tuple[str, str, float]],
) -> list[SensitivityPoint]:
    """Generic port of ``sensitivity.js``: vary one field ±delta around its base value.

    ``vary`` is a list of ``(key, label, delta_pct)``. Mirrors ``sensitivity()``: compute the metric at
    ``base*(1-delta)`` and ``base*(1+delta)``, report ``low/high`` as offsets from the base metric, and
    ``range`` as ``abs(hi-lo)``; the caller sorts by range descending same as the JS's
    ``.sort((a,b) => b.range - a.range)``.
    """
    base_metric = metric_fn(inputs)
    points: list[SensitivityPoint] = []
    for key, label, delta in vary:
        base_value = float(inputs.get(key, 0.0) or 0.0)
        lo_inputs = {**inputs, key: base_value * (1 - delta)}
        hi_inputs = {**inputs, key: base_value * (1 + delta)}
        lo = metric_fn(lo_inputs)
        hi = metric_fn(hi_inputs)
        points.append(
            SensitivityPoint(
                key=key,
                label=label,
                delta_pct=delta,
                base=base_metric,
                low=min(lo, hi) - base_metric,
                high=max(lo, hi) - base_metric,
                range=abs(hi - lo),
            )
        )
    points.sort(key=lambda p: p.range, reverse=True)
    return points


# --------------------------------------------------------------------------- compare


def compare_scenarios(
    scenarios: dict[str, dict[str, Any]],
    metric_fns: dict[str, Callable[[dict[str, Any]], float]],
) -> list[dict[str, Any]]:
    """Port of the "side by side full configs" idea in compare.js — a row per scenario per metric."""
    rows: list[dict[str, Any]] = []
    for name, inputs in scenarios.items():
        row: dict[str, Any] = {"scenario": name}
        for metric_name, fn in metric_fns.items():
            row[metric_name] = fn(inputs)
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- depreciation


def depreciated_value(
    price: float,
    rate: float,
    year: int,
    method: str = "declining",
    first_year_rate: float | None = None,
) -> float:
    """Faithful float port of ``depreciation.js#depreciatedValue`` (declining/straight/realistic).

    * ``declining``: V_n = V0*(1-d)^n  (geometric / default)
    * ``straight``:  V_n = V0*(1-d*n)  (linear on original price)
    * ``realistic``: a heavier first-year hit then geometric decline:
                     V_1 = V0*(1-d1); V_n = V_1*(1-d)^(n-1)
    The value never goes below 0, same as the JS's ``Math.max(0, v)``.
    """
    if year <= 0:
        return price
    d = min(max(rate, 0.0), 0.95)
    if method == "straight":
        v = price * (1 - d * year)
    elif method == "realistic":
        d1 = min(max(first_year_rate if first_year_rate is not None else 0.25, 0.0), 0.95)
        after_first = price * (1 - d1)
        v = after_first if year == 1 else after_first * (1 - d) ** (year - 1)
    else:
        v = price * (1 - d) ** year
    return max(0.0, v)


__all__ = [
    "MonteCarloBand",
    "MonteCarloResult",
    "SensitivityPoint",
    "box_muller",
    "compare_scenarios",
    "depreciated_value",
    "mulberry32",
    "one_way_sensitivity",
    "percentile",
    "q2",
    "random_normal",
    "run_monte_carlo_retirement",
]
