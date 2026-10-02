"""IVA mensual (MX) — trasladado − acreditable, with the LIVA art. 5 credit checks.

IVA is a cash-basis tax: IVA *trasladado* is owed on what was effectively collected in the month
(same PUE/REP/PPD classification as RESICO income), and IVA *acreditable* only exists for expense
CFDIs that satisfy LIVA art. 5 — actually paid, paid by a traceable means, the RFC on the invoice is
ours, and the CFDI's `UsoCFDI` is one we allow.

**Documented heuristics** (both marked ``(verify)`` in the explain):

* *Bank-traceable payment* — ``forma_pago`` ``"01"`` is efectivo and fails the traceability test;
  every other code is treated as traceable. Codes 02/03/04/28 (cheque, transferencia, tarjetas) are
  the clean cases; the long tail (compensación 17, etc.) is accepted here and flagged.
* *Fixed assets* — the CFDI's ``UsoCFDI`` is our only signal. ``G01``/``G03`` (mercancías / gastos en
  general) are treated as ordinary expenses; ``I01``–``I08`` (construcciones, mobiliario, equipo de
  cómputo, …) are treated as **inversiones**, which is what the SAT prefill silently leaves out of
  IVA acreditable. Note the law does allow crediting IVA on investments — this exclusion mirrors the
  prefill's behaviour and is surfaced as a difference, not as tax advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ...core.explain import Citation, Explain
from ...core.money import Amount, q2
from ..registry import RuleResult, registry
from .resico import _as_date, _dec, _in_period, classify_income

LIVA_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LIVA.pdf"

CITATION_LIVA_5 = Citation(
    law="LIVA",
    article="5",
    url=LIVA_URL,
    effective_from=date(2026, 1, 1),
    trust_tier="primary",
    excerpt=(
        "Para que sea acreditable el IVA: que corresponda a bienes o servicios estrictamente "
        "indispensables, que conste por separado en el CFDI y que haya sido efectivamente pagado."
    ),
)

CASH_FORMA_PAGO = "01"
ALLOWED_USO_CFDI = {"G01", "G03"}
FIXED_ASSET_USO_PREFIX = "I0"


@dataclass
class CreditItem:
    uuid: str
    iva: Decimal
    fecha: date | None
    uso_cfdi: str | None
    forma_pago: str | None


@dataclass
class IvaClassification:
    period: str
    trasladado: Decimal = Decimal("0")
    acreditable: Decimal = Decimal("0")
    credited: list[CreditItem] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)

    def excluded_by(self, reason: str) -> list[dict[str, Any]]:
        return [e for e in self.excluded if e["reason"] == reason]


def _is_paid(doc: dict[str, Any], all_docs: list[dict[str, Any]]) -> bool:
    """A received CFDI is 'paid' when it is PUE, or PPD with a payment complement referring to it."""
    metodo = doc.get("metodo_pago")
    if metodo == "PUE":
        return True
    if doc.get("paid") is True:
        return True
    uuid = str(doc.get("uuid"))
    for other in all_docs:
        if str(other.get("tipo")) != "P":
            continue
        for pago in other.get("pagos") or []:
            if str(pago.get("uuid_relacionado")) == uuid:
                return True
    return False


def _doc_iva(doc: dict[str, Any]) -> Decimal:
    if doc.get("iva_trasladado") is not None:
        return _dec(doc["iva_trasladado"])
    if doc.get("iva") is not None:
        return _dec(doc["iva"])
    if doc.get("impuestos_trasladados") is not None:
        return _dec(doc["impuestos_trasladados"])
    return q2(_dec(doc.get("total")) - _dec(doc.get("subtotal")))


def classify_iva(
    documents: list[dict[str, Any]],
    period: str,
    rfc: str | None = None,
) -> IvaClassification:
    out = IvaClassification(period=period)

    income = classify_income(documents, period, ws_rfc=rfc)
    out.trasladado = q2(sum((item.gross - item.amount for item in income.items), Decimal("0")))

    recibidos = [d for d in documents if (d.get("direction") or "") == "recibido"]
    for doc in recibidos:
        if str(doc.get("tipo")) not in {"I", "E"}:
            continue
        fecha = _as_date(doc.get("fecha"))
        if not _in_period(fecha, period):
            continue
        uuid = str(doc.get("uuid"))
        iva = q2(_doc_iva(doc))
        uso = doc.get("uso_cfdi")
        forma = doc.get("forma_pago")
        base = {
            "uuid": uuid,
            "amount": str(iva),
            "total": str(q2(_dec(doc.get("total")))),
            "uso_cfdi": uso,
            "forma_pago": forma,
        }
        if rfc and doc.get("receptor_rfc") and str(doc["receptor_rfc"]) != rfc:
            out.excluded.append({**base, "reason": "rfc_mismatch"})
            continue
        if not _is_paid(doc, documents):
            out.excluded.append({**base, "reason": "not_paid"})
            continue
        if str(forma) == CASH_FORMA_PAGO:
            out.excluded.append({**base, "reason": "cash_paid_expense"})
            continue
        if uso and str(uso).startswith(FIXED_ASSET_USO_PREFIX):
            out.excluded.append({**base, "reason": "fixed_asset_iva"})
            continue
        if uso is not None and str(uso) not in ALLOWED_USO_CFDI:
            out.excluded.append({**base, "reason": "uso_cfdi_not_allowed"})
            continue
        if iva <= 0:
            out.excluded.append({**base, "reason": "no_iva_on_document"})
            continue
        out.credited.append(CreditItem(uuid=uuid, iva=iva, fecha=fecha, uso_cfdi=uso, forma_pago=forma))

    out.acreditable = q2(sum((c.iva for c in out.credited), Decimal("0")))
    return out


class IvaMonthlyRule:
    """IVA a cargo del mes = IVA trasladado cobrado − IVA acreditable (LIVA art. 5)."""

    id = "mx.iva.monthly"
    version = "2026.1"
    jurisdiction = "MX"
    citation = CITATION_LIVA_5
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
        result = classify_iva(list(documents or []), period, rfc=rfc)
        payable = q2(result.trasladado - result.acreditable)
        explain = Explain(
            summary=(
                f"IVA de {period}: trasladado {result.trasladado} − acreditable {result.acreditable} "
                f"= {payable} {currency}" + (" (saldo a favor)" if payable < 0 else " a cargo")
            ),
            rule_versions=[f"{self.id}@{self.version}"],
            citations=[self.citation],
        )
        explain.add_step("IVA trasladado (sobre lo cobrado)", result.trasladado, formula="Σ (bruto − neto) PUE/REP")
        for item in result.credited:
            explain.add_step(
                f"IVA acreditable {item.uuid}",
                item.iva,
                formula=f"uso {item.uso_cfdi} · forma de pago {item.forma_pago}",
            )
        for ex in result.excluded:
            explain.add_step(f"no acreditable {ex['uuid']} ({ex['reason']})", ex["amount"])
        explain.add_step("IVA acreditable", result.acreditable)
        explain.add_step("IVA a cargo", payable, formula=f"{result.trasladado} − {result.acreditable}")
        explain.add_step(
            "(verify)",
            "heurísticas: forma_pago 01 = efectivo (no rastreable); UsoCFDI I0x = inversión",
        )
        return RuleResult(value=Amount(amount=payable, currency=currency), explain=explain)


monthly = registry.register(IvaMonthlyRule())
