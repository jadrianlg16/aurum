"""Insights engine: deterministic, code-only nudges assembled from what the other
modules already compute. Nothing here invents a number — every ``Insight.amount`` is read from a
tax/pf/ledger result that already carries its own ``Explain``; this module only decides *whether* a
nudge fires and writes a short human sentence (localized via ``aurum.core.i18n``) around it.

Reads (in-process imports, all defensive — a missing optional module, or a workspace with no
data for a given kind, degrades to "skip this insight" rather than raising):
    aurum.tax.month_close      -> pue_not_collected / deposit_without_cfdi / cash_paid_expense / etc.,
                                   "you may owe ~X by the 17th"
    aurum.taxus.service        -> US quarterly estimate due dates (only when 'US' in workspace.jurisdictions)
    aurum.pf.budgets           -> 80/100 budget alerts
    aurum.pf.goals             -> off-track goals (monthly_required > recent contribution pace)
    aurum.pf.credit            -> card cut/due dates in the next 7 days
    aurum.pf.review            -> spending anomalies
    aurum.organizer.alerts     -> subscription/bill/income alerts — the ONE producer of "bill due"
                                   nudges (pf has no bill-due producer of its own)
    aurum.rules.mx.resico      -> RESICO annual cap pace (regime-exit risk)
    aurum.ledger.base          -> missing bank statement for the period (no Assets:Bank: postings at all)

Tax nudges (month-close diffs, "you may owe", RESICO cap pace, US quarterly estimates) only fire when
the workspace has the tax module on — ``core.workspaces.module_on(ws, "tax")``; simple-mode
workspaces never see them, and the Telegram digest inherits the same gate.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from ..core.explain import Citation, Explain
from ..core.i18n import ws_lang
from ..core.money import Amount, q2
from ..core.workspaces import Workspace, WorkspaceNotFound, get_workspace, module_on
from ..ledger.base import get_ledger
from .i18n import t as i18n_t

Severity = Literal["info", "warn", "urgent"]


class Action(BaseModel):
    label: str
    href: str


class Insight(BaseModel):
    id: str
    ws_id: str
    kind: str
    severity: Severity
    title: str
    body: str
    amount: Amount | None = None
    due_date: str | None = None
    explain: Explain
    actions: list[Action] = Field(default_factory=list)


def _iid(ws_id: str, kind: str, *parts: str) -> str:
    raw = "|".join((ws_id, kind, *parts))
    return f"ins-{kind}-{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _days_until(d: date, today: date) -> int:
    return (d - today).days


def _current_period(today: date | None = None) -> str:
    today = today or date.today()
    return today.strftime("%Y-%m")


def _safe_workspace(ws_id: str) -> Workspace | None:
    try:
        return get_workspace(ws_id)
    except WorkspaceNotFound:
        return None


# --------------------------------------------------------------------------- MX month-close diffs


_DIFF_SEVERITY: dict[str, Severity] = {
    "pue_not_collected": "warn",
    "deposit_without_cfdi": "warn",
    "cash_paid_expense": "info",
    "fixed_asset_iva": "info",
    "ppd_missing_rep": "info",
}

_DIFF_ACTION_HREF = "/api/tax/mx/resico/{ws}/{period}"


def _month_close_insights(ws_id: str, period: str, lang: str, currency: str) -> list[Insight]:
    out: list[Insight] = []
    try:
        from ..tax.month_close import month_close
    except ImportError:
        return out
    try:
        payload = month_close(ws_id, period, lang=lang)
    except Exception:  # noqa: BLE001 — no CFDIs/ledger data yet for this workspace/period
        return out

    for d in payload.get("diffs", []):
        kind = d["kind"]
        severity = _DIFF_SEVERITY.get(kind, "info")
        amount = Amount.model_validate(d["amount"])
        explain = Explain.model_validate(d["explain"])
        out.append(
            Insight(
                id=_iid(ws_id, kind, period),
                ws_id=ws_id,
                kind=kind,
                severity=severity,
                title=i18n_t(f"insights.title.{kind}", lang),
                body=explain.summary,
                amount=amount,
                due_date=payload.get("deadline"),
                explain=explain,
                actions=[
                    Action(
                        label=i18n_t("insights.action.view_month_close", lang),
                        href=_DIFF_ACTION_HREF.format(ws=ws_id, period=period),
                    )
                ],
            )
        )

    # "You may owe ~X by the 17th" -- ISR + IVA payable, only when there is something to pay.
    try:
        isr = Decimal(payload["isr"]["value"]["amount"])
        iva_payable = Decimal(payload["iva"]["payable"]["amount"])
    except (KeyError, TypeError):
        isr = iva_payable = Decimal("0")
    total_due = q2(isr + iva_payable)
    if total_due > 0:
        deadline = date.fromisoformat(payload["deadline"])
        days_left = _days_until(deadline, date.today())
        severity: Severity = "urgent" if days_left <= 7 else "warn" if days_left <= 15 else "info"
        explain = Explain(
            summary=i18n_t("insights.you_may_owe", lang, amount=str(total_due), currency=currency, date=payload["deadline"]),
            rule_versions=Explain.model_validate(payload["isr"]["explain"]).rule_versions,
        )
        explain.add_step(i18n_t("insights.step_isr", lang), isr)
        explain.add_step(i18n_t("insights.step_iva", lang), iva_payable)
        explain.add_step(i18n_t("insights.step_total", lang), total_due, formula="isr + iva_payable")
        out.append(
            Insight(
                id=_iid(ws_id, "you_may_owe", period),
                ws_id=ws_id,
                kind="you_may_owe",
                severity=severity,
                title=i18n_t("insights.title.you_may_owe", lang, amount=f"{total_due} {currency}"),
                body=explain.summary,
                amount=Amount(amount=total_due, currency=currency),
                due_date=payload["deadline"],
                explain=explain,
                actions=[
                    Action(
                        label=i18n_t("insights.action.view_month_close", lang),
                        href=_DIFF_ACTION_HREF.format(ws=ws_id, period=period),
                    )
                ],
            )
        )
    return out


# --------------------------------------------------------------------------- US quarterly estimate


def _us_quarterly_insight(ws: Workspace, lang: str) -> list[Insight]:
    if "US" not in ws.jurisdictions:
        return []
    try:
        from ..taxus import service as taxus_service
    except ImportError:
        return []
    today = date.today()
    try:
        payload = taxus_service.annual(ws.id, today.year)
    except Exception:  # noqa: BLE001 — defensive: taxus reads a profile shape we don't own
        return []
    if not payload.get("applicable"):
        return []
    quarterly = payload.get("quarterly") or {}
    due_dates = quarterly.get("due_dates") or []
    amount_each = quarterly.get("amount_each")
    if not due_dates or not amount_each:
        return []
    upcoming = sorted(date.fromisoformat(d) for d in due_dates if date.fromisoformat(d) >= today)
    if not upcoming:
        return []
    next_due = upcoming[0]
    days_left = _days_until(next_due, today)
    if days_left > 30:
        return []
    severity: Severity = "urgent" if days_left <= 7 else "warn"
    explain = Explain.model_validate(quarterly["explain"])
    amount = Amount.model_validate(amount_each)
    return [
        Insight(
            id=_iid(ws.id, "us_quarterly_estimate", next_due.isoformat()),
            ws_id=ws.id,
            kind="us_quarterly_estimate",
            severity=severity,
            title=i18n_t("insights.title.us_quarterly_estimate", lang),
            body=i18n_t(
                "insights.us_quarterly_estimate",
                lang,
                amount=amount.amount,
                currency=amount.currency,
                date=next_due.isoformat(),
            ),
            amount=amount,
            due_date=next_due.isoformat(),
            explain=explain,
            actions=[
                Action(
                    label=i18n_t("insights.action.view_us_tax", lang),
                    href=f"/api/tax/us/{ws.id}/{today.year}",
                )
            ],
        )
    ]


# --------------------------------------------------------------------------- budgets


def _budget_insights(ws_id: str, period: str, lang: str) -> list[Insight]:
    try:
        from ..pf import budgets
    except ImportError:
        return []
    try:
        status = budgets.budget_status(ws_id, period, lang)
    except Exception:  # noqa: BLE001
        return []
    out: list[Insight] = []
    for row in status.get("budgets", []):
        if row["alert"] == "none":
            continue
        severity: Severity = "urgent" if row["alert"] == "100" else "warn"
        explain = Explain.model_validate(row["explain"])
        out.append(
            Insight(
                id=_iid(ws_id, "budget_alert", period, row["budget_id"]),
                ws_id=ws_id,
                kind="budget_alert",
                severity=severity,
                title=i18n_t("insights.title.budget_alert", lang, name=row.get("label_name") or row["label_id"]),
                body=i18n_t(
                    "insights.budget_alert",
                    lang,
                    name=row.get("label_name") or row["label_id"],
                    pct=str(q2(Decimal(str(row["pct"])))),  # budget_status pct is already a percent
                    spent=row["spent"]["amount"],
                    budget=row["budget"]["amount"],
                    currency=row["spent"]["currency"],
                ),
                amount=Amount.model_validate(row["remaining"]),
                explain=explain,
                actions=[Action(label=i18n_t("insights.action.view_budgets", lang), href=f"/api/pf/{ws_id}/budgets/status?period={period}")],
            )
        )
    return out


# --------------------------------------------------------------------------- goals


def _recent_monthly_contribution(ws_id: str, account: str, months: int = 3) -> Decimal:
    """Average of the last ``months`` months' net inflow into ``account`` (proxy for savings pace)."""
    from dateutil.relativedelta import relativedelta

    ledger = get_ledger()
    today = date.today()
    start = today - relativedelta(months=months)
    total = Decimal("0")
    for txn in ledger.journal(ws_id, start=start, end=today):
        for p in txn.postings:
            if p.amount is not None and p.account == account and p.amount.amount > 0:
                total += p.amount.amount
    return total / months if months else Decimal("0")


def _goal_insights(ws_id: str, lang: str) -> list[Insight]:
    try:
        from ..pf import goals as goals_mod
    except ImportError:
        return []
    out: list[Insight] = []
    try:
        goal_rows = goals_mod.list_goals(ws_id)
    except Exception:  # noqa: BLE001
        return out
    for g in goal_rows:
        try:
            gp = goals_mod.goal_with_progress(ws_id, g, lang)
        except Exception:  # noqa: BLE001
            continue
        if not gp.get("monthly_required"):
            continue
        required = Decimal(gp["monthly_required"]["amount"])
        if required <= 0:
            continue
        pace = _recent_monthly_contribution(ws_id, g["account"])
        if pace >= required:
            continue
        explain = Explain(summary=i18n_t("insights.goal_off_track", lang, name=g["name"]))
        explain.add_step(i18n_t("insights.step_monthly_required", lang), required)
        explain.add_step(i18n_t("insights.step_recent_pace", lang), q2(pace))
        out.append(
            Insight(
                id=_iid(ws_id, "goal_off_track", g["id"]),
                ws_id=ws_id,
                kind="goal_off_track",
                severity="warn",
                title=i18n_t("insights.title.goal_off_track", lang, name=g["name"]),
                body=explain.summary,
                amount=Amount(amount=q2(required - pace), currency=g["currency"]),
                due_date=g.get("target_date"),
                explain=explain,
                actions=[Action(label=i18n_t("insights.action.view_goals", lang), href=f"/api/pf/{ws_id}/goals")],
            )
        )
    return out


# --------------------------------------------------------------------------- credit cards


def _card_insights(ws_id: str, lang: str) -> list[Insight]:
    try:
        from ..pf import credit
    except ImportError:
        return []
    out: list[Insight] = []
    today = date.today()
    try:
        cards = credit.list_cards(ws_id)
    except Exception:  # noqa: BLE001
        return out
    for c in cards:
        try:
            status = credit.card_status(ws_id, c, today=today, lang=lang)
        except Exception:  # noqa: BLE001
            continue
        for date_key, kind, i18n_key in (
            ("next_cut_date", "card_cut_due", "insights.card_cut_due"),
            ("next_due_date", "card_payment_due", "insights.card_payment_due"),
        ):
            d = date.fromisoformat(status[date_key])
            days_left = _days_until(d, today)
            if days_left > 7:
                continue
            severity: Severity = "urgent" if days_left <= 2 else "warn"
            explain = Explain.model_validate(status["explain"])
            out.append(
                Insight(
                    id=_iid(ws_id, kind, c["id"], status[date_key]),
                    ws_id=ws_id,
                    kind=kind,
                    severity=severity,
                    title=i18n_t(f"insights.title.{kind}", lang, name=status["name"]),
                    body=i18n_t(i18n_key, lang, name=status["name"], date=status[date_key]),
                    amount=Amount.model_validate(status["balance"]),
                    due_date=status[date_key],
                    explain=explain,
                    actions=[Action(label=i18n_t("insights.action.view_credit", lang), href=f"/api/pf/{ws_id}/credit/cards")],
                )
            )
    return out


# --------------------------------------------------------------------------- spending anomalies


def _anomaly_insights(ws_id: str, period: str, lang: str, currency: str = "MXN") -> list[Insight]:
    try:
        from ..pf import review
    except ImportError:
        return []
    try:
        out_review = review.monthly_review(ws_id, period, lang)
    except Exception:  # noqa: BLE001
        return []
    out: list[Insight] = []
    for a in out_review.get("anomalies", []):
        explain = Explain(summary=i18n_t("insights.anomaly", lang, name=a["label"], ratio=a["ratio"]))
        explain.add_step(i18n_t("insights.step_amount", lang), a["amount"])
        explain.add_step(i18n_t("insights.step_trailing_average", lang), a["trailing_average"])
        out.append(
            Insight(
                id=_iid(ws_id, "spending_anomaly", period, a["label"]),
                ws_id=ws_id,
                kind="spending_anomaly",
                severity="warn",
                title=i18n_t("insights.title.spending_anomaly", lang, name=a["label"]),
                body=explain.summary,
                amount=Amount(amount=Decimal(a["amount"]), currency=currency),
                explain=explain,
                actions=[Action(label=i18n_t("insights.action.view_review", lang), href=f"/api/pf/{ws_id}/review/{period}")],
            )
        )
    return out


# --------------------------------------------------------------------------- regime-exit risk (RESICO cap)


def _regime_exit_insight(ws: Workspace, period: str, lang: str, currency: str) -> list[Insight]:
    if "MX" not in ws.jurisdictions or (ws.profile or {}).get("regime") != "RESICO_PF":
        return []
    try:
        from ..rules.mx.resico import ANNUAL_CAP, classify_income
        from ..tax.sources import load_cfdis
    except ImportError:
        return []
    year = period.split("-")[0]
    month = int(period.split("-")[1])
    docs, _source = load_cfdis(ws.id)
    if not docs:
        return []
    ytd = Decimal("0")
    rfc = (ws.profile or {}).get("rfc")
    for m in range(1, month + 1):
        p = f"{year}-{m:02d}"
        try:
            ytd += classify_income(docs, p, ws_rfc=rfc).collected
        except Exception:  # noqa: BLE001
            continue
    if ytd <= 0:
        return []
    annualized = q2((ytd / month) * 12)
    pace_pct = (annualized / ANNUAL_CAP) if ANNUAL_CAP else Decimal("0")
    if pace_pct < Decimal("0.8"):
        return []
    severity: Severity = "urgent" if pace_pct >= 1 else "warn"
    explain = Explain(
        summary=i18n_t("insights.regime_exit_risk", lang, pct=str(q2(pace_pct * 100)), cap=str(ANNUAL_CAP), currency=currency),
        citations=[
            Citation(law="LISR", article="113-E", trust_tier="primary", excerpt="RESICO personas físicas: tope anual de ingresos $3,500,000.00 MXN (verify exact wording).")
        ],
    )
    explain.add_step(i18n_t("insights.step_ytd_income", lang), ytd)
    explain.add_step(i18n_t("insights.step_annualized", lang), annualized, formula="(ytd / months_elapsed) * 12")
    explain.add_step(i18n_t("insights.step_cap", lang), ANNUAL_CAP)
    return [
        Insight(
            id=_iid(ws.id, "regime_exit_risk", year),
            ws_id=ws.id,
            kind="regime_exit_risk",
            severity=severity,
            title=i18n_t("insights.title.regime_exit_risk", lang),
            body=explain.summary,
            amount=Amount(amount=annualized, currency=currency),
            explain=explain,
            actions=[Action(label=i18n_t("insights.action.view_month_close", lang), href=f"/api/tax/mx/resico/{ws.id}/{period}")],
        )
    ]


# --------------------------------------------------------------------------- missing statements


def _missing_statement_insight(ws_id: str, period: str, lang: str) -> list[Insight]:
    from ..rules.mx.resico import period_bounds

    try:
        start, end = period_bounds(period)
    except ValueError:
        return []
    ledger = get_ledger()
    try:
        lines = ledger.journal(ws_id, start=start, end=end, account_prefix="Assets:Bank:")
    except Exception:  # noqa: BLE001
        return []
    if lines:
        return []
    # Nothing at all this period could mean the workspace has no bank accounts yet -- only flag when
    # earlier periods DID have bank postings (so this is a gap, not "workspace has no bank account").
    try:
        earlier = ledger.journal(ws_id, start=None, end=start - timedelta(days=1), account_prefix="Assets:Bank:")
    except Exception:  # noqa: BLE001
        return []
    if not earlier:
        return []
    explain = Explain(summary=i18n_t("insights.missing_statement", lang, period=period))
    return [
        Insight(
            id=_iid(ws_id, "missing_statement", period),
            ws_id=ws_id,
            kind="missing_statement",
            severity="info",
            title=i18n_t("insights.title.missing_statement", lang),
            body=explain.summary,
            due_date=end.isoformat(),
            explain=explain,
            actions=[Action(label=i18n_t("insights.action.upload_statement", lang), href=f"/api/ingest/{ws_id}/bank/csv")],
        )
    ]


# --------------------------------------------------------------------------- organizer alerts


def _organizer_insights(ws_id: str, lang: str) -> list[Insight]:
    """Money-organizer alerts as insights. Defensive: the module may be absent.

    The alert already carries a localized title/body and its own ``Explain``; this only re-wraps it
    so Avisos and Telegram carry it. Kinds are prefixed ``organizer_`` and the insight **id is the
    alert id** (``org-<kind>-<hash>``), so dismissing it from either surface hides it in both.
    """
    try:
        from ..organizer.alerts import compute_alerts
    except Exception:  # noqa: BLE001 - organizer module not present
        return []
    try:
        alerts = compute_alerts(ws_id, lang=lang)
    except Exception:  # noqa: BLE001 - a bare workspace must never break the digest
        return []
    out: list[Insight] = []
    for a in alerts:
        out.append(
            Insight(
                id=a.id,
                ws_id=ws_id,
                kind=f"organizer_{a.kind}",
                severity=a.severity,
                title=a.title,
                body=a.body,
                amount=a.new_amount,
                due_date=a.due.isoformat() if a.due else None,
                explain=a.explain or Explain(summary=a.body),
                actions=[Action(label=i18n_t("insights.action.view_organizer", lang), href=f"/api/organizer/{ws_id}/alerts")],
            )
        )
    return out


# --------------------------------------------------------------------------- entry point


def build_insights(ws_id: str, period: str | None = None, lang: str | None = None) -> list[Insight]:
    ws = _safe_workspace(ws_id)
    if ws is None:
        return []
    period = period or _current_period()
    resolved_lang = ws_lang(ws_id, lang)
    currency = ws.base_currency or "MXN"

    tax_on = module_on(ws_id, "tax")
    out: list[Insight] = []
    if "MX" in ws.jurisdictions:
        if tax_on:
            out.extend(_month_close_insights(ws_id, period, resolved_lang, currency))
            out.extend(_regime_exit_insight(ws, period, resolved_lang, currency))
        out.extend(_missing_statement_insight(ws_id, period, resolved_lang))
    if tax_on:
        out.extend(_us_quarterly_insight(ws, resolved_lang))
    out.extend(_budget_insights(ws_id, period, resolved_lang))
    out.extend(_goal_insights(ws_id, resolved_lang))
    out.extend(_card_insights(ws_id, resolved_lang))
    out.extend(_anomaly_insights(ws_id, period, resolved_lang, currency))
    out.extend(_organizer_insights(ws_id, resolved_lang))

    order = {"urgent": 0, "warn": 1, "info": 2}
    out.sort(key=lambda i: order.get(i.severity, 3))
    return out
