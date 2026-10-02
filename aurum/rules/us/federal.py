"""US federal rules for a sole proprietor: Schedule C, SE tax, income tax, quarterly estimates.

Four rules live here. None of them is a return and none of them is advice: they reproduce the
arithmetic of the statute so a figure can be shown with its worked steps and its citation.

* ``us.fed.schedule_c_net``     — gross receipts − returns − cost of goods sold − expenses (§ 162, Sch. C).
* ``us.fed.se_tax``             — § 1401/1402: 12.4% OASDI up to the wage base + 2.9% Medicare + 0.9% additional.
* ``us.fed.income_tax``         — § 1 rate tables on taxable income after the § 63 standard deduction.
* ``us.fed.quarterly_estimate`` — § 6654 safe harbour, four equal installments.

Every constant comes from :mod:`aurum.rules.us.constants_2026`; anything unverified there makes the
explain summary carry ``(verify)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from ...core.explain import Citation, Explain
from ...core.i18n import t
from ...core.money import Amount, q2
from ..registry import RuleResult, registry
from . import constants_2026 as K

CURRENCY = "USD"


def NOT_ADVICE(lang: str = "es") -> str:  # noqa: N802 - kept as a call-alike for existing callers
    return t("rules.not_advice", lang)

_STATUS_ALIASES = {
    "single": "single",
    "s": "single",
    "married_filing_jointly": "mfj",
    "mfj": "mfj",
    "married_filing_separately": "mfs",
    "mfs": "mfs",
    "head_of_household": "hoh",
    "hoh": "hoh",
    "qss": "single",
    "qualifying_surviving_spouse": "single",
}


def normalize_status(value: str | None) -> str:
    key = (value or "single").strip().lower()
    if key not in _STATUS_ALIASES:
        raise ValueError(f"unknown filing_status {value!r}; expected one of {sorted(set(_STATUS_ALIASES))}")
    return _STATUS_ALIASES[key]


def dec(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    if isinstance(value, float):
        raise TypeError("money inputs must be Decimal/str/int, not float")
    if isinstance(value, dict):
        return sum((dec(v) for v in value.values()), Decimal("0"))
    if isinstance(value, (list, tuple)):
        return sum((dec(v) for v in value), Decimal("0"))
    return Decimal(str(value))


def _pct(rate: Decimal) -> str:
    """``Decimal("0.10")`` -> ``"10%"``. ``normalize()`` alone gives ``1E+1``, which reads as noise."""
    value = (rate * Decimal(100)).normalize()
    if value == value.to_integral_value():
        value = value.quantize(Decimal(1))
    return f"{value}%"


# --------------------------------------------------------------------------- Schedule C


class ScheduleCNetRule:
    """Net profit or loss from a sole proprietorship (Form 1040 Schedule C)."""

    id = "us.fed.schedule_c_net"
    version = "2026.1"
    jurisdiction = "US"
    citation = Citation(
        law="IRC",
        article="61 / 162 (Schedule C)",
        url=K.USC26,
        effective_from=date(2026, 1, 1),
        trust_tier="primary",
        excerpt="Gross income from a trade or business less the ordinary and necessary expenses of carrying it on.",
    )
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        gross_receipts: Any = None,
        returns_and_allowances: Any = None,
        cost_of_goods_sold: Any = None,
        expenses: Any = None,
        currency: str = CURRENCY,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        gross = q2(dec(gross_receipts))
        returns = q2(dec(returns_and_allowances))
        cogs = q2(dec(cost_of_goods_sold))
        exp_total = q2(dec(expenses))
        net = q2(gross - returns - cogs - exp_total)
        explain = Explain(
            summary=t(
                "rules.us.fed.schedule_c.summary",
                lang,
                net=net,
                currency=currency,
                gross=gross,
                returns=returns,
                cogs=cogs,
                exp_total=exp_total,
                not_advice=NOT_ADVICE(lang),
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation],
        )
        explain.add_step(t("rules.us.fed.schedule_c.step.gross_receipts", lang), gross)
        explain.add_step(t("rules.us.fed.schedule_c.step.returns", lang), returns)
        explain.add_step(t("rules.us.fed.schedule_c.step.cogs", lang), cogs)
        if isinstance(expenses, dict):
            for name, value in sorted(expenses.items()):
                explain.add_step(t("rules.us.fed.schedule_c.step.expense", lang, name=name), q2(dec(value)))
        explain.add_step(t("rules.us.fed.schedule_c.step.total_expenses", lang), exp_total)
        explain.add_step(
            t("rules.us.fed.schedule_c.step.net_profit", lang), net, formula=f"{gross} − {returns} − {cogs} − {exp_total}"
        )
        if net < 0:
            explain.add_step(
                t("rules.us.fed.schedule_c.step.loss_label", lang),
                t("rules.us.fed.schedule_c.step.loss_note", lang),
            )
        return RuleResult(value=Amount(amount=net, currency=currency), explain=explain)


# --------------------------------------------------------------------------- self-employment tax


@dataclass
class SelfEmploymentTax:
    net_earnings: Decimal
    oasdi_base: Decimal
    oasdi: Decimal
    medicare: Decimal
    additional_medicare: Decimal
    total: Decimal
    deductible_half: Decimal


def self_employment_tax(net_profit: Decimal, status: str, wages: Decimal = Decimal("0")) -> SelfEmploymentTax:
    """§ 1401/1402 arithmetic. ``wages`` are W-2 wages already subject to FICA in the same year."""
    net_earnings = q2(max(Decimal("0"), net_profit) * K.SE_NET_EARNINGS_FACTOR.value)
    remaining_base = max(Decimal("0"), K.SS_WAGE_BASE.value - max(Decimal("0"), wages))
    oasdi_base = min(net_earnings, remaining_base)
    oasdi = q2(oasdi_base * K.SE_OASDI_RATE.value)
    medicare = q2(net_earnings * K.SE_MEDICARE_RATE.value)
    threshold = K.ADDL_MEDICARE_THRESHOLDS.value[status]
    over = max(Decimal("0"), wages + net_earnings - threshold)
    additional = q2(min(over, net_earnings) * K.ADDL_MEDICARE_RATE.value)
    total = q2(oasdi + medicare + additional)
    deductible = q2((oasdi + medicare) * K.SE_TAX_DEDUCTION_SHARE.value)
    return SelfEmploymentTax(net_earnings, oasdi_base, oasdi, medicare, additional, total, deductible)


class SelfEmploymentTaxRule:
    """Self-employment tax: 12.4% OASDI to the wage base + 2.9% Medicare + 0.9% additional Medicare."""

    id = "us.fed.se_tax"
    version = "2026.1"
    jurisdiction = "US"
    citation = Citation(
        law="IRC",
        article="1401 / 1402",
        url=K.USC26,
        effective_from=date(2026, 1, 1),
        trust_tier="primary",
        excerpt=(
            "A tax on self-employment income: the old-age, survivors and disability insurance portion and "
            "the hospital insurance portion, plus the additional Medicare tax of § 1401(b)(2)."
        ),
    )
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        net_profit: Any = None,
        filing_status: str = "single",
        wages: Any = None,
        currency: str = CURRENCY,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        if net_profit is None:
            raise ValueError("net_profit (Schedule C line 31) is required")
        status = normalize_status(filing_status)
        profit = q2(dec(net_profit))
        w2 = q2(dec(wages))
        se = self_employment_tax(profit, status, w2)
        mark = K.verify_mark(K.SE_NET_EARNINGS_FACTOR)
        explain = Explain(
            summary=t(
                "rules.us.fed.se_tax.summary",
                lang,
                total=se.total,
                currency=currency,
                oasdi=se.oasdi,
                medicare=se.medicare,
                additional=se.additional_medicare,
                mark=mark,
                not_advice=NOT_ADVICE(lang),
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[
                self.citation,
                K.SS_WAGE_BASE.citation,
                K.ADDL_MEDICARE_THRESHOLDS.citation,
            ],
        )
        explain.add_step(t("rules.us.fed.se_tax.step.schedule_c_net", lang), profit)
        explain.add_step(
            t("rules.us.fed.se_tax.step.net_earnings", lang) + K.SE_NET_EARNINGS_FACTOR.mark,
            se.net_earnings,
            formula=f"{max(Decimal('0'), profit)} × {K.SE_NET_EARNINGS_FACTOR.value} (§ 1402(a)(12))",
        )
        explain.add_step(t("rules.us.fed.se_tax.step.w2_wages", lang), w2)
        explain.add_step(
            t("rules.us.fed.se_tax.step.wage_base", lang),
            K.SS_WAGE_BASE.value,
            formula=f"source: {K.SS_WAGE_BASE.source_url}",
        )
        explain.add_step(
            t("rules.us.fed.se_tax.step.oasdi_base", lang), se.oasdi_base, formula="min(net earnings, base − wages)"
        )
        explain.add_step(t("rules.us.fed.se_tax.step.oasdi", lang), se.oasdi, formula=f"{se.oasdi_base} × {K.SE_OASDI_RATE.value}")
        explain.add_step(t("rules.us.fed.se_tax.step.medicare", lang), se.medicare, formula=f"{se.net_earnings} × {K.SE_MEDICARE_RATE.value}")
        explain.add_step(
            t("rules.us.fed.se_tax.step.addl_threshold", lang, status=status),
            K.ADDL_MEDICARE_THRESHOLDS.value[status],
            formula="§ 1401(b)(2)(A)",
        )
        explain.add_step(
            t("rules.us.fed.se_tax.step.addl_medicare", lang),
            se.additional_medicare,
            formula=f"0.9% of the self-employment income above the {status} threshold",
        )
        explain.add_step(t("rules.us.fed.se_tax.step.total", lang), se.total, formula="OASDI + Medicare + additional Medicare")
        explain.add_step(
            t("rules.us.fed.se_tax.step.deductible_half", lang),
            se.deductible_half,
            formula=f"({se.oasdi} + {se.medicare}) × {K.SE_TAX_DEDUCTION_SHARE.value}",
        )
        return RuleResult(value=Amount(amount=se.total, currency=currency), explain=explain)


# --------------------------------------------------------------------------- income tax


@dataclass
class IncomeTax:
    agi: Decimal
    deduction: Decimal
    deduction_kind: str
    taxable_income: Decimal
    tax: Decimal
    marginal_rate: Decimal
    effective_rate: Decimal
    bracket_steps: list[tuple[Decimal, Decimal, Decimal]]  # (slice, rate, tax on the slice)


def bracket_tax(taxable_income: Decimal, status: str) -> IncomeTax:
    """Walk the § 1(j)(2) table for ``status``; returns the tax and the per-bracket slices."""
    table = K.BRACKETS.value[status]
    remaining = max(Decimal("0"), taxable_income)
    lower = Decimal("0")
    total = Decimal("0")
    steps: list[tuple[Decimal, Decimal, Decimal]] = []
    marginal = table[0][1]
    for upper, rate in table:
        if remaining <= 0:
            break
        width = (upper - lower) if upper is not None else remaining
        chunk = min(remaining, width)
        if chunk > 0:
            tax_on_chunk = chunk * rate
            steps.append((chunk, rate, q2(tax_on_chunk)))
            total += tax_on_chunk
            marginal = rate
            remaining -= chunk
        lower = upper if upper is not None else lower
    tax = q2(total)
    effective = q2(tax / taxable_income * 100) if taxable_income > 0 else Decimal("0.00")
    return IncomeTax(
        agi=Decimal("0"),
        deduction=Decimal("0"),
        deduction_kind="",
        taxable_income=q2(max(Decimal("0"), taxable_income)),
        tax=tax,
        marginal_rate=marginal,
        effective_rate=effective,
        bracket_steps=steps,
    )


def income_tax(
    status: str,
    schedule_c_net: Decimal = Decimal("0"),
    other_income: Decimal = Decimal("0"),
    se_tax_deduction: Decimal = Decimal("0"),
    adjustments: Decimal = Decimal("0"),
    itemized_deductions: Decimal | None = None,
    taxable_income: Decimal | None = None,
) -> IncomeTax:
    standard = K.STANDARD_DEDUCTION.value[status]
    if taxable_income is not None:
        agi = q2(taxable_income)
        deduction = Decimal("0.00")
        kind = "given"
        base = q2(taxable_income)
    else:
        agi = q2(schedule_c_net + other_income - se_tax_deduction - adjustments)
        if itemized_deductions is not None and itemized_deductions > standard:
            deduction, kind = q2(itemized_deductions), "itemized"
        else:
            deduction, kind = q2(standard), "standard"
        base = q2(max(Decimal("0"), agi - deduction))
    result = bracket_tax(base, status)
    result.agi = agi
    result.deduction = deduction
    result.deduction_kind = kind
    return result


class IncomeTaxRule:
    """Federal income tax on taxable income — § 1 rate tables and the § 63 standard deduction."""

    id = "us.fed.income_tax"
    version = "2026.1"
    jurisdiction = "US"
    citation = Citation(
        law="IRC",
        article="1(j)(2) / 63(c)",
        url=K.RP_2025_32,
        effective_from=date(2026, 1, 1),
        trust_tier="primary",
        excerpt="2026 rate tables and standard deduction as adjusted by Rev. Proc. 2025-32.",
    )
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        filing_status: str = "single",
        schedule_c_net: Any = None,
        other_income: Any = None,
        se_tax_deduction: Any = None,
        adjustments: Any = None,
        itemized_deductions: Any = None,
        taxable_income: Any = None,
        currency: str = CURRENCY,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        status = normalize_status(filing_status)
        result = income_tax(
            status,
            schedule_c_net=dec(schedule_c_net),
            other_income=dec(other_income),
            se_tax_deduction=dec(se_tax_deduction),
            adjustments=dec(adjustments),
            itemized_deductions=None if itemized_deductions is None else dec(itemized_deductions),
            taxable_income=None if taxable_income is None else dec(taxable_income),
        )
        explain = Explain(
            summary=t(
                "rules.us.fed.income_tax.summary",
                lang,
                status=status,
                tax=result.tax,
                currency=currency,
                taxable=result.taxable_income,
                marginal=_pct(result.marginal_rate),
                effective=result.effective_rate,
                not_advice=NOT_ADVICE(lang),
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation, K.BRACKETS.citation, K.STANDARD_DEDUCTION.citation],
        )
        if taxable_income is None:
            explain.add_step(t("rules.us.fed.se_tax.step.schedule_c_net", lang), q2(dec(schedule_c_net)))
            explain.add_step(t("rules.us.fed.income_tax.step.other_income", lang), q2(dec(other_income)))
            explain.add_step(t("rules.us.fed.income_tax.step.less_se", lang), q2(dec(se_tax_deduction)))
            explain.add_step(t("rules.us.fed.income_tax.step.less_adjustments", lang), q2(dec(adjustments)))
            explain.add_step(t("rules.us.fed.income_tax.step.agi", lang), result.agi)
            kind_label = t(f"rules.us.fed.income_tax.deduction_kind.{result.deduction_kind}", lang)
            explain.add_step(
                t("rules.us.fed.income_tax.step.deduction", lang, kind=kind_label, status=status),
                result.deduction,
                formula=f"§ 63(c)(2), 2026: standard = {K.STANDARD_DEDUCTION.value[status]}",
            )
        explain.add_step(t("rules.us.fed.income_tax.step.taxable_income", lang), result.taxable_income)
        for chunk, rate, tax_on_chunk in result.bracket_steps:
            explain.add_step(
                t("rules.us.fed.income_tax.step.bracket", lang, rate=_pct(rate)), tax_on_chunk, formula=f"{chunk} × {rate}"
            )
        explain.add_step(t("rules.us.fed.income_tax.step.income_tax", lang), result.tax, formula="Σ of the bracket slices (§ 1(j)(2) table)")
        explain.add_step(t("rules.us.fed.income_tax.step.marginal_rate", lang), _pct(result.marginal_rate))
        explain.add_step(
            t("rules.us.fed.step.not_modelled", lang),
            t("rules.us.fed.income_tax.step.not_modelled_note", lang),
        )
        return RuleResult(value=Amount(amount=result.tax, currency=currency), explain=explain)


# --------------------------------------------------------------------------- quarterly estimates


@dataclass
class QuarterlyEstimate:
    required_annual: Decimal
    basis: str
    withholding: Decimal
    remaining: Decimal
    amount_each: Decimal
    due_dates: list[date]
    de_minimis: bool


def quarterly_estimate(
    current_year_tax: Decimal,
    status: str,
    prior_year_tax: Decimal | None = None,
    prior_year_agi: Decimal | None = None,
    withholding: Decimal = Decimal("0"),
    lang: str = "es",
) -> QuarterlyEstimate:
    """§ 6654: the smaller of 90% of this year's tax and 100%/110% of last year's."""
    current_leg = q2(current_year_tax * K.ESTIMATE_CURRENT_YEAR_SHARE.value)
    pct90 = _pct(K.ESTIMATE_CURRENT_YEAR_SHARE.value)
    if prior_year_tax is None:
        required, basis = current_leg, t("rules.us.fed.quarterly.basis.no_prior", lang, pct=pct90)
    else:
        agi_threshold = K.ESTIMATE_HIGH_INCOME_AGI.value["mfs" if status == "mfs" else "default"]
        high = prior_year_agi is not None and prior_year_agi > agi_threshold
        share = K.ESTIMATE_HIGH_INCOME_SHARE.value if high else K.ESTIMATE_PRIOR_YEAR_SHARE.value
        prior_leg = q2(prior_year_tax * share)
        if prior_leg <= current_leg:
            required, basis = prior_leg, t("rules.us.fed.quarterly.basis.safe_harbor", lang, pct=_pct(share))
        else:
            required, basis = current_leg, t("rules.us.fed.quarterly.basis.current_year", lang, pct=pct90)
    remaining = q2(max(Decimal("0"), required - withholding))
    de_minimis = q2(current_year_tax - withholding) < K.ESTIMATE_DE_MINIMIS.value
    each = Decimal("0.00") if de_minimis else q2(remaining / 4)
    return QuarterlyEstimate(
        required_annual=required,
        basis=basis,
        withholding=q2(withholding),
        remaining=remaining,
        amount_each=each,
        due_dates=list(K.ESTIMATE_DUE_DATES.value),
        de_minimis=de_minimis,
    )


class QuarterlyEstimateRule:
    """Required annual estimated payment under the § 6654 safe harbour, split into four installments."""

    id = "us.fed.quarterly_estimate"
    version = "2026.1"
    jurisdiction = "US"
    citation = Citation(
        law="IRC",
        article="6654",
        url=K.IRS_ESTIMATED,
        effective_from=date(2026, 1, 1),
        trust_tier="primary",
        excerpt=(
            "Required annual payment: the lesser of 90% of the tax for the year or 100% (110% for higher "
            "prior-year AGI) of the tax shown on the prior year's return, in four installments."
        ),
    )
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        current_year_tax: Any = None,
        filing_status: str = "single",
        prior_year_tax: Any = None,
        prior_year_agi: Any = None,
        withholding: Any = None,
        currency: str = CURRENCY,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        if current_year_tax is None:
            raise ValueError("current_year_tax (income tax + self-employment tax) is required")
        status = normalize_status(filing_status)
        est = quarterly_estimate(
            q2(dec(current_year_tax)),
            status,
            prior_year_tax=None if prior_year_tax is None else q2(dec(prior_year_tax)),
            prior_year_agi=None if prior_year_agi is None else q2(dec(prior_year_agi)),
            withholding=dec(withholding),
            lang=lang,
        )
        explain = Explain(
            summary=t(
                "rules.us.fed.quarterly.summary",
                lang,
                each=est.amount_each,
                currency=currency,
                remaining=est.remaining,
                basis=est.basis,
                not_advice=NOT_ADVICE(lang),
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation, K.ESTIMATE_DUE_DATES.citation],
        )
        explain.add_step(t("rules.us.fed.quarterly.step.projected_tax", lang), q2(dec(current_year_tax)))
        explain.add_step(
            t("rules.us.fed.quarterly.step.pct_current", lang, pct=_pct(K.ESTIMATE_CURRENT_YEAR_SHARE.value)),
            q2(dec(current_year_tax) * K.ESTIMATE_CURRENT_YEAR_SHARE.value),
        )
        if prior_year_tax is not None:
            explain.add_step(t("rules.us.fed.quarterly.step.prior_tax", lang), q2(dec(prior_year_tax)))
            explain.add_step(
                t("rules.us.fed.quarterly.step.prior_agi", lang),
                q2(dec(prior_year_agi)) if prior_year_agi is not None else t("rules.us.fed.quarterly.unknown", lang),
            )
            explain.add_step(
                t("rules.us.fed.quarterly.step.safe_harbor_threshold", lang),
                K.ESTIMATE_HIGH_INCOME_AGI.value["mfs" if status == "mfs" else "default"],
                formula=t("rules.us.fed.quarterly.step.safe_harbor_note", lang),
            )
        explain.add_step(t("rules.us.fed.quarterly.step.required_annual", lang), est.required_annual, formula=est.basis)
        explain.add_step(t("rules.us.fed.quarterly.step.less_withholding", lang), est.withholding)
        explain.add_step(t("rules.us.fed.quarterly.step.to_pay", lang), est.remaining)
        explain.add_step(t("rules.us.fed.quarterly.step.each_installment", lang), est.amount_each, formula=f"{est.remaining} ÷ 4")
        for i, due in enumerate(est.due_dates, start=1):
            explain.add_step(t("rules.us.fed.quarterly.step.installment_due", lang, i=i), due.isoformat())
        explain.add_step(
            t("rules.us.fed.quarterly.step.due_dates", lang),
            t("rules.us.fed.quarterly.step.due_dates_note", lang),
        )
        if est.de_minimis:
            explain.add_step(
                t("rules.us.fed.quarterly.step.no_penalty", lang),
                t("rules.us.fed.quarterly.step.no_penalty_note", lang, de_minimis=K.ESTIMATE_DE_MINIMIS.value),
            )
        return RuleResult(value=Amount(amount=est.amount_each, currency=currency), explain=explain)


schedule_c_net = registry.register(ScheduleCNetRule())
se_tax = registry.register(SelfEmploymentTaxRule())
federal_income_tax = registry.register(IncomeTaxRule())
quarterly_estimate_rule = registry.register(QuarterlyEstimateRule())
