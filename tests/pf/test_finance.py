"""Numeric cross-checks against the author's financial-sim project (https://github.com/jadrianlg16/financial-sim)
(src/domain/finance.js), run with node
(2026-09-05):

    node -e '... import { pmt, buildAmortization, npv, irr, equivalentAnnualCost } from
    "file:///.../finance.js"; console.log(pmt(100000, 0.12, 12)); ...'

produced: pmt(100000, 0.12, 12) = 8884.87886783416; buildAmortization row1 interest=1000,
principal=7884.878867834161; totalInterest=6618.546414009936; npv(0.01, [-1000,300,300,300,300]) =
170.5896655155114; irr([-1000,300,300,300,300]) = 0.07713847298437035;
equivalentAnnualCost(10000, 0.08, 5) = 2504.564545668364.
"""

from __future__ import annotations

from decimal import Decimal

from aurum.pf.finance import (
    build_amortization,
    equivalent_annual_cost,
    irr,
    npv,
    pmt,
)

D = Decimal


def approx(a: Decimal, b: float, tol: str = "0.0001") -> bool:
    return abs(a - D(str(b))) < D(tol)


def test_pmt_matches_js_case():
    # node: pmt(100000, 0.12, 12) = 8884.87886783416
    result = pmt(D("100000"), D("0.12"), 12)
    assert approx(result, 8884.87886783416, "0.001")


def test_build_amortization_matches_js_case():
    # node: buildAmortization(100000, 0.12, 12) → row1 interest=1000, principal=7884.878867834161,
    # totalInterest=6618.546414009936
    am = build_amortization(D("100000"), D("0.12"), 12)
    assert approx(am.rows[0].interest, 1000, "0.001")
    assert approx(am.rows[0].principal, 7884.878867834161, "0.01")
    assert approx(am.total_interest, 6618.546414009936, "0.01")
    # balance fully amortizes by the last row
    assert abs(am.rows[-1].balance) < D("0.01")


def test_npv_and_irr_match_js_case():
    # node: npv(0.01, [-1000,300,300,300,300]) = 170.5896655155114
    # node: irr([-1000,300,300,300,300]) = 0.07713847298437035
    cashflows = [D("-1000"), D("300"), D("300"), D("300"), D("300")]
    assert approx(npv(D("0.01"), cashflows), 170.5896655155114, "0.001")
    rate = irr(cashflows)
    assert rate is not None
    assert approx(rate, 0.07713847298437035, "0.0001")


def test_equivalent_annual_cost_matches_js_case():
    # node: equivalentAnnualCost(10000, 0.08, 5) = 2504.564545668364
    result = equivalent_annual_cost(D("10000"), D("0.08"), D("5"))
    assert approx(result, 2504.564545668364, "0.01")
