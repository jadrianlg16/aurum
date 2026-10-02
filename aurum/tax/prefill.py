"""Prefill audit — the MX wedge.

SAT already pre-fills the RESICO declaration from CFDIs. Aurum computes the same figures
independently, predicts what the prefill will show, and then explains every difference against
*reality* — where reality means the bank lines in the ledger, not the XML.

The five differences we can produce from a month of CFDIs + bank lines:

``pue_not_collected``    a PUE invoice SAT counts as income that never arrived in the bank.
``ppd_missing_rep``      a PPD invoice with no payment complement — SAT counts nothing, so the
                         income is invisible until the REP is issued.
``deposit_without_cfdi`` money in the bank with no CFDI behind it (RESICO income must be invoiced).
``cash_paid_expense``    an expense paid in efectivo — IVA not creditable (LIVA art. 5).
``fixed_asset_iva``      IVA on an investment/fixed asset, which the prefill leaves out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ..core.explain import Citation, Explain
from ..core.i18n import t
from ..core.money import Amount, q2
from ..rules.mx.iva import classify_iva
from ..rules.mx.resico import IncomeClassification, classify_income, period_bounds
from ..rules.registry import load_rules, registry
from .sources import BankLine, bank_lines, load_cfdis

MATCH_TOLERANCE = Decimal("0.50")

PREFILL_CITATION = Citation(
    law="RMF 2026",
    article="declaración prellenada RESICO",
    url="https://www.sat.gob.mx/",
    trust_tier="official_guidance",
    excerpt=(
        "Desde 2023 la declaración mensual de RESICO se prellena con los CFDI de ingreso, egreso y "
        "los complementos de pago; el prellenado supone cobrada toda factura PUE."
    ),
)


@dataclass
class Diff:
    kind: str
    amount: Decimal
    documents: list[str]
    explain: Explain

    def as_json(self, currency: str = "MXN") -> dict[str, Any]:
        return {
            "kind": self.kind,
            "amount": Amount(amount=self.amount, currency=currency).model_dump(mode="json"),
            "documents": self.documents,
            "explain": self.explain.model_dump(mode="json"),
        }


@dataclass
class PrefillAudit:
    ws_id: str
    period: str
    currency: str
    source: str
    income: IncomeClassification
    iva: Any
    prefill_income: Decimal
    prefill_isr: Decimal
    prefill_iva_acreditable: Decimal
    diffs: list[Diff] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    matched_deposits: list[BankLine] = field(default_factory=list)
    unmatched_deposits: list[BankLine] = field(default_factory=list)

    def diff(self, kind: str) -> Diff | None:
        return next((d for d in self.diffs if d.kind == kind), None)


def _explain(summary: str, steps: list[tuple[str, Any]], rule_versions: list[str] | None = None) -> Explain:
    ex = Explain(summary=summary, citations=[PREFILL_CITATION], rule_versions=rule_versions or [])
    for label, value in steps:
        ex.add_step(label, value)
    return ex


def audit(
    ws_id: str,
    period: str,
    documents: list[dict[str, Any]] | None = None,
    rfc: str | None = None,
    currency: str = "MXN",
    lang: str | None = None,
) -> PrefillAudit:
    load_rules()
    docs, source = load_cfdis(ws_id, documents)
    income = classify_income(docs, period, ws_rfc=rfc)
    iva = classify_iva(docs, period, rfc=rfc)

    isr_rule = registry.get("mx.resico.isr_monthly", on=period_bounds(period)[1])
    prefill_isr = isr_rule.compute(collected_income=income.collected, currency=currency).value.amount

    result = PrefillAudit(
        ws_id=ws_id,
        period=period,
        currency=currency,
        source=source,
        income=income,
        iva=iva,
        prefill_income=income.collected,
        prefill_isr=prefill_isr,
        prefill_iva_acreditable=iva.acreditable,
        warnings=list(income.warnings),
    )

    deposits = [line for line in bank_lines(ws_id, period) if line.amount > 0 and not line.is_opening]
    used: set[int] = set()
    uncollected = []
    for item in income.items:
        wanted = {item.uuid, item.related_uuid} - {None}
        match_index = next(
            (i for i, line in enumerate(deposits) if i not in used and line.cfdi_uuid in wanted),
            None,
        )
        if match_index is None:
            match_index = next(
                (
                    i
                    for i, line in enumerate(deposits)
                    if i not in used and line.cfdi_uuid is None and abs(line.amount - item.gross) <= MATCH_TOLERANCE
                ),
                None,
            )
        if match_index is None:
            if item.kind == "pue":
                uncollected.append(item)
            continue
        used.add(match_index)
        result.matched_deposits.append(deposits[match_index])

    result.unmatched_deposits = [line for i, line in enumerate(deposits) if i not in used]

    if uncollected:
        total = q2(sum((i.gross for i in uncollected), Decimal("0")))
        result.diffs.append(
            Diff(
                kind="pue_not_collected",
                amount=total,
                documents=[i.uuid for i in uncollected],
                explain=_explain(
                    t("tax.diff.pue_not_collected", lang, count=len(uncollected), total=total, currency=currency),
                    [(f"PUE sin depósito {i.uuid}", i.gross) for i in uncollected]
                    + [("Total", total)],
                ),
            )
        )

    missing_rep = [e for e in income.excluded if e["reason"] == "ppd_missing_rep"]
    if missing_rep:
        total = q2(sum((Decimal(e["gross"]) for e in missing_rep), Decimal("0")))
        result.diffs.append(
            Diff(
                kind="ppd_missing_rep",
                amount=total,
                documents=[e["uuid"] for e in missing_rep],
                explain=_explain(
                    t("tax.diff.ppd_missing_rep", lang, count=len(missing_rep), total=total, currency=currency),
                    [(f"PPD sin REP {e['uuid']}", e["gross"]) for e in missing_rep] + [("Total", total)],
                ),
            )
        )

    if result.unmatched_deposits:
        total = q2(sum((line.amount for line in result.unmatched_deposits), Decimal("0")))
        result.diffs.append(
            Diff(
                kind="deposit_without_cfdi",
                amount=total,
                documents=[],
                explain=_explain(
                    t(
                        "tax.diff.deposit_without_cfdi",
                        lang,
                        count=len(result.unmatched_deposits),
                        total=total,
                        currency=currency,
                    ),
                    [
                        (f"{line.date.isoformat()} {line.payee or line.narration}", line.amount)
                        for line in result.unmatched_deposits
                    ]
                    + [("Total", total)],
                ),
            )
        )

    for kind, i18n_key in (
        ("cash_paid_expense", "tax.diff.cash_paid_expense"),
        ("fixed_asset_iva", "tax.diff.fixed_asset_iva"),
    ):
        rows = iva.excluded_by(kind)
        if not rows:
            continue
        total = q2(sum((Decimal(r["amount"]) for r in rows), Decimal("0")))
        result.diffs.append(
            Diff(
                kind=kind,
                amount=total,
                documents=[r["uuid"] for r in rows],
                explain=_explain(
                    t(i18n_key, lang, total=total, currency=currency),
                    [(f"{r['uuid']} (uso {r['uso_cfdi']}, forma {r['forma_pago']})", r["amount"]) for r in rows]
                    + [("Total", total)],
                ),
            )
        )

    return result
