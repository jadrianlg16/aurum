"""Cross-border MX/US rules — informational checklists, never a decision.

* ``xb.residency``          — MX residency (CFF art. 9) and US residency (IRC § 7701(b) substantial presence).
* ``xb.treaty_tiebreaker``  — US–MX treaty art. 4 tie-breaker ladder for someone resident in both.
* ``xb.fbar``               — aggregate foreign-account balance against the USD 10,000 FinCEN threshold.
* ``xb.feie_vs_ftc``        — § 911 exclusion vs § 901 credit: what each is worth, and what to explore.

None of these rules decides anything. Residency and treaty positions have consequences that depend on
facts Aurum never sees; the output is a set of flags plus the citation to read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ...core.explain import Citation, Explain
from ...core.i18n import t
from ...core.money import Amount, q2
from ..registry import RuleResult, registry
from ..us import constants_2026 as K
from ..us.federal import dec

DAYS = "DAY"
STEPS = "STP"
USD = "USD"


def NOT_ADVICE(lang: str = "es") -> str:  # noqa: N802 - kept as a call-alike for existing callers
    return t("rules.xb.not_advice", lang)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "sí", "y"}
    return bool(value)


def _int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(Decimal(str(value)))


# --------------------------------------------------------------------------- residency


@dataclass
class Residency:
    us_resident: bool
    us_basis: str
    weighted_days: Decimal
    spt_met: bool
    mx_resident: bool
    mx_basis: str
    dual: bool
    notes: list[str] = field(default_factory=list)


def residency(
    days_us: int = 0,
    days_us_prior_1: int = 0,
    days_us_prior_2: int = 0,
    days_mx: int = 0,
    home_us: bool = False,
    home_mx: bool = False,
    citizenship: list[str] | None = None,
    green_card: bool = False,
    mx_source_income_share: Decimal | None = None,
    main_professional_center: str | None = None,
    lang: str = "es",
) -> Residency:
    weights = K.SPT_WEIGHTS.value
    weighted = (
        Decimal(days_us) * weights["current"]
        + Decimal(days_us_prior_1) * weights["prior_1"]
        + Decimal(days_us_prior_2) * weights["prior_2"]
    )
    weighted_q = q2(weighted)
    spt = days_us >= K.SPT_CURRENT_YEAR_MIN_DAYS.value and weighted >= K.SPT_WEIGHTED_DAYS.value

    cits = {c.strip().upper() for c in (citizenship or [])}
    notes: list[str] = []
    if "US" in cits:
        us_resident, us_basis = True, t("rules.xb.residency.basis.us_citizen", lang)
    elif green_card:
        us_resident, us_basis = True, t("rules.xb.residency.basis.green_card", lang)
    elif spt:
        us_resident, us_basis = True, t(
            "rules.xb.residency.basis.spt_met", lang, days_us=days_us, weighted=weighted_q, threshold=K.SPT_WEIGHTED_DAYS.value
        )
    else:
        us_resident, us_basis = False, t(
            "rules.xb.residency.basis.spt_not_met", lang, days_us=days_us, weighted=weighted_q
        )
    if not us_resident and days_us > 0:
        notes.append(t("rules.xb.residency.note.nonresident_1040nr", lang))
    if us_resident and spt and not green_card and "US" not in cits:
        notes.append(t("rules.xb.residency.note.closer_connection", lang))

    if home_mx and not home_us:
        mx_resident, mx_basis = True, t("rules.xb.residency.mx_basis.home_only_mx", lang)
    elif home_mx and home_us:
        share = mx_source_income_share
        if share is not None and share > K.MX_RESIDENCY_CFF9.value["center_of_vital_interests_income_share"]:
            mx_resident = True
            mx_basis = t("rules.xb.residency.mx_basis.vital_interests", lang, share=share)
        elif (main_professional_center or "").strip().upper() == "MX":
            mx_resident = True
            mx_basis = t("rules.xb.residency.mx_basis.professional_center", lang)
        else:
            mx_resident = False
            mx_basis = t("rules.xb.residency.mx_basis.no_vital_interests", lang)
    else:
        mx_resident, mx_basis = False, t("rules.xb.residency.mx_basis.no_home", lang)

    if days_mx >= 183 and not mx_resident:
        notes.append(t("rules.xb.residency.note.days_mx_signal", lang, days_mx=days_mx))
    if mx_resident and not home_mx:
        notes.append(t("rules.xb.residency.note.presumed_continue", lang))

    return Residency(
        us_resident=us_resident,
        us_basis=us_basis,
        weighted_days=weighted_q,
        spt_met=spt,
        mx_resident=mx_resident,
        mx_basis=mx_basis,
        dual=us_resident and mx_resident,
        notes=notes,
    )


class ResidencyRule:
    """Tax residency in each country: CFF art. 9 (MX) and the substantial presence test (US)."""

    id = "xb.residency"
    version = "2026.1"
    jurisdiction = "XB"
    citation = Citation(
        law="IRC",
        article="7701(b)(3) · CFF art. 9",
        url=K.IRS_SPT,
        effective_from=date(2026, 1, 1),
        trust_tier="primary",
        excerpt=(
            "Substantial presence: 31 days in the current year and 183 weighted days over three years "
            "(current 1, prior 1/3, second prior 1/6). CFF art. 9: casa habitación, then centre of vital interests."
        ),
    )
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        days_us: Any = 0,
        days_us_prior_1: Any = 0,
        days_us_prior_2: Any = 0,
        days_mx: Any = 0,
        home_us: Any = False,
        home_mx: Any = False,
        citizenship: list[str] | None = None,
        green_card: Any = False,
        mx_source_income_share: Any = None,
        main_professional_center: str | None = None,
        currency: str = DAYS,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        result = residency(
            days_us=_int(days_us),
            days_us_prior_1=_int(days_us_prior_1),
            days_us_prior_2=_int(days_us_prior_2),
            days_mx=_int(days_mx),
            home_us=_truthy(home_us),
            home_mx=_truthy(home_mx),
            citizenship=citizenship,
            green_card=_truthy(green_card),
            mx_source_income_share=None if mx_source_income_share is None else dec(mx_source_income_share),
            main_professional_center=main_professional_center,
            lang=lang,
        )
        if result.dual:
            verdict = t("rules.xb.residency.verdict.dual", lang)
        elif result.us_resident:
            verdict = t("rules.xb.residency.verdict.us", lang)
        elif result.mx_resident:
            verdict = t("rules.xb.residency.verdict.mx", lang)
        else:
            verdict = t("rules.xb.residency.verdict.neither", lang)
        explain = Explain(
            summary=t(
                "rules.xb.residency.summary",
                lang,
                verdict=verdict,
                weighted=result.weighted_days,
                mark=K.MX_RESIDENCY_CFF9.mark,
                not_advice=NOT_ADVICE(lang),
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation, K.SPT_WEIGHTS.citation, K.MX_RESIDENCY_CFF9.citation],
            confidence=0.6,
        )
        explain.add_step(t("rules.xb.residency.step.days_current", lang), _int(days_us))
        explain.add_step(
            t("rules.xb.residency.step.days_prior1", lang), _int(days_us_prior_1), formula=t("rules.xb.residency.step.days_prior1_note", lang)
        )
        explain.add_step(
            t("rules.xb.residency.step.days_prior2", lang), _int(days_us_prior_2), formula=t("rules.xb.residency.step.days_prior2_note", lang)
        )
        explain.add_step(
            t("rules.xb.residency.step.weighted_days", lang),
            result.weighted_days,
            formula=t("rules.xb.residency.step.weighted_days_note", lang, threshold=K.SPT_WEIGHTED_DAYS.value),
        )
        explain.add_step(t("rules.xb.residency.step.spt_met", lang), str(result.spt_met))
        explain.add_step(t("rules.xb.residency.step.us_resident", lang), str(result.us_resident), formula=result.us_basis)
        explain.add_step(t("rules.xb.residency.step.days_mx", lang), _int(days_mx))
        explain.add_step(t("rules.xb.residency.step.casa_habitacion", lang), f"{_truthy(home_mx)} / {_truthy(home_us)}")
        explain.add_step(t("rules.xb.residency.step.mx_resident", lang), str(result.mx_resident), formula=result.mx_basis)
        explain.add_step(t("rules.xb.residency.step.dual", lang), str(result.dual))
        for note in result.notes:
            explain.add_step(t("rules.xb.residency.step.note", lang), note)
        return RuleResult(value=Amount(amount=result.weighted_days, currency=currency), explain=explain)


# --------------------------------------------------------------------------- treaty tie-breaker


TIEBREAKER_LABELS = {
    "permanent_home": "Permanent home available in only one State",
    "center_of_vital_interests": "Centre of vital interests (personal and economic relations)",
    "habitual_abode": "Habitual abode",
    "nationality": "Nationality",
    "competent_authority": "Mutual agreement between the competent authorities",
}


def _tiebreaker_label(key: str, lang: str = "es") -> str:
    return t(f"rules.xb.tiebreaker.label.{key}", lang)


@dataclass
class Tiebreaker:
    applies: bool
    resolved_at: int
    resolved_to: str | None
    checklist: list[dict[str, Any]]


def treaty_tiebreaker(
    dual_resident: bool,
    permanent_home: str | None = None,
    center_of_vital_interests: str | None = None,
    habitual_abode: str | None = None,
    nationality: str | None = None,
    lang: str = "es",
) -> Tiebreaker:
    answers = {
        "permanent_home": permanent_home,
        "center_of_vital_interests": center_of_vital_interests,
        "habitual_abode": habitual_abode,
        "nationality": nationality,
    }
    checklist: list[dict[str, Any]] = []
    resolved_at, resolved_to = 0, None
    for index, step in enumerate(K.TREATY_MX_US_ART4.value, start=1):
        answer = (answers.get(step) or "").strip().upper() or None
        decisive = bool(resolved_at == 0 and answer in {"MX", "US"})
        checklist.append(
            {
                "step": index,
                "key": step,
                "label": _tiebreaker_label(step, lang),
                "answer": answer,
                "decisive": decisive,
            }
        )
        if decisive:
            resolved_at, resolved_to = index, answer
    return Tiebreaker(
        applies=dual_resident,
        resolved_at=resolved_at if dual_resident else 0,
        resolved_to=resolved_to if dual_resident else None,
        checklist=checklist,
    )


class TreatyTiebreakerRule:
    """US–MX treaty art. 4 tie-breaker ladder for a dual resident — a checklist, not a conclusion."""

    id = "xb.treaty_tiebreaker"
    version = "2026.1"
    jurisdiction = "XB"
    citation = K.TREATY_MX_US_ART4.citation
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        dual_resident: Any = False,
        permanent_home: str | None = None,
        center_of_vital_interests: str | None = None,
        habitual_abode: str | None = None,
        nationality: str | None = None,
        currency: str = STEPS,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        result = treaty_tiebreaker(
            _truthy(dual_resident),
            permanent_home=permanent_home,
            center_of_vital_interests=center_of_vital_interests,
            habitual_abode=habitual_abode,
            nationality=nationality,
            lang=lang,
        )
        if not result.applies:
            summary = t("rules.xb.tiebreaker.summary.not_applicable", lang)
        elif result.resolved_to:
            summary = t(
                "rules.xb.tiebreaker.summary.resolved",
                lang,
                country=result.resolved_to,
                step=result.resolved_at,
                label=_tiebreaker_label(K.TREATY_MX_US_ART4.value[result.resolved_at - 1], lang),
                mark=K.TREATY_MX_US_ART4.mark,
            )
        else:
            summary = t("rules.xb.tiebreaker.summary.unresolved", lang, mark=K.TREATY_MX_US_ART4.mark)
        explain = Explain(
            summary=f"{summary} {NOT_ADVICE(lang)}",
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation],
            confidence=0.5,
        )
        explain.add_step(t("rules.xb.tiebreaker.step.dual_resident", lang), str(result.applies))
        for item in result.checklist:
            explain.add_step(
                t("rules.xb.tiebreaker.step.step_label", lang, step=item["step"], label=item["label"]),
                item["answer"] or t("rules.xb.tiebreaker.answer.unanswered", lang),
                formula=t("rules.xb.tiebreaker.answer.decisive", lang)
                if item["decisive"]
                else t("rules.xb.tiebreaker.answer.not_decisive", lang),
            )
        explain.add_step(
            t("rules.xb.tiebreaker.step.cost_label", lang),
            t("rules.xb.tiebreaker.step.cost_note", lang),
        )
        return RuleResult(value=Amount(amount=Decimal(result.resolved_at), currency=currency), explain=explain)


# --------------------------------------------------------------------------- FBAR


@dataclass
class Fbar:
    aggregate: Decimal
    required: bool
    accounts: list[dict[str, Any]]
    threshold: Decimal


def fbar(foreign_accounts: list[dict[str, Any]] | None, us_person: bool = True) -> Fbar:
    accounts = []
    aggregate = Decimal("0")
    for account in foreign_accounts or []:
        balance = q2(dec(account.get("max_balance_usd")))
        aggregate += balance
        accounts.append(
            {
                "country": account.get("country"),
                "institution": account.get("institution"),
                "max_balance_usd": str(balance),
            }
        )
    aggregate = q2(aggregate)
    return Fbar(
        aggregate=aggregate,
        required=us_person and aggregate > K.FBAR_THRESHOLD_USD.value,
        accounts=accounts,
        threshold=K.FBAR_THRESHOLD_USD.value,
    )


class FbarRule:
    """FinCEN Form 114: required when foreign accounts together exceed USD 10,000 at any time in the year."""

    id = "xb.fbar"
    version = "2026.1"
    jurisdiction = "XB"
    citation = K.FBAR_THRESHOLD_USD.citation
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        foreign_accounts: list[dict[str, Any]] | None = None,
        us_person: Any = True,
        currency: str = USD,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        result = fbar(foreign_accounts, us_person=_truthy(us_person))
        verdict = (
            t("rules.xb.fbar.verdict.required", lang) if result.required else t("rules.xb.fbar.verdict.not_required", lang)
        )
        explain = Explain(
            summary=t(
                "rules.xb.fbar.summary",
                lang,
                aggregate=result.aggregate,
                threshold=result.threshold,
                verdict=verdict,
                not_advice=NOT_ADVICE(lang),
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation, K.FBAR_DUE_DATE.citation],
        )
        explain.add_step(t("rules.xb.fbar.step.us_person", lang), str(_truthy(us_person)))
        for account in result.accounts:
            explain.add_step(
                t(
                    "rules.xb.fbar.step.account",
                    lang,
                    country=account.get("country") or "?",
                    institution=account.get("institution") or "",
                ).strip(),
                account["max_balance_usd"],
                formula=t("rules.xb.fbar.step.account_note", lang),
            )
        explain.add_step(t("rules.xb.fbar.step.aggregate", lang), result.aggregate, formula=t("rules.xb.fbar.step.aggregate_note", lang))
        explain.add_step(t("rules.xb.fbar.step.threshold", lang), result.threshold, formula=t("rules.xb.fbar.step.threshold_note", lang))
        explain.add_step(t("rules.xb.fbar.step.required", lang), str(result.required))
        explain.add_step(
            t("rules.xb.fbar.step.deadline", lang),
            t(
                "rules.xb.fbar.step.deadline_value",
                lang,
                due=K.FBAR_DUE_DATE.value["due"].isoformat(),
                extension=K.FBAR_DUE_DATE.value["automatic_extension"].isoformat(),
            ),
        )
        explain.add_step(
            t("rules.xb.fbar.step.not_fatca_label", lang),
            t("rules.xb.fbar.step.not_fatca_note", lang),
        )
        return RuleResult(value=Amount(amount=result.aggregate, currency=currency), explain=explain)


# --------------------------------------------------------------------------- FEIE vs FTC


@dataclass
class FeieVsFtc:
    foreign_earned_income: Decimal
    exclusion_available: Decimal
    exclusion_cap: Decimal
    foreign_tax_paid: Decimal
    qualifies: bool
    qualification_basis: str
    options: list[dict[str, Any]]


def feie_vs_ftc(
    foreign_earned_income: Decimal,
    foreign_tax_paid: Decimal = Decimal("0"),
    days_abroad: int = 0,
    bona_fide_resident: bool = False,
    lang: str = "es",
) -> FeieVsFtc:
    cap = K.FEIE_AMOUNT.value
    physical = days_abroad >= K.FEIE_PHYSICAL_PRESENCE_DAYS.value
    qualifies = physical or bona_fide_resident
    if bona_fide_resident:
        basis = t("rules.xb.feie.basis.bona_fide", lang)
    elif physical:
        basis = t("rules.xb.feie.basis.physical", lang, days=days_abroad, min_days=K.FEIE_PHYSICAL_PRESENCE_DAYS.value)
    else:
        basis = t("rules.xb.feie.basis.neither", lang, days=days_abroad)
    income = max(Decimal("0"), foreign_earned_income)
    available = q2(min(income, cap)) if qualifies else Decimal("0.00")
    options = [
        {
            "option": "FEIE",
            "citation": "IRC § 911",
            "value_usd": str(available),
            "what_it_does": t("rules.xb.feie.option.feie.what", lang),
            "watch_out": t("rules.xb.feie.option.feie.watch", lang),
        },
        {
            "option": "FTC",
            "citation": "IRC § 901 / § 904",
            "value_usd": str(q2(max(Decimal("0"), foreign_tax_paid))),
            "what_it_does": t("rules.xb.feie.option.ftc.what", lang),
            "watch_out": t("rules.xb.feie.option.ftc.watch", lang),
        },
    ]
    return FeieVsFtc(
        foreign_earned_income=q2(income),
        exclusion_available=available,
        exclusion_cap=cap,
        foreign_tax_paid=q2(max(Decimal("0"), foreign_tax_paid)),
        qualifies=qualifies,
        qualification_basis=basis,
        options=options,
    )


class FeieVsFtcRule:
    """What the § 911 exclusion and the § 901 credit are each worth — a comparison to explore, not a choice."""

    id = "xb.feie_vs_ftc"
    version = "2026.1"
    jurisdiction = "XB"
    citation = K.FEIE_AMOUNT.citation
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        foreign_earned_income: Any = None,
        foreign_tax_paid: Any = None,
        days_abroad: Any = 0,
        bona_fide_resident: Any = False,
        currency: str = USD,
        lang: str = "es",
        **_: Any,
    ) -> RuleResult:
        if foreign_earned_income is None:
            raise ValueError("foreign_earned_income is required")
        result = feie_vs_ftc(
            dec(foreign_earned_income),
            foreign_tax_paid=dec(foreign_tax_paid),
            days_abroad=_int(days_abroad),
            bona_fide_resident=_truthy(bona_fide_resident),
            lang=lang,
        )
        mark = K.verify_mark(K.FEIE_PHYSICAL_PRESENCE_DAYS, K.FTC_CONCEPT)
        explain = Explain(
            summary=t(
                "rules.xb.feie.summary",
                lang,
                available=result.exclusion_available,
                cap=result.exclusion_cap,
                paid=result.foreign_tax_paid,
                mark=mark,
                not_advice=NOT_ADVICE(lang),
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation, K.FEIE_PHYSICAL_PRESENCE_DAYS.citation, K.FTC_CONCEPT.citation],
            confidence=0.5,
        )
        explain.add_step(t("rules.xb.feie.step.foreign_income", lang), result.foreign_earned_income)
        explain.add_step(t("rules.xb.feie.step.cap", lang), result.exclusion_cap, formula="§ 911(b)(2)(D)(i), Rev. Proc. 2025-32")
        explain.add_step(t("rules.xb.feie.step.qualifies", lang), str(result.qualifies), formula=result.qualification_basis)
        explain.add_step(t("rules.xb.feie.step.available", lang), result.exclusion_available, formula=t("rules.xb.feie.step.available_note", lang))
        explain.add_step(t("rules.xb.feie.step.tax_paid", lang), result.foreign_tax_paid)
        for option in result.options:
            explain.add_step(
                t("rules.xb.feie.step.option", lang, option=option["option"], citation=option["citation"]),
                option["value_usd"],
                formula=f"{option['what_it_does']} — {option['watch_out']}",
            )
        explain.add_step(
            t("rules.xb.feie.step.no_se_relief_label", lang),
            t("rules.xb.feie.step.no_se_relief_note", lang),
        )
        return RuleResult(value=Amount(amount=result.exclusion_available, currency=currency), explain=explain)


residency_rule = registry.register(ResidencyRule())
treaty_tiebreaker_rule = registry.register(TreatyTiebreakerRule())
fbar_rule = registry.register(FbarRule())
feie_vs_ftc_rule = registry.register(FeieVsFtcRule())
