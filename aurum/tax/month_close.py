"""Month close: the month-close payload, assembled from rules + the prefill audit."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from ..core.explain import Explain
from ..core.i18n import t
from ..core.money import Amount, q2
from ..rules.mx.resico import period_bounds
from ..rules.registry import load_rules, registry
from .prefill import audit
from .sources import load_cfdis

DEADLINE_DAY = 17


def deadline_for(period: str) -> date:
    """LISR art. 113-E: the monthly payment is due by the 17th of the following month."""
    year, month = (int(x) for x in period.split("-")[:2])
    return date(year + (month == 12), (month % 12) + 1, DEADLINE_DAY)


def _amount(value: Decimal, currency: str) -> dict[str, str]:
    return Amount(amount=q2(value), currency=currency).model_dump(mode="json")


def _retentions(documents: list[dict[str, Any]], counted_uuids: set[str]) -> tuple[Decimal, Decimal]:
    """Retentions on the invoices whose income was counted this month.

    Heuristic: a REP is attributed the retentions of the invoice it pays. Partial payments are not
    pro-rated — ``(verify)`` once art. 113-J is read in the statute.
    """
    isr = Decimal("0")
    iva = Decimal("0")
    for doc in documents:
        if str(doc.get("uuid")) not in counted_uuids:
            continue
        if doc.get("isr_retenido") not in (None, ""):
            isr += Decimal(str(doc["isr_retenido"]))
        if doc.get("iva_retenido") not in (None, ""):
            iva += Decimal(str(doc["iva_retenido"]))
    return q2(isr), q2(iva)


def month_close(
    ws_id: str,
    period: str,
    documents: list[dict[str, Any]] | None = None,
    rfc: str | None = None,
    currency: str = "MXN",
    lang: str | None = None,
) -> dict[str, Any]:
    load_rules()
    on = period_bounds(period)[1]
    docs, _source = load_cfdis(ws_id, documents)

    income_rule = registry.get("mx.resico.income_cash_basis", on=on)
    isr_rule = registry.get("mx.resico.isr_monthly", on=on)
    iva_rule = registry.get("mx.iva.monthly", on=on)

    income_result = income_rule.compute(documents=docs, period=period, rfc=rfc, currency=currency)
    isr_result = isr_rule.compute(collected_income=income_result.value.amount, currency=currency)
    iva_result = iva_rule.compute(documents=docs, period=period, rfc=rfc, currency=currency)

    report = audit(ws_id, period, documents=docs, rfc=rfc, currency=currency, lang=lang)

    counted_uuids: set[str] = set()
    for item in report.income.items:
        counted_uuids.add(item.related_uuid or item.uuid)
    isr_retained, iva_retained = _retentions(docs, counted_uuids)

    warnings = list(report.warnings)
    if report.diffs:
        warnings.append(t("tax.warning_mismatch", lang))
    warnings.append(t("tax.warning_draft", lang))

    prefill_explain = Explain(
        summary=t(
            "tax.prefill_summary",
            lang,
            period=period,
            income=q2(report.prefill_income),
            isr=q2(report.prefill_isr),
            iva_acreditable=q2(report.prefill_iva_acreditable),
            currency=currency,
        ),
        rule_versions=[f"{isr_rule.id}@{isr_rule.version}", f"{income_rule.id}@{income_rule.version}"],
        citations=income_rule.citation and [income_rule.citation] or [],
    )
    prefill_explain.add_step(t("tax.prefill_step_income", lang), q2(report.prefill_income))
    prefill_explain.add_step(t("tax.prefill_step_isr", lang), q2(report.prefill_isr))
    prefill_explain.add_step(
        t("tax.prefill_step_iva", lang),
        q2(report.prefill_iva_acreditable),
        formula=t("tax.prefill_formula_iva", lang),
    )

    return {
        "period": period,
        "workspace": ws_id,
        "currency": currency,
        "income": {
            "collected": income_result.value.model_dump(mode="json"),
            "by_rule": [
                {
                    "rule": f"{income_rule.id}@{income_rule.version}",
                    "value": income_result.value.model_dump(mode="json"),
                }
            ],
            "explain": income_result.explain.model_dump(mode="json"),
        },
        "isr": {
            "value": isr_result.value.model_dump(mode="json"),
            "explain": isr_result.explain.model_dump(mode="json"),
        },
        "iva": {
            "trasladado": _amount(report.iva.trasladado, currency),
            "acreditable": _amount(report.iva.acreditable, currency),
            "payable": iva_result.value.model_dump(mode="json"),
            "explain": iva_result.explain.model_dump(mode="json"),
        },
        "retentions": {
            "isr": _amount(isr_retained, currency),
            "iva": _amount(iva_retained, currency),
        },
        "prefill_expected": {
            "income": _amount(report.prefill_income, currency),
            "isr": _amount(report.prefill_isr, currency),
            "iva_acreditable": _amount(report.prefill_iva_acreditable, currency),
            "explain": prefill_explain.model_dump(mode="json"),
        },
        "diffs": [d.as_json(currency) for d in report.diffs],
        "deadline": deadline_for(period).isoformat(),
        "status": "draft",
        "warnings": warnings,
    }
