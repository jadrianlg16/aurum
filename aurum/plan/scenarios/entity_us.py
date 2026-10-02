"""US sole proprietorship vs single-member LLC (disregarded) vs S-corp sketch.

Informational only — it does not call the tax rule registry (the registered ``us.fed.se_tax`` rule and
the ``aurum/taxus`` module are separate). Every constant below except
the Social Security wage base is marked ``(verify)``: they have not been checked against the primary statutes, and it should not be
treated as tax advice. Citations point at the relevant IRC sections for a human to verify.

* Sole proprietorship / single-member LLC (disregarded entity for federal tax purposes): all net
  self-employment income is subject to SE tax (Social Security + Medicare) under IRC §1401 (verify),
  reported on Schedule SE/C. An LLC changes liability exposure, not the federal tax treatment, when it
  has a single member and makes no entity election.
* S-corp sketch: the owner splits profit into a "reasonable salary" (W-2, subject to FICA) and the
  remainder as a distribution (not subject to SE tax/FICA) — the classic S-corp payroll-tax planning
  lever, per IRC §§1361-1362 (verify) governing S-corp eligibility/election, with "reasonable
  compensation" case law and IRS guidance (not cited here) constraining how low the salary can go.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from ...core.explain import Citation, Explain
from ...core.i18n import t
from ...rules.us import constants_2026 as K

CITATION_1401 = Citation(
    law="IRC",
    article="§1401 (verify)",
    url="https://www.law.cornell.edu/uscode/text/26/1401",
    trust_tier="professional",
    excerpt="Self-employment tax imposed on net earnings from self-employment. (verify — not yet read in the primary text.)",
)
CITATION_1361 = Citation(
    law="IRC",
    article="§§1361-1362 (verify)",
    url="https://www.law.cornell.edu/uscode/text/26/1361",
    trust_tier="professional",
    excerpt="S corporation eligibility and election. (verify — not yet read in the primary text.)",
)

# (verify) 2026 SE tax constants — not read in a primary source (the wage base below is the exception).
SE_TAX_RATE = Decimal("0.153")  # 12.4% OASDI + 2.9% Medicare, combined employer+employee share (verify)
SE_TAX_DEDUCTION_FACTOR = Decimal("0.9235")  # the 92.35% net-earnings adjustment (verify)
# The 2026 Social Security wage base (USD 184,500) is the verified constant from the US rule set
# (IRS Topic 751, read on irs.gov); the 2025 base was USD 176,100.
SS_WAGE_BASE_2026 = K.SS_WAGE_BASE.value
ADDITIONAL_MEDICARE_THRESHOLD = Decimal("200000")  # (verify) single-filer threshold, not indexed
ADDITIONAL_MEDICARE_RATE = Decimal("0.009")  # (verify)
FICA_RATE_EMPLOYEE_SIDE = Decimal("0.0765")  # 6.2% OASDI (below wage base) + 1.45% Medicare, employee share


class Inputs(BaseModel):
    annual_net_profit: str = Field("100000.00", description="Net profit before any owner compensation, USD.")
    reasonable_salary: str = Field(
        "60000.00", description="S-corp sketch: the W-2 salary paid to the owner-employee."
    )
    currency: str = "USD"


def _se_tax(net_profit: Decimal) -> Decimal:
    base = (net_profit * SE_TAX_DEDUCTION_FACTOR).quantize(Decimal("0.01"))
    ss_base = min(base, SS_WAGE_BASE_2026)
    ss_tax = ss_base * Decimal("0.124")
    medicare_tax = base * Decimal("0.029")
    additional = max(Decimal("0"), base - ADDITIONAL_MEDICARE_THRESHOLD) * ADDITIONAL_MEDICARE_RATE
    return (ss_tax + medicare_tax + additional).quantize(Decimal("0.01"))


def _payroll_tax_on_salary(salary: Decimal) -> Decimal:
    ss_base = min(salary, SS_WAGE_BASE_2026)
    ss = ss_base * Decimal("0.124")  # both halves combined (employer + employee), payroll-tax-equivalent
    medicare = salary * Decimal("0.029")
    additional = max(Decimal("0"), salary - ADDITIONAL_MEDICARE_THRESHOLD) * ADDITIONAL_MEDICARE_RATE
    return (ss + medicare + additional).quantize(Decimal("0.01"))


def run(inputs: Inputs, lang: str = "es") -> dict:
    net_profit = Decimal(inputs.annual_net_profit)
    salary = Decimal(inputs.reasonable_salary)
    salary = min(salary, net_profit)
    distribution = net_profit - salary

    sole_prop_se_tax = _se_tax(net_profit)
    llc_se_tax = sole_prop_se_tax  # disregarded entity: identical federal tax treatment (verify)
    scorp_payroll_tax = _payroll_tax_on_salary(salary)  # distribution not subject to SE/FICA (verify)
    scorp_savings = sole_prop_se_tax - scorp_payroll_tax

    explain = Explain(
        summary=t(
            "plan.entity_us.summary",
            lang,
            sole_prop=sole_prop_se_tax,
            currency=inputs.currency,
            salary=salary,
            savings=scorp_savings,
        ),
        citations=[CITATION_1401, CITATION_1361],
        confidence=0.4,
    )
    explain.add_step(t("plan.entity_us.step.net_profit", lang), net_profit)
    explain.add_step(
        t("plan.entity_us.step.sole_prop_se_tax", lang),
        sole_prop_se_tax,
        formula=t("plan.entity_us.step.sole_prop_se_tax.formula", lang, value=sole_prop_se_tax),
    )
    explain.add_step(
        t("plan.entity_us.step.llc_se_tax", lang),
        llc_se_tax,
        formula=t("plan.entity_us.step.llc_se_tax.formula", lang),
    )
    explain.add_step(t("plan.entity_us.step.scorp_salary", lang), salary)
    explain.add_step(t("plan.entity_us.step.scorp_distribution", lang), distribution)
    explain.add_step(t("plan.entity_us.step.scorp_payroll_tax", lang), scorp_payroll_tax)
    explain.add_step(t("plan.entity_us.step.scorp_savings", lang), scorp_savings)
    explain.add_step(
        t("plan.entity_us.step.verify_label", lang),
        t("plan.entity_us.step.verify_note", lang),
    )

    return {
        "inputs": inputs.model_dump(),
        "results": {
            "sole_proprietorship": {"se_tax": str(sole_prop_se_tax)},
            "single_member_llc": {"se_tax": str(llc_se_tax)},
            "s_corp_sketch": {
                "salary": str(salary),
                "distribution": str(distribution),
                "payroll_tax": str(scorp_payroll_tax),
                "estimated_savings_vs_sole_prop": str(scorp_savings),
            },
            "verified": False,
        },
        "explain": explain.model_dump(),
    }


SCHEMA = Inputs.model_json_schema()
METRIC_PATH: tuple = ("results", "s_corp_sketch", "estimated_savings_vs_sole_prop")  # dot-path into results, for the /sensitivity endpoint's scalar metric

__all__ = ["Inputs", "SCHEMA", "run"]
