"""Decimal financial math: pmt, amortization, NPV/IRR, EAC.

Ported from the author's financial-sim project (https://github.com/jadrianlg16/financial-sim),
``src/domain/finance.js`` (``pmt``, ``buildAmortization``,
``buildBalloonAmortization``, ``npv``, ``irr``, ``solvePeriodicRate``, ``equivalentAnnualCost``) with
Decimal instead of JS floats. Behavior mirrors the JS 1:1; see tests/pf/test_finance.py for numeric cases
cross-checked against node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

TWO = Decimal("0.01")
ZERO = Decimal("0")


def pmt(principal: Decimal, annual_rate: Decimal, months: int) -> Decimal:
    """Monthly payment for a fully-amortizing loan."""
    if months <= 0:
        return ZERO
    r = annual_rate / 12
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** (-months))


@dataclass
class AmortizationRow:
    month: int
    payment: Decimal
    interest: Decimal
    principal: Decimal
    balance: Decimal
    cum_interest: Decimal
    cum_principal: Decimal
    balloon: Decimal = ZERO


@dataclass
class Amortization:
    payment: Decimal
    rows: list[AmortizationRow] = field(default_factory=list)
    total_paid: Decimal = ZERO
    total_interest: Decimal = ZERO
    balloon: Decimal = ZERO


def build_amortization(principal: Decimal, annual_rate: Decimal, months: int) -> Amortization:
    if principal <= 0 or months <= 0:
        return Amortization(payment=ZERO)
    payment = pmt(principal, annual_rate, months)
    r = annual_rate / 12
    bal = principal
    rows: list[AmortizationRow] = []
    cum_int = ZERO
    cum_prin = ZERO
    for m in range(1, months + 1):
        interest = bal * r
        principal_part = payment - interest
        bal = max(ZERO, bal - principal_part)
        cum_int += interest
        cum_prin += principal_part
        rows.append(
            AmortizationRow(
                month=m,
                payment=payment,
                interest=interest,
                principal=principal_part,
                balance=bal,
                cum_interest=cum_int,
                cum_principal=cum_prin,
            )
        )
    return Amortization(
        payment=payment,
        rows=rows,
        total_paid=payment * months,
        total_interest=payment * months - principal,
    )


def build_balloon_amortization(
    principal: Decimal, annual_rate: Decimal, months: int, balloon_amount: Decimal
) -> Amortization:
    if principal <= 0 or months <= 0:
        return Amortization(payment=ZERO)
    balloon = max(ZERO, min(balloon_amount, principal))
    r = annual_rate / 12
    if r == 0:
        payment = (principal - balloon) / months
    else:
        pv_balloon = balloon * (1 + r) ** (-months)
        payment = (principal - pv_balloon) * r / (1 - (1 + r) ** (-months))
    bal = principal
    rows: list[AmortizationRow] = []
    cum_int = ZERO
    cum_prin = ZERO
    for m in range(1, months + 1):
        interest = bal * r
        principal_part = payment - interest
        balloon_this_month = (bal - principal_part) if m == months else ZERO
        principal_part += balloon_this_month
        bal = max(ZERO, bal - principal_part)
        cum_int += interest
        cum_prin += principal_part
        rows.append(
            AmortizationRow(
                month=m,
                payment=payment + balloon_this_month,
                interest=interest,
                principal=principal_part,
                balance=bal,
                cum_interest=cum_int,
                cum_principal=cum_prin,
                balloon=balloon_this_month,
            )
        )
    total_paid = payment * months + balloon
    return Amortization(
        payment=payment, rows=rows, total_paid=total_paid, total_interest=total_paid - principal, balloon=balloon
    )


def npv(rate_per_period: Decimal, cashflows: list[Decimal]) -> Decimal:
    total = ZERO
    for t, cf in enumerate(cashflows):
        total += cf / (1 + rate_per_period) ** t
    return total


def irr(cashflows: list[Decimal], lo: Decimal = Decimal("-0.95"), hi: Decimal = Decimal("5")) -> Decimal | None:
    """IRR by robust bisection; requires a sign change in the cashflows. None mirrors the JS's NaN."""

    def f(r: Decimal) -> Decimal:
        return npv(r, cashflows)

    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fmid = f(mid)
        if abs(fmid) < Decimal("0.0000001"):
            return mid
        if flo * fmid < 0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return (lo + hi) / 2


def solve_periodic_rate(net_received: Decimal, payment: Decimal, n: int) -> Decimal:
    """Periodic rate solving netReceived = payment * [1-(1+j)^-n]/j (for CAT-style effective rates)."""
    if net_received <= 0 or payment <= 0 or n <= 0:
        return ZERO

    def g(j: Decimal) -> Decimal:
        if j == 0:
            return payment * n - net_received
        return payment * (1 - (1 + j) ** (-n)) / j - net_received

    lo, hi = Decimal("0.000000001"), Decimal("5")
    if g(lo) * g(hi) > 0:
        return ZERO
    for _ in range(200):
        mid = (lo + hi) / 2
        gm = g(mid)
        if abs(gm) < Decimal("0.000001"):
            return mid
        if g(lo) * gm < 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def equivalent_annual_cost(pv_cost: Decimal, annual_rate: Decimal, years: Decimal) -> Decimal:
    if years <= 0:
        return pv_cost
    if annual_rate == 0:
        return pv_cost / years
    annuity_factor = (1 - (1 + annual_rate) ** (-years)) / annual_rate
    return pv_cost / annuity_factor
