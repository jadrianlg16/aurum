"""GET income — sources per month, gross vs net, expected vs received, smoothing."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter

from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from . import ledger_view, store

router = APIRouter()

# Only withholdings count as "retained" income: IVA-Acreditable is a credit, never a retention.
RETENTION_PREFIXES: tuple[str, ...] = ("Assets:Taxes:ISR-Retenido", "Assets:Taxes:IVA-Retenido")


def _months_back(n: int, today: date | None = None) -> list[str]:
    today = today or date.today()
    return [(today.replace(day=1) - relativedelta(months=i)).strftime("%Y-%m") for i in range(n - 1, -1, -1)]


def income_by_month(ws_id: str, months: int = 6, today: date | None = None, currency: str | None = None) -> dict[str, dict]:
    """Void-aware, signed sums per month: gross income per ``Income:`` account and retained withholdings."""
    currency = currency or store.base_currency(ws_id)
    keys = _months_back(months, today)
    wanted = set(keys)
    start = date.fromisoformat(keys[0] + "-01")
    by_month: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    retained_by_month: dict[str, Decimal] = defaultdict(Decimal)
    for t, p in ledger_view.live_postings(ws_id, start=start):
        key = t.date.strftime("%Y-%m")
        if key not in wanted or p.amount is None or p.amount.currency != currency:
            continue
        if p.account.startswith("Income:"):
            # income postings are credits (negative); gross = -amount
            by_month[key][p.account] += -p.amount.amount
        elif p.account.startswith(RETENTION_PREFIXES):
            retained_by_month[key] += p.amount.amount
    return {"by_month": by_month, "retained_by_month": retained_by_month}


def _read_cfdi_expected(ws_id: str, period: str) -> dict | None:
    """Defensive read of the ingest module's ``ingest_cfdi`` table — absent → ledger-only view."""
    conn = store.db()
    try:
        rows = conn.execute(
            "SELECT metodo_pago, direction, total, uuid FROM ingest_cfdi "
            "WHERE ws_id=? AND strftime('%Y-%m', fecha)=? AND direction='emitido'",
            (ws_id, period),
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    issued = Decimal("0")
    pending_ppd = Decimal("0")
    for r in rows:
        total = Decimal(str(r["total"]))
        issued += total
        if r["metodo_pago"] == "PPD":
            pending_ppd += total
    return {
        "issued": str(issued),
        "pending_ppd_without_rep": str(pending_ppd),
        "count": len(rows),
    }


def get_income(ws_id: str, months: int = 6, today: date | None = None, lang: str | None = None) -> dict:
    today = today or date.today()
    currency = store.base_currency(ws_id)
    data = income_by_month(ws_id, months, today, currency)
    month_keys = _months_back(months, today)
    sources: dict[str, dict] = {}
    series = []
    for key in month_keys:
        month_totals = data["by_month"].get(key, {})
        retained = data["retained_by_month"].get(key, Decimal("0"))
        gross = sum(month_totals.values(), Decimal("0"))
        net = gross - retained
        series.append(
            {
                "month": key,
                "gross": store.money(gross, currency),
                "retained": store.money(retained, currency),
                "net": store.money(net, currency),
                "by_source": {acct: str(q2(amt)) for acct, amt in month_totals.items()},
                "expected_vs_received": _read_cfdi_expected(ws_id, key),
            }
        )
        for acct in month_totals:
            sources.setdefault(acct, {"account": acct, "months": {}})
            sources[acct]["months"][key] = str(q2(month_totals[acct]))

    grosses = [Decimal(m["gross"]["amount"]) for m in series]
    avg = sum(grosses, Decimal("0")) / len(grosses) if grosses else Decimal("0")
    explain = Explain(summary=i18n_t("pf.income_smoothed", ws_lang(ws_id, lang), months=months))
    explain.add_step("average", avg, formula=f"sum(gross)/{len(grosses)}" if grosses else "0")
    return {
        "months": series,
        "sources": list(sources.values()),
        "smoothed_average": store.money(avg, currency),
        "currency": currency,
        "explain": explain.model_dump(),
    }


@router.get("/{ws}/income")
def api_income(ws: str, months: int = 6, lang: str | None = None) -> dict:
    return get_income(ws, months, lang=lang)
