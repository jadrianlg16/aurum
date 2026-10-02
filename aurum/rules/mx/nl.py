"""Employer payroll taxes for a Nuevo León employer: ISN, IMSS employer quotas, INFONAVIT.

Three rules live here. None of them is a filing and none of them is advice: they reproduce the
arithmetic of the statute so a figure can be shown with its worked steps and its citation.

* ``mx.nl.isn``                   — Ley de Hacienda del Estado de NL art. 154-160: 3% on the taxable
                                    payroll base, art. 160 exemptions removed first.
* ``mx.imss.employer_quotas``     — LSS arts. 25, 71/72, 106, 107, 147, 168, 211: employer quotas by
                                    branch on the SBC, with the 25-UMA cap and the 3-UMA excedente
                                    threshold. Returns a per-branch breakdown.
* ``mx.infonavit.employer``       — LINFONAVIT art. 29 fr. II: 5% of the same capped base.

Every constant comes from :mod:`aurum.rules.mx.nl_constants_2026`; anything unverified there makes the
explain summary carry ``(verify)``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from ...core.explain import Citation, Explain
from ...core.money import Amount, q2
from ..registry import RuleResult, registry
from . import nl_constants_2026 as K

CURRENCY = "MXN"
NOT_ADVICE = (
    "Informational only — Aurum is not a filing and not tax advice; review with a licensed contador."
)


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
    """``Decimal("0.03")`` -> ``"3%"``. ``normalize()`` alone gives ``3E+0``, which reads as noise."""
    value = (rate * Decimal(100)).normalize()
    if value == value.to_integral_value():
        value = value.quantize(Decimal(1))
    return f"{value}%"


def _mark(*consts: K.Const) -> str:
    """``" (verify)"`` if any constant behind a figure was not read in a primary source."""
    return " (verify)" if any(not c.verified for c in consts) else ""


# --------------------------------------------------------------------------- ISN Nuevo León


class ISNNuevoLeonRule:
    """Impuesto Sobre Nóminas del Estado de Nuevo León — 3% of the taxable payroll base."""

    id = "mx.nl.isn"
    version = "2026.1"
    jurisdiction = "MX"
    citation = K.ISN_RATE.citation
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        payroll: Any = None,
        concepts: dict[str, Any] | None = None,
        exempt_amount: Any = None,
        exempt_entity: bool = False,
        currency: str = CURRENCY,
        **_: Any,
    ) -> RuleResult:
        """``payroll`` is the gross of every remuneration paid in the period (art. 154).

        Exemptions can be given three ways, and they add up:

        * ``concepts``  — a mapping concept → amount. Keys present in ``K.ISN_EXEMPT_CONCEPTS`` are
          removed from the base and the rest are added to it; when ``payroll`` is also given, only
          the exempt keys are subtracted (``payroll`` is then the full gross).
        * ``exempt_amount`` — a lump sum the caller has already identified as art. 160 exempt.
        * ``exempt_entity`` — art. 160 fr. II: the *employer* is exempt (non-profit welfare
          institution, chamber, union, school, service club, religious association).
        """
        exempt_keys = K.ISN_EXEMPT_CONCEPTS.value
        concepts = concepts or {}
        by_concept_taxable = {k: q2(dec(v)) for k, v in concepts.items() if k not in exempt_keys}
        by_concept_exempt = {k: q2(dec(v)) for k, v in concepts.items() if k in exempt_keys}

        if payroll is None or payroll == "":
            gross = q2(sum(by_concept_taxable.values(), Decimal("0")) + sum(by_concept_exempt.values(), Decimal("0")))
        else:
            gross = q2(dec(payroll))
        exempt = q2(sum(by_concept_exempt.values(), Decimal("0")) + dec(exempt_amount))
        base = q2(max(gross - exempt, Decimal("0")))
        rate = K.ISN_RATE.value
        tax = q2(Decimal("0")) if exempt_entity else q2(base * rate)

        explain = Explain(
            summary=(
                f"ISN Nuevo León: {tax} {currency} = {_pct(rate)} × base gravable {base} {currency}"
                f"{K.ISN_RATE.mark}. {NOT_ADVICE}"
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[
                K.ISN_TAXABLE_NOTE.citation,
                K.ISN_RATE.citation,
                K.ISN_EXEMPT_CONCEPTS.citation,
                K.ISN_DUE_DAY.citation,
            ],
        )
        explain.add_step("Erogaciones por remuneraciones al trabajo personal (art. 154)", gross)
        for name, value in sorted(by_concept_taxable.items()):
            explain.add_step(f"Gravado · {name}", value)
        for name, value in sorted(by_concept_exempt.items()):
            explain.add_step(f"Exento · {name}", value, formula=exempt_keys[name])
        if dec(exempt_amount):
            explain.add_step("Exento · monto declarado por el usuario", q2(dec(exempt_amount)))
        explain.add_step("Total exento (art. 160)", exempt)
        explain.add_step("Base gravable (art. 156)", base, formula=f"{gross} − {exempt}")
        explain.add_step("Tasa (art. 157)", _pct(rate) + K.ISN_RATE.mark)
        if exempt_entity:
            explain.add_step(
                "Sujeto exento (art. 160 fr. II)",
                "0.00",
                formula="instituciones de asistencia social, cámaras, sindicatos, escuelas, clubes de servicio "
                "o asociaciones religiosas",
            )
        explain.add_step("ISN del periodo", tax, formula=f"{base} × {rate}")
        explain.add_step(
            "Fecha límite de pago (art. 158)",
            f"día {K.ISN_DUE_DAY.value} del mes siguiente",
            formula=(
                f"pago trimestral opcional si el impuesto anual del año anterior no excedió "
                f"{K.ISN_QUARTERLY_THRESHOLD.value} MXN y se presentó el aviso"
            ),
        )
        return RuleResult(value=Amount(amount=tax, currency=currency), explain=explain)


# --------------------------------------------------------------------------- IMSS employer quotas


def capped_sbc(sbc_daily: Decimal) -> tuple[Decimal, Decimal, bool]:
    """Return (capped daily SBC, the 25-UMA ceiling, whether the cap bit)."""
    ceiling = q2(K.SBC_CAP_UMA.value * K.UMA_DAILY.value)
    if sbc_daily > ceiling:
        return ceiling, ceiling, True
    return sbc_daily, ceiling, False


def cv_employer_rate(sbc_daily: Decimal, table: list[dict[str, Any]] | None = None) -> tuple[Decimal, str]:
    """The graduated cesantía-y-vejez employer rate for a daily SBC, plus its bracket label."""
    rows = table or K.CV_EMPLOYER_TABLE_2026.value
    minimum_wage = K.MINIMUM_WAGE_DAILY.value
    if sbc_daily <= minimum_wage:
        return rows[0]["rate"], rows[0]["label"]
    uma = K.UMA_DAILY.value
    for row in rows[1:]:
        upper = row["upper_uma"]
        if upper is None:
            continue
        if sbc_daily <= upper * uma:
            return row["rate"], row["label"]
    return rows[-1]["rate"], rows[-1]["label"]


class IMSSEmployerQuotasRule:
    """Employer IMSS quotas by branch on the SBC (LSS arts. 25, 71, 106, 107, 147, 168, 211)."""

    id = "mx.imss.employer_quotas"
    version = "2026.1"
    jurisdiction = "MX"
    citation = Citation(
        law="LSS",
        article="25, 71, 106, 107, 147, 168, 211",
        url=K.LSS_URL,
        effective_from=date(2026, 1, 1),
        trust_tier="primary",
        excerpt=(
            "Cuotas obrero-patronales de los seguros de riesgos de trabajo, enfermedades y maternidad, "
            "invalidez y vida, retiro, cesantía en edad avanzada y vejez, y guarderías y prestaciones "
            "sociales, sobre el salario base de cotización."
        ),
    )
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        sbc_daily: Any = None,
        days: Any = 30,
        riesgo_prima: Any = None,
        currency: str = CURRENCY,
        **_: Any,
    ) -> RuleResult:
        """Employer quotas for one insured worker for ``days`` days at daily SBC ``sbc_daily``.

        ``riesgo_prima`` is the employer's own riesgo-de-trabajo prima (LSS art. 72 siniestralidad
        formula); it defaults to the 0.5% statutory minimum, which is almost never the real one.
        """
        raw_sbc = q2(dec(sbc_daily))
        sbc, ceiling, capped = capped_sbc(raw_sbc)
        n_days = dec(days, "30")
        uma = K.UMA_DAILY.value
        prima = dec(riesgo_prima) if riesgo_prima not in (None, "") else K.RT_MINIMUM_PRIMA.value

        excedente_threshold = q2(K.EM_EXCEDENTE_THRESHOLD_UMA.value * uma)
        excedente = max(sbc - excedente_threshold, Decimal("0"))
        cv_rate, cv_label = cv_employer_rate(sbc)

        branches: list[dict[str, Any]] = [
            {
                "branch": "riesgos_trabajo",
                "article": "71/72",
                "rate": prima,
                "base": q2(sbc * n_days),
                "amount": q2(sbc * n_days * prima),
                "verified": riesgo_prima not in (None, ""),
                "note": "prima propia del patrón" if riesgo_prima not in (None, "") else "prima mínima de riesgo (0.5%)",
            },
            {
                "branch": "em_especie_cuota_fija",
                "article": "106 I",
                "rate": K.EM_ESPECIE_FIXED_UMA_RATE.value,
                "base": q2(uma * n_days),
                "amount": q2(uma * n_days * K.EM_ESPECIE_FIXED_UMA_RATE.value),
                "verified": K.EM_ESPECIE_FIXED_UMA_RATE.verified,
                "note": "sobre la UMA, no sobre el SBC",
            },
            {
                "branch": "em_especie_excedente",
                "article": "106 II",
                "rate": K.EM_ESPECIE_EXCEDENTE_EMPLOYER.value,
                "base": q2(excedente * n_days),
                "amount": q2(excedente * n_days * K.EM_ESPECIE_EXCEDENTE_EMPLOYER.value),
                "verified": K.EM_ESPECIE_EXCEDENTE_EMPLOYER.verified,
                "note": f"sobre (SBC − 3 UMA) = ({sbc} − {excedente_threshold})",
            },
            {
                "branch": "em_dinero",
                "article": "107",
                "rate": K.EM_DINERO_EMPLOYER.value,
                "base": q2(sbc * n_days),
                "amount": q2(sbc * n_days * K.EM_DINERO_EMPLOYER.value),
                "verified": K.EM_DINERO_EMPLOYER.verified,
                "note": "70% de la cuota del 1%",
            },
            {
                "branch": "gastos_medicos_pensionados",
                "article": "25",
                "rate": K.GMP_EMPLOYER.value,
                "base": q2(sbc * n_days),
                "amount": q2(sbc * n_days * K.GMP_EMPLOYER.value),
                "verified": K.GMP_EMPLOYER.verified,
                "note": "",
            },
            {
                "branch": "invalidez_vida",
                "article": "147",
                "rate": K.IV_EMPLOYER.value,
                "base": q2(sbc * n_days),
                "amount": q2(sbc * n_days * K.IV_EMPLOYER.value),
                "verified": K.IV_EMPLOYER.verified,
                "note": "",
            },
            {
                "branch": "retiro",
                "article": "168 I",
                "rate": K.RETIRO_EMPLOYER.value,
                "base": q2(sbc * n_days),
                "amount": q2(sbc * n_days * K.RETIRO_EMPLOYER.value),
                "verified": K.RETIRO_EMPLOYER.verified,
                "note": "",
            },
            {
                "branch": "cesantia_vejez",
                "article": "168 II a)",
                "rate": cv_rate,
                "base": q2(sbc * n_days),
                "amount": q2(sbc * n_days * cv_rate),
                "verified": K.CV_EMPLOYER_TABLE_2026.verified,
                "note": f"tabla gradual 2026, rango {cv_label}",
            },
            {
                "branch": "guarderias",
                "article": "211",
                "rate": K.GUARDERIAS_EMPLOYER.value,
                "base": q2(sbc * n_days),
                "amount": q2(sbc * n_days * K.GUARDERIAS_EMPLOYER.value),
                "verified": K.GUARDERIAS_EMPLOYER.verified,
                "note": "",
            },
        ]
        total = q2(sum((b["amount"] for b in branches), Decimal("0")))
        any_unverified = any(not b["verified"] for b in branches)

        explain = Explain(
            summary=(
                f"Cuotas patronales IMSS: {total} {currency} por {n_days} días con SBC {sbc} {currency}"
                f"{' (verify)' if any_unverified else ''}. {NOT_ADVICE}"
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[
                K.SBC_CAP_UMA.citation,
                K.EM_ESPECIE_FIXED_UMA_RATE.citation,
                K.EM_DINERO_TOTAL.citation,
                K.GMP_EMPLOYER.citation,
                K.IV_EMPLOYER.citation,
                K.RETIRO_EMPLOYER.citation,
                K.CV_EMPLOYER_TABLE_FINAL.citation,
                K.GUARDERIAS_EMPLOYER.citation,
            ],
        )
        explain.add_step("SBC diario declarado", raw_sbc)
        explain.add_step(
            "Tope 25 UMA (art. 28)",
            ceiling,
            formula=f"25 × UMA {uma}" + (" — aplicado" if capped else " — no aplica"),
        )
        explain.add_step("SBC diario de cálculo", sbc)
        explain.add_step("Días del periodo", n_days)
        explain.add_step("UMA diaria 2026", uma, formula="INEGI, vigente desde 2026-02-01")
        for b in branches:
            explain.add_step(
                f"{b['branch']} (art. {b['article']})",
                b["amount"],
                formula=f"{_pct(b['rate'])} × {b['base']}"
                + (f" · {b['note']}" if b["note"] else "")
                + ("" if b["verified"] else " (verify)"),
            )
        explain.add_step("Total cuotas patronales", total)
        if any_unverified:
            explain.add_step(
                "Sin verificar",
                ", ".join(b["branch"] for b in branches if not b["verified"]),
                formula="ver docs/modules/rules-mx-nl.md",
            )
        result = RuleResult(value=Amount(amount=total, currency=currency), explain=explain)
        # Breakdown rides on the explain steps; callers that want it structured use ``breakdown()``.
        return result

    def breakdown(self, **inputs: Any) -> dict[str, Any]:
        """Same computation, returned per branch — used by the payroll module."""
        raw_sbc = q2(dec(inputs.get("sbc_daily")))
        sbc, ceiling, capped = capped_sbc(raw_sbc)
        n_days = dec(inputs.get("days", 30), "30")
        currency = inputs.get("currency", CURRENCY)
        result = self.compute(**inputs)
        rows = []
        for step in result.explain.steps:
            if "(art. " in step.label and step.label.split(" (art. ")[0] in _BRANCH_NAMES:
                rows.append(
                    {
                        "branch": step.label.split(" (art. ")[0],
                        "amount": {"amount": step.value, "currency": currency},
                        "formula": step.formula,
                    }
                )
        return {
            "sbc_daily": {"amount": str(sbc), "currency": currency},
            "sbc_capped": capped,
            "ceiling": {"amount": str(ceiling), "currency": currency},
            "days": str(n_days),
            "branches": rows,
            "total": result.value.model_dump(mode="json"),
            "explain": result.explain.model_dump(mode="json"),
        }


_BRANCH_NAMES = {
    "riesgos_trabajo",
    "em_especie_cuota_fija",
    "em_especie_excedente",
    "em_dinero",
    "gastos_medicos_pensionados",
    "invalidez_vida",
    "retiro",
    "cesantia_vejez",
    "guarderias",
}


def employee_imss_quotas(sbc_daily: Decimal, days: Decimal) -> dict[str, Decimal]:
    """Worker-side IMSS retentions (LSS arts. 25, 106 II, 107, 147, 168 II b) — the payroll deduction."""
    sbc, _ceiling, _capped = capped_sbc(q2(sbc_daily))
    excedente = max(sbc - q2(K.EM_EXCEDENTE_THRESHOLD_UMA.value * K.UMA_DAILY.value), Decimal("0"))
    return {
        "em_especie_excedente": q2(excedente * days * K.EM_ESPECIE_EXCEDENTE_EMPLOYEE.value),
        "em_dinero": q2(sbc * days * K.EM_DINERO_EMPLOYEE.value),
        "gastos_medicos_pensionados": q2(sbc * days * K.GMP_EMPLOYEE.value),
        "invalidez_vida": q2(sbc * days * K.IV_EMPLOYEE.value),
        "cesantia_vejez": q2(sbc * days * K.CV_EMPLOYEE.value),
    }


# --------------------------------------------------------------------------- INFONAVIT


class InfonavitEmployerRule:
    """INFONAVIT employer contribution — 5% of the same capped base as IMSS (LINFONAVIT art. 29 fr. II)."""

    id = "mx.infonavit.employer"
    version = "2026.1"
    jurisdiction = "MX"
    citation = K.INFONAVIT_EMPLOYER.citation
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        sbc_daily: Any = None,
        days: Any = 30,
        base: Any = None,
        currency: str = CURRENCY,
        **_: Any,
    ) -> RuleResult:
        rate = K.INFONAVIT_EMPLOYER.value
        if base not in (None, ""):
            amount_base = q2(dec(base))
            raw_sbc = capped = ceiling = None
            n_days = dec(days, "30")
        else:
            raw_sbc = q2(dec(sbc_daily))
            sbc, ceiling, capped = capped_sbc(raw_sbc)
            n_days = dec(days, "30")
            amount_base = q2(sbc * n_days)
        contribution = q2(amount_base * rate)

        explain = Explain(
            summary=(
                f"Aportación patronal INFONAVIT: {contribution} {currency} = {_pct(rate)} × {amount_base} "
                f"{currency}{K.INFONAVIT_EMPLOYER.mark}. {NOT_ADVICE}"
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[K.INFONAVIT_EMPLOYER.citation, K.SBC_CAP_UMA.citation],
        )
        if raw_sbc is not None:
            explain.add_step("SBC diario declarado", raw_sbc)
            explain.add_step(
                "Tope 25 UMA (LSS art. 28, aplicable por remisión del art. 29 fr. II)",
                ceiling,
                formula="aplicado" if capped else "no aplica",
            )
            explain.add_step("Días del periodo", n_days)
        explain.add_step("Base de aportación", amount_base)
        explain.add_step("Tasa (art. 29 fr. II)", _pct(rate) + K.INFONAVIT_EMPLOYER.mark)
        explain.add_step("Aportación", contribution, formula=f"{amount_base} × {rate}")
        explain.add_step(
            "Entero",
            "bimestral, junto con las cuotas de retiro, cesantía y vejez",
            formula="Aurum lo devenga mensualmente",
        )
        return RuleResult(value=Amount(amount=contribution, currency=currency), explain=explain)


isn_nl = registry.register(ISNNuevoLeonRule())
imss_employer_quotas = registry.register(IMSSEmployerQuotasRule())
infonavit_employer = registry.register(InfonavitEmployerRule())
