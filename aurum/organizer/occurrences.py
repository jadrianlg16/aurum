"""Projected occurrences and their paid/unpaid status.

An occurrence is *derived*, not stored: the due dates come from the commitment's cadence and the
status from the ledger. The ``organizer_occurrences`` table only holds **overrides** — a manual
"paid"/"skipped" mark, with the pf entry that backs it — so re-projecting never loses a user decision
and never invents one.

History: ``build()`` projects from the **earliest evidence** of the commitment — ``floor =
min(started, last_seen, first price observation)`` — so past months populate instead of starting at the
last charge, and the stored ``next_due`` is never appended (the *effective* next due is computed by
``commitments.effective_next_due``). One void-aware ledger read per ``build()``; callers that build
many commitments share it through ``txns=``.

Matching rule (stated in every ``explain``): first a pf entry **linked** by ``commitment_id`` within
±7 days (amount ignored — the user said this is the payment); else a live ledger transaction whose
normalized payee contains one of the commitment's normalized merchant patterns as **whole words**,
within **±3 days** of the due date and **±10 %** of the expected amount (an ``amount_variable``
commitment matches on the date window alone). Nearest date wins.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

from ..core.money import Amount, q2
from . import cadence as cad
from . import normalize, pf_bridge, store
from .models import Commitment, Occurrence

DATE_WINDOW_DAYS = 3
LINK_WINDOW_DAYS = 7
AMOUNT_TOLERANCE = Decimal("0.10")
MISSED_AFTER_DAYS = 3
FLOOR_SLACK_DAYS = 3


class MarkError(Exception):
    """A mark/un-mark rule violation the router turns into a 4xx (``status_code``, ``detail``)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# --------------------------------------------------------------------------- matching


def _pattern_regexes(c: Commitment) -> list[re.Pattern[str]]:
    raw = [normalize.normalize(p) for p in c.merchant_patterns if p] or [normalize.normalize(c.name)]
    out = []
    for pattern in raw:
        if not pattern:
            continue
        out.append(re.compile(rf"(?<![A-Z0-9]){re.escape(pattern)}(?![A-Z0-9])"))
    return out


def _txn_magnitude(c: Commitment, txn) -> Decimal:
    magnitude = Decimal("0")
    for p in txn.postings:
        if p.amount is None:
            continue
        if c.kind == "income":
            if p.account.startswith("Income:") and p.amount.amount < 0:
                magnitude = -p.amount.amount
        elif p.account.startswith(("Expenses:", "Liabilities:")) and p.amount.amount > 0:
            magnitude = p.amount.amount
    return magnitude


def _linked_match(ws_id: str, c: Commitment, due: date) -> str | None:
    if not c.id:
        return None
    rows = pf_bridge.linked_entries(
        ws_id, c.id, due - timedelta(days=LINK_WINDOW_DAYS), due + timedelta(days=LINK_WINDOW_DAYS)
    )
    best: tuple[int, str] | None = None
    for row in rows:
        distance = abs((store.as_date(row["date"]) - due).days)
        if best is None or distance < best[0]:
            best = (distance, row["txn_id"])
    return best[1] if best else None


def find_matching_txn(ws_id: str, c: Commitment, due: date, txns: list | None = None) -> str | None:
    """Ledger transaction paying ``c`` on ``due``, or None. Deterministic: link first, then the
    nearest payee match. ``txns`` (from :func:`pf_bridge.live_txns`) may be shared by the caller."""
    linked = _linked_match(ws_id, c, due)
    if linked:
        return linked
    window_start = due - timedelta(days=DATE_WINDOW_DAYS)
    window_end = due + timedelta(days=DATE_WINDOW_DAYS)
    if txns is None:
        txns = pf_bridge.live_txns(ws_id, window_start, window_end)
    regexes = _pattern_regexes(c)
    if not regexes:
        return None
    expected = q2(c.amount.amount)
    best: tuple[int, str] | None = None
    for txn in txns:
        if txn.date < window_start or txn.date > window_end:
            continue
        merchant = normalize.normalize(txn.payee or txn.narration or "")
        if not any(r.search(merchant) for r in regexes):
            continue
        magnitude = _txn_magnitude(c, txn)
        if magnitude == 0:
            continue
        if not c.amount_variable and expected > 0 and abs(magnitude - expected) > expected * AMOUNT_TOLERANCE:
            continue
        txn_id = (txn.links or [None])[0]
        if txn_id is None:
            continue
        distance = abs((txn.date - due).days)
        if best is None or distance < best[0]:
            best = (distance, txn_id)
    return best[1] if best else None


# --------------------------------------------------------------------------- overrides


def get_override(ws_id: str, commitment_id: str, due: date) -> dict | None:
    conn = store.db()
    row = conn.execute(
        "SELECT status, txn_id, amount, currency, entry_id, auto_created FROM organizer_occurrences "
        "WHERE ws_id=? AND commitment_id=? AND due=?",
        (ws_id, commitment_id, due.isoformat()),
    ).fetchone()
    return dict(row) if row else None


def _overrides_between(ws_id: str, commitment_id: str, start: date, end: date) -> dict[date, dict]:
    conn = store.db()
    rows = conn.execute(
        "SELECT due, status, txn_id, amount, currency, entry_id, auto_created FROM organizer_occurrences "
        "WHERE ws_id=? AND commitment_id=? AND due>=? AND due<=?",
        (ws_id, commitment_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    return {store.as_date(r["due"]): dict(r) for r in rows}


# --------------------------------------------------------------------------- projection


def history_floor(ws_id: str, c: Commitment) -> date:
    """Earliest evidence of the commitment: min(started, last_seen, first price observation). Always
    defined because ``create()`` records a price at ``last_seen or next_due``; the stored ``next_due``
    is the last resort."""
    candidates = [d for d in (c.started, c.last_seen) if d is not None]
    if c.id:
        conn = store.db()
        row = conn.execute(
            "SELECT MIN(observed) AS first FROM organizer_price_history WHERE ws_id=? AND commitment_id=?",
            (ws_id, c.id),
        ).fetchone()
        first = store.as_date(row["first"]) if row and row["first"] else None
        if first is not None:
            candidates.append(first)
    return min(candidates) if candidates else c.next_due


def _resolve(c: Commitment, due: date, today: date, override: dict | None, txn_id: str | None) -> Occurrence:
    amount = (
        Amount(amount=Decimal(override["amount"]), currency=override["currency"])
        if override and override.get("amount")
        else c.amount
    )
    if override:
        return Occurrence(
            commitment_id=c.id, due=due, amount=amount, status=override["status"],
            txn_id=override.get("txn_id"), entry_id=override.get("entry_id"),
            auto_created=bool(override.get("auto_created")),
        )
    if txn_id:
        status = "paid"
    elif due < today - timedelta(days=MISSED_AFTER_DAYS):
        status = "missed"
    elif due <= today:
        status = "due"
    else:
        status = "upcoming"
    entry_id = None
    if txn_id:
        owner = pf_bridge.pf_entry_by_txn(c.ws_id, txn_id) if c.ws_id else None
        entry_id = owner["id"] if owner else None
    return Occurrence(commitment_id=c.id, due=due, amount=amount, status=status, txn_id=txn_id,
                      entry_id=entry_id)


def build(ws_id: str, c: Commitment, start: date, end: date, today: date | None = None,
          txns: list | None = None) -> list[Occurrence]:
    """Every occurrence of ``c`` in ``[start, end]`` with its resolved status, projected from the
    earliest evidence (never before ``floor − 3 days``) and clipped at ``ended``."""
    today = today or date.today()
    if end < start:
        return []
    if c.status == "cancelled" and c.ended and c.ended < start:
        return []
    floor = history_floor(ws_id, c)
    lower = max(start, floor - timedelta(days=FLOOR_SLACK_DAYS))
    if lower > end:
        return []
    dues = cad.occurrences_between(
        floor, c.cadence, lower, end, interval_days=c.interval_days,
        anchor_day=c.anchor_day, weekday=c.weekday,
    )
    # a trial bills nothing before it ends: its first real occurrence is the one after trial_ends
    trial_floor = c.trial_ends if c.status == "trial" and c.trial_ends else None
    dues = sorted({
        d for d in dues
        if d >= floor - timedelta(days=FLOOR_SLACK_DAYS)
        and (c.started is None or d >= c.started - timedelta(days=FLOOR_SLACK_DAYS))
        and (trial_floor is None or d >= trial_floor)
        and (c.ended is None or d <= c.ended)
    })
    if not dues:
        return []
    if c.status == "paused":
        return [Occurrence(commitment_id=c.id, due=d, amount=c.amount, status="skipped") for d in dues]
    overrides = _overrides_between(ws_id, c.id, dues[0], dues[-1]) if c.id else {}
    if txns is None:
        txns = pf_bridge.live_txns(
            ws_id, dues[0] - timedelta(days=DATE_WINDOW_DAYS), dues[-1] + timedelta(days=DATE_WINDOW_DAYS)
        )
    out: list[Occurrence] = []
    for due in dues:
        override = overrides.get(due)
        if override and _override_entry_voided(ws_id, override):
            # Void-aware: a 'paid' mark whose logged entry was deleted no longer counts; the
            # occurrence falls back to live matching, so it reads due/missed/upcoming again.
            override = None
        txn_id = None if override else find_matching_txn(ws_id, c, due, txns=txns)
        out.append(_resolve(c, due, today, override, txn_id))
    return out


def _override_entry_voided(ws_id: str, override: dict) -> bool:
    if override.get("status") != "paid" or not override.get("entry_id"):
        return False
    row = pf_bridge.pf_entry_row(ws_id, override["entry_id"])
    return row is None or bool(row["voided"])


def recent(ws_id: str, c: Commitment, limit: int = 12, today: date | None = None,
           txns: list | None = None) -> list[Occurrence]:
    """The last ``limit`` occurrences up to today (newest last), for the commitment drawer."""
    today = today or date.today()
    span_days = cad.nominal_days(c.cadence, c.interval_days) * (limit + 1)
    start = today - timedelta(days=span_days)
    return build(ws_id, c, start, today, today=today, txns=txns)[-limit:]


# --------------------------------------------------------------------------- marks


def mark(ws_id: str, commitment_id: str, due: date, status: str, txn_id: str | None = None,
         amount: Amount | None = None, *, entry_id: str | None = None,
         auto_created: bool = False) -> Occurrence:
    """Write (upsert) the override row. Low-level: the mark rules live in :func:`mark_occurrence`."""
    from . import commitments as cmt

    c = cmt.get(ws_id, commitment_id)
    value = amount or c.amount
    value = Amount(amount=q2(value.amount), currency=value.currency)
    conn = store.db()
    conn.execute(
        "INSERT INTO organizer_occurrences (id, ws_id, commitment_id, due, amount, currency, status, "
        "txn_id, marked_at, entry_id, auto_created) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(ws_id, commitment_id, due) DO UPDATE SET status=excluded.status, "
        "txn_id=excluded.txn_id, amount=excluded.amount, marked_at=excluded.marked_at, "
        "entry_id=excluded.entry_id, auto_created=excluded.auto_created",
        (store.new_id("occ"), ws_id, commitment_id, due.isoformat(), str(q2(value.amount)),
         value.currency, status, txn_id, store.now(), entry_id, int(auto_created)),
    )
    conn.commit()
    return Occurrence(commitment_id=commitment_id, due=due, amount=value, status=status, txn_id=txn_id,
                      entry_id=entry_id, auto_created=auto_created)


def _void_auto_created(ws_id: str, override: dict | None) -> str | None:
    """Void the pf entry an earlier mark created, only when it is still untouched. Returns its id."""
    if not override or not override.get("auto_created") or not override.get("entry_id"):
        return None
    row = pf_bridge.pf_entry_row(ws_id, override["entry_id"])
    if row is None or row["voided"] or row["updated_at"] != row["created_at"]:
        return None
    try:
        pf_bridge.void_pf_entry(ws_id, row["id"])
    except ValueError as e:  # already voided between the read and the write
        raise MarkError(409, str(e)) from e
    except PermissionError as e:
        raise MarkError(403, str(e)) from e
    except KeyError as e:
        raise MarkError(404, f"entry {row['id']} not found") from e
    return row["id"]


def _account_for_entry(ws_id: str, c: Commitment, account_id: str | None) -> str:
    if account_id:
        return account_id
    if c.account_id:
        return c.account_id
    hit = pf_bridge.accounts_index(ws_id).get(c.account)
    if hit and not hit["archived"]:
        return hit["id"]
    raise MarkError(400, "Primero elige una cuenta")


def mark_occurrence(ws_id: str, c: Commitment, due: date, status: str, *, entry_id: str | None = None,
                    log_entry: bool = False, amount: Amount | None = None,
                    account_id: str | None = None, txn_id: str | None = None) -> Occurrence:
    """The rules for ``POST /occurrences/mark``:

    * ``skipped`` → override skipped (an auto-created, unedited entry on that occurrence is voided first);
    * ``paid`` + ``entry_id`` → link that pf entry (404 when missing/voided), stamp ``commitment_id``;
    * ``paid`` alone → idempotent when a paid override already carries a live entry; else match first
      (link, then payee); else, with ``log_entry``, create the pf entry (``auto_created``); else a
      plain paid mark (legacy ``txn_id`` honoured).
    """
    existing = get_override(ws_id, c.id, due)
    if status == "skipped":
        _void_auto_created(ws_id, existing)
        return mark(ws_id, c.id, due, "skipped", None, amount)

    if entry_id:
        row = pf_bridge.pf_entry_row(ws_id, entry_id)
        if row is None or row["voided"]:
            raise MarkError(404, f"entry {entry_id} not found")
        pf_bridge.stamp_commitment(ws_id, entry_id, c.id)
        value = amount or Amount(amount=Decimal(str(row["amount"])), currency=row["currency"])
        return mark(ws_id, c.id, due, "paid", row["txn_id"], value, entry_id=entry_id, auto_created=False)

    if existing and existing["status"] == "paid" and existing.get("entry_id"):
        row = pf_bridge.pf_entry_row(ws_id, existing["entry_id"])
        if row is not None and not row["voided"]:
            return _resolve(c, due, due, existing, None)

    if txn_id is None:
        txn_id = find_matching_txn(ws_id, c, due)
    if txn_id:
        owner = pf_bridge.pf_entry_by_txn(ws_id, txn_id)
        return mark(ws_id, c.id, due, "paid", txn_id, amount,
                    entry_id=owner["id"] if owner else None, auto_created=False)

    if not log_entry:
        return mark(ws_id, c.id, due, "paid", None, amount)

    if c.kind == "transfer":
        raise MarkError(400, "Un pago de tipo transferencia se registra desde Movimientos")
    value = amount or c.amount
    if q2(value.amount) <= 0:
        raise MarkError(400, "Indica el monto")
    target_account = _account_for_entry(ws_id, c, account_id)
    try:
        row = pf_bridge.create_pf_entry(
            ws_id, kind="income" if c.kind == "income" else "expense", when=due,
            amount=Amount(amount=q2(value.amount), currency=value.currency), account_id=target_account,
            label_id=c.label_id, payee=c.name, commitment_id=c.id,
        )
    except KeyError as e:
        raise MarkError(404, f"account or category not found: {e}") from e
    except ValueError as e:
        raise MarkError(400, str(e)) from e
    return mark(ws_id, c.id, due, "paid", row["txn_id"], value, entry_id=row["id"], auto_created=True)


def unmark_occurrence(ws_id: str, commitment_id: str, due: date) -> tuple[bool, str | None]:
    """``DELETE /occurrences/mark``: drop the override; void the entry only when the mark created it
    and nobody edited it since. → ``(removed, voided_entry_id)``."""
    existing = get_override(ws_id, commitment_id, due)
    if existing is None:
        return False, None
    voided = _void_auto_created(ws_id, existing)
    conn = store.db()
    conn.execute(
        "DELETE FROM organizer_occurrences WHERE ws_id=? AND commitment_id=? AND due=?",
        (ws_id, commitment_id, due.isoformat()),
    )
    conn.commit()
    return True, voided
