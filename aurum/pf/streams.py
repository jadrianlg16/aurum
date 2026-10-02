"""Income streams a person sets up by hand.

Each stream is mirrored into one or more ``organizer`` commitments of kind ``"income"`` so the
calendar, forecast and safe-to-spend views pick it up for free — this module only ever calls
``aurum.organizer.commitments``'s public functions, never touches ``organizer_*`` tables directly.

Semimonthly pay (e.g. the 15th and the 30th) mirrors into **one monthly-cadence commitment per anchor
day** rather than a single "semimonthly" commitment: the organizer's ``Commitment`` model has no such
cadence, but two independent monthly commitments — each clamped to the length of the month the same
way a single monthly bill is — are mathematically identical for forecasting and project correctly across
every month end.

``PUT`` is a partial merge and updates **in place** (id/created_at kept; mirrored commitments
patched through ``org_commitments.update`` when the spec count matches, never delete+recreate);
``active=false`` pauses the commitments; a bad ``account_id`` is a 404 with nothing written. Mirrored
commitments carry normalized ``merchant_patterns`` so bank lines match them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.money import Amount, q2
from ..core.validation import DayOfMonth, IsoDate, Weekday
from ..ledger.base import get_ledger
from ..organizer import commitments as org_commitments
from ..organizer import normalize
from ..organizer.models import Commitment, CommitmentIn
from . import accounts_admin, labels, store
from .types import MoneyIn, PositiveMoney

router = APIRouter()

SourceType = Literal["salary", "freelance", "rent", "pension", "investment", "other"]
StreamCadence = Literal["monthly", "semimonthly", "biweekly", "weekly", "annual", "irregular"]


class IncomeStreamIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    source_type: SourceType
    amount: PositiveMoney
    gross_amount: MoneyIn | None = None
    cadence: StreamCadence
    anchor_days: list[DayOfMonth] = Field(default_factory=list)
    weekday: Weekday | None = None
    next_expected: IsoDate | None = None
    account_id: str
    label_id: str | None = None
    active: bool = True
    notes: str | None = None


class IncomeStreamPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    source_type: SourceType | None = None
    amount: PositiveMoney | None = None
    gross_amount: MoneyIn | None = None
    cadence: StreamCadence | None = None
    anchor_days: list[DayOfMonth] | None = None
    weekday: Weekday | None = None
    next_expected: IsoDate | None = None
    account_id: str | None = None
    label_id: str | None = None
    active: bool | None = None
    notes: str | None = None


# --------------------------------------------------------------------------- organizer mirroring


def _next_expected(body: IncomeStreamIn) -> date | None:
    return date.fromisoformat(body.next_expected) if body.next_expected else None


def _last_anchor_on_or_before(today: date, day: int) -> date:
    """The most recent month-day ``day`` that is on or before ``today`` (clamped to month length)."""
    from ..organizer.cadence import clamp_day

    this_month = clamp_day(today.year, today.month, day)
    if this_month <= today:
        return this_month
    prev = today - relativedelta(months=1)
    return clamp_day(prev.year, prev.month, day)


def _commitment_specs(body: IncomeStreamIn, ledger_account: str, today: date) -> list[CommitmentIn]:
    next_expected = _next_expected(body)
    common: dict = {
        "kind": "income",
        "account": ledger_account,
        "label_id": body.label_id,
        "essential": "needs",
        "source": "manual",
        "confidence": 1.0,
        "notes": body.notes,
        "category_hint": body.source_type,
        "merchant_patterns": merchant_patterns(body.name),
        "status": "active" if body.active else "paused",
    }
    if body.cadence == "semimonthly":
        days = body.anchor_days or [15, 30]
        # `started` = the last payday on or before today: the organizer projects history from the
        # earliest evidence (occurrences.history_floor), so without it a stream created after the
        # 15th has no occurrence for that 15th and an income entry logged for it never shows as
        # received.
        return [
            CommitmentIn(
                name=f"{body.name} ({d})", amount=body.amount, cadence="monthly", anchor_day=d,
                started=_last_anchor_on_or_before(today, d), **common,
            )
            for d in days
        ]
    if body.cadence == "monthly":
        day = body.anchor_days[0] if body.anchor_days else (next_expected or today).day
        return [
            CommitmentIn(
                name=body.name, amount=body.amount, cadence="monthly", anchor_day=day,
                next_due=next_expected, started=_last_anchor_on_or_before(today, day), **common,
            )
        ]
    if body.cadence in ("weekly", "biweekly"):
        wd = body.weekday if body.weekday is not None else today.weekday()
        return [
            CommitmentIn(
                name=body.name, amount=body.amount, cadence=body.cadence, weekday=wd,
                next_due=next_expected, **common,
            )
        ]
    if body.cadence == "annual":
        nd = next_expected or (today + relativedelta(years=1))
        return [
            CommitmentIn(
                name=body.name, amount=body.amount, cadence="annual", anchor_day=nd.day,
                next_due=nd, **common,
            )
        ]
    # irregular: no real cadence to mirror faithfully — approximate as a 30-day custom step so it
    # still shows up in the calendar/forecast, clearly re-projectable by hand from the app.
    nd = next_expected or (today + relativedelta(days=30))
    return [
        CommitmentIn(name=body.name, amount=body.amount, cadence="custom", interval_days=30, next_due=nd, **common)
    ]


def merchant_patterns(name: str) -> list[str]:
    out = [normalize.normalize(name), name.upper()]
    return list(dict.fromkeys(p for p in out if p))


def _row(r) -> dict:
    d = store.row_to_dict(r)
    d["anchor_days"] = store.loads(d.get("anchor_days"), [])
    d["commitment_ids"] = store.loads(d.get("commitment_ids"), [])
    d["active"] = bool(d["active"])
    return d


def _to_output(row: dict, account_names: dict[str, str] | None = None) -> dict:
    out = dict(row)
    out["amount"] = store.money(row["amount"], row["currency"])
    out["gross_amount"] = store.money(row["gross_amount"], row["currency"]) if row["gross_amount"] else None
    if account_names is None:
        try:
            out["account_name"] = accounts_admin.get_row(row["ws_id"], row["account_id"])["name"]
        except KeyError:
            out["account_name"] = None
    else:
        out["account_name"] = account_names.get(row["account_id"])
    return out


def _validate(ws_id: str, body: IncomeStreamIn) -> dict:
    """Account (404) and label kind (400) checks — before anything is written."""
    account = accounts_admin.get_row(ws_id, body.account_id)  # KeyError → 404
    if body.label_id:
        label = labels.get_label(ws_id, body.label_id)  # KeyError → 404
        if label["kind"] != "income":
            raise ValueError("label_id must be an income category")
    return account


# --------------------------------------------------------------------------- CRUD


def create_stream(ws_id: str, body: IncomeStreamIn, today: date | None = None) -> dict:
    today = today or date.today()
    account = _validate(ws_id, body)
    specs = _commitment_specs(body, account["account"], today)
    created: list[Commitment] = [org_commitments.create(ws_id, spec, today) for spec in specs]
    next_expected = min((c.next_due for c in created), default=_next_expected(body) or today)

    stream_id = store.new_id("inc")
    ts = store.now()
    conn = store.db()
    conn.execute(
        "INSERT INTO pf_income_streams (id, ws_id, name, source_type, amount, currency, gross_amount, "
        "cadence, anchor_days, weekday, next_expected, account_id, label_id, active, notes, "
        "commitment_ids, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            stream_id, ws_id, body.name, body.source_type, str(q2(body.amount.amount)), body.amount.currency,
            str(q2(body.gross_amount.amount)) if body.gross_amount else None, body.cadence,
            store.dumps(body.anchor_days), body.weekday, next_expected.isoformat(), body.account_id,
            body.label_id, int(body.active), body.notes, store.dumps([c.id for c in created]), ts, ts,
        ),
    )
    conn.commit()
    return get_stream(ws_id, stream_id)


def _fetch(ws_id: str, stream_id: str) -> dict:
    conn = store.db()
    row = conn.execute("SELECT * FROM pf_income_streams WHERE ws_id=? AND id=?", (ws_id, stream_id)).fetchone()
    if row is None:
        raise KeyError(stream_id)
    return _row(row)


def get_stream(ws_id: str, stream_id: str) -> dict:
    return _to_output(_fetch(ws_id, stream_id))


def list_streams(ws_id: str, active_only: bool = False) -> list[dict]:
    conn = store.db()
    sql = "SELECT * FROM pf_income_streams WHERE ws_id=?"
    if active_only:
        sql += " AND active=1"
    sql += " ORDER BY next_expected"
    names = {a["id"]: a["name"] for a in accounts_admin.list_rows(ws_id, include_archived=True)}
    return [_to_output(_row(r), names) for r in conn.execute(sql, (ws_id,)).fetchall()]


def _remove_commitments(ws_id: str, commitment_ids: list[str]) -> None:
    hard = getattr(org_commitments, "hard_delete", None)  # the organizer has only soft_delete today
    for cid in commitment_ids:
        try:
            if hard is not None:
                hard(ws_id, cid)
            else:
                org_commitments.soft_delete(ws_id, cid)
        except KeyError:
            pass


def merge_patch(existing: dict, patch: IncomeStreamPatch) -> IncomeStreamIn:
    changed = patch.model_dump(exclude_unset=True)
    base = {
        "name": existing["name"],
        "source_type": existing["source_type"],
        "amount": Amount(amount=existing["amount"], currency=existing["currency"]),
        "gross_amount": Amount(amount=existing["gross_amount"], currency=existing["currency"])
        if existing.get("gross_amount") else None,
        "cadence": existing["cadence"],
        "anchor_days": existing["anchor_days"],
        "weekday": existing.get("weekday"),
        "next_expected": existing.get("next_expected"),
        "account_id": existing["account_id"],
        "label_id": existing.get("label_id"),
        "active": existing["active"],
        "notes": existing.get("notes"),
    }
    base.update(changed)
    return IncomeStreamIn(**base)


def update_stream(ws_id: str, stream_id: str, body: IncomeStreamIn | IncomeStreamPatch,
                  today: date | None = None) -> dict:
    """Merge + update in place. Mirrored commitments are patched when their count still matches the new
    spec (same ids, ``created_at`` untouched); otherwise the old ones are removed and new ones created."""
    today = today or date.today()
    existing = _fetch(ws_id, stream_id)
    merged = merge_patch(existing, body) if isinstance(body, IncomeStreamPatch) else body
    account = _validate(ws_id, merged)  # 404/400 before any write
    specs = _commitment_specs(merged, account["account"], today)

    old_ids: list[str] = existing["commitment_ids"]
    resolved: list[Commitment] = []
    for cid in old_ids:
        try:
            resolved.append(org_commitments.get(ws_id, cid))
        except KeyError:
            break
    if old_ids and len(resolved) == len(old_ids) == len(specs):
        updated = [org_commitments.update(ws_id, c.id, spec, today) for c, spec in zip(resolved, specs, strict=True)]
        new_ids = [c.id for c in updated]
    else:
        _remove_commitments(ws_id, old_ids)
        updated = [org_commitments.create(ws_id, spec, today) for spec in specs]
        new_ids = [c.id for c in updated]
    next_expected = min((c.next_due for c in updated), default=_next_expected(merged) or today)

    conn = store.db()
    conn.execute(
        "UPDATE pf_income_streams SET name=?, source_type=?, amount=?, currency=?, gross_amount=?, cadence=?, "
        "anchor_days=?, weekday=?, next_expected=?, account_id=?, label_id=?, active=?, notes=?, "
        "commitment_ids=?, updated_at=? WHERE ws_id=? AND id=?",
        (
            merged.name, merged.source_type, str(q2(merged.amount.amount)), merged.amount.currency,
            str(q2(merged.gross_amount.amount)) if merged.gross_amount else None, merged.cadence,
            store.dumps(merged.anchor_days), merged.weekday, next_expected.isoformat(), merged.account_id,
            merged.label_id, int(merged.active), merged.notes, store.dumps(new_ids), store.now(), ws_id, stream_id,
        ),
    )
    conn.commit()
    return get_stream(ws_id, stream_id)


def delete_stream(ws_id: str, stream_id: str) -> dict:
    existing = _fetch(ws_id, stream_id)
    _remove_commitments(ws_id, existing["commitment_ids"])
    conn = store.db()
    cur = conn.execute("DELETE FROM pf_income_streams WHERE ws_id=? AND id=?", (ws_id, stream_id))
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(stream_id)
    return {"id": stream_id, "deleted": True}


# --------------------------------------------------------------------------- expected vs received


def stream_history(ws_id: str, stream_id: str, limit: int = 12, today: date | None = None) -> list[dict]:
    """Per projected occurrence: expected vs received. A pf entry stamped with the commitment id wins;
    otherwise the organizer's own matching (normalized payee) decides."""
    from ..organizer import occurrences as org_occ
    from . import entries as pf_entries

    stream = _fetch(ws_id, stream_id)
    ledger = get_ledger()
    journal = None
    rows: list[dict] = []
    for cid in stream["commitment_ids"]:
        try:
            c = org_commitments.get(ws_id, cid)
        except KeyError:
            continue
        for occ in org_occ.recent(ws_id, c, limit=limit, today=today):
            received = None
            status = occ.status
            linked = pf_entries.find_by_commitment(ws_id, cid, occ.due)
            if linked is not None:
                received = {"amount": str(q2(abs(Decimal(linked["amount"]["amount"])))),
                            "currency": linked["amount"]["currency"]}
                status = "paid" if status not in ("paid", "skipped") else status
            elif occ.txn_id:
                if journal is None:
                    journal = ledger.journal(ws_id)
                txn = next((t for t in journal if occ.txn_id in t.links), None)
                if txn:
                    for p in txn.postings:
                        if p.amount is not None and p.account.startswith("Income:"):
                            received = store.money(-p.amount.amount, p.amount.currency)
                            break
            rows.append(
                {
                    "due": occ.due.isoformat(),
                    "expected": occ.amount.model_dump(mode="json"),
                    "received": received,
                    "status": status,
                    "entry_id": linked["id"] if linked else None,
                }
            )
    rows.sort(key=lambda r: r["due"])
    return rows


# --- router -----------------------------------------------------------------------------------


@router.post("/{ws}/income/streams")
def api_create_stream(ws: str, body: IncomeStreamIn) -> dict:
    try:
        return create_stream(ws, body)
    except KeyError as e:
        raise HTTPException(404, f"account or label {str(e).strip(chr(39))} not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{ws}/income/streams")
def api_list_streams(ws: str, active_only: bool = False) -> list[dict]:
    return list_streams(ws, active_only)


@router.get("/{ws}/income/streams/{stream_id}")
def api_get_stream(ws: str, stream_id: str) -> dict:
    try:
        return get_stream(ws, stream_id)
    except KeyError as e:
        raise HTTPException(404, f"income stream {stream_id} not found") from e


@router.put("/{ws}/income/streams/{stream_id}")
def api_update_stream(ws: str, stream_id: str, body: IncomeStreamPatch) -> dict:
    try:
        return update_stream(ws, stream_id, body)
    except KeyError as e:
        raise HTTPException(404, f"{str(e).strip(chr(39))} not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{ws}/income/streams/{stream_id}")
def api_delete_stream(ws: str, stream_id: str) -> dict:
    try:
        return delete_stream(ws, stream_id)
    except KeyError as e:
        raise HTTPException(404, f"income stream {stream_id} not found") from e


@router.get("/{ws}/income/streams/{stream_id}/history")
def api_stream_history(ws: str, stream_id: str, limit: int = 12) -> list[dict]:
    try:
        return stream_history(ws, stream_id, limit)
    except KeyError as e:
        raise HTTPException(404, f"income stream {stream_id} not found") from e
