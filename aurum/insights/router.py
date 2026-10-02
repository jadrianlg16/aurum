"""``/api/insights``: the nudge list, digest, dismissals, deadline calendar and Telegram webhook."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from ..core.db import connect
from ..core.i18n import ws_lang
from ..core.workspaces import WorkspaceNotFound, get_workspace, module_on
from . import telegram as telegram_mod
from .digest import digest_text
from .engine import build_insights

router = APIRouter(tags=["insights"])


def _current_period() -> str:
    return date.today().strftime("%Y-%m")


def _dismissed_ids(ws_id: str) -> set[str]:
    conn = connect()
    try:
        rows = conn.execute("SELECT insight_id FROM insights_dismissed WHERE ws_id=?", (ws_id,)).fetchall()
        return {r["insight_id"] for r in rows}
    finally:
        conn.close()


@router.get("/{ws}")
def api_list_insights(ws: str, period: str | None = None, lang: str | None = None, include_dismissed: bool = False) -> list[dict]:
    period = period or _current_period()
    insights = build_insights(ws, period, lang)
    if not include_dismissed:
        dismissed = _dismissed_ids(ws)
        insights = [i for i in insights if i.id not in dismissed]
    return [i.model_dump(mode="json") for i in insights]


@router.get("/{ws}/digest")
def api_digest(ws: str, period: str | None = None, lang: str | None = None, format: str = "text", llm: bool = False) -> Any:
    period = period or _current_period()
    resolved_lang = ws_lang(ws, lang)
    insights = [i for i in build_insights(ws, period, lang) if i.id not in _dismissed_ids(ws)]
    urgent = [i for i in insights if i.severity == "urgent"]
    text = digest_text(ws, period, insights, resolved_lang, use_llm=llm)
    if format == "json":
        return {
            "workspace": ws,
            "period": period,
            "text": text,
            "urgent_count": len(urgent),
            "insights": [i.model_dump(mode="json") for i in insights],
        }
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(text)


@router.post("/{ws}/{insight_id}/dismiss")
def api_dismiss(ws: str, insight_id: str) -> dict:
    """Organizer-born insights (``org-…`` ids) are dismissed in the organizer's own table so the alert
    disappears from Mi dinero too; everything else lands in ``insights_dismissed``."""
    from datetime import UTC, datetime

    if insight_id.startswith("org-"):
        from ..organizer import alerts as org_alerts

        org_alerts.dismiss(ws, insight_id)
        return {"ok": True, "ws_id": ws, "insight_id": insight_id}

    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO insights_dismissed (ws_id, insight_id, dismissed_at) VALUES (?,?,?)",
            (ws, insight_id, datetime.now(UTC).isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "ws_id": ws, "insight_id": insight_id}


# --------------------------------------------------------------------------- calendar


def _mx_calendar(ws_id: str, start: date, end: date) -> list[dict]:
    """MX declaration deadlines that fall in [start, end]: monthly (17th), DIOT (17th, same declaration
    since RESICO folded it in -- (verify) whether a separate DIOT filing still applies), and the annual
    declaration for personas físicas, historically due by the last day of April -- (verify) exact date
    against LISR art. 150 before this is treated as authoritative. Only for MX workspaces with the tax
    module on."""
    out: list[dict] = []
    if not module_on(ws_id, "tax"):
        return out
    try:
        if "MX" not in get_workspace(ws_id).jurisdictions:
            return out
    except (WorkspaceNotFound, ValueError):
        return out
    # A month's declaration is due the 17th of the *following* month, so start one month earlier than
    # the requested range to catch a deadline that lands in-range but whose period started before it.
    first = date(start.year, start.month, 1)
    cur = date(first.year - (first.month == 1), first.month - 1 if first.month > 1 else 12, 1)
    while cur <= end:
        year, month = cur.year, cur.month
        next_month = date(year + (month == 12), (month % 12) + 1, 1)
        deadline = date(next_month.year, next_month.month, 17)
        if start <= deadline <= end:
            period = f"{year:04d}-{month:02d}"
            out.append(
                {
                    "kind": "mx_monthly_declaration",
                    "date": deadline.isoformat(),
                    "period": period,
                    "title": "Declaración mensual RESICO / DIOT",
                    "note": "(verify) whether DIOT is filed separately from the monthly declaration",
                }
            )
        if month == 4:
            annual_deadline = date(year, 4, 30)
            if start <= annual_deadline <= end:
                out.append(
                    {
                        "kind": "mx_annual_declaration",
                        "date": annual_deadline.isoformat(),
                        "period": str(year - 1),
                        "title": "Declaración anual personas físicas",
                        "note": "(verify) exact due date against LISR art. 150",
                    }
                )
        cur = next_month
    return out


def _us_calendar(ws_id: str, start: date, end: date) -> list[dict]:
    try:
        from ..core.workspaces import get_workspace as _get_ws
        from ..taxus import service as taxus_service
    except ImportError:
        return []
    if not module_on(ws_id, "tax"):
        return []
    try:
        ws = _get_ws(ws_id)
    except WorkspaceNotFound:
        return []
    if "US" not in ws.jurisdictions:
        return []
    out: list[dict] = []
    for year in {start.year, end.year}:
        try:
            payload = taxus_service.annual(ws_id, year)
        except Exception:  # noqa: BLE001
            continue
        for d in (payload.get("quarterly") or {}).get("due_dates", []):
            dd = date.fromisoformat(d)
            if start <= dd <= end:
                out.append({"kind": "us_quarterly_estimate", "date": dd.isoformat(), "period": str(year), "title": "US quarterly estimated payment"})
    return out


def _card_calendar(ws_id: str, start: date, end: date) -> list[dict]:
    try:
        from ..pf import credit
    except ImportError:
        return []
    out: list[dict] = []
    try:
        cards = credit.list_cards(ws_id)
    except Exception:  # noqa: BLE001
        return out
    for c in cards:
        try:
            status = credit.card_status(ws_id, c)
        except Exception:  # noqa: BLE001
            continue
        for key, kind in (("next_cut_date", "card_cut"), ("next_due_date", "card_due")):
            dd = date.fromisoformat(status[key])
            if start <= dd <= end:
                out.append({"kind": kind, "date": dd.isoformat(), "title": f"{status['name']} {kind.split('_')[1]}"})
    return out


def _goal_calendar(ws_id: str, start: date, end: date) -> list[dict]:
    try:
        from ..pf import goals as goals_mod
    except ImportError:
        return []
    out: list[dict] = []
    try:
        rows = goals_mod.list_goals(ws_id)
    except Exception:  # noqa: BLE001
        return out
    for g in rows:
        if not g.get("target_date"):
            continue
        dd = date.fromisoformat(g["target_date"])
        if start <= dd <= end:
            out.append({"kind": "goal_target_date", "date": dd.isoformat(), "title": g["name"]})
    return out


@router.get("/{ws}/calendar")
def api_calendar(ws: str, from_: str = Query(alias="from"), to: str = Query()) -> list[dict]:
    start = date.fromisoformat(from_)
    end = date.fromisoformat(to)
    if end < start:
        raise HTTPException(400, "`to` must not be before `from`")
    out = _mx_calendar(ws, start, end) + _us_calendar(ws, start, end) + _card_calendar(ws, start, end) + _goal_calendar(ws, start, end)
    out.sort(key=lambda d: d["date"])
    return out


# --------------------------------------------------------------------------- telegram webhook


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)) -> dict:
    if not telegram_mod.check_secret(x_telegram_bot_api_secret_token):
        raise HTTPException(401, "invalid secret token")
    try:
        update = await request.json()
    except Exception as e:  # noqa: BLE001 -- malformed body, never a 500
        raise HTTPException(400, f"invalid update JSON: {e}") from e
    result = telegram_mod.handle_update(update)
    if result.get("chat_id"):
        try:
            telegram_mod.send_message(result["chat_id"], result["reply"])
        except Exception:  # noqa: BLE001 -- webhook must ack Telegram even if the reply send fails
            pass
    return {"ok": True, **{k: v for k, v in result.items() if k != "reply"}}
