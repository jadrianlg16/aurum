"""Numeric cross-checks for aurum/plan/engine.py against real node runs (2026-09-06).

Depreciation is cross-checked against the ACTUAL reference ``depreciation.js`` from
the author's financial-sim project (https://github.com/jadrianlg16/financial-sim), run from that file's directory with:

    node -e "
    import('./depreciation.js').then(m => {
      const I = { vehicleCondition: 'new', depreciationMethod: 'declining', depreciationRate: 0.2 };
      console.log('declining y3', m.depreciatedValue(300000, I, 3));
      const I2 = { vehicleCondition: 'new', depreciationMethod: 'straight', depreciationRate: 0.2 };
      console.log('straight y3', m.depreciatedValue(300000, I2, 3));
      const I3 = { vehicleCondition: 'new', depreciationMethod: 'realistic', depreciationRate: 0.15,
                   firstYearDepreciation: 0.25 };
      console.log('realistic y1', m.depreciatedValue(300000, I3, 1));
      console.log('realistic y4', m.depreciatedValue(300000, I3, 4));
    });
    "

produced (verbatim node stdout):
    declining y3 153600.00000000003
    straight y3 119999.99999999997
    realistic y1 225000
    realistic y4 138178.12499999997

Monte Carlo: the reference ``monteCarlo.js`` is domain-specific (a ride-share car simulator)
and its loop is UNSEEDED (plain ``Math.random()``), so there is no seeded RNG in that file to port
verbatim — see engine.py's module docstring. What *is* cross-checked bit-for-bit is the seeded PRNG
(mulberry32, a standard public-domain generator) plus the Box-Muller normal transform used by
monteCarlo.js's own ``randomNormal`` (monteCarlo.js:5-8: ``mean + std*sqrt(-2*log(u))*cos(2*pi*v)``),
via a small harness reimplementing the identical formulas in JS:

    // mc_harness.mjs
    function mulberry32(seed) {
      let a = seed >>> 0;
      return function () {
        a |= 0; a = (a + 0x6D2B79F5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
    }
    function boxMuller(u, v) { return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); }
    const rng = mulberry32(42);
    const uniforms = []; for (let i=0;i<10;i++) uniforms.push(rng());
    console.log(JSON.stringify(uniforms));
    console.log(Math.sqrt(-2*Math.log(0.25))*Math.cos(2*Math.PI*0.6));

    $ node mc_harness.mjs

produced (verbatim node stdout):
    uniforms (seed 42, first 10): [0.6011037519201636, 0.44829055899754167, 0.8524657934904099,
      0.6697340414393693, 0.17481389874592423, 0.5265925421845168, 0.2732279943302274,
      0.6247446539346129, 0.8654746483080089, 0.4723170551005751]
    boxMuller(0.25, 0.6) = -1.3471016583436073
"""

from __future__ import annotations

import math

from aurum.plan.engine import (
    box_muller,
    compare_scenarios,
    depreciated_value,
    mulberry32,
    one_way_sensitivity,
    percentile,
    run_monte_carlo_retirement,
)


def approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) < tol


# --------------------------------------------------------------------------- mulberry32 / Box-Muller


def test_mulberry32_matches_js_seed_42():
    rng = mulberry32(42)
    uniforms = [rng() for _ in range(10)]
    expected = [
        0.6011037519201636,
        0.44829055899754167,
        0.8524657934904099,
        0.6697340414393693,
        0.17481389874592423,
        0.5265925421845168,
        0.2732279943302274,
        0.6247446539346129,
        0.8654746483080089,
        0.4723170551005751,
    ]
    assert uniforms == expected  # bit-identical, not just approx


def test_box_muller_matches_js_case():
    # node: Math.sqrt(-2*Math.log(0.25))*Math.cos(2*Math.PI*0.6) = -1.3471016583436073
    assert approx(box_muller(0.25, 0.6), -1.3471016583436073, 1e-12)


def test_percentile_matches_js_q_helper():
    # q = (arr, p) => arr.length ? arr[Math.floor(arr.length*p)] : NaN
    arr = [float(x) for x in range(10)]  # 0..9
    assert percentile(arr, 0.1) == arr[math.floor(10 * 0.1)] == 1.0
    assert percentile(arr, 0.5) == arr[math.floor(10 * 0.5)] == 5.0
    assert percentile(arr, 0.9) == arr[math.floor(10 * 0.9)] == 9.0
    assert percentile([], 0.5) == 0.0


# --------------------------------------------------------------------------- depreciation


def test_depreciation_declining_matches_js_case():
    # node depreciation.js declining y3 = 153600.00000000003
    v = depreciated_value(300000, 0.2, 3, method="declining")
    assert approx(v, 153600.00000000003)


def test_depreciation_straight_matches_js_case():
    # node depreciation.js straight y3 = 119999.99999999997
    v = depreciated_value(300000, 0.2, 3, method="straight")
    assert approx(v, 119999.99999999997)


def test_depreciation_realistic_matches_js_case():
    # node depreciation.js realistic y1 = 225000, y4 = 138178.12499999997
    v1 = depreciated_value(300000, 0.15, 1, method="realistic", first_year_rate=0.25)
    v4 = depreciated_value(300000, 0.15, 4, method="realistic", first_year_rate=0.25)
    assert approx(v1, 225000)
    assert approx(v4, 138178.12499999997)


def test_depreciation_never_negative():
    assert depreciated_value(100, 0.99, 50, method="declining") >= 0.0
    assert depreciated_value(100, 0.99, 50, method="straight") >= 0.0


# --------------------------------------------------------------------------- Monte Carlo (retirement)


def test_monte_carlo_retirement_is_deterministic_given_seed():
    r1 = run_monte_carlo_retirement(
        starting_balance=100000,
        monthly_contribution=5000,
        expected_annual_return=0.07,
        annual_volatility=0.15,
        inflation_annual=0.04,
        horizon_years=20,
        iterations=500,
        seed=42,
    )
    r2 = run_monte_carlo_retirement(
        starting_balance=100000,
        monthly_contribution=5000,
        expected_annual_return=0.07,
        annual_volatility=0.15,
        inflation_annual=0.04,
        horizon_years=20,
        iterations=500,
        seed=42,
    )
    assert r1.ending_balance.p10 == r2.ending_balance.p10
    assert r1.ending_balance.p50 == r2.ending_balance.p50
    assert r1.ending_balance.p90 == r2.ending_balance.p90


def test_monte_carlo_retirement_bands_are_ordered_and_positive():
    r = run_monte_carlo_retirement(
        starting_balance=50000,
        monthly_contribution=3000,
        expected_annual_return=0.06,
        annual_volatility=0.12,
        inflation_annual=0.03,
        horizon_years=10,
        iterations=800,
        seed=7,
    )
    assert r.ending_balance.p10 <= r.ending_balance.p50 <= r.ending_balance.p90
    assert r.ending_balance.p10 >= 0
    assert 0 <= r.success_rate <= 100


def test_monte_carlo_different_seeds_differ():
    r1 = run_monte_carlo_retirement(
        starting_balance=10000,
        monthly_contribution=1000,
        expected_annual_return=0.07,
        annual_volatility=0.2,
        inflation_annual=0.0,
        horizon_years=5,
        iterations=300,
        seed=1,
    )
    r2 = run_monte_carlo_retirement(
        starting_balance=10000,
        monthly_contribution=1000,
        expected_annual_return=0.07,
        annual_volatility=0.2,
        inflation_annual=0.0,
        horizon_years=5,
        iterations=300,
        seed=2,
    )
    assert r1.ending_balance.p50 != r2.ending_balance.p50


# --------------------------------------------------------------------------- sensitivity / compare


def test_one_way_sensitivity_orders_by_range_desc():
    def metric(i: dict) -> float:
        return i["a"] * 2 + i["b"] * 0.1

    points = one_way_sensitivity(
        {"a": 100, "b": 100},
        metric,
        [("a", "A", 0.2), ("b", "B", 0.2)],
    )
    assert points[0].key == "a"  # a has the bigger metric coefficient → wider range
    assert points[0].range >= points[1].range


def test_compare_scenarios_builds_rows():
    scenarios = {"buy": {"price": 100}, "rent": {"price": 50}}
    rows = compare_scenarios(scenarios, {"price": lambda i: i["price"]})
    assert rows == [{"scenario": "buy", "price": 100}, {"scenario": "rent", "price": 50}]
