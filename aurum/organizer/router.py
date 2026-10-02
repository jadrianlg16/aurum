"""Every organizer endpoint, mounted at ``/api/organizer``.

Test clock: every route resolves "today" through :func:`_today` — the wall clock unless the
request carries ``?today=YYYY-MM-DD`` **and** ``AURUM_TEST_CLOCK=1`` is set (any other case → 422), so
tests can freeze the date without monkeypatching ``date.today`` in a dozen modules.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.i18n import ws_lang
from ..core.money import Amount
from ..core.validation import IsoDate, date_q, optional_period_q, validate_date
from . import alerts as alerts_mod
from . import cadence as cad
from . import calendar_view, commitments, detect, forecast, occurrences, organize, pf_bridge, plan
from . import quickadd as quickadd_mod
from . import summary as summary_mod
from .models import CommitmentIn, CommitmentPatch

router = APIRouter(tags=["organizer"])

MAX_CALENDAR_MONTHS = 24
MAX_FORECAST_DAYS = 400


def wall_today() -> date:
    """Module-level wrapper so tests can monkeypatch the wall clock in one place."""
    return date.today()


def _today(today: str | None = Query(default=None, description="YYYY-MM-DD, tests only")) -> date:
    if today is None or today == "":
        return wall_today()
    if os.environ.get("AURUM_TEST_CLOCK") != "1":
        raise HTTPException(422, "today is only accepted when AURUM_TEST_CLOCK=1")
    return date.fromisoformat(validate_date(today, "today"))


Today = Annotated[date, Depends(_today)]
FromQ = Annotated[str | None, Depends(date_q("from"))]
ToQ = Annotated[str | None, Depends(date_q("to"))]
PeriodQ = Annotated[str | None, Depends(optional_period_q)]


def _lang(ws: str, lang: str | None) -> str:
    return ws_lang(ws, lang)


def _get_or_404(ws: str, commitment_id: str):
    try:
        return commitments.get(ws, commitment_id)
    except KeyError as e:
        raise HTTPException(404, f"commitment {commitment_id} not found") from e


def _duplicate_guard(ws: str, body: CommitmentIn) -> None:
    if body.force:
        return
    hit = commitments.find_duplicate(ws, body.name, body.merchant_patterns)
    if hit is not None:
        raise HTTPException(
            409, {"code": "duplicate", "existing_id": hit.id, "existing_name": hit.name},
        )


def _create_or_404(ws: str, body: CommitmentIn, today: date):
    try:
        return commitments.create(ws, body, today=today)
    except KeyError as e:
        raise HTTPException(404, "commitment account not found") from e


def _rows(ws: str, items, lang: str, today: date) -> list[dict]:
    """Serialize commitments sharing ONE ledger read and one accounts index; lazily persist a stale
    stored ``next_due`` and sort by the effective one."""
    if not items:
        return []
    longest = max(2 * 365, max(cad.nominal_days(c.cadence, c.interval_days) * 2 for c in items))
    txns = pf_bridge.live_txns(ws, today - timedelta(days=10), today + timedelta(days=longest + 10))
    accounts = pf_bridge.accounts_index(ws)
    out = []
    for c in items:
        row = commitments.with_explain(ws, c, lang, today=today, txns=txns, accounts=accounts)
        if c.next_due < today:
            commitments.persist_next_due(ws, c.id, date.fromisoformat(row["next_due"]), today)
        out.append(row)
    out.sort(key=lambda r: (r["next_due"], r["name"]))
    return out


# --------------------------------------------------------------------------- summary & setup


@router.get("/{ws}/summary")
def api_summary(ws: str, today: Today, lang: str | None = None) -> dict:
    commitments.activate_ended_trials(ws, today)
    return summary_mod.summary(ws, today=today, lang=_lang(ws, lang))


@router.get("/{ws}/setup/status")
def api_setup_status(ws: str, today: Today, lang: str | None = None) -> dict:
    return summary_mod.setup_status(ws, today=today, lang=_lang(ws, lang))


class SetupRun(BaseModel):
    months: int = Field(default=3, ge=1, le=24)


@router.post("/{ws}/setup/run")
def api_setup_run(ws: str, today: Today, body: SetupRun | None = None, lang: str | None = None) -> dict:
    return summary_mod.setup_run(ws, months=(body or SetupRun()).months, today=today, lang=_lang(ws, lang))


# --------------------------------------------------------------------------- commitments


@router.get("/{ws}/commitments")
def api_list_commitments(ws: str, today: Today, kind: str | None = None, status: str | None = None,
                         lang: str | None = None) -> list[dict]:
    commitments.activate_ended_trials(ws, today)
    return _rows(ws, commitments.list_commitments(ws, kind, status), _lang(ws, lang), today)


@router.post("/{ws}/commitments")
def api_create_commitment(ws: str, today: Today, body: CommitmentIn, lang: str | None = None) -> dict:
    _duplicate_guard(ws, body)
    created = _create_or_404(ws, body, today)
    return commitments.with_explain(ws, created, _lang(ws, lang), today=today)


@router.get("/{ws}/commitments/{commitment_id}")
def api_get_commitment(ws: str, today: Today, commitment_id: str, lang: str | None = None) -> dict:
    commitments.activate_ended_trials(ws, today)
    c = _get_or_404(ws, commitment_id)
    data = _rows(ws, [c], _lang(ws, lang), today)[0]
    data["price_history"] = commitments.price_history(ws, commitment_id)
    data["occurrences"] = [o.model_dump(mode="json") for o in occurrences.recent(ws, c, 12, today=today)]
    data["loan"] = None
    if c.linked_loan_id:
        try:
            from ..pf import credit as pf_credit

            am = pf_credit.loan_amortization(ws, c.linked_loan_id)
            paid = sum(1 for o in occurrences.recent(ws, c, 120, today=today) if o.status == "paid")
            data["loan"] = {
                "loan_id": c.linked_loan_id,
                "payment": am["payment"],
                "total_paid": am["total_paid"],
                "total_interest": am["total_interest"],
                "months": len(am["rows"]),
                "payments_seen": paid,
                "balance_after_seen": am["rows"][min(paid, len(am["rows"]) - 1)]["balance"]
                if am["rows"] else None,
                "explain": am["explain"],
            }
        except Exception:  # noqa: BLE001 — pf absent or loan deleted; the drawer just hides the panel
            data["loan"] = None
    return data


@router.put("/{ws}/commitments/{commitment_id}")
def api_update_commitment(ws: str, today: Today, commitment_id: str, body: CommitmentPatch,
                          lang: str | None = None) -> dict:
    _get_or_404(ws, commitment_id)
    try:
        updated = commitments.update_partial(ws, commitment_id, body, today=today)
    except KeyError as e:
        raise HTTPException(404, "commitment account not found") from e
    return commitments.with_explain(ws, updated, _lang(ws, lang), today=today)


@router.delete("/{ws}/commitments/{commitment_id}")
def api_delete_commitment(ws: str, today: Today, commitment_id: str, lang: str | None = None) -> dict:
    try:
        c = commitments.soft_delete(ws, commitment_id, today=today)
    except KeyError as e:
        raise HTTPException(404, f"commitment {commitment_id} not found") from e
    return commitments.with_explain(ws, c, _lang(ws, lang), today=today)


@router.post("/{ws}/commitments/{commitment_id}/review")
def api_review_commitment(ws: str, today: Today, commitment_id: str) -> dict:
    try:
        when = commitments.mark_reviewed(ws, commitment_id, today)
    except KeyError as e:
        raise HTTPException(404, f"commitment {commitment_id} not found") from e
    return {"reviewed_at": when.isoformat()}


class StatusBody(BaseModel):
    cancel_notes: str | None = None


@router.post("/{ws}/commitments/{commitment_id}/{action}")
def api_commitment_action(ws: str, today: Today, commitment_id: str, action: str,
                          body: StatusBody | None = None, lang: str | None = None) -> dict:
    mapping = {"pause": "paused", "resume": "active", "cancel": "cancelled"}
    if action not in mapping:
        raise HTTPException(400, "action must be pause, resume or cancel")
    try:
        c = commitments.set_status(
            ws, commitment_id, mapping[action],
            ended=today if action == "cancel" else None,
            cancel_notes=(body.cancel_notes if body else None),
        )
    except KeyError as e:
        raise HTTPException(404, f"commitment {commitment_id} not found") from e
    return commitments.with_explain(ws, c, _lang(ws, lang), today=today)


# --------------------------------------------------------------------------- quick add


class QuickAdd(BaseModel):
    text: str
    force: bool = False


@router.post("/{ws}/quickadd")
def api_quickadd(ws: str, today: Today, body: QuickAdd, save: int = 0, lang: str | None = None) -> dict:
    resolved = _lang(ws, lang)
    try:
        parsed, explain = quickadd_mod.parse(body.text, ws, today=today, lang=resolved,
                                             currency=pf_bridge.base_currency(ws))
    except quickadd_mod.QuickAddError as e:
        raise HTTPException(400, str(e)) from e
    auto_label = organize.apply_rules_to_quickadd(ws, body.text)
    if auto_label:
        parsed = parsed.model_copy(update={"label_id": auto_label["label_id"]})
        explain.add_step("auto_label", auto_label["label_name"], formula=f"{auto_label['source']} match")
    if save:
        if body.force:
            parsed = parsed.model_copy(update={"force": True})
        _duplicate_guard(ws, parsed)
        created = _create_or_404(ws, parsed, today)
        out = commitments.with_explain(ws, created, resolved, today=today)
        out["explain"] = explain.model_dump()
        out["saved"] = True
        out["auto_label"] = auto_label
        return out
    preview = parsed.model_dump(mode="json")
    preview["explain"] = explain.model_dump()
    return {"preview": preview, "saved": False, "auto_label": auto_label,
            "explain": explain.model_dump()}


# --------------------------------------------------------------------------- detection


@router.post("/{ws}/detect")
def api_detect(ws: str, today: Today, lang: str | None = None) -> dict:
    resolved = _lang(ws, lang)
    found = detect.detect(ws, today=today, lang=resolved)
    return {"candidates": [c.model_dump(mode="json") for c in found], "count": len(found)}


@router.get("/{ws}/detect")
def api_list_candidates(ws: str, status: str = "open") -> dict:
    found = detect.list_candidates(ws, status)
    return {"candidates": [c.model_dump(mode="json") for c in found], "count": len(found)}


class AcceptBody(BaseModel):
    candidate_id: str
    overrides: dict | None = None


@router.post("/{ws}/detect/accept")
def api_detect_accept(ws: str, today: Today, body: AcceptBody, lang: str | None = None) -> dict:
    try:
        created = detect.accept(ws, body.candidate_id, body.overrides, today=today)
    except KeyError as e:
        raise HTTPException(404, f"candidate {body.candidate_id} not found") from e
    return commitments.with_explain(ws, created, _lang(ws, lang), today=today)


class DismissBody(BaseModel):
    candidate_id: str


@router.post("/{ws}/detect/dismiss")
def api_detect_dismiss(ws: str, body: DismissBody) -> dict:
    try:
        detect.get_candidate(ws, body.candidate_id)
    except KeyError as e:
        raise HTTPException(404, f"candidate {body.candidate_id} not found") from e
    detect.set_candidate_status(ws, body.candidate_id, "dismissed")
    return {"ok": True, "candidate_id": body.candidate_id, "status": "dismissed"}


# --------------------------------------------------------------------------- alerts


@router.get("/{ws}/alerts")
def api_alerts(ws: str, today: Today, lang: str | None = None) -> list[dict]:
    commitments.activate_ended_trials(ws, today)
    return [a.model_dump(mode="json") for a in alerts_mod.compute_alerts(ws, today=today, lang=_lang(ws, lang))]


@router.post("/{ws}/alerts/{alert_id}/dismiss")
def api_dismiss_alert(ws: str, alert_id: str) -> dict:
    alerts_mod.dismiss(ws, alert_id)
    return {"ok": True, "alert_id": alert_id}


# --------------------------------------------------------------------------- calendar


@router.get("/{ws}/calendar")
def api_calendar(ws: str, today: Today, from_: FromQ, to: ToQ,
                 lang: str | None = None) -> dict:
    start = date.fromisoformat(from_) if from_ else today.replace(day=1)
    end = date.fromisoformat(to) if to else start + timedelta(days=45)
    if end < start:
        raise HTTPException(400, "`to` must not be before `from`")
    if end > start + relativedelta(months=MAX_CALENDAR_MONTHS):
        raise HTTPException(422, f"range must be {MAX_CALENDAR_MONTHS} months or less")
    commitments.activate_ended_trials(ws, today)
    return calendar_view.calendar(ws, start, end, today=today, lang=_lang(ws, lang))


# --------------------------------------------------------------------------- occurrences


class MarkOccurrenceBody(BaseModel):
    commitment_id: str
    date: IsoDate
    status: Literal["paid", "skipped"]
    entry_id: str | None = None
    log_entry: bool = False
    amount: Amount | None = None
    account_id: str | None = None


def _mark(ws: str, body: MarkOccurrenceBody, txn_id: str | None = None) -> occurrences.Occurrence:
    c = _get_or_404(ws, body.commitment_id)
    try:
        return occurrences.mark_occurrence(
            ws, c, date.fromisoformat(body.date), body.status, entry_id=body.entry_id,
            log_entry=body.log_entry, amount=body.amount, account_id=body.account_id, txn_id=txn_id,
        )
    except occurrences.MarkError as e:
        raise HTTPException(e.status_code, e.detail) from e


@router.post("/{ws}/occurrences/mark")
def api_mark(ws: str, body: MarkOccurrenceBody) -> dict:
    occ = _mark(ws, body)
    return {"occurrence": occ.model_dump(mode="json"), "entry_id": occ.entry_id}


@router.delete("/{ws}/occurrences/mark")
def api_unmark(ws: str, commitment_id: str = Query(...), date_: str = Query(..., alias="date")) -> dict:
    _get_or_404(ws, commitment_id)
    due = date.fromisoformat(validate_date(date_, "date"))
    try:
        removed, voided = occurrences.unmark_occurrence(ws, commitment_id, due)
    except occurrences.MarkError as e:
        raise HTTPException(e.status_code, e.detail) from e
    return {"removed": removed, "voided_entry_id": voided}


class MarkBody(BaseModel):
    """Legacy alias body (``POST /occurrences/{cid}/{due}/mark``)."""

    status: Literal["paid", "skipped"]
    txn_id: str | None = None
    amount: Amount | None = None


@router.post("/{ws}/occurrences/{commitment_id}/{due}/mark")
def api_mark_occurrence(ws: str, commitment_id: str, due: date, body: MarkBody) -> dict:
    occ = _mark(
        ws,
        MarkOccurrenceBody(commitment_id=commitment_id, date=due.isoformat(), status=body.status,
                           amount=body.amount),
        txn_id=body.txn_id,
    )
    return occ.model_dump(mode="json")


# --------------------------------------------------------------------------- forecast


@router.get("/{ws}/forecast")
def api_forecast(ws: str, today: Today, days: int = Query(default=90, ge=1, le=MAX_FORECAST_DAYS),
                 lang: str | None = None) -> dict:
    commitments.activate_ended_trials(ws, today)
    return forecast.forecast(ws, days=days, today=today, lang=_lang(ws, lang))


class BufferBody(BaseModel):
    buffer: str | None = None


@router.put("/{ws}/forecast/buffer")
def api_set_buffer(ws: str, body: BufferBody) -> dict:
    value = None
    if body.buffer is not None:
        try:
            value = Decimal(body.buffer)
        except InvalidOperation as e:
            raise HTTPException(400, "buffer must be a decimal string") from e
    forecast.set_buffer(ws, value)
    commitment_list = commitments.list_commitments(ws)
    effective, formula = forecast.effective_buffer(ws, commitment_list)
    return {"buffer": {"amount": str(effective), "currency": pf_bridge.base_currency(ws)}, "source": formula}


# --------------------------------------------------------------------------- plan


@router.get("/{ws}/plan")
def api_plan(ws: str, today: Today, period: PeriodQ, lang: str | None = None) -> dict:
    return plan.build_plan(ws, period, today=today, lang=_lang(ws, lang))


class AutoPlanBody(BaseModel):
    months: int = Field(default=3, ge=1, le=24)
    period: str | None = None


@router.post("/{ws}/plan/auto")
def api_plan_auto(ws: str, today: Today, body: AutoPlanBody | None = None, lang: str | None = None) -> dict:
    body = body or AutoPlanBody()
    return plan.auto_plan(ws, months=body.months, period=body.period, today=today, lang=_lang(ws, lang))


class PlanItem(BaseModel):
    label_id: str
    planned: str


class PlanBody(BaseModel):
    items: list[PlanItem]
    period: str | None = None


@router.put("/{ws}/plan")
def api_put_plan(ws: str, today: Today, body: PlanBody) -> dict:
    return plan.put_plan(ws, [i.model_dump() for i in body.items], body.period, today=today)


# --------------------------------------------------------------------------- organize & rules


class Assignment(BaseModel):
    txn_id: str
    label_id: str
    create_rule: bool = False


class OrganizeBody(BaseModel):
    assign: list[Assignment]


@router.post("/{ws}/organize")
def api_organize(ws: str, body: OrganizeBody, lang: str | None = None) -> dict:
    return organize.organize(ws, [a.model_dump() for a in body.assign], lang=_lang(ws, lang))


@router.get("/{ws}/rules")
def api_rules(ws: str) -> list[dict]:
    return organize.list_rules(ws)


@router.delete("/{ws}/rules/{rule_id}")
def api_delete_rule(ws: str, rule_id: str) -> dict:
    try:
        organize.delete_rule(ws, rule_id)
    except KeyError as e:
        raise HTTPException(404, f"rule {rule_id} not found") from e
    return {"ok": True}
