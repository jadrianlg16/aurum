"""RESICO persona física — ISR rules.

Three rules live here:

* ``mx.resico.income_cash_basis`` — which CFDIs count as income in a month (SAT's own prefill rules:
  PUE in the issue month, REP in the ``FechaPago`` month, PPD without REP not counted).
* ``mx.resico.isr_monthly`` — LISR art. 113-E: a *tiered flat* rate applied to the whole month's
  collected income excluding IVA, with **no deductions at all**.
* ``mx.resico.retention_pm`` — the 1.25% ISR withheld when the receptor is a persona moral
  (art. 113-J). Marked ``(verify)``: not read in the primary statute.

Nothing here is invented. Numbers that the spec does not pin are marked ``(verify)`` in the explain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ...core.explain import Citation, Explain
from ...core.money import Amount, q2
from ..registry import RuleResult, registry

LISR_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LISR.pdf"

CITATION_113E = Citation(
    law="LISR",
    article="113-E",
    url=LISR_URL,
    effective_from=date(2026, 1, 1),
    trust_tier="primary",
    excerpt=(
        "Pago mensual: tasa aplicada a la totalidad de los ingresos amparados por CFDI efectivamente "
        "cobrados en el mes, sin IVA y sin deducción alguna."
    ),
)
CITATION_113J = Citation(
    law="LISR",
    article="113-J",
    url=LISR_URL,
    effective_from=date(2026, 1, 1),
    trust_tier="primary",
    excerpt="Retención de ISR por personas morales que reciban servicios de contribuyentes del RESICO.",
)

# LISR art. 113-E monthly table (2026). Upper bound → flat rate on the WHOLE month's income.
ISR_TABLE: list[tuple[Decimal, Decimal]] = [
    (Decimal("25000.00"), Decimal("0.0100")),
    (Decimal("50000.00"), Decimal("0.0110")),
    (Decimal("83333.33"), Decimal("0.0150")),
    (Decimal("208333.33"), Decimal("0.0200")),
    (Decimal("3500000.00"), Decimal("0.0250")),
]
ANNUAL_CAP = Decimal("3500000.00")
RETENTION_PM_RATE = Decimal("0.0125")  # (verify) — art. 113-J not read in the primary text


def period_bounds(period: str) -> tuple[date, date]:
    """``"2026-08"`` → (2026-08-01, 2026-08-31)."""
    year, month = (int(x) for x in period.split("-")[:2])
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)
    return start, date.fromordinal(end.toordinal() - 1)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _dec(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    if isinstance(value, float):
        raise TypeError("money inputs must be Decimal/str/int, not float")
    return Decimal(str(value))


def _in_period(day: date | None, period: str) -> bool:
    start, end = period_bounds(period)
    return day is not None and start <= day <= end


# --------------------------------------------------------------------------- cash basis


@dataclass
class IncomeItem:
    uuid: str
    kind: str  # "pue" | "rep"
    fecha: date
    amount: Decimal  # net of IVA
    gross: Decimal  # as invoiced/paid, IVA included
    related_uuid: str | None = None
    note: str | None = None


@dataclass
class IncomeClassification:
    period: str
    collected: Decimal = Decimal("0")
    items: list[IncomeItem] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def uuids(self) -> list[str]:
        return [i.uuid for i in self.items]


def _net_of_iva(monto: Decimal, related: dict[str, Any] | None, pago: dict[str, Any]) -> tuple[Decimal, str | None]:
    """Net a payment amount of IVA. Prefer explicit fields, then the related invoice's ratio."""
    if pago.get("subtotal") is not None:
        return _dec(pago["subtotal"]), None
    if pago.get("iva") is not None:
        return monto - _dec(pago["iva"]), None
    if related:
        total = _dec(related.get("total"))
        subtotal = _dec(related.get("subtotal"))
        if total > 0 and subtotal > 0:
            return (monto * subtotal / total), None
    return monto, "IVA share unknown for this payment — amount taken gross (verify)"


def classify_income(documents: list[dict[str, Any]], period: str, ws_rfc: str | None = None) -> IncomeClassification:
    """SAT's cash-basis prefill rules over a list of CFDI-like dicts.

    PUE (tipo I/E, emitido) counts in the month it was issued; a payment complement (tipo P) counts in
    the month of each ``FechaPago``; a PPD invoice with no REP does not count at all.
    """
    out = IncomeClassification(period=period)
    by_uuid = {str(d.get("uuid")): d for d in documents if d.get("uuid")}
    emitidos = [
        d
        for d in documents
        if (d.get("direction") or "emitido") == "emitido"
        and (ws_rfc is None or not d.get("emisor_rfc") or str(d.get("emisor_rfc")) == ws_rfc)
    ]

    paid_ppd: dict[str, Decimal] = {}
    for doc in emitidos:
        if str(doc.get("tipo")) != "P":
            continue
        for pago in doc.get("pagos") or []:
            related_uuid = pago.get("uuid_relacionado")
            if related_uuid:
                paid_ppd[str(related_uuid)] = paid_ppd.get(str(related_uuid), Decimal("0")) + _dec(pago.get("monto"))
            fecha_pago = _as_date(pago.get("fecha_pago"))
            if not _in_period(fecha_pago, period):
                continue
            monto = _dec(pago.get("monto"))
            related = by_uuid.get(str(related_uuid)) if related_uuid else None
            net, note = _net_of_iva(monto, related, pago)
            if note:
                out.warnings.append(f"{doc.get('uuid')}: {note}")
            assert fecha_pago is not None
            out.items.append(
                IncomeItem(
                    uuid=str(doc.get("uuid")),
                    kind="rep",
                    fecha=fecha_pago,
                    amount=q2(net),
                    gross=q2(monto),
                    related_uuid=str(related_uuid) if related_uuid else None,
                    note=note,
                )
            )

    for doc in emitidos:
        tipo = str(doc.get("tipo"))
        if tipo not in {"I", "E"}:
            continue
        fecha = _as_date(doc.get("fecha"))
        metodo = doc.get("metodo_pago")
        sign = Decimal("-1") if tipo == "E" else Decimal("1")
        subtotal = _dec(doc.get("subtotal")) * sign
        if metodo == "PUE":
            if _in_period(fecha, period):
                assert fecha is not None
                out.items.append(
                    IncomeItem(
                        uuid=str(doc.get("uuid")),
                        kind="pue",
                        fecha=fecha,
                        amount=q2(subtotal),
                        gross=q2(_dec(doc.get("total")) * sign),
                    )
                )
        elif metodo == "PPD":
            if not paid_ppd.get(str(doc.get("uuid"))) and _in_period(fecha, period):
                out.excluded.append(
                    {
                        "uuid": str(doc.get("uuid")),
                        "reason": "ppd_missing_rep",
                        "amount": str(q2(subtotal)),
                        "gross": str(q2(_dec(doc.get("total")) * sign)),
                    }
                )
        elif _in_period(fecha, period):
            out.excluded.append(
                {
                    "uuid": str(doc.get("uuid")),
                    "reason": "unknown_metodo_pago",
                    "amount": str(q2(subtotal)),
                    "gross": str(q2(_dec(doc.get("total")) * sign)),
                }
            )
            out.warnings.append(f"{doc.get('uuid')}: metodo_pago missing — not counted (verify)")

    out.items.sort(key=lambda i: (i.fecha, i.uuid))
    out.collected = q2(sum((i.amount for i in out.items), Decimal("0")))
    return out


class IncomeCashBasisRule:
    """Collected RESICO income for a month under SAT's prefill rules (PUE / REP / PPD)."""

    id = "mx.resico.income_cash_basis"
    version = "2026.1"
    jurisdiction = "MX"
    citation = Citation(
        law="RMF 2026",
        article="prefill RESICO (CFDI de ingreso, egreso y complementos de pago)",
        url="https://www.sat.gob.mx/",
        effective_from=date(2026, 1, 1),
        trust_tier="official_guidance",
        excerpt=(
            "La declaración de RESICO se prellena con los CFDI: PUE en el mes de emisión, REP en el mes "
            "de la FechaPago; PPD sin REP no se considera cobrado."
        ),
    )
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        documents: list[dict[str, Any]] | None = None,
        period: str = "",
        rfc: str | None = None,
        currency: str = "MXN",
        **_: Any,
    ) -> RuleResult:
        if not period:
            raise ValueError("period ('YYYY-MM') is required")
        result = classify_income(list(documents or []), period, ws_rfc=rfc)
        explain = Explain(
            summary=(
                f"Ingreso efectivamente cobrado en {period}: {result.collected} {currency} "
                f"({len(result.items)} documento(s), IVA excluido)."
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation],
        )
        for item in result.items:
            label = "PUE emitido" if item.kind == "pue" else "REP (FechaPago)"
            explain.add_step(
                f"{label} {item.uuid}",
                item.amount,
                formula=f"{item.fecha.isoformat()} · bruto {item.gross} → sin IVA {item.amount}",
            )
        for ex in result.excluded:
            explain.add_step(f"excluido {ex['uuid']} ({ex['reason']})", ex["amount"])
        for warning in result.warnings:
            explain.add_step("aviso", warning)
        explain.add_step("Total cobrado", result.collected, formula="Σ PUE del mes + Σ REP del mes")
        return RuleResult(value=Amount(amount=result.collected, currency=currency), explain=explain)


class IsrMonthlyRule:
    """Monthly RESICO ISR: tiered flat rate on the month's collected income, no deductions (art. 113-E)."""

    id = "mx.resico.isr_monthly"
    version = "2026.1"
    jurisdiction = "MX"
    citation = CITATION_113E
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def rate_for(self, income: Decimal) -> tuple[Decimal, Decimal | None]:
        for upper, rate in ISR_TABLE:
            if income <= upper:
                return rate, upper
        return ISR_TABLE[-1][1], None

    def compute(
        self,
        collected_income: Decimal | str | int | None = None,
        currency: str = "MXN",
        **_: Any,
    ) -> RuleResult:
        if collected_income is None:
            raise ValueError("collected_income is required")
        income = q2(_dec(collected_income))
        if income < 0:
            raise ValueError("collected_income must not be negative")
        rate, upper = self.rate_for(income)
        isr = q2(income * rate)
        pct = f"{(rate * 100).normalize()}%"
        bracket = f"≤ {upper}" if upper is not None else f"> {ANNUAL_CAP} (fuera de tabla)"
        explain = Explain(
            summary=f"ISR RESICO del mes: {isr} {currency} = {income} × {pct} (sin deducciones).",
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation],
        )
        explain.add_step("Ingreso cobrado del mes (sin IVA)", income)
        explain.add_step("Deducciones aplicables", Decimal("0.00"), formula="art. 113-E: ninguna")
        explain.add_step("Tramo de la tabla mensual", bracket, formula="LISR art. 113-E (2026)")
        explain.add_step("Tasa aplicable", pct)
        explain.add_step("ISR del mes", isr, formula=f"{income} × {rate}")
        explain.add_step(
            "Fecha límite de pago",
            "día 17 del mes siguiente",
            formula="LISR art. 113-E",
        )
        if income > ANNUAL_CAP:
            explain.add_step(
                "Aviso",
                f"el ingreso del mes excede el tope anual de {ANNUAL_CAP} MXN del RESICO (verify)",
            )
        return RuleResult(value=Amount(amount=isr, currency=currency), explain=explain)


class RetentionPersonaMoralRule:
    """ISR withheld (1.25%) when the client is a persona moral — art. 113-J. Marked (verify)."""

    id = "mx.resico.retention_pm"
    version = "2026.1"
    jurisdiction = "MX"
    citation = CITATION_113J
    effective_from = date(2026, 1, 1)
    effective_to: date | None = None

    def compute(
        self,
        amount: Decimal | str | int | None = None,
        receptor_is_persona_moral: bool = True,
        currency: str = "MXN",
        **_: Any,
    ) -> RuleResult:
        if amount is None:
            raise ValueError("amount (income before IVA, paid by the persona moral) is required")
        base = q2(_dec(amount))
        withheld = q2(base * RETENTION_PM_RATE) if receptor_is_persona_moral else Decimal("0.00")
        explain = Explain(
            summary=(
                f"Retención de ISR: {withheld} {currency} (1.25% sobre {base}). "
                "(verify) — art. 113-J no confirmado en el texto primario."
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation],
            confidence=0.5,
        )
        explain.add_step("Base (ingreso sin IVA pagado por la persona moral)", base)
        explain.add_step("Receptor es persona moral", str(receptor_is_persona_moral))
        explain.add_step("Tasa de retención", "1.25% (verify)")
        explain.add_step("Retención", withheld, formula=f"{base} × {RETENTION_PM_RATE}")
        explain.add_step(
            "(verify)",
            "confirmar tasa, base y acreditamiento contra el pago mensual en LISR art. 113-J",
        )
        return RuleResult(value=Amount(amount=withheld, currency=currency), explain=explain)


income_cash_basis = registry.register(IncomeCashBasisRule())
isr_monthly = registry.register(IsrMonthlyRule())
retention_pm = registry.register(RetentionPersonaMoralRule())
