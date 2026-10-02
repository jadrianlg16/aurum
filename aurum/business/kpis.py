"""Business KPIs for a period: revenue, gross margin, opex by group, runway, AR/AP, tax reserve.

Every figure is read from the ledger (the ledger is the truth) and carries an ``Explain``.
The account-group contract is the one the business chart templates establish:

* ``Income:*``            — revenue (booked negative in Beancount, reported positive here)
* ``Expenses:COGS:*``     — cost of goods sold
* ``Expenses:Payroll:*``  — payroll cost (reported as its own group, and inside opex totals)
* ``Expenses:Opex:*``     — operating expenses, one group per second-to-last segment
* ``Assets:Bank:*``, ``Assets:Cash`` — cash for the runway
* ``Assets:Receivable:*``, ``Liabilities:Payable:*`` — AR / AP

The tax reserve calls :func:`aurum.tax.month_close.month_close` **in process** when the workspace is
MX; if the tax module is not installed the reserve degrades to the ledger's own IVA/ISR liability
balances and says so.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta

from ..core.explain import Explain
from ..core.i18n import t
from ..core.money import q2
from ..core.workspaces import WorkspaceNotFound, get_workspace
from ..ledger.base import get_ledger

CURRENCY = "MXN"
RUNWAY_LOOKBACK_MONTHS = 3


def period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(x) for x in period.split("-"))
    start = date(year, month, 1)
    return start, start + relativedelta(months=1) - relativedelta(days=1)


def prev_period(period: str) -> str:
    year, month = (int(x) for x in period.split("-"))
    return (date(year, month, 1) - relativedelta(months=1)).strftime("%Y-%m")


def _flows(ws_id: str, start: date, end: date) -> dict[str, Decimal]:
    """Signed movement per account in the window (Beancount sign convention preserved)."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for txn in get_ledger().journal(ws_id, start=start, end=end):
        for p in txn.postings:
            if p.amount is None:
                continue
            totals[p.account] += p.amount.amount
    return totals


def _sum_prefix(flows: dict[str, Decimal], prefix: str, sign: int = 1) -> Decimal:
    return q2(sum((v for a, v in flows.items() if a.startswith(prefix)), Decimal("0")) * sign)


def _group(account: str, prefix: str) -> str:
    """``Expenses:Opex:Rent`` under prefix ``Expenses:Opex:`` -> ``Rent``."""
    tail = account[len(prefix) :] if account.startswith(prefix) else account
    return tail.split(":")[0] or account


def _workspace_profile(ws_id: str) -> tuple[str, bool, str]:
    """(base currency, is a MX workspace, declared tax regime)."""
    try:
        ws = get_workspace(ws_id)
    except WorkspaceNotFound:
        return CURRENCY, True, ""
    regime = str((ws.profile or {}).get("regime") or "")
    return ws.base_currency or CURRENCY, "MX" in (ws.jurisdictions or []), regime


def kpis(ws_id: str, period: str, currency: str | None = None, lang: str = "es") -> dict[str, Any]:
    start, end = period_bounds(period)
    ws_currency, is_mx, regime = _workspace_profile(ws_id)
    currency = currency or ws_currency
    flows = _flows(ws_id, start, end)

    revenue = _sum_prefix(flows, "Income:", sign=-1)
    cogs = _sum_prefix(flows, "Expenses:COGS:")
    payroll = _sum_prefix(flows, "Expenses:Payroll:")
    opex_total = q2(
        sum(
            (v for a, v in flows.items() if a.startswith("Expenses:") and not a.startswith("Expenses:COGS:")),
            Decimal("0"),
        )
    )
    gross_profit = q2(revenue - cogs)
    gross_margin = (gross_profit / revenue).quantize(Decimal("0.0001")) if revenue > 0 else None
    operating_profit = q2(gross_profit - opex_total)

    opex_by_group: dict[str, Decimal] = defaultdict(Decimal)
    for account, value in flows.items():
        if not account.startswith("Expenses:") or account.startswith("Expenses:COGS:"):
            continue
        if account.startswith("Expenses:Opex:"):
            opex_by_group[_group(account, "Expenses:Opex:")] += value
        elif account.startswith("Expenses:Payroll:"):
            opex_by_group["Payroll"] += value
        else:
            opex_by_group[_group(account, "Expenses:")] += value

    balances = get_ledger().balances(ws_id, as_of=end)

    def balance_of(prefix: str, sign: int = 1) -> Decimal:
        total = Decimal("0")
        for account, amounts in balances.items():
            if not account.startswith(prefix):
                continue
            for amount in amounts:
                if amount.currency == currency:
                    total += amount.amount
        result = q2(total * sign)
        return result + Decimal("0") if result != 0 else Decimal("0.00")

    cash = q2(balance_of("Assets:Bank:") + balance_of("Assets:Cash"))
    receivables = balance_of("Assets:Receivable:")
    payables = balance_of("Liabilities:Payable:", sign=-1)

    burn, burn_months = _average_burn(ws_id, period, currency)
    runway = (cash / burn).quantize(Decimal("0.1")) if burn > 0 else None

    reserve = tax_reserve(ws_id, period, currency, is_mx, balances, regime=regime, lang=lang)

    na = t("business.kpis.gross_margin.na", lang)
    return {
        "workspace": ws_id,
        "period": period,
        "currency": currency,
        "revenue": _figure(
            revenue,
            currency,
            t("business.kpis.revenue.label", lang),
            [(t("business.kpis.revenue.step", lang), revenue, None)],
            lang,
        ),
        "cogs": _figure(cogs, currency, t("business.kpis.cogs.label", lang), [(t("business.kpis.cogs.step", lang), cogs, None)], lang),
        "gross_profit": _figure(
            gross_profit,
            currency,
            t("business.kpis.gross_profit.label", lang),
            [(t("business.kpis.gross_profit.step", lang), gross_profit, f"{revenue} − {cogs}")],
            lang,
        ),
        "gross_margin": {
            "value": str(gross_margin) if gross_margin is not None else None,
            "percent": str((gross_margin * 100).quantize(Decimal("0.01"))) if gross_margin is not None else None,
            "explain": _explain(
                t("business.kpis.gross_margin.label", lang)
                + (f" {(gross_margin * 100).quantize(Decimal('0.01'))}%" if gross_margin is not None else f" {na}"),
                [(t("business.kpis.gross_margin.step", lang), gross_margin if gross_margin is not None else na, f"{gross_profit} ÷ {revenue}")],
            ),
        },
        "operating_expenses": {
            "total": {"amount": str(opex_total), "currency": currency},
            "by_group": [
                {"group": name, "amount": {"amount": str(q2(value)), "currency": currency}}
                for name, value in sorted(opex_by_group.items(), key=lambda kv: kv[1], reverse=True)
            ],
            "payroll": {"amount": str(payroll), "currency": currency},
            "explain": _explain(
                t("business.kpis.opex.summary", lang, total=opex_total, currency=currency),
                [
                    (t("business.kpis.opex.group_step", lang, name=n), q2(v), None)
                    for n, v in sorted(opex_by_group.items(), key=lambda kv: kv[1], reverse=True)
                ],
            ),
        },
        "operating_profit": _figure(
            operating_profit,
            currency,
            t("business.kpis.operating_profit.label", lang),
            [(t("business.kpis.operating_profit.step", lang), operating_profit, f"{gross_profit} − {opex_total}")],
            lang,
        ),
        "cash": _figure(cash, currency, t("business.kpis.cash.label", lang), [(t("business.kpis.cash.step", lang), cash, None)], lang),
        "receivables": _figure(
            receivables, currency, t("business.kpis.receivables.label", lang), [(t("business.kpis.receivables.step", lang), receivables, None)], lang
        ),
        "payables": _figure(
            payables, currency, t("business.kpis.payables.label", lang), [(t("business.kpis.payables.step", lang), payables, None)], lang
        ),
        "runway": {
            "months": str(runway) if runway is not None else None,
            "average_burn": {"amount": str(burn), "currency": currency},
            "lookback_months": burn_months,
            "explain": _explain(
                t("business.kpis.runway.summary", lang, months=runway) if runway is not None else t("business.kpis.runway.na", lang),
                [
                    (t("business.kpis.runway.step.cash", lang), cash, None),
                    (
                        t("business.kpis.runway.step.burn", lang, months=burn_months),
                        burn,
                        t("business.kpis.runway.step.burn_formula", lang),
                    ),
                    (
                        t("business.kpis.runway.step.months", lang),
                        runway if runway is not None else t("business.kpis.runway.na_value", lang),
                        f"{cash} ÷ {burn}" if burn > 0 else None,
                    ),
                ],
            ),
        },
        "tax_reserve": reserve,
    }


def _average_burn(ws_id: str, period: str, currency: str) -> tuple[Decimal, int]:
    """Average monthly net cash burn over the trailing months (0 when the business is profitable)."""
    burns: list[Decimal] = []
    p = period
    for _ in range(RUNWAY_LOOKBACK_MONTHS):
        start, end = period_bounds(p)
        flows = _flows(ws_id, start, end)
        income = _sum_prefix(flows, "Income:", sign=-1)
        expense = q2(sum((v for a, v in flows.items() if a.startswith("Expenses:")), Decimal("0")))
        burns.append(q2(expense - income))
        p = prev_period(p)
    positive = [b for b in burns if b > 0]
    if not positive:
        return Decimal("0"), len(burns)
    return q2(sum(positive, Decimal("0")) / len(positive)), len(burns)


def tax_reserve(
    ws_id: str,
    period: str,
    currency: str,
    is_mx: bool,
    balances: dict[str, list[Any]] | None = None,
    regime: str = "",
    lang: str = "es",
) -> dict[str, Any]:
    """ISR + IVA the business should be holding back for this period."""
    steps: list[tuple[str, Any, str | None]] = []
    isr = Decimal("0")
    iva = Decimal("0")
    source = "ledger"
    warnings: list[str] = []

    if is_mx:
        try:
            from ..tax.month_close import month_close

            close = month_close(ws_id, period, currency=currency)
            isr = q2(Decimal(str(close["isr"]["value"]["amount"])))
            iva = q2(Decimal(str(close["iva"]["payable"]["amount"])))
            source = "aurum.tax.month_close"
            if regime and "RESICO" not in regime.upper():
                warnings.append(t("business.kpis.tax_reserve.warning_regime", lang, regime=regime))
            steps.append((t("business.kpis.tax_reserve.step.isr_month_close", lang), isr, t("business.kpis.tax_reserve.step.isr_formula", lang)))
            steps.append((t("business.kpis.tax_reserve.step.iva_month_close", lang), iva, t("business.kpis.tax_reserve.step.iva_formula", lang)))
        except ModuleNotFoundError:
            warnings.append(t("business.kpis.tax_reserve.warning_no_tax_module", lang))
        except Exception as exc:  # pragma: no cover - month_close lives in the tax module
            warnings.append(t("business.kpis.tax_reserve.warning_month_close_failed", lang, exc=type(exc).__name__))

    if source == "ledger":
        balances = balances if balances is not None else get_ledger().balances(ws_id)
        for account, amounts in balances.items():
            for amount in amounts:
                if amount.currency != currency:
                    continue
                if account.startswith("Liabilities:Taxes:ISR"):
                    isr += -amount.amount
                elif account.startswith("Liabilities:Taxes:IVA"):
                    iva += -amount.amount
        isr, iva = q2(isr), q2(iva)
        steps.append((t("business.kpis.tax_reserve.step.isr_payable", lang), isr, None))
        steps.append((t("business.kpis.tax_reserve.step.iva_payable", lang), iva, None))

    total = q2(isr + iva)
    steps.append((t("business.kpis.tax_reserve.step.total", lang), total, t("business.kpis.tax_reserve.step.total_formula", lang)))
    explain = _explain(t("business.kpis.tax_reserve.summary", lang, total=total, currency=currency, source=source), steps)
    explain["citations"] = []
    return {
        "total": {"amount": str(total), "currency": currency},
        "isr": {"amount": str(isr), "currency": currency},
        "iva": {"amount": str(iva), "currency": currency},
        "source": source,
        "warnings": warnings,
        "explain": explain,
    }


def _explain(summary: str, steps: list[tuple[str, Any, str | None]]) -> dict[str, Any]:
    explain = Explain(summary=summary)
    for label, value, formula in steps:
        explain.add_step(label, value, formula=formula)
    return explain.model_dump(mode="json")


def _figure(
    value: Decimal,
    currency: str,
    label: str,
    steps: list[tuple[str, Any, str | None]],
    lang: str = "es",
) -> dict[str, Any]:
    return {
        "amount": str(value),
        "currency": currency,
        "explain": _explain(t("business.kpis.figure.summary", lang, label=label, value=value, currency=currency), steps),
    }
