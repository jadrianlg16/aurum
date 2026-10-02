"""Régimen General (Actividad Empresarial y Profesional) — ISR "pagos provisionales".

One rule lives here:

* ``mx.general.isr_provisional`` — LISR art. 106 (personas físicas con actividad empresarial y
  profesional): the provisional payment for a period is computed on the **cumulative** taxable base for
  the year (cumulative income minus cumulative authorized deductions, LISR art. 105) run through the
  **cumulative monthly** Tarifa art. 96 table (i.e. the single-month table's cuota fija/tasa scaled by
  the number of elapsed months), minus prior provisional payments already made and any ISR retentions
  withheld by clients in the period.

Unlike RESICO (``mx.resico.isr_monthly``), this regime **does** allow deductions.

## Verification status of the 2026 monthly table

``ISR_TABLE_MONTHLY_2026`` below is **verified** against a primary source: it reproduces table **"A.V —
Tarifa aplicable durante 2026 para el cálculo de los pagos provisionales mensuales a que se refieren los
artículos 96 de la Ley del ISR y 175 de su Reglamento"** from **Anexo 8 de la Resolución Miscelánea
Fiscal para 2026**, published in the Diario Oficial de la Federación on **2026-12-28** (yes, the DOF
publication for the *2026* fiscal year table was itself published 2025-12-28 — that is normal: SAT
publishes each year's monthly tariff shortly before the year starts).

* Source: SAT, "ANEXO 8 DE LA RESOLUCIÓN MISCELÁNEA FISCAL PARA 2026", section A.V.
  URL: https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rmf/anexos/Anexo-8-RMF-2026_DOF-28122025.pdf
  Also published in DOF: Domingo 28 de diciembre de 2025, "PODER EJECUTIVO — SECRETARIA DE HACIENDA Y
  CREDITO PUBLICO — Anexos 4, 5, 6, 8, 15 y 25 de la Resolución Miscelánea Fiscal para 2026".
* Accessed: 2026-09-06, by fetching the PDF directly and reading table A.V on its page 5.
* ``verified = True`` on the citation and on the rule's ``TABLE_VERIFIED`` flag.

If SAT republishes a corrected Anexo 8, or a future year's table is needed, add a new dated bracket set
and register a new rule **version** (do not mutate this one) per the rule registry's versioning contract.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from ...core.explain import Citation, Explain
from ...core.money import Amount, q2
from ..registry import RuleResult, registry

ANEXO8_URL = (
    "https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rmf/anexos/"
    "Anexo-8-RMF-2026_DOF-28122025.pdf"
)

TABLE_VERIFIED = True
TABLE_ACCESSED = date(2026, 9, 6)

CITATION_ART_96 = Citation(
    law="LISR",
    article="96 (Anexo 8 RMF 2026, tabla A.V)",
    url=ANEXO8_URL,
    effective_from=date(2026, 1, 1),
    trust_tier="primary",
    excerpt=(
        "Tarifa aplicable durante 2026 para el cálculo de los pagos provisionales mensuales a que se "
        "refieren los artículos 96 de la Ley del ISR y 175 de su Reglamento, así como la regla 3.12.2 "
        "(DOF 28/12/2025)."
    ),
)
CITATION_ART_106 = Citation(
    law="LISR",
    article="106",
    url="https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf",
    effective_from=date(2026, 1, 1),
    trust_tier="primary",
    excerpt=(
        "Personas físicas con actividad empresarial y profesional: pago provisional mensual sobre la "
        "utilidad fiscal acumulada del ejercicio (ingresos acumulados menos deducciones autorizadas "
        "acumuladas), aplicando la tarifa acumulada al periodo, disminuyendo pagos provisionales "
        "anteriores y retenciones."
    ),
)

# LISR art. 96 monthly bracket table for 2026 (single month; scaled ×N for a cumulative N-month period).
# Each row: (upper_limit_of_bracket, cuota_fija, rate_over_excess). VERIFIED — see module docstring.
ISR_TABLE_MONTHLY_2026: list[tuple[Decimal, Decimal, Decimal]] = [
    (Decimal("844.59"), Decimal("0.00"), Decimal("0.0192")),
    (Decimal("7168.51"), Decimal("16.22"), Decimal("0.0640")),
    (Decimal("12598.02"), Decimal("420.95"), Decimal("0.1088")),
    (Decimal("14644.64"), Decimal("1011.68"), Decimal("0.1600")),
    (Decimal("17533.64"), Decimal("1339.14"), Decimal("0.1792")),
    (Decimal("35362.83"), Decimal("1856.84"), Decimal("0.2136")),
    (Decimal("55736.68"), Decimal("5665.16"), Decimal("0.2352")),
    (Decimal("106410.50"), Decimal("10457.09"), Decimal("0.3000")),
    (Decimal("141880.66"), Decimal("25659.23"), Decimal("0.3200")),
    (Decimal("425641.99"), Decimal("37009.69"), Decimal("0.3400")),
    (None, Decimal("133488.54"), Decimal("0.3500")),  # "en adelante"
]


def _dec(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    if isinstance(value, float):
        raise TypeError("money inputs must be Decimal/str/int, not float")
    return Decimal(str(value))


def cumulative_table_for_month(month_number: int) -> list[tuple[Decimal | None, Decimal, Decimal]]:
    """Scale the single-month table ×``month_number`` for a period ending in that calendar month.

    LISR art. 96's mechanic: the monthly tariff's limits and cuota fija scale linearly with the number
    of months elapsed in the fiscal year (rates stay the same); e.g. month 3 uses 3× the monthly limits
    and 3× the monthly cuota fija.
    """
    if month_number < 1 or month_number > 12:
        raise ValueError("month_number must be 1..12")
    n = Decimal(month_number)
    scaled: list[tuple[Decimal | None, Decimal, Decimal]] = []
    for upper, cuota, rate in ISR_TABLE_MONTHLY_2026:
        scaled.append((upper * n if upper is not None else None, cuota * n, rate))
    return scaled


def apply_table(base: Decimal, table: list[tuple[Decimal | None, Decimal, Decimal]]) -> tuple[Decimal, Decimal, Decimal | None]:
    """Return (tax, rate, bracket_upper) for ``base`` under a limite-inferior/cuota-fija/tasa table."""
    prev_upper = Decimal("0")
    for upper, cuota, rate in table:
        if upper is None or base <= upper:
            excedente = base - prev_upper
            return cuota + excedente * rate, rate, upper
        prev_upper = upper
    # unreachable: last row has upper=None
    upper, cuota, rate = table[-1]
    return cuota + (base - prev_upper) * rate, rate, None


class IsrProvisionalRule:
    """Actividad Empresarial y Profesional — pago provisional mensual acumulado (LISR art. 106).

    Inputs:
      cumulative_income: ingresos acumulados del ejercicio a la fecha (sin IVA).
      cumulative_deductions: deducciones autorizadas acumuladas del ejercicio a la fecha.
      month_number: mes del periodo (1..12), para escalar la tarifa acumulada.
      prior_provisional_payments: suma de pagos provisionales de ISR ya enterados en el ejercicio.
      retentions: ISR retenido por clientes (personas morales) en el periodo, acumulado.
    """

    id = "mx.general.isr_provisional"
    version = "2026.1"
    jurisdiction = "MX"
    citation = CITATION_ART_106
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None
    verified: bool = TABLE_VERIFIED  # the 2026 monthly table itself is verified against Anexo 8 RMF 2026

    def compute(
        self,
        cumulative_income: Decimal | str | int | None = None,
        cumulative_deductions: Decimal | str | int | None = None,
        month_number: int | None = None,
        prior_provisional_payments: Decimal | str | int | None = None,
        retentions: Decimal | str | int | None = None,
        currency: str = "MXN",
        **_: Any,
    ) -> RuleResult:
        if cumulative_income is None:
            raise ValueError("cumulative_income is required")
        if month_number is None:
            raise ValueError("month_number (1..12) is required")
        income = q2(_dec(cumulative_income))
        deductions = q2(_dec(cumulative_deductions))
        prior = q2(_dec(prior_provisional_payments))
        withheld = q2(_dec(retentions))

        base = max(Decimal("0.00"), income - deductions)
        table = cumulative_table_for_month(int(month_number))
        tax_before_credits, rate, upper = apply_table(base, table)
        tax_before_credits = q2(tax_before_credits)
        payment_due = max(Decimal("0.00"), q2(tax_before_credits - prior - withheld))

        pct = f"{(rate * 100).normalize()}%"
        bracket = f"≤ {upper}" if upper is not None else "en adelante"
        explain = Explain(
            summary=(
                f"Pago provisional (mes {month_number}): {payment_due} {currency} "
                f"= ISR s/tarifa acumulada ({tax_before_credits}) − pagos previos ({prior}) "
                f"− retenciones ({withheld})."
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[CITATION_ART_106, CITATION_ART_96],
            confidence=None if TABLE_VERIFIED else 0.5,
        )
        explain.add_step("Ingresos acumulados", income)
        explain.add_step("Deducciones autorizadas acumuladas", deductions)
        explain.add_step("Base gravable (utilidad fiscal acumulada)", base, formula="ingresos − deducciones")
        explain.add_step(
            "Tarifa acumulada aplicable",
            bracket,
            formula=f"LISR art. 96 (Anexo 8 RMF 2026) × {month_number} mes(es)"
            + ("" if TABLE_VERIFIED else " (verify)"),
        )
        explain.add_step("Tasa marginal", pct)
        explain.add_step("ISR según tarifa acumulada", tax_before_credits, formula=f"cuota fija + excedente × {pct}")
        explain.add_step("Pagos provisionales anteriores del ejercicio", prior)
        explain.add_step("Retenciones de ISR del periodo", withheld)
        explain.add_step(
            "Pago provisional a enterar",
            payment_due,
            formula="ISR acumulado − pagos previos − retenciones (mínimo 0)",
        )
        if not TABLE_VERIFIED:
            explain.add_step(
                "(verify)",
                "confirmar la tabla mensual del ejercicio vigente contra el Anexo 8 de la RMF publicado en el DOF",
            )
        return RuleResult(value=Amount(amount=payment_due, currency=currency), explain=explain)


isr_provisional = registry.register(IsrProvisionalRule())

__all__ = [
    "ANEXO8_URL",
    "CITATION_ART_96",
    "CITATION_ART_106",
    "ISR_TABLE_MONTHLY_2026",
    "TABLE_ACCESSED",
    "TABLE_VERIFIED",
    "IsrProvisionalRule",
    "apply_table",
    "cumulative_table_for_month",
    "isr_provisional",
]
