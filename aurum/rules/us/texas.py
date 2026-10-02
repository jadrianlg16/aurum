"""Texas state rules: franchise tax (Tax Code ch. 171) and sales & use tax (ch. 151).

* ``us.tx.franchise_no_tax_due`` — is the entity below the no-tax-due threshold, and if not, what does
  the margin computation look like? A sole proprietorship is not a taxable entity at all.
* ``us.tx.sales_use_basics``     — state 6.25% plus local up to 2% (max 8.25% combined), and the use-tax
  counterpart on out-of-state purchases brought into Texas.

Both are informational: Texas filing is done in Webfile, never here.
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
from .federal import CURRENCY, NOT_ADVICE, _pct, dec

NON_TAXABLE_ENTITIES = {"sole_proprietorship", "sole_prop", "general_partnership_natural_persons"}


@dataclass
class Franchise:
    total_revenue: Decimal
    taxable_entity: bool
    no_tax_due: bool
    reason: str
    margin: Decimal
    margin_method: str
    apportioned_margin: Decimal
    rate: Decimal
    tax: Decimal
    ez_eligible: bool
    ez_tax: Decimal | None
    reports_still_required: list[str]


def franchise(
    total_revenue: Decimal,
    entity_type: str = "llc",
    business_type: str = "other",
    cost_of_goods_sold: Decimal = Decimal("0"),
    compensation: Decimal = Decimal("0"),
    apportionment_factor: Decimal = Decimal("1"),
    lang: str = "es",
) -> Franchise:
    threshold = K.TX_NO_TAX_DUE_THRESHOLD.value
    rate = (
        K.TX_RATE_RETAIL_WHOLESALE.value
        if business_type in {"retail", "wholesale", "retail_wholesale"}
        else K.TX_RATE_OTHER.value
    )
    revenue = q2(max(Decimal("0"), total_revenue))

    if entity_type.strip().lower() in NON_TAXABLE_ENTITIES:
        return Franchise(
            total_revenue=revenue,
            taxable_entity=False,
            no_tax_due=True,
            reason=t("rules.us.tx.franchise.reason.sole_prop", lang),
            margin=Decimal("0.00"),
            margin_method="n/a",
            apportioned_margin=Decimal("0.00"),
            rate=rate,
            tax=Decimal("0.00"),
            ez_eligible=False,
            ez_tax=None,
            reports_still_required=[],
        )

    candidates: list[tuple[str, Decimal]] = [
        (t("rules.us.tx.franchise.margin.revenue_share", lang), q2(revenue * K.TX_MARGIN_REVENUE_SHARE.value)),
        (t("rules.us.tx.franchise.margin.less_cogs", lang), q2(revenue - max(Decimal("0"), cost_of_goods_sold))),
        (t("rules.us.tx.franchise.margin.less_compensation", lang), q2(revenue - max(Decimal("0"), compensation))),
        (t("rules.us.tx.franchise.margin.flat", lang), q2(revenue - K.TX_MARGIN_FLAT_DEDUCTION.value)),
    ]
    method, margin = min(candidates, key=lambda c: c[1])
    margin = q2(max(Decimal("0"), margin))
    apportioned = q2(margin * apportionment_factor)
    tax = q2(apportioned * rate)
    ez_eligible = revenue <= K.TX_EZ_THRESHOLD.value
    ez_tax = q2(revenue * apportionment_factor * K.TX_EZ_RATE.value) if ez_eligible else None

    if revenue <= threshold:
        return Franchise(
            total_revenue=revenue,
            taxable_entity=True,
            no_tax_due=True,
            reason=t("rules.us.tx.franchise.reason.below_threshold", lang, revenue=revenue, threshold=threshold),
            margin=margin,
            margin_method=method,
            apportioned_margin=apportioned,
            rate=rate,
            tax=Decimal("0.00"),
            ez_eligible=ez_eligible,
            ez_tax=ez_tax,
            reports_still_required=[t("rules.us.tx.franchise.report.pir", lang)],
        )

    return Franchise(
        total_revenue=revenue,
        taxable_entity=True,
        no_tax_due=False,
        reason=t("rules.us.tx.franchise.reason.above_threshold", lang, revenue=revenue, threshold=threshold),
        margin=margin,
        margin_method=method,
        apportioned_margin=apportioned,
        rate=rate,
        tax=tax,
        ez_eligible=ez_eligible,
        ez_tax=ez_tax,
        reports_still_required=[t("rules.us.tx.franchise.report.franchise_and_pir", lang), t("rules.us.tx.franchise.report.pir", lang)],
    )


class FranchiseNoTaxDueRule:
    """Texas franchise tax: no-tax-due check against the 2026 threshold, plus the margin computation."""

    id = "us.tx.franchise_no_tax_due"
    version = "2026.1"
    jurisdiction = "US-TX"
    citation = Citation(
        law="Texas Tax Code",
        article="ch. 171 (§§ 171.002, 171.006, 171.101, 171.1016)",
        url=K.TX_FRANCHISE,
        effective_from=date(2026, 1, 1),
        trust_tier="official_guidance",
        excerpt=(
            "Franchise tax on taxable margin; entities at or below the no-tax-due threshold owe no tax but "
            "still file an information report."
        ),
    )
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        total_revenue: Any = None,
        entity_type: str = "llc",
        business_type: str = "other",
        cost_of_goods_sold: Any = None,
        compensation: Any = None,
        apportionment_factor: Any = None,
        currency: str = CURRENCY,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        if total_revenue is None:
            raise ValueError("total_revenue (annualized) is required")
        result = franchise(
            q2(dec(total_revenue)),
            entity_type=entity_type,
            business_type=business_type,
            cost_of_goods_sold=dec(cost_of_goods_sold),
            compensation=dec(compensation),
            apportionment_factor=dec(apportionment_factor, "1"),
            lang=lang,
        )
        mark = K.verify_mark(
            K.TX_MARGIN_REVENUE_SHARE, K.TX_MARGIN_FLAT_DEDUCTION, K.TX_SOLE_PROP_NOT_TAXABLE
        )
        verdict = (
            t("rules.us.tx.franchise.verdict.no_tax_due", lang)
            if result.no_tax_due
            else t("rules.us.tx.franchise.verdict.tax_due", lang, tax=result.tax, currency=currency)
        )
        explain = Explain(
            summary=t(
                "rules.us.tx.franchise.summary",
                lang,
                verdict=verdict,
                reason=result.reason,
                mark=mark,
                not_advice=NOT_ADVICE(lang),
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation, K.TX_NO_TAX_DUE_THRESHOLD.citation],
        )
        explain.add_step(t("rules.us.tx.franchise.step.total_revenue", lang), result.total_revenue)
        explain.add_step(t("rules.us.tx.franchise.step.taxable_entity", lang), str(result.taxable_entity), formula="§ 171.0002")
        explain.add_step(
            t("rules.us.tx.franchise.step.no_tax_due_threshold", lang),
            K.TX_NO_TAX_DUE_THRESHOLD.value,
            formula=f"source: {K.TX_NO_TAX_DUE_THRESHOLD.source_url}",
        )
        if result.taxable_entity:
            explain.add_step(
                t("rules.us.tx.franchise.step.margin", lang) + K.TX_MARGIN_REVENUE_SHARE.mark,
                result.margin,
                formula=result.margin_method,
            )
            explain.add_step(t("rules.us.tx.franchise.step.apportioned", lang), result.apportioned_margin)
            rate_kind = (
                t("rules.us.tx.franchise.rate_kind.retail_wholesale", lang)
                if result.rate == K.TX_RATE_RETAIL_WHOLESALE.value
                else t("rules.us.tx.franchise.rate_kind.other", lang)
            )
            explain.add_step(t("rules.us.tx.franchise.step.rate", lang), _pct(result.rate), formula=f"§ 171.002 ({rate_kind})")
            if result.ez_tax is not None:
                explain.add_step(
                    t("rules.us.tx.franchise.step.ez", lang),
                    result.ez_tax,
                    formula=f"total revenue × {K.TX_EZ_RATE.value} (available up to {K.TX_EZ_THRESHOLD.value})",
                )
            explain.add_step(
                t("rules.us.tx.franchise.step.compensation_limit", lang), K.TX_COMPENSATION_DEDUCTION_LIMIT.value
            )
        explain.add_step(t("rules.us.tx.franchise.step.tax_due", lang), result.tax, formula=result.reason)
        for report in result.reports_still_required:
            explain.add_step(t("rules.us.tx.franchise.step.still_required", lang), report)
        explain.add_step(
            t("rules.us.fed.step.not_modelled", lang),
            t("rules.us.tx.franchise.step.not_modelled", lang),
        )
        return RuleResult(value=Amount(amount=result.tax, currency=currency), explain=explain)


# --------------------------------------------------------------------------- sales & use


@dataclass
class SalesUse:
    taxable_sales: Decimal
    out_of_state_purchases: Decimal
    state_rate: Decimal
    local_rate: Decimal
    combined_rate: Decimal
    sales_tax: Decimal
    use_tax: Decimal
    total: Decimal
    capped: bool


def sales_use(
    taxable_sales: Decimal,
    out_of_state_purchases: Decimal = Decimal("0"),
    local_rate: Decimal | None = None,
) -> SalesUse:
    state = K.TX_SALES_STATE_RATE.value
    local = K.TX_SALES_LOCAL_MAX_RATE.value if local_rate is None else max(Decimal("0"), local_rate)
    capped = local > K.TX_SALES_LOCAL_MAX_RATE.value
    local = min(local, K.TX_SALES_LOCAL_MAX_RATE.value)
    combined = state + local
    sales_tax = q2(max(Decimal("0"), taxable_sales) * combined)
    use_tax = q2(max(Decimal("0"), out_of_state_purchases) * combined)
    return SalesUse(
        taxable_sales=q2(taxable_sales),
        out_of_state_purchases=q2(out_of_state_purchases),
        state_rate=state,
        local_rate=local,
        combined_rate=combined,
        sales_tax=sales_tax,
        use_tax=use_tax,
        total=q2(sales_tax + use_tax),
        capped=capped,
    )


class SalesUseBasicsRule:
    """Texas sales & use tax: 6.25% state + up to 2% local (8.25% max combined)."""

    id = "us.tx.sales_use_basics"
    version = "2026.1"
    jurisdiction = "US-TX"
    citation = Citation(
        law="Texas Tax Code",
        article="ch. 151 (with chs. 321/322/323 local taxes)",
        url=K.TX_SALES,
        effective_from=date(2026, 1, 1),
        trust_tier="official_guidance",
        excerpt=(
            "State sales and use tax of 6.25%; local taxing jurisdictions may impose up to 2% for a maximum "
            "combined rate of 8.25%."
        ),
    )
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        taxable_sales: Any = None,
        out_of_state_purchases: Any = None,
        local_rate: Any = None,
        currency: str = CURRENCY,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        result = sales_use(
            dec(taxable_sales),
            dec(out_of_state_purchases),
            None if local_rate is None else dec(local_rate),
        )
        explain = Explain(
            summary=t(
                "rules.us.tx.sales_use.summary",
                lang,
                rate=_pct(result.combined_rate),
                total=result.total,
                currency=currency,
                sales=result.sales_tax,
                use=result.use_tax,
                not_advice=NOT_ADVICE(lang),
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation, K.TX_SALES_STATE_RATE.citation],
        )
        explain.add_step(t("rules.us.tx.sales_use.step.state_rate", lang), _pct(result.state_rate), formula="§ 151.051")
        explain.add_step(t("rules.us.tx.sales_use.step.local_rate", lang), _pct(result.local_rate), formula="chs. 321/322/323, capped at 2%")
        explain.add_step(
            t("rules.us.tx.sales_use.step.combined_rate", lang),
            _pct(result.combined_rate),
            formula=t("rules.us.tx.sales_use.step.combined_rate_note", lang, max_rate=_pct(K.TX_SALES_MAX_COMBINED_RATE.value)),
        )
        explain.add_step(t("rules.us.tx.sales_use.step.taxable_sales", lang), result.taxable_sales)
        explain.add_step(t("rules.us.tx.sales_use.step.sales_tax", lang), result.sales_tax, formula=f"{result.taxable_sales} × {result.combined_rate}")
        explain.add_step(t("rules.us.tx.sales_use.step.out_of_state", lang), result.out_of_state_purchases)
        explain.add_step(
            t("rules.us.tx.sales_use.step.use_tax", lang),
            result.use_tax,
            formula=t("rules.us.tx.sales_use.step.use_tax_note", lang),
        )
        explain.add_step(t("rules.us.tx.sales_use.step.total", lang), result.total)
        if result.capped:
            explain.add_step(t("rules.us.tx.sales_use.step.capped_label", lang), t("rules.us.tx.sales_use.step.capped", lang))
        explain.add_step(
            t("rules.us.tx.sales_use.step.services_note_label", lang),
            t("rules.us.tx.sales_use.step.services_note", lang),
        )
        explain.add_step(
            t("rules.us.fed.step.not_modelled", lang),
            t("rules.us.tx.sales_use.step.not_modelled", lang),
        )
        return RuleResult(value=Amount(amount=result.total, currency=currency), explain=explain)


franchise_no_tax_due = registry.register(FranchiseNoTaxDueRule())
sales_use_basics = registry.register(SalesUseBasicsRule())
