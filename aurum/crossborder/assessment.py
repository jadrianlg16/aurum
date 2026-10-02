"""Compose the cross-border assessment from the ``xb.*`` rules.

Every section is a rule result with its explain; ``flags`` are the short, plain-language sentences a
user reads first. A flag never says what to do — it says what to look into, and with whom.
"""

from __future__ import annotations

from typing import Any

from ..core.i18n import t
from ..rules.registry import load_rules, registry
from ..rules.us import constants_2026 as K
from .profile import CrossBorderProfile


def assess(ws_id: str, profile: CrossBorderProfile, lang: str = "es") -> dict[str, Any]:
    load_rules()

    residency = registry.get("xb.residency").compute(
        days_us=profile.days_us,
        days_us_prior_1=profile.days_us_prior_1,
        days_us_prior_2=profile.days_us_prior_2,
        days_mx=profile.days_mx,
        home_us=profile.home_us,
        home_mx=profile.home_mx,
        citizenship=profile.citizenship,
        green_card=profile.green_card,
        mx_source_income_share=profile.mx_source_income_share,
        main_professional_center=profile.main_professional_center,
        lang=lang,
    )
    us_resident = _step(residency, t("rules.xb.residency.step.us_resident", lang)) == "True"
    mx_resident = _step(residency, t("rules.xb.residency.step.mx_resident", lang)) == "True"
    dual = us_resident and mx_resident

    treaty = registry.get("xb.treaty_tiebreaker").compute(
        dual_resident=dual,
        permanent_home=profile.treaty_permanent_home,
        center_of_vital_interests=profile.treaty_center_of_vital_interests,
        habitual_abode=profile.treaty_habitual_abode,
        nationality=profile.treaty_nationality,
        lang=lang,
    )

    us_person = us_resident or "US" in profile.citizenship or profile.green_card
    fbar = registry.get("xb.fbar").compute(
        foreign_accounts=[a.model_dump(mode="json") for a in profile.foreign_accounts],
        us_person=us_person,
        lang=lang,
    )
    fbar_required = _step(fbar, t("rules.xb.fbar.step.required", lang)) == "True"

    feie = registry.get("xb.feie_vs_ftc").compute(
        foreign_earned_income=profile.foreign_earned_income_usd(),
        foreign_tax_paid=profile.foreign_tax_paid_usd,
        days_abroad=profile.days_abroad_for_feie,
        bona_fide_resident=profile.bona_fide_resident_abroad,
        lang=lang,
    )

    flags = _flags(
        profile, us_resident, mx_resident, dual, us_person, fbar_required, fbar.value.amount, feie, lang
    )

    return {
        "workspace": ws_id,
        "profile": profile.model_dump(mode="json"),
        "residency": {
            "mx": mx_resident,
            "us": us_resident,
            "dual": dual,
            "weighted_us_days": residency.value.model_dump(mode="json"),
            "explain": residency.explain.model_dump(mode="json"),
        },
        "treaty": {
            "applies": dual,
            "resolved_at_step": int(treaty.value.amount),
            "checklist": [
                {"step": i + 1, "key": key, "label": t(f"rules.xb.tiebreaker.label.{key}", lang)}
                for i, key in enumerate(K.TREATY_MX_US_ART4.value)
            ],
            "explain": treaty.explain.model_dump(mode="json"),
        },
        "fbar": {
            "required": fbar_required,
            "aggregate": fbar.value.model_dump(mode="json"),
            "threshold": str(K.FBAR_THRESHOLD_USD.value),
            "explain": fbar.explain.model_dump(mode="json"),
        },
        "feie_vs_ftc": {
            "options": [
                {"option": "FEIE", "citation": "IRC 911", "value": feie.value.model_dump(mode="json")},
                {
                    "option": "FTC",
                    "citation": "IRC 901",
                    "value": {"amount": str(profile.foreign_tax_paid_usd), "currency": "USD"},
                },
            ],
            "explain": feie.explain.model_dump(mode="json"),
        },
        "flags": flags,
        "unverified_constants": [c.key for c in K.unverified() if c.key.startswith("xb.")],
        "disclaimer": t("rules.xb.assessment.disclaimer", lang),
    }


def _step(result: Any, label: str) -> str | None:
    for step in result.explain.steps:
        if step.label == label:
            return step.value
    return None


def _flags(
    profile: CrossBorderProfile,
    us_resident: bool,
    mx_resident: bool,
    dual: bool,
    us_person: bool,
    fbar_required: bool,
    aggregate: Any,
    feie: Any,
    lang: str = "es",
) -> list[str]:
    flags: list[str] = []
    if fbar_required:
        flags.append(t("rules.xb.assessment.flag.fbar_required", lang, aggregate=aggregate, threshold=K.FBAR_THRESHOLD_USD.value))
    elif profile.foreign_accounts and us_person:
        flags.append(t("rules.xb.assessment.flag.fbar_not_required", lang))
    if dual:
        flags.append(t("rules.xb.assessment.flag.dual_residency", lang))
    if us_resident and not mx_resident:
        flags.append(t("rules.xb.assessment.flag.us_resident", lang))
    if mx_resident and not us_resident:
        flags.append(t("rules.xb.assessment.flag.mx_resident", lang))
    if not us_resident and not mx_resident:
        flags.append(t("rules.xb.assessment.flag.neither_resident", lang))
    if feie.value.amount > 0:
        flags.append(
            t(
                "rules.xb.assessment.flag.feie_vs_ftc",
                lang,
                available=feie.value.amount,
                paid=profile.foreign_tax_paid_usd,
            )
        )
    elif profile.foreign_earned_income_usd() > 0 and us_person:
        flags.append(t("rules.xb.assessment.flag.feie_vs_ftc_neither", lang))
    if us_person and profile.days_us == 0 and profile.days_mx > 0:
        flags.append(t("rules.xb.assessment.flag.abroad_still_filing", lang))
    if not profile.foreign_accounts and us_person:
        flags.append(t("rules.xb.assessment.flag.no_accounts_recorded", lang))
    return flags
