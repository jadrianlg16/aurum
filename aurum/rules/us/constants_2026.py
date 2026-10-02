"""Year-effective US federal + Texas constants for tax year 2026.

Every number a US rule uses lives here as a :class:`Const` record — ``value``, ``citation``,
``source_url``, ``verified`` — so a reader can tell at a glance which figures were read in a primary
source and which are still assumptions. Anything with ``verified=False`` is rendered ``(verify)`` in
the explain summary of any rule that touches it (never guess a rate).

Verification pass: 2026-09-06, against IRS Rev. Proc. 2025-32 (the 2026 inflation adjustments),
irs.gov topic/FAQ pages, and comptroller.texas.gov. See ``docs/modules/rules-us.md`` for the table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ...core.explain import Citation

YEAR = 2026

RP_2025_32 = "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf"
IRS_TC751 = "https://www.irs.gov/taxtopics/tc751"
IRS_ADDL_MEDICARE = (
    "https://www.irs.gov/businesses/small-businesses-self-employed/"
    "questions-and-answers-for-the-additional-medicare-tax"
)
IRS_SE_TAX = (
    "https://www.irs.gov/businesses/small-businesses-self-employed/"
    "self-employment-tax-social-security-and-medicare-taxes"
)
IRS_ESTIMATED = "https://www.irs.gov/faqs/estimated-tax"
IRS_SPT = "https://www.irs.gov/individuals/international-taxpayers/substantial-presence-test"
IRS_FBAR = (
    "https://www.irs.gov/businesses/small-businesses-self-employed/"
    "report-of-foreign-bank-and-financial-accounts-fbar"
)
TX_FRANCHISE = "https://comptroller.texas.gov/taxes/franchise/"
TX_SALES = "https://comptroller.texas.gov/taxes/sales/"
USC26 = "https://uscode.house.gov/view.xhtml?path=/prelim@title26&edition=prelim"
TREATY_MX_US = "https://www.irs.gov/businesses/international-businesses/mexico-tax-treaty-documents"
CFF_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/CFF.pdf"

VERIFIED_ON = date(2026, 9, 6)


@dataclass(frozen=True)
class Const:
    """One year-effective constant with the citation that produced it."""

    key: str
    value: Any
    citation: Citation
    source_url: str
    verified: bool = False
    verified_on: date | None = None
    note: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def mark(self) -> str:
        """``""`` when read in a primary/official source, ``" (verify)"`` otherwise."""
        return "" if self.verified else " (verify)"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": _jsonable(self.value),
            "citation": self.citation.model_dump(mode="json"),
            "source_url": self.source_url,
            "verified": self.verified,
            "verified_on": self.verified_on.isoformat() if self.verified_on else None,
            "note": self.note,
        }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _irc(article: str, excerpt: str = "") -> Citation:
    return Citation(
        law="IRC",
        article=article,
        url=USC26,
        effective_from=date(YEAR, 1, 1),
        trust_tier="primary",
        excerpt=excerpt or None,
    )


def _irs(article: str, url: str, excerpt: str = "") -> Citation:
    return Citation(
        law="IRS guidance",
        article=article,
        url=url,
        effective_from=date(YEAR, 1, 1),
        trust_tier="official_guidance",
        excerpt=excerpt or None,
    )


def _tx(chapter: str, url: str, excerpt: str = "") -> Citation:
    return Citation(
        law="Texas Tax Code",
        article=chapter,
        url=url,
        effective_from=date(YEAR, 1, 1),
        trust_tier="official_guidance",
        excerpt=excerpt or None,
    )


D = Decimal

# --------------------------------------------------------------------------- self-employment tax

SE_NET_EARNINGS_FACTOR = Const(
    key="se.net_earnings_factor",
    value=D("0.9235"),
    citation=_irc(
        "1402(a)(12)",
        "Net earnings from self-employment are reduced by 7.65% (1 - 0.0765 = 0.9235).",
    ),
    source_url=USC26,
    verified=False,
    note="Arithmetic from the 7.65% reduction in § 1402(a)(12); the statutory text was not read.",
)

SE_OASDI_RATE = Const(
    key="se.oasdi_rate",
    value=D("0.124"),
    citation=_irc("1401(a)", "Old-age, survivors, and disability insurance portion of the SE tax."),
    source_url=IRS_SE_TAX,
    verified=True,
    verified_on=VERIFIED_ON,
    note='IRS: "12.4% for social security" (self-employment tax page).',
)

SE_MEDICARE_RATE = Const(
    key="se.medicare_rate",
    value=D("0.029"),
    citation=_irc("1401(b)(1)", "Hospital insurance portion of the SE tax."),
    source_url=IRS_SE_TAX,
    verified=True,
    verified_on=VERIFIED_ON,
    note='IRS: "2.9% for Medicare"; combined SE rate 15.3%.',
)

SS_WAGE_BASE = Const(
    key="se.social_security_wage_base",
    value=D("184500"),
    citation=_irs("Topic no. 751 — Social Security wage base 2026", IRS_TC751),
    source_url=IRS_TC751,
    verified=True,
    verified_on=VERIFIED_ON,
    note="SSA contribution and benefit base for 2026 (USD 176,100 in 2025).",
)

ADDL_MEDICARE_RATE = Const(
    key="se.additional_medicare_rate",
    value=D("0.009"),
    citation=_irc("1401(b)(2)", "Additional Medicare Tax on SE income above the threshold."),
    source_url=IRS_ADDL_MEDICARE,
    verified=True,
    verified_on=VERIFIED_ON,
    note='IRS Q&A: "The rate is 0.9 percent."',
)

ADDL_MEDICARE_THRESHOLDS = Const(
    key="se.additional_medicare_thresholds",
    value={
        "single": D("200000"),
        "hoh": D("200000"),
        "qss": D("200000"),
        "mfj": D("250000"),
        "mfs": D("125000"),
    },
    citation=_irc("1401(b)(2)(A)", "Threshold amounts by filing status."),
    source_url=IRS_ADDL_MEDICARE,
    verified=True,
    verified_on=VERIFIED_ON,
    note="IRS Q&A table: MFJ 250,000 · MFS 125,000 · single/HoH/QSS 200,000.",
)

SE_TAX_DEDUCTION_SHARE = Const(
    key="se.deductible_share",
    value=D("0.5"),
    citation=_irc("164(f)", "One-half of the self-employment tax is deductible in figuring AGI."),
    source_url=IRS_SE_TAX,
    verified=True,
    verified_on=VERIFIED_ON,
    note='IRS: deduct "the employer-equivalent portion" of SE tax when figuring AGI.',
)

# --------------------------------------------------------------------------- income tax

FILING_STATUSES = ("single", "mfj", "mfs", "hoh")

# Each table: list of (upper bound of the bracket or None, marginal rate). § 1(j)(2), Rev. Proc. 2025-32 § 4.01.
BRACKETS = Const(
    key="fed.brackets",
    value={
        "single": [
            (D("12400"), D("0.10")),
            (D("50400"), D("0.12")),
            (D("105700"), D("0.22")),
            (D("201775"), D("0.24")),
            (D("256225"), D("0.32")),
            (D("640600"), D("0.35")),
            (None, D("0.37")),
        ],
        "mfj": [
            (D("24800"), D("0.10")),
            (D("100800"), D("0.12")),
            (D("211400"), D("0.22")),
            (D("403550"), D("0.24")),
            (D("512450"), D("0.32")),
            (D("768700"), D("0.35")),
            (None, D("0.37")),
        ],
        "mfs": [
            (D("12400"), D("0.10")),
            (D("50400"), D("0.12")),
            (D("105700"), D("0.22")),
            (D("201775"), D("0.24")),
            (D("256225"), D("0.32")),
            (D("384350"), D("0.35")),
            (None, D("0.37")),
        ],
        "hoh": [
            (D("17700"), D("0.10")),
            (D("67450"), D("0.12")),
            (D("105700"), D("0.22")),
            (D("201750"), D("0.24")),
            (D("256200"), D("0.32")),
            (D("640600"), D("0.35")),
            (None, D("0.37")),
        ],
    },
    citation=_irc("1(j)(2)", "2026 rate tables as adjusted by Rev. Proc. 2025-32 § 4.01."),
    source_url=RP_2025_32,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Read from the primary PDF of Rev. Proc. 2025-32, Tables 1-4 (§ 4.01).",
)

STANDARD_DEDUCTION = Const(
    key="fed.standard_deduction",
    value={"single": D("16100"), "mfj": D("32200"), "mfs": D("16100"), "hoh": D("24150")},
    citation=_irc("63(c)(2)", "Standard deduction for taxable years beginning in 2026."),
    source_url=RP_2025_32,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Rev. Proc. 2025-32 § 4.14(1): MFJ 32,200 · HoH 24,150 · single 16,100 · MFS 16,100.",
)

# --------------------------------------------------------------------------- estimated tax

ESTIMATE_CURRENT_YEAR_SHARE = Const(
    key="fed.estimate.current_year_share",
    value=D("0.90"),
    citation=_irc("6654(d)(1)(B)(i)", "90% of the tax shown on the return for the taxable year."),
    source_url=IRS_ESTIMATED,
    verified=True,
    verified_on=VERIFIED_ON,
    note="IRS estimated-tax FAQ.",
)

ESTIMATE_PRIOR_YEAR_SHARE = Const(
    key="fed.estimate.prior_year_share",
    value=D("1.00"),
    citation=_irc("6654(d)(1)(B)(ii)", "100% of the tax shown on the prior year's return."),
    source_url=IRS_ESTIMATED,
    verified=True,
    verified_on=VERIFIED_ON,
    note="IRS estimated-tax FAQ.",
)

ESTIMATE_HIGH_INCOME_SHARE = Const(
    key="fed.estimate.high_income_prior_year_share",
    value=D("1.10"),
    citation=_irc("6654(d)(1)(C)(i)", "110% of prior-year tax when prior-year AGI exceeds the threshold."),
    source_url=IRS_ESTIMATED,
    verified=True,
    verified_on=VERIFIED_ON,
    note="IRS estimated-tax FAQ.",
)

ESTIMATE_HIGH_INCOME_AGI = Const(
    key="fed.estimate.high_income_agi",
    value={"default": D("150000"), "mfs": D("75000")},
    citation=_irc("6654(d)(1)(C)(i)", "AGI greater than $150,000 ($75,000 if married filing separately)."),
    source_url=IRS_ESTIMATED,
    verified=True,
    verified_on=VERIFIED_ON,
    note="IRS estimated-tax FAQ.",
)

ESTIMATE_DE_MINIMIS = Const(
    key="fed.estimate.de_minimis",
    value=D("1000"),
    citation=_irc("6654(e)(1)", "No penalty when the tax due after withholding is less than $1,000."),
    source_url="https://www.irs.gov/taxtopics/tc306",
    verified=True,
    verified_on=VERIFIED_ON,
    note='IRS Topic 306: "owe less than $1,000 in tax after subtracting withholding and refundable credits".',
)

# Statutory dates; each shifts to the next business day when it falls on a weekend or legal holiday.
ESTIMATE_DUE_DATES = Const(
    key="fed.estimate.due_dates",
    value=[date(2026, 4, 15), date(2026, 6, 15), date(2026, 9, 15), date(2027, 1, 15)],
    citation=_irc("6654(c)(2)", "Due dates of the four required installments for a calendar-year individual."),
    source_url=IRS_ESTIMATED,
    verified=True,
    verified_on=VERIFIED_ON,
    note="IRS estimated-tax FAQ: Apr 15 · Jun 15 · Sep 15 · Jan 15 of the following year.",
)

# --------------------------------------------------------------------------- Texas franchise tax

TX_NO_TAX_DUE_THRESHOLD = Const(
    key="tx.franchise.no_tax_due_threshold",
    value=D("2650000"),
    citation=_tx("ch. 171 (§ 171.006 adjustment)", TX_FRANCHISE, "No tax due threshold for 2026 reports."),
    source_url=TX_FRANCHISE,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Texas Comptroller franchise page, 2026 report year: USD 2,650,000 annualized total revenue.",
)

TX_RATE_RETAIL_WHOLESALE = Const(
    key="tx.franchise.rate_retail_wholesale",
    value=D("0.00375"),
    citation=_tx("§ 171.002(b)", TX_FRANCHISE, "0.375% for taxable entities primarily in retail or wholesale trade."),
    source_url=TX_FRANCHISE,
    verified=True,
    verified_on=VERIFIED_ON,
)

TX_RATE_OTHER = Const(
    key="tx.franchise.rate_other",
    value=D("0.0075"),
    citation=_tx("§ 171.002(a)", TX_FRANCHISE, "0.75% general franchise tax rate on taxable margin."),
    source_url=TX_FRANCHISE,
    verified=True,
    verified_on=VERIFIED_ON,
)

TX_EZ_RATE = Const(
    key="tx.franchise.ez_rate",
    value=D("0.00331"),
    citation=_tx("§ 171.1016", TX_FRANCHISE, "E-Z computation rate 0.331% of apportioned total revenue."),
    source_url=TX_FRANCHISE,
    verified=True,
    verified_on=VERIFIED_ON,
)

TX_EZ_THRESHOLD = Const(
    key="tx.franchise.ez_threshold",
    value=D("20000000"),
    citation=_tx("§ 171.1016(a)", TX_FRANCHISE, "E-Z computation available up to USD 20 million total revenue."),
    source_url=TX_FRANCHISE,
    verified=True,
    verified_on=VERIFIED_ON,
)

TX_COMPENSATION_DEDUCTION_LIMIT = Const(
    key="tx.franchise.compensation_deduction_limit",
    value=D("480000"),
    citation=_tx("§ 171.1013", TX_FRANCHISE, "Wages and cash compensation limit per person, 2026."),
    source_url=TX_FRANCHISE,
    verified=True,
    verified_on=VERIFIED_ON,
)

TX_MARGIN_REVENUE_SHARE = Const(
    key="tx.franchise.margin_revenue_share",
    value=D("0.70"),
    citation=_tx("§ 171.101(a)(1)(A)", TX_FRANCHISE, "Margin = 70% of total revenue (one of the options)."),
    source_url=TX_FRANCHISE,
    verified=False,
    note="Not shown on the Comptroller landing page read on 2026-09-06; confirm in § 171.101.",
)

TX_MARGIN_FLAT_DEDUCTION = Const(
    key="tx.franchise.margin_flat_deduction",
    value=D("1000000"),
    citation=_tx("§ 171.101(a)(1)(B)(ii)", TX_FRANCHISE, "Total revenue minus USD 1 million (one of the options)."),
    source_url=TX_FRANCHISE,
    verified=False,
    note="Not yet confirmed in the primary text.",
)

TX_SOLE_PROP_NOT_TAXABLE = Const(
    key="tx.franchise.sole_proprietor_not_taxable",
    value=True,
    citation=_tx("§ 171.0002(b)(1)", TX_FRANCHISE, "A sole proprietorship is not a taxable entity."),
    source_url=TX_FRANCHISE,
    verified=False,
    note="Widely reported; the statutory text has not been read.",
)

# --------------------------------------------------------------------------- Texas sales & use tax

TX_SALES_STATE_RATE = Const(
    key="tx.sales.state_rate",
    value=D("0.0625"),
    citation=_tx("ch. 151 (§ 151.051)", TX_SALES, "State sales and use tax rate: 6.25%."),
    source_url=TX_SALES,
    verified=True,
    verified_on=VERIFIED_ON,
)

TX_SALES_LOCAL_MAX_RATE = Const(
    key="tx.sales.local_max_rate",
    value=D("0.02"),
    citation=_tx("chs. 321/322/323", TX_SALES, "Local jurisdictions may impose up to 2%."),
    source_url=TX_SALES,
    verified=True,
    verified_on=VERIFIED_ON,
)

TX_SALES_MAX_COMBINED_RATE = Const(
    key="tx.sales.max_combined_rate",
    value=D("0.0825"),
    citation=_tx("ch. 151 + chs. 321/322/323", TX_SALES, "Maximum combined rate 8.25%."),
    source_url=TX_SALES,
    verified=True,
    verified_on=VERIFIED_ON,
)

# --------------------------------------------------------------------------- cross-border

SPT_CURRENT_YEAR_MIN_DAYS = Const(
    key="xb.spt.current_year_min_days",
    value=31,
    citation=_irc("7701(b)(3)(A)(i)", "At least 31 days of presence in the current calendar year."),
    source_url=IRS_SPT,
    verified=True,
    verified_on=VERIFIED_ON,
)

SPT_WEIGHTED_DAYS = Const(
    key="xb.spt.weighted_days",
    value=183,
    citation=_irc("7701(b)(3)(A)(ii)", "183 weighted days over the current and two preceding years."),
    source_url=IRS_SPT,
    verified=True,
    verified_on=VERIFIED_ON,
)

SPT_WEIGHTS = Const(
    key="xb.spt.weights",
    value={"current": D("1"), "prior_1": D("1") / D("3"), "prior_2": D("1") / D("6")},
    citation=_irc("7701(b)(3)(A)(ii)", "Current year 1, first preceding year 1/3, second preceding year 1/6."),
    source_url=IRS_SPT,
    verified=True,
    verified_on=VERIFIED_ON,
)

FBAR_THRESHOLD_USD = Const(
    key="xb.fbar.threshold_usd",
    value=D("10000"),
    citation=Citation(
        law="31 C.F.R.",
        article="1010.350",
        url=IRS_FBAR,
        effective_from=date(YEAR, 1, 1),
        trust_tier="primary",
        excerpt="Aggregate value of foreign financial accounts exceeding USD 10,000 at any time in the year.",
    ),
    source_url=IRS_FBAR,
    verified=True,
    verified_on=VERIFIED_ON,
    note='IRS FBAR page: "exceeded $10,000 at any time during the calendar year reported".',
)

FBAR_DUE_DATE = Const(
    key="xb.fbar.due_date",
    value={"due": date(2027, 4, 15), "automatic_extension": date(2027, 10, 15)},
    citation=Citation(
        law="31 C.F.R.",
        article="1010.306(c)",
        url=IRS_FBAR,
        effective_from=date(YEAR, 1, 1),
        trust_tier="official_guidance",
        excerpt="April 15 following the calendar year reported, with an automatic extension to October 15.",
    ),
    source_url=IRS_FBAR,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Dates shown are for the 2026 reporting year (filed in 2027).",
)

FEIE_AMOUNT = Const(
    key="xb.feie.amount",
    value=D("132900"),
    citation=_irc("911(b)(2)(D)(i)", "Foreign earned income exclusion amount for taxable years beginning in 2026."),
    source_url=RP_2025_32,
    verified=True,
    verified_on=VERIFIED_ON,
    note="Rev. Proc. 2025-32 § 4.39, read in the primary PDF: USD 132,900.",
)

FEIE_PHYSICAL_PRESENCE_DAYS = Const(
    key="xb.feie.physical_presence_days",
    value=330,
    citation=_irc("911(d)(1)(B)", "330 full days in a foreign country during any period of 12 consecutive months."),
    source_url=USC26,
    verified=False,
    note="Statutory text not yet read.",
)

MX_RESIDENCY_CFF9 = Const(
    key="xb.mx.residency_cff9",
    value={
        "test": "casa habitación en México; si también hay casa en el extranjero, centro de intereses vitales",
        "center_of_vital_interests_income_share": D("0.50"),
    },
    citation=Citation(
        law="CFF",
        article="9",
        url=CFF_URL,
        effective_from=date(YEAR, 1, 1),
        trust_tier="primary",
        excerpt=(
            "Se consideran residentes en México las personas físicas que hayan establecido su casa "
            "habitación en México; cuando también tengan casa habitación en otro país, se considerará "
            "el centro de intereses vitales."
        ),
    ),
    source_url=CFF_URL,
    verified=False,
    note="CFF art. 9 has not been read in the primary text; the >50% MX-source income test is (verify).",
)

TREATY_MX_US_ART4 = Const(
    key="xb.treaty.article_4",
    value=[
        "permanent_home",
        "center_of_vital_interests",
        "habitual_abode",
        "nationality",
        "competent_authority",
    ],
    citation=Citation(
        law="US–MX income tax treaty",
        article="4 (Residence)",
        url=TREATY_MX_US,
        effective_from=date(YEAR, 1, 1),
        trust_tier="primary",
        excerpt="Tie-breaker: permanent home → centre of vital interests → habitual abode → nationality → mutual agreement.",
    ),
    source_url=TREATY_MX_US,
    verified=False,
    note="The treaty text has not been read; the ordering follows the OECD model and is (verify).",
)

FTC_CONCEPT = Const(
    key="xb.ftc.concept",
    value="credit for income taxes paid to a foreign country, limited by the US tax on foreign-source income",
    citation=_irc("901", "Credit against US tax for income taxes paid or accrued to a foreign country."),
    source_url=USC26,
    verified=False,
    note="Concept only; § 904 limitation and basketing are not modelled.",
)


ALL: list[Const] = [
    SE_NET_EARNINGS_FACTOR,
    SE_OASDI_RATE,
    SE_MEDICARE_RATE,
    SS_WAGE_BASE,
    ADDL_MEDICARE_RATE,
    ADDL_MEDICARE_THRESHOLDS,
    SE_TAX_DEDUCTION_SHARE,
    BRACKETS,
    STANDARD_DEDUCTION,
    ESTIMATE_CURRENT_YEAR_SHARE,
    ESTIMATE_PRIOR_YEAR_SHARE,
    ESTIMATE_HIGH_INCOME_SHARE,
    ESTIMATE_HIGH_INCOME_AGI,
    ESTIMATE_DE_MINIMIS,
    ESTIMATE_DUE_DATES,
    TX_NO_TAX_DUE_THRESHOLD,
    TX_RATE_RETAIL_WHOLESALE,
    TX_RATE_OTHER,
    TX_EZ_RATE,
    TX_EZ_THRESHOLD,
    TX_COMPENSATION_DEDUCTION_LIMIT,
    TX_MARGIN_REVENUE_SHARE,
    TX_MARGIN_FLAT_DEDUCTION,
    TX_SOLE_PROP_NOT_TAXABLE,
    TX_SALES_STATE_RATE,
    TX_SALES_LOCAL_MAX_RATE,
    TX_SALES_MAX_COMBINED_RATE,
    SPT_CURRENT_YEAR_MIN_DAYS,
    SPT_WEIGHTED_DAYS,
    SPT_WEIGHTS,
    FBAR_THRESHOLD_USD,
    FBAR_DUE_DATE,
    FEIE_AMOUNT,
    FEIE_PHYSICAL_PRESENCE_DAYS,
    MX_RESIDENCY_CFF9,
    TREATY_MX_US_ART4,
    FTC_CONCEPT,
]

BY_KEY: dict[str, Const] = {c.key: c for c in ALL}


def unverified(consts: list[Const] | None = None) -> list[Const]:
    return [c for c in (consts if consts is not None else ALL) if not c.verified]


def verify_mark(*consts: Const) -> str:
    """``" (verify)"`` when any of ``consts`` is unverified, else ``""``."""
    return " (verify)" if any(not c.verified for c in consts) else ""


def table() -> list[dict[str, Any]]:
    """Every constant as a JSON-able record — powers ``GET /api/tax/us/constants``."""
    return [c.as_dict() for c in ALL]


__all__ = ["ALL", "BY_KEY", "Const", "YEAR", "table", "unverified", "verify_mark"]
