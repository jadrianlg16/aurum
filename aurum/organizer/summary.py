"""``GET /summary`` and the 3-step setup status/run."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal

from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from . import alerts as alerts_mod
from . import commitments as cmt
from . import detect as detect_mod
from . import forecast as forecast_mod
from . import occurrences as occ
from . import pf_bridge, store
from . import plan as plan_mod

NEXT_DAYS = 7


def has_bank_lines(ws_id: str) -> int:
    conn = store.db()
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM ingest_bank_lines WHERE ws_id=?", (ws_id,)).fetchone()
    except sqlite3.OperationalError:  # pragma: no cover
        return 0
    return int(count)


def setup_status(ws_id: str, today: date | None = None, lang: str | None = None) -> dict:
    today = today or date.today()
    lang = lang or ws_lang(ws_id)
    commitments = cmt.list_commitments(ws_id)
    bank_lines = has_bank_lines(ws_id)
    incomes = [c for c in commitments if c.kind == "income" and c.status in ("active", "trial")]
    period = today.strftime("%Y-%m")
    budgets = plan_mod._budgets(ws_id, period)  # noqa: SLF001 - same module family, read-only helper
    candidates = detect_mod.list_candidates(ws_id, "open")
    steps = {
        "has_bank_lines": bank_lines > 0,
        "has_commitments": len(commitments) > 0,
        "has_income": len(incomes) > 0,
        "has_plan": len(budgets) > 0,
    }
    done = sum(1 for v in steps.values() if v)
    explain = Explain(summary=i18n_t("organizer.setup", lang))
    explain.add_step("bank_lines", bank_lines)
    explain.add_step("commitments", len(commitments))
    explain.add_step("income_commitments", len(incomes))
    explain.add_step("budgets", len(budgets), formula=f"pf_budgets for {period}")
    explain.add_step("open_candidates", len(candidates))
    return {
        **steps,
        "counts": {
            "bank_lines": bank_lines,
            "commitments": len(commitments),
            "income_commitments": len(incomes),
            "budgets": len(budgets),
            "open_candidates": len(candidates),
        },
        "progress": f"{done}/4",
        "explain": explain.model_dump(),
    }


def setup_run(ws_id: str, months: int = 3, today: date | None = None, lang: str | None = None) -> dict:
    """Detect + auto-plan in one call. Nothing is accepted automatically: the wizard confirms."""
    today = today or date.today()
    lang = lang or ws_lang(ws_id)
    candidates = detect_mod.detect(ws_id, today=today, lang=lang)
    auto = plan_mod.auto_plan(ws_id, months=months, today=today, lang=lang)
    income_candidates = [c for c in candidates if c.preview.kind == "income"]
    explain = Explain(summary=i18n_t("organizer.setup", lang))
    explain.add_step("candidates_found", len(candidates))
    explain.add_step("income_candidates", len(income_candidates))
    explain.add_step("budgets_written", len(auto["written"]), formula=f"averages over {months} months")
    return {
        "candidates": [c.model_dump(mode="json") for c in candidates[:20]],
        "candidates_total": len(candidates),
        "income_candidates": [c.model_dump(mode="json") for c in income_candidates],
        "plan": auto,
        "status": setup_status(ws_id, today, lang),
        "explain": explain.model_dump(),
    }


def summary(ws_id: str, today: date | None = None, lang: str | None = None) -> dict:
    today = today or date.today()
    lang = lang or ws_lang(ws_id)
    commitments = cmt.list_commitments(ws_id)
    active = [c for c in commitments if c.status in ("active", "trial")]
    currency = pf_bridge.base_currency(ws_id)
    horizon = today + timedelta(days=NEXT_DAYS)
    txns = pf_bridge.live_txns(ws_id, today - timedelta(days=70), today + timedelta(days=70))

    by_kind: dict[str, Decimal] = {}
    total = Decimal("0")
    for c in active:
        if c.kind == "income":
            continue
        monthly = cmt.monthly_equivalent(c)
        by_kind[c.kind] = by_kind.get(c.kind, Decimal("0")) + monthly
        total += monthly

    annual_subs = q2(sum(
        (cmt.annual_equivalent(c) for c in active if c.kind == "subscription"), Decimal("0")
    ))

    upcoming = []
    for c in active:
        for o in occ.build(ws_id, c, today, horizon, today=today, txns=txns):
            upcoming.append({
                "commitment_id": c.id, "name": c.name, "kind": c.kind,
                "due": o.due.isoformat(),
                "amount": {"amount": str(q2(o.amount.amount)), "currency": o.amount.currency},
                "status": o.status, "txn_id": o.txn_id, "entry_id": o.entry_id,
                "amount_variable": bool(c.amount_variable),
            })
    upcoming.sort(key=lambda r: (r["due"], r["name"]))

    period = today.strftime("%Y-%m")
    start, end = plan_mod._period_bounds(period)  # noqa: SLF001
    uncategorized_count = len(plan_mod.uncategorized(ws_id, start, end, txns))
    alert_list = alerts_mod.compute_alerts(ws_id, today=today, lang=lang, txns=txns)

    explain = Explain(summary=i18n_t("organizer.summary", lang))
    explain.add_step("active_commitments", len(active))
    explain.add_step("monthly_committed", q2(total), formula="Σ amount × periods_per_year / 12")
    explain.add_step("annual_subscriptions", annual_subs,
                     formula="Σ amount × periods_per_year (kind = subscription)")
    explain.add_step("next_7_days", len(upcoming), formula=f"occurrences in [{today}, {horizon}]")
    explain.add_step("alerts", len(alert_list))

    return {
        "monthly_committed": {
            "total": {"amount": str(q2(total)), "currency": currency},
            "by_kind": {
                k: {"amount": str(q2(v)), "currency": currency} for k, v in sorted(by_kind.items())
            },
        },
        "annual_subscriptions": {"amount": str(annual_subs), "currency": currency},
        "next_7_days": upcoming,
        "alerts_count": len(alert_list),
        "safe_to_spend": forecast_mod.safe_to_spend(ws_id, today, lang, commitments, txns=txns),
        "uncategorized_count": uncategorized_count,
        "setup": setup_status(ws_id, today, lang),
        "explain": explain.model_dump(),
    }
