"""Commitment CRUD + price history + projected occurrences.

Stable functions other modules call (keep these signatures): ``create(ws, CommitmentIn, today=None)``,
``get``, ``list_commitments(ws, kind=None, status=None)``, ``soft_delete``, ``set_status``,
``record_price``. ``get()``/``list_commitments()`` return the **stored** ``next_due``; the *effective*
value (first not-paid/skipped projected due ≥ today) is computed by :func:`effective_next_due` and is
what API rows carry.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import Amount, q2
from . import cadence as cad
from . import normalize, pf_bridge, store
from .models import Commitment, CommitmentIn, CommitmentPatch

_COLUMNS = (
    "id, ws_id, kind, name, merchant_patterns, amount, currency, amount_variable, cadence, "
    "interval_days, anchor_day, weekday, next_due, account, account_id, label_id, essential, status, "
    "trial_ends, started, ended, auto_pay, cancel_notes, linked_loan_id, linked_card_id, "
    "source, confidence, last_seen, notes, category_hint, reviewed_at, created_at, updated_at"
)

# Fields ``update_partial`` leaves untouched unless the patch names them explicitly.
_PROTECTED = (
    "source", "confidence", "started", "last_seen", "ended", "linked_loan_id", "linked_card_id",
    "category_hint", "account_id", "reviewed_at",
)
_CADENCE_FIELDS = ("cadence", "interval_days", "anchor_day", "weekday")
_ACTIVE_LIKE = ("active", "trial", "paused")


def row_to_commitment(row) -> Commitment:
    d = dict(row)
    return Commitment(
        id=d["id"],
        ws_id=d["ws_id"],
        kind=d["kind"],
        name=d["name"],
        merchant_patterns=store.loads(d["merchant_patterns"], []),
        amount=Amount(amount=Decimal(d["amount"]), currency=d["currency"]),
        amount_variable=bool(d["amount_variable"]),
        cadence=d["cadence"],
        interval_days=d["interval_days"],
        anchor_day=d["anchor_day"],
        weekday=d["weekday"],
        next_due=store.as_date(d["next_due"]),
        account=d["account"],
        account_id=d.get("account_id"),
        label_id=d["label_id"],
        essential=d["essential"],
        status=d["status"],
        trial_ends=store.as_date(d["trial_ends"]),
        started=store.as_date(d["started"]),
        ended=store.as_date(d["ended"]),
        auto_pay=bool(d["auto_pay"]),
        cancel_notes=d["cancel_notes"],
        linked_loan_id=d["linked_loan_id"],
        linked_card_id=d["linked_card_id"],
        source=d["source"],
        confidence=float(d["confidence"]),
        last_seen=store.as_date(d["last_seen"]),
        notes=d["notes"],
        category_hint=d["category_hint"],
        reviewed_at=store.as_date(d["reviewed_at"]),
    )


def normalize_patterns(patterns: list[str], name: str) -> list[str]:
    """Merchant patterns are stored normalized (``normalize.normalize`` is idempotent over the alias
    table); an empty list falls back to the normalized name."""
    out: list[str] = []
    for p in patterns or []:
        n = normalize.normalize(p)
        if n and n not in out:
            out.append(n)
    if not out:
        n = normalize.normalize(name)
        if n:
            out.append(n)
    return out


def _derive_anchor(cadence: str, anchor_day: int | None, next_due: date) -> int | None:
    """Month cadences keep the day of the first due as their anchor, so 10-31 projects to 11-30 and
    springs back to 12-31 instead of drifting to the 30th forever."""
    if cadence in cad.MONTH_STEP and anchor_day is None:
        return next_due.day
    return anchor_day


def _resolved_next_due(body: CommitmentIn, today: date | None = None) -> date:
    if body.next_due is not None:
        return body.next_due
    today = today or date.today()
    anchor = body.last_seen or body.started or today
    return cad.project_next(
        anchor, body.cadence, today=today, interval_days=body.interval_days,
        anchor_day=body.anchor_day, weekday=body.weekday, strictly_after=False,
    )


def create(ws_id: str, body: CommitmentIn, today: date | None = None) -> Commitment:
    """Insert a commitment. ``account_id`` (pf) wins over ``account`` (ledger name); an unknown
    ``account_id`` raises ``KeyError`` (the router answers 404)."""
    conn = store.db()
    cid = store.new_id("cmt")
    ts = store.now()
    next_due = _resolved_next_due(body, today)
    anchor_day = _derive_anchor(body.cadence, body.anchor_day, next_due)
    account_id, account = pf_bridge.resolve_account(ws_id, body.account_id, body.account)
    patterns = normalize_patterns(body.merchant_patterns, body.name)
    conn.execute(
        f"INSERT INTO organizer_commitments ({_COLUMNS}) VALUES ({','.join('?' * 33)})",
        (
            cid, ws_id, body.kind, body.name, store.dumps(patterns),
            str(q2(body.amount.amount)), body.amount.currency, int(body.amount_variable), body.cadence,
            body.interval_days, anchor_day, body.weekday, next_due.isoformat(), account, account_id,
            body.label_id, body.essential, body.status, store.iso(body.trial_ends),
            store.iso(body.started), store.iso(body.ended), int(body.auto_pay), body.cancel_notes,
            body.linked_loan_id, body.linked_card_id, body.source, float(body.confidence),
            store.iso(body.last_seen), body.notes, body.category_hint, None, ts, ts,
        ),
    )
    conn.commit()
    record_price(ws_id, cid, body.last_seen or next_due, body.amount, source=body.source)
    return get(ws_id, cid)


def get(ws_id: str, cid: str) -> Commitment:
    conn = store.db()
    row = conn.execute("SELECT * FROM organizer_commitments WHERE ws_id=? AND id=?", (ws_id, cid)).fetchone()
    if row is None:
        raise KeyError(cid)
    return row_to_commitment(row)


def list_commitments(
    ws_id: str, kind: str | None = None, status: str | None = None
) -> list[Commitment]:
    conn = store.db()
    sql = "SELECT * FROM organizer_commitments WHERE ws_id=?"
    args: list[object] = [ws_id]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY next_due, name"
    return [row_to_commitment(r) for r in conn.execute(sql, args).fetchall()]


def find_duplicate(ws_id: str, name: str, patterns: list[str] | None = None,
                   exclude_id: str | None = None) -> Commitment | None:
    """An active/trial/paused commitment with the same normalized name (accents/case/noise stripped —
    NOT the alias merchant, so "Seguro auto" and "Seguro casa" stay distinct) or a shared merchant
    pattern."""
    wanted_name = normalize.clean(name)
    wanted_patterns = set(normalize_patterns(patterns or [], name))
    for c in list_commitments(ws_id):
        if c.status not in _ACTIVE_LIKE or c.id == exclude_id:
            continue
        if wanted_name and normalize.clean(c.name) == wanted_name:
            return c
        if wanted_patterns & set(c.merchant_patterns):
            return c
    return None


def _delete_same_day_manual_prices(ws_id: str, cid: str, when: date) -> None:
    """Drop manual observations dated today **or later** — a same-day correction replaces the row, and
    a future-dated manual row can only be the stamp ``create()`` left at ``next_due``."""
    conn = store.db()
    conn.execute(
        "DELETE FROM organizer_price_history WHERE ws_id=? AND commitment_id=? AND observed>=? AND source='manual'",
        (ws_id, cid, when.isoformat()),
    )
    conn.commit()


def update_partial(ws_id: str, cid: str, patch: CommitmentPatch, today: date | None = None) -> Commitment:
    """PATCH-merge: only the keys present in ``patch`` change. Cadence/anchor/interval/weekday changes
    re-project ``next_due`` (unless the patch sets it); an amount change records a price observed
    today after wiping same-day manual observations, so a typo correction never fires an alert."""
    existing = get(ws_id, cid)
    today = today or date.today()
    # values straight from the model (a nested ``model_dump(exclude_unset=True)`` would drop Amount.currency)
    changes = {k: getattr(patch, k) for k in patch.model_fields_set if k != "force"}
    if changes.get("next_due", "unset") is None:
        changes.pop("next_due")  # null never clears a due date; it means "re-project or keep"
    merged = existing.model_dump()
    merged.pop("explain", None)
    wanted_id = changes.pop("account_id", None)
    wanted_account = changes.pop("account", None)
    merged.update(changes)

    if wanted_id or wanted_account:
        merged["account_id"], merged["account"] = pf_bridge.resolve_account(ws_id, wanted_id, wanted_account)
    elif "account_id" in patch.model_fields_set and wanted_id is None:
        merged["account_id"] = None  # explicit null unlinks the pf account; the ledger name stays
    if "merchant_patterns" in changes:
        merged["merchant_patterns"] = normalize_patterns(changes["merchant_patterns"] or [], merged["name"])

    cadence_changed = any(k in changes and changes[k] != getattr(existing, k) for k in _CADENCE_FIELDS)
    if cadence_changed and "next_due" not in changes:
        merged["next_due"] = cad.project_next(
            today, merged["cadence"], today=today, interval_days=merged["interval_days"],
            anchor_day=merged["anchor_day"], weekday=merged["weekday"], strictly_after=False,
        )
    next_due = store.as_date(merged["next_due"])
    if "anchor_day" in changes and changes["anchor_day"] is None:
        merged["anchor_day"] = None
    merged["anchor_day"] = _derive_anchor(merged["cadence"], merged["anchor_day"], next_due)

    amount = merged["amount"]
    amount_value = q2(Decimal(str(amount["amount"]))) if isinstance(amount, dict) else q2(amount.amount)
    currency = amount["currency"] if isinstance(amount, dict) else amount.currency

    conn = store.db()
    conn.execute(
        "UPDATE organizer_commitments SET kind=?, name=?, merchant_patterns=?, amount=?, currency=?, "
        "amount_variable=?, cadence=?, interval_days=?, anchor_day=?, weekday=?, next_due=?, account=?, "
        "account_id=?, label_id=?, essential=?, status=?, trial_ends=?, started=?, ended=?, auto_pay=?, "
        "cancel_notes=?, linked_loan_id=?, linked_card_id=?, source=?, confidence=?, last_seen=?, notes=?, "
        "category_hint=?, reviewed_at=?, updated_at=? WHERE ws_id=? AND id=?",
        (
            merged["kind"], merged["name"], store.dumps(merged["merchant_patterns"]), str(amount_value),
            currency, int(bool(merged["amount_variable"])), merged["cadence"], merged["interval_days"],
            merged["anchor_day"], merged["weekday"], next_due.isoformat(), merged["account"],
            merged["account_id"], merged["label_id"], merged["essential"], merged["status"],
            store.iso(merged["trial_ends"]), store.iso(merged["started"]), store.iso(merged["ended"]),
            int(bool(merged["auto_pay"])), merged["cancel_notes"], merged["linked_loan_id"],
            merged["linked_card_id"], merged["source"], float(merged["confidence"]),
            store.iso(merged["last_seen"]), merged["notes"], merged["category_hint"],
            store.iso(merged["reviewed_at"]), store.now(), ws_id, cid,
        ),
    )
    conn.commit()
    if "amount" in changes and amount_value != q2(existing.amount.amount):
        _delete_same_day_manual_prices(ws_id, cid, today)
        record_price(ws_id, cid, today, Amount(amount=amount_value, currency=currency), source="manual")
    return get(ws_id, cid)


def update(ws_id: str, cid: str, body: CommitmentIn, today: date | None = None) -> Commitment:
    """Full replace, kept for callers that still send a whole ``CommitmentIn``: a thin wrapper that
    turns every field of the body into a patch."""
    data = body.model_dump(exclude={"force"})
    for key in ("next_due", "account", "account_id"):
        if data.get(key) is None:
            data.pop(key)  # a full body without these keeps the stored values (old ``update`` semantics)
    return update_partial(ws_id, cid, CommitmentPatch(**data), today=today)


def set_status(ws_id: str, cid: str, status: str, *, ended: date | None = None,
               cancel_notes: str | None = None) -> Commitment:
    get(ws_id, cid)  # 404s on unknown id
    conn = store.db()
    conn.execute(
        "UPDATE organizer_commitments SET status=?, ended=?, cancel_notes=COALESCE(?, cancel_notes), "
        "updated_at=? WHERE ws_id=? AND id=?",
        (status, store.iso(ended), cancel_notes, store.now(), ws_id, cid),
    )
    conn.commit()
    return get(ws_id, cid)


def soft_delete(ws_id: str, cid: str, today: date | None = None) -> Commitment:
    """DELETE is a soft delete: status ``cancelled`` + ``ended`` today. Nothing is ever erased."""
    return set_status(ws_id, cid, "cancelled", ended=today or date.today())


def mark_reviewed(ws_id: str, cid: str, when: date | None = None) -> date:
    get(ws_id, cid)
    when = when or date.today()
    conn = store.db()
    conn.execute(
        "UPDATE organizer_commitments SET reviewed_at=?, updated_at=? WHERE ws_id=? AND id=?",
        (when.isoformat(), store.now(), ws_id, cid),
    )
    conn.commit()
    return when


# --------------------------------------------------------------------------- read-path roll-forward


def activate_ended_trials(ws_id: str, today: date) -> int:
    """``trial`` → ``active`` once ``trial_ends`` is in the past (applied lazily on every read path)."""
    conn = store.db()
    cur = conn.execute(
        "UPDATE organizer_commitments SET status='active', updated_at=? "
        "WHERE ws_id=? AND status='trial' AND trial_ends IS NOT NULL AND trial_ends < ?",
        (store.now(), ws_id, today.isoformat()),
    )
    conn.commit()
    return cur.rowcount


def persist_next_due(ws_id: str, cid: str, effective: date, today: date) -> bool:
    """Idempotent roll-forward of a stale stored ``next_due`` (only when it is already in the past)."""
    conn = store.db()
    cur = conn.execute(
        "UPDATE organizer_commitments SET next_due=? WHERE ws_id=? AND id=? AND next_due < ?",
        (effective.isoformat(), ws_id, cid, today.isoformat()),
    )
    conn.commit()
    return cur.rowcount > 0


def effective_next_due(ws_id: str, c: Commitment, today: date, txns: list | None = None) -> date:
    """First projected due ≥ today whose status is neither paid nor skipped, looked for over
    ``[today, today + 2 × nominal cadence days]``. Paused/cancelled: the first projected due ≥ today.
    Nothing in the window → the cadence projection of the stored value."""
    from . import occurrences as occ

    if c.status in ("paused", "cancelled"):
        return cad.project_next(
            c.next_due, c.cadence, today=today, interval_days=c.interval_days,
            anchor_day=c.anchor_day, weekday=c.weekday, strictly_after=False,
        )
    horizon = today + timedelta(days=2 * cad.nominal_days(c.cadence, c.interval_days))
    for o in occ.build(ws_id, c, today, horizon, today=today, txns=txns):
        if o.due >= today and o.status not in ("paid", "skipped"):
            return o.due
    return cad.project_next(
        c.next_due, c.cadence, today=today, interval_days=c.interval_days,
        anchor_day=c.anchor_day, weekday=c.weekday, strictly_after=False,
    )


# --------------------------------------------------------------------------- price history


def record_price(ws_id: str, cid: str, observed: date | None, amount: Amount,
                 source: str = "detected") -> None:
    if observed is None:
        return
    conn = store.db()
    conn.execute(
        "INSERT OR IGNORE INTO organizer_price_history (ws_id, commitment_id, observed, amount, "
        "currency, source) VALUES (?,?,?,?,?,?)",
        (ws_id, cid, observed.isoformat(), str(q2(amount.amount)), amount.currency, source),
    )
    conn.commit()


def price_history(ws_id: str, cid: str) -> list[dict]:
    conn = store.db()
    rows = conn.execute(
        "SELECT observed, amount, currency, source FROM organizer_price_history "
        "WHERE ws_id=? AND commitment_id=? ORDER BY observed, amount",
        (ws_id, cid),
    ).fetchall()
    return [
        {"observed": r["observed"], "amount": {"amount": r["amount"], "currency": r["currency"]},
         "source": r["source"]}
        for r in rows
    ]


def monthly_equivalent(c: Commitment) -> Decimal:
    """Amount normalized to one month = amount × periods_per_year / 12."""
    per_year = Decimal(str(cad.periods_per_year(c.cadence, c.interval_days)))
    return q2(c.amount.amount * per_year / Decimal("12"))


def annual_equivalent(c: Commitment) -> Decimal:
    per_year = Decimal(str(cad.periods_per_year(c.cadence, c.interval_days)))
    return q2(c.amount.amount * per_year)


def commitment_explain(c: Commitment, lang: str, next_due: date | None = None) -> Explain:
    e = Explain(summary=i18n_t("organizer.commitment", lang, name=c.name, cadence=c.cadence))
    e.add_step("amount", f"{q2(c.amount.amount)} {c.amount.currency}")
    e.add_step(
        "monthly_equivalent", monthly_equivalent(c),
        formula=f"amount × {cad.periods_per_year(c.cadence, c.interval_days)}/12",
    )
    e.add_step("next_due", (next_due or c.next_due).isoformat())
    e.confidence = c.confidence
    return e


def with_explain(ws_id: str, c: Commitment, lang: str | None = None, today: date | None = None,
                 txns: list | None = None, accounts: dict | None = None) -> dict:
    """API row: the commitment with its explain, monthly/annual equivalents, ``account_id`` /
    ``account_name`` and the **effective** ``next_due`` (the stored one is kept as ``stored_next_due``)."""
    lang = lang or ws_lang(ws_id)
    today = today or date.today()
    accounts = accounts if accounts is not None else pf_bridge.accounts_index(ws_id)
    effective = effective_next_due(ws_id, c, today, txns=txns) if c.id else c.next_due
    data = c.model_dump(mode="json")
    data["stored_next_due"] = c.next_due.isoformat()
    data["next_due"] = effective.isoformat()
    hit = accounts.get(c.account_id) if c.account_id else accounts.get(c.account)
    data["account_id"] = hit["id"] if hit else c.account_id
    data["account_name"] = hit["name"] if hit else None
    data["explain"] = commitment_explain(c, lang, effective).model_dump()
    data["monthly_equivalent"] = {"amount": str(monthly_equivalent(c)), "currency": c.amount.currency}
    data["annual_equivalent"] = {"amount": str(annual_equivalent(c)), "currency": c.amount.currency}
    return data
