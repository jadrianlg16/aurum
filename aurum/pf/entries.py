"""The human transaction API.

No accounting vocabulary leaves this module. A caller sends ``{kind, date, amount, account_id, ...}``
and gets back a flat row with one signed amount, an account name and a category (label) name — never
postings, never debit/credit. Underneath, every entry still becomes a balanced double-entry Beancount
transaction via ``aurum.ledger.base.get_ledger().append()``, so the ledger stays the single store of record.

Validate-then-write: every edit builds and validates the new transaction BEFORE anything touches the
ledger; the ledger is untouched on any 4xx. Edit = reversal of the old transaction + a fresh one; delete =
reversal only; both under one per-workspace lock, and a SQLite failure after the ledger writes is compensated
by reversing what was just appended. Reversals carry ``#entry-reversal`` and ``meta.reverses`` so
:mod:`aurum.pf.ledger_view` can hide both sides. A missing ledger transaction on edit/delete is a 409
(``EntryConflict``), as is a second delete.

Every transaction this module writes carries ``meta["pf_entry_id"]`` (and ``commitment_id`` when the entry
pays a fixed commitment) so :func:`list_entries` can tell "one of mine" apart from a transaction another
subsystem (CFDI import, payroll, statement import) wrote straight to the ledger — those are still listed,
read-only, with ``source`` set, ``editable: false`` and a plain ``non_editable_reason``.
"""

from __future__ import annotations

import base64
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import Amount, q2
from ..core.validation import IsoDate, date_q
from ..ledger.base import Posting, Transaction, get_ledger
from . import accounts_admin, labels, ledger_view, store
from .types import PositiveMoney

router = APIRouter()

EntryKind = Literal["expense", "income", "transfer"]
Source = Literal["manual", "quickadd", "import", "cfdi", "payroll", "organizer"]

_INTERNAL_TAGS = {"opening-balance", "balance-adjustment", "voided-reversal", "entry-reversal", "sign-migration"}
_TAG_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_CURRENCY_RE = re.compile(r"^[A-Z][A-Z0-9]{2}$")

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class EntryConflict(Exception):
    """Already voided, or the ledger transaction behind the row is gone → 409."""


class BulkError(Exception):
    def __init__(self, index: int, msg: str) -> None:
        super().__init__(msg)
        self.index = index
        self.msg = msg


class SplitIn(BaseModel):
    label_id: str
    amount: PositiveMoney
    note: str | None = None


class EntryIn(BaseModel):
    kind: EntryKind
    date: IsoDate
    amount: PositiveMoney
    account_id: str
    to_account_id: str | None = None
    label_id: str | None = None
    payee: str | None = None
    note: str | None = None
    tags: list[str] = Field(default_factory=list)
    splits: list[SplitIn] | None = None
    source: Source = "manual"
    commitment_id: str | None = None
    # Receipt photo id (``rcp-…``, aurum/ingest/receipts.py) — metadata only, never part of the ledger.
    attachment: str | None = None


class EntryPatch(BaseModel):
    """Partial update: send only what changed. Missing fields keep their stored value."""

    kind: EntryKind | None = None
    date: IsoDate | None = None
    amount: PositiveMoney | None = None
    account_id: str | None = None
    to_account_id: str | None = None
    label_id: str | None = None
    payee: str | None = None
    note: str | None = None
    tags: list[str] | None = None
    splits: list[SplitIn] | None = None
    commitment_id: str | None = None
    attachment: str | None = None


class EntriesBulk(BaseModel):
    entries: list[EntryIn]


# --------------------------------------------------------------------------- locks


_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _write_lock(ws_id: str) -> threading.RLock:
    with _locks_guard:
        lock = _locks.get(ws_id)
        if lock is None:
            lock = threading.RLock()
            _locks[ws_id] = lock
        return lock


# --------------------------------------------------------------------------- helpers


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value) or []
        except ValueError:
            return []
    return list(value)


def merge_patch(existing: dict, patch: EntryPatch) -> EntryIn:
    """Overlay a partial update on the stored row and return the full EntryIn the writer expects."""
    changed = patch.model_dump(exclude_unset=True)
    stored_amount = Amount(amount=str(existing["amount"]).lstrip("-"), currency=existing.get("currency") or "MXN")
    base = {
        "kind": existing["kind"],
        "date": existing["date"],
        "amount": stored_amount,
        "account_id": existing["account_id"],
        "to_account_id": existing.get("to_account_id"),
        "label_id": existing.get("label_id"),
        "payee": existing.get("payee"),
        "note": existing.get("note"),
        "tags": _as_list(existing.get("tags")),
        "splits": [SplitIn(**sp) for sp in _as_list(existing.get("splits"))] or None,
        "source": existing.get("source") or "manual",
        "commitment_id": existing.get("commitment_id"),
        "attachment": existing.get("attachment"),
    }
    base.update(changed)
    return EntryIn(**base)


def _clean_tags(tags: list[str]) -> list[str]:
    out = []
    for tag in tags:
        text = str(tag).strip()
        if not _TAG_RE.match(text):
            raise ValueError(f"invalid tag {tag!r}: letters, digits, '_' and '-' only")
        out.append(text)
    return out


def _clean_amount(amount: Amount, field_name: str = "amount") -> Amount:
    currency = str(amount.currency).strip().upper()
    if not _CURRENCY_RE.match(currency):
        raise ValueError(f"{field_name}: currency must be a 3-letter code")
    value = q2(amount.amount)
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return Amount(amount=value, currency=currency)


def _default_label_account(kind: EntryKind) -> str:
    return "Income:Other" if kind == "income" else "Expenses:Other"


def _kind_word(kind: str, lang: str) -> str:
    return i18n_t(f"pf.entry.kind_plural.{kind}", lang)


def _label_for(ws_id: str, label_id: str, kind: EntryKind, lang: str) -> dict:
    try:
        label = labels.get_label(ws_id, label_id)
    except KeyError as exc:
        raise KeyError(f"label {label_id} not found") from exc
    if label["kind"] != kind:
        raise ValueError(
            i18n_t("pf.entry.label_kind_mismatch", lang, kind=_kind_word(label["kind"], lang),
                   expected=_kind_word(kind, lang))
        )
    return label


@dataclass
class Prepared:
    """Everything a write needs, built and validated before the ledger is touched."""

    body: EntryIn
    txn: Transaction
    account: dict
    to_account: dict | None
    label: dict | None
    splits: list[dict] = field(default_factory=list)


def _prepare(ws_id: str, body: EntryIn, entry_id: str) -> Prepared:
    lang = ws_lang(ws_id)
    try:
        account = accounts_admin.get_row(ws_id, body.account_id)
    except KeyError as exc:
        raise KeyError(f"account {body.account_id} not found") from exc
    if account["archived"]:
        raise ValueError(f"account {body.account_id} is archived")
    amount = _clean_amount(body.amount)
    tags = _clean_tags(body.tags)
    if body.attachment:
        from ..ingest import receipts

        if not receipts.exists(ws_id, body.attachment):
            raise KeyError(f"receipt {body.attachment} not found")
    to_account = None
    label = None
    splits: list[dict] = []

    if body.kind == "transfer":
        if body.splits:
            raise ValueError("splits are not supported for transfers")
        if not body.to_account_id:
            raise ValueError("transfer requires to_account_id")
        if body.to_account_id == body.account_id:
            raise ValueError("a transfer needs two different accounts")
        try:
            to_account = accounts_admin.get_row(ws_id, body.to_account_id)
        except KeyError as exc:
            raise KeyError(f"account {body.to_account_id} not found") from exc
        if to_account["archived"]:
            raise ValueError(f"account {body.to_account_id} is archived")
        if body.label_id:
            label = _label_for(ws_id, body.label_id, "transfer", lang)
        postings = [Posting(account=to_account["account"], amount=amount), Posting(account=account["account"])]
    else:
        if body.label_id:
            label = _label_for(ws_id, body.label_id, body.kind, lang)
        label_account = label["account"] if label else _default_label_account(body.kind)
        sign = Decimal("1") if body.kind == "expense" else Decimal("-1")
        if body.splits:
            total = Decimal("0")
            postings = []
            for s in body.splits:
                s_amount = _clean_amount(s.amount, "split amount")
                if s_amount.currency != amount.currency:
                    raise ValueError("split currency must match the entry currency")
                s_label = _label_for(ws_id, s.label_id, body.kind, lang)
                total += s_amount.amount
                postings.append(
                    Posting(account=s_label["account"], amount=Amount(amount=sign * s_amount.amount, currency=amount.currency))
                )
                splits.append({"label_id": s.label_id, "amount": s_amount.model_dump(mode="json"), "note": s.note})
            if q2(total) != amount.amount:
                raise ValueError(f"splits must sum to {amount.amount}, got {q2(total)}")
            postings.append(Posting(account=account["account"]))
        elif body.kind == "expense":
            postings = [Posting(account=label_account, amount=amount), Posting(account=account["account"])]
        else:
            postings = [Posting(account=account["account"], amount=amount), Posting(account=label_account)]

    meta = {"pf_entry_id": entry_id}
    if body.commitment_id:
        meta["commitment_id"] = body.commitment_id
    txn = Transaction(
        date=date.fromisoformat(body.date),
        payee=body.payee,
        narration=body.note or body.payee or i18n_t(f"pf.entry.{body.kind}", lang),
        postings=postings,
        tags=tags,
        meta=meta,
    )
    txn.balanced()  # raises ValueError on an unbalanceable transaction before any write
    cleaned = body.model_copy(update={"amount": amount, "tags": tags,
                                      "to_account_id": body.to_account_id if body.kind == "transfer" else None})
    return Prepared(body=cleaned, txn=txn, account=account, to_account=to_account, label=label, splits=splits)


def _reversal(original: Transaction, entry_id: str) -> Transaction:
    reversed_postings = [
        Posting(account=p.account, amount=Amount(amount=-p.amount.amount, currency=p.amount.currency))
        for p in original.balanced()
        if p.amount is not None
    ]
    return Transaction(
        date=original.date,
        payee=original.payee,
        narration=f"Reversa: {original.narration}",
        postings=reversed_postings,
        tags=["entry-reversal"],
        meta={**original.meta, "pf_entry_id": entry_id, "reverses": original.links[0] if original.links else ""},
    )


def _find_txn(ws_id: str, txn_id: str, when: str | None = None) -> Transaction | None:
    day = date.fromisoformat(when) if when else None
    for txn in get_ledger().journal(ws_id, start=day, end=day):
        if txn_id in txn.links:
            return txn
    return None


# --------------------------------------------------------------------------- pf_entries CRUD


def _row(r) -> dict:
    d = store.row_to_dict(r)
    d["tags"] = store.loads(d.get("tags"), [])
    d["splits"] = store.loads(d.get("splits"), [])
    d["voided"] = bool(d["voided"])
    d["editable"] = bool(d["editable"])
    d.setdefault("commitment_id", None)
    return d


def _signed_amount(kind: str, amount: str, currency: str) -> dict:
    magnitude = Decimal(amount)
    signed = magnitude if kind == "income" else -magnitude
    return store.money(signed, currency)


@dataclass
class _Ctx:
    """Lookup maps built once per list call (never a ledger load per row)."""

    accounts_by_id: dict[str, dict]
    accounts_by_ledger: dict[str, dict]
    labels_by_id: dict[str, dict]
    labels_by_account: dict[str, dict]
    lang: str


def _ctx(ws_id: str, lang: str | None = None) -> _Ctx:
    rows = accounts_admin.list_rows(ws_id, include_archived=True)
    lbls = labels.list_labels(ws_id, include_archived=True)
    return _Ctx(
        accounts_by_id={a["id"]: a for a in rows},
        accounts_by_ledger={a["account"]: a for a in rows},
        labels_by_id={lb["id"]: lb for lb in lbls},
        labels_by_account={lb["account"]: lb for lb in lbls},
        lang=ws_lang(ws_id, lang),
    )


def _to_human_row(ws_id: str, row: dict, ctx: _Ctx) -> dict:
    account = ctx.accounts_by_id.get(row["account_id"])
    to_account = ctx.accounts_by_id.get(row["to_account_id"]) if row.get("to_account_id") else None
    label = ctx.labels_by_id.get(row["label_id"]) if row.get("label_id") else None
    splits_out = []
    for s in row["splits"]:
        s_label = ctx.labels_by_id.get(s.get("label_id")) if s.get("label_id") else None
        splits_out.append(
            {
                "label_id": s.get("label_id"),
                "label_name": s_label["name"] if s_label else None,
                "amount": s.get("amount"),
                "note": s.get("note"),
            }
        )
    editable = bool(row["editable"]) and not row["voided"]
    return {
        "id": row["id"],
        "date": row["date"],
        "kind": row["kind"],
        "payee": row["payee"],
        "note": row["note"],
        "amount": _signed_amount(row["kind"], row["amount"], row["currency"]),
        "account_id": row["account_id"],
        "account_name": account["name"] if account else row["account_id"],
        "to_account_id": row["to_account_id"],
        "to_account_name": to_account["name"] if to_account else None,
        "label_id": row["label_id"],
        "label_name": label["name"] if label else None,
        "splits": splits_out,
        "tags": row["tags"],
        "source": row["source"],
        "txn_id": row["txn_id"],
        "commitment_id": row.get("commitment_id"),
        "attachment": row["attachment"],
        "voided": bool(row["voided"]),
        "editable": editable,
        "non_editable_reason": None if editable else (row["non_editable_reason"] or (
            i18n_t("pf.entry.voided", ctx.lang) if row["voided"] else None)),
    }


def _insert_row(conn, ws_id: str, entry_id: str, p: Prepared, txn_id: str) -> None:
    body = p.body
    ts = store.now()
    conn.execute(
        "INSERT INTO pf_entries (id, ws_id, kind, date, amount, currency, account_id, to_account_id, "
        "label_id, payee, note, tags, splits, source, txn_id, voided, editable, non_editable_reason, "
        "attachment, created_at, updated_at, commitment_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,1,NULL,?,?,?,?)",
        (
            entry_id, ws_id, body.kind, body.date, str(body.amount.amount), body.amount.currency,
            body.account_id, body.to_account_id, body.label_id, body.payee, body.note, store.dumps(body.tags),
            store.dumps(p.splits), body.source, txn_id, body.attachment or None, ts, ts, body.commitment_id,
        ),
    )
    conn.commit()


def create_entry(ws_id: str, body: EntryIn) -> dict:
    """Validate everything, then (under the workspace lock) append the transaction and insert the row.
    If the row insert fails, the transaction is reversed before the error propagates."""
    entry_id = store.new_id("ent")
    prepared = _prepare(ws_id, body, entry_id)
    ledger = get_ledger()
    with _write_lock(ws_id):
        txn_id = ledger.append(ws_id, prepared.txn)
        try:
            _insert_row(store.db(), ws_id, entry_id, prepared, txn_id)
        except BaseException:
            ledger.append(ws_id, _reversal(prepared.txn.model_copy(update={"links": [txn_id]}), entry_id))
            raise
    return get_entry(ws_id, entry_id)


def _fetch_row(ws_id: str, entry_id: str) -> dict:
    conn = store.db()
    row = conn.execute("SELECT * FROM pf_entries WHERE ws_id=? AND id=?", (ws_id, entry_id)).fetchone()
    if row is None:
        raise KeyError(f"entry {entry_id} not found")
    return _row(row)


def get_entry(ws_id: str, entry_id: str, lang: str | None = None) -> dict:
    return _to_human_row(ws_id, _fetch_row(ws_id, entry_id), _ctx(ws_id, lang))


def _check_writable(existing: dict) -> None:
    if existing["voided"]:
        raise EntryConflict(f"entry {existing['id']} was already deleted")
    if not existing["editable"]:
        raise PermissionError(existing["non_editable_reason"] or f"entry {existing['id']} is not editable")


def update_entry(ws_id: str, entry_id: str, body: EntryIn) -> dict:
    existing = _fetch_row(ws_id, entry_id)
    _check_writable(existing)
    prepared = _prepare(ws_id, body, entry_id)  # every 4xx happens here, ledger untouched
    ledger = get_ledger()
    with _write_lock(ws_id):
        original = _find_txn(ws_id, existing["txn_id"], existing["date"]) or _find_txn(ws_id, existing["txn_id"])
        if original is None:
            raise EntryConflict(f"ledger transaction {existing['txn_id']} for entry {entry_id} not found")
        ledger.append(ws_id, _reversal(original, entry_id))
        new_txn_id = ledger.append(ws_id, prepared.txn)
        b = prepared.body
        try:
            conn = store.db()
            conn.execute(
                "UPDATE pf_entries SET kind=?, date=?, amount=?, currency=?, account_id=?, to_account_id=?, "
                "label_id=?, payee=?, note=?, tags=?, splits=?, txn_id=?, commitment_id=?, attachment=?, "
                "updated_at=? WHERE ws_id=? AND id=?",
                (
                    b.kind, b.date, str(b.amount.amount), b.amount.currency, b.account_id, b.to_account_id,
                    b.label_id, b.payee, b.note, store.dumps(b.tags), store.dumps(prepared.splits), new_txn_id,
                    b.commitment_id, b.attachment or None, store.later_than(existing["created_at"]), ws_id, entry_id,
                ),
            )
            conn.commit()
        except BaseException:
            # compensate: undo the transaction the row never got to point at, then re-raise
            ledger.append(ws_id, _reversal(prepared.txn.model_copy(update={"links": [new_txn_id]}), entry_id))
            raise
    return get_entry(ws_id, entry_id)


def delete_entry(ws_id: str, entry_id: str) -> dict:
    existing = _fetch_row(ws_id, entry_id)
    _check_writable(existing)
    ledger = get_ledger()
    with _write_lock(ws_id):
        original = _find_txn(ws_id, existing["txn_id"], existing["date"]) or _find_txn(ws_id, existing["txn_id"])
        if original is None:
            raise EntryConflict(f"ledger transaction {existing['txn_id']} for entry {entry_id} not found")
        ledger.append(ws_id, _reversal(original, entry_id))
        conn = store.db()
        conn.execute(
            "UPDATE pf_entries SET voided=1, updated_at=? WHERE ws_id=? AND id=?", (store.now(), ws_id, entry_id)
        )
        conn.commit()
    return {"id": entry_id, "voided": True}


def bulk_create(ws_id: str, entries: list[EntryIn], *, atomic: bool = True) -> dict:
    """Validate every item before the first write. ``atomic=True``: any failure reverses what was written,
    voids those rows and raises ``BulkError(index, msg)``; ``atomic=False`` (CSV import) keeps the good
    rows and reports per-item errors."""
    prepared: list[tuple[int, str, Prepared]] = []
    errors: list[dict] = []
    for i, body in enumerate(entries):
        entry_id = store.new_id("ent")
        try:
            prepared.append((i, entry_id, _prepare(ws_id, body, entry_id)))
        except (KeyError, ValueError) as exc:
            msg = str(exc).strip("'")
            if atomic:
                raise BulkError(i, msg) from exc
            errors.append({"index": i, "msg": msg})
    ledger = get_ledger()
    created: list[str] = []
    written: list[tuple[str, Transaction, str]] = []
    with _write_lock(ws_id):
        for i, entry_id, p in prepared:
            try:
                txn_id = ledger.append(ws_id, p.txn)
                written.append((entry_id, p.txn, txn_id))
                _insert_row(store.db(), ws_id, entry_id, p, txn_id)
                created.append(entry_id)
            except Exception as exc:  # noqa: BLE001 — a write failure mid-batch
                if not atomic:
                    errors.append({"index": i, "msg": str(exc)})
                    continue
                conn = store.db()
                for eid, txn, tid in written:
                    ledger.append(ws_id, _reversal(txn.model_copy(update={"links": [tid]}), eid))
                    conn.execute("UPDATE pf_entries SET voided=1, updated_at=? WHERE ws_id=? AND id=?",
                                 (store.now(), ws_id, eid))
                conn.commit()
                raise BulkError(i, str(exc)) from exc
    return {"created": created, "errors": errors}


def is_unedited(ws_id: str, entry_id: str) -> bool:
    """True when the row was never edited (``created_at == updated_at``) — organizer un-mark checks this."""
    row = _fetch_row(ws_id, entry_id)
    return row["created_at"] == row["updated_at"]


def find_by_commitment(ws_id: str, commitment_id: str, due: date, window_days: int = 3) -> dict | None:
    """The live entry stamped with ``commitment_id`` closest to ``due`` within ±``window_days``, or None."""
    conn = store.db()
    lo = (due - _days(window_days)).isoformat()
    hi = (due + _days(window_days)).isoformat()
    rows = conn.execute(
        "SELECT * FROM pf_entries WHERE ws_id=? AND commitment_id=? AND voided=0 AND date>=? AND date<=?",
        (ws_id, commitment_id, lo, hi),
    ).fetchall()
    if not rows:
        return None
    best = min(rows, key=lambda r: (abs((date.fromisoformat(r["date"]) - due).days), r["id"]))
    return _to_human_row(ws_id, _row(best), _ctx(ws_id))


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)


# --------------------------------------------------------------------------- foreign (other-subsystem) rows


def _synthesize_foreign_entry(ws_id: str, txn: Transaction, txn_id: str, ctx: _Ctx) -> dict | None:
    postings = txn.balanced()
    income_leg = next((p for p in postings if p.account.startswith("Income:")), None)
    expense_leg = next((p for p in postings if p.account.startswith("Expenses:")), None)
    asset_legs = [p for p in postings if p.account.startswith(("Assets:", "Liabilities:")) and p.amount is not None]
    if not asset_legs:
        return None

    if income_leg is not None:
        kind, cat_leg = "income", income_leg
        primary = max(asset_legs, key=lambda p: p.amount.amount)
        to_leg = None
    elif expense_leg is not None:
        kind, cat_leg = "expense", expense_leg
        primary = min(asset_legs, key=lambda p: p.amount.amount)
        to_leg = None
    elif len(asset_legs) >= 2:
        kind, cat_leg = "transfer", None
        primary = min(asset_legs, key=lambda p: p.amount.amount)  # the outflow side
        to_leg = max(asset_legs, key=lambda p: p.amount.amount)
    else:
        return None

    currency = primary.amount.currency
    # the money that hit the account: Σ Assets/Liabilities legs on the primary side
    if kind == "transfer":
        magnitude = abs(primary.amount.amount)
    else:
        same_side = [p for p in asset_legs if (p.amount.amount < 0) == (primary.amount.amount < 0)]
        magnitude = abs(sum((p.amount.amount for p in same_side if p.amount.currency == currency), Decimal("0")))
    account = ctx.accounts_by_ledger.get(primary.account)
    to_account = ctx.accounts_by_ledger.get(to_leg.account) if to_leg is not None else None
    label = ctx.labels_by_account.get(cat_leg.account) if cat_leg is not None else None

    source = "import"
    for guess in ("cfdi", "payroll", "quickadd", "organizer"):
        if guess in txn.tags or txn.meta.get("source") == guess:
            source = guess
            break

    return {
        "id": txn_id,
        "date": txn.date.isoformat(),
        "kind": kind,
        "payee": txn.payee,
        "note": txn.narration or None,
        "amount": _signed_amount(kind, str(magnitude), currency),
        "account_id": account["id"] if account else None,
        "account_name": account["name"] if account else primary.account.rsplit(":", 1)[-1],
        "to_account_id": to_account["id"] if to_account else None,
        "to_account_name": to_account["name"] if to_account else (to_leg.account.rsplit(":", 1)[-1] if to_leg else None),
        "label_id": label["id"] if label else None,
        "label_name": label["name"] if label else None,
        "splits": [],
        "tags": list(txn.tags),
        "source": source,
        "txn_id": txn_id,
        "commitment_id": txn.meta.get("commitment_id") or None,
        "attachment": None,
        "voided": False,
        "editable": False,
        "non_editable_reason": i18n_t("pf.entry.external_source", ctx.lang, source=source),
    }


def _foreign_entries(ws_id: str, start: date | None, end: date | None, ctx: _Ctx) -> list[dict]:
    out = []
    for txn in ledger_view.live_txns(ws_id, start, end):
        if txn.meta.get("pf_entry_id") or txn.meta.get("pf_account_id"):
            continue
        if _INTERNAL_TAGS.intersection(txn.tags):
            continue
        txn_id = txn.links[0] if txn.links else None
        if txn_id is None:
            continue
        row = _synthesize_foreign_entry(ws_id, txn, txn_id, ctx)
        if row is not None:
            out.append(row)
    return out


# --------------------------------------------------------------------------- listing


def encode_cursor(row: dict) -> str:
    return base64.urlsafe_b64encode(f"{row['date']}|{row['id']}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        text = base64.urlsafe_b64decode(padded.encode()).decode()
        when, _, ident = text.partition("|")
        date.fromisoformat(when)
        if not ident:
            raise ValueError
        return when, ident
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid cursor") from exc


def list_entries(
    ws_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: str | None = None,
    label_id: str | None = None,
    kind: str | None = None,
    q: str | None = None,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    commitment_id: str | None = None,
    lang: str | None = None,
) -> dict:
    """``{"entries", "next_cursor", "totals"}``: keyset pages ordered (date desc, id desc); totals over
    the FULL filtered set (voids excluded, foreign rows included, transfers and non-base currencies counted
    but never summed)."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    after = decode_cursor(cursor) if cursor else None
    ctx = _ctx(ws_id, lang)
    conn = store.db()
    sql = "SELECT * FROM pf_entries WHERE ws_id=? AND voided=0"
    args: list[object] = [ws_id]
    if date_from:
        sql += " AND date>=?"
        args.append(date_from.isoformat())
    if date_to:
        sql += " AND date<=?"
        args.append(date_to.isoformat())
    if account_id:
        sql += " AND (account_id=? OR to_account_id=?)"
        args.extend([account_id, account_id])
    if label_id:
        sql += " AND label_id=?"
        args.append(label_id)
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if commitment_id:
        sql += " AND commitment_id=?"
        args.append(commitment_id)
    rows = [_to_human_row(ws_id, _row(r), ctx) for r in conn.execute(sql, args).fetchall()]
    rows.extend(_foreign_entries(ws_id, date_from, date_to, ctx))

    if account_id:
        rows = [r for r in rows if r["account_id"] == account_id or r["to_account_id"] == account_id]
    if label_id:
        rows = [r for r in rows if r["label_id"] == label_id]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if commitment_id:
        rows = [r for r in rows if r["commitment_id"] == commitment_id]
    if q:
        needle = q.lower()
        rows = [
            r for r in rows
            if needle in (r["payee"] or "").lower() or needle in (r["note"] or "").lower()
        ]

    base = store.base_currency(ws_id)
    total_in = total_out = Decimal("0")
    for r in rows:
        if r["kind"] == "transfer" or r["amount"]["currency"] != base:
            continue
        value = Decimal(r["amount"]["amount"])
        if r["kind"] == "income":
            total_in += value
        else:
            total_out += abs(value)
    totals = {
        "in": store.money(total_in, base),
        "out": store.money(total_out, base),
        "net": store.money(total_in - total_out, base),
        "count": len(rows),
    }

    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    if after is not None:
        rows_page = [r for r in rows if (r["date"], r["id"]) < after]
    else:
        rows_page = rows
    page = rows_page[:limit]
    next_cursor = encode_cursor(page[-1]) if len(rows_page) > limit and page else None
    return {"entries": page, "next_cursor": next_cursor, "totals": totals}


# --- router -----------------------------------------------------------------------------------


def _http_error(e: Exception) -> HTTPException:
    if isinstance(e, KeyError):
        return HTTPException(404, str(e).strip("'"))
    if isinstance(e, EntryConflict):
        return HTTPException(409, str(e))
    if isinstance(e, PermissionError):
        return HTTPException(403, str(e))
    return HTTPException(400, str(e))


@router.post("/{ws}/entries")
def api_create_entry(ws: str, body: EntryIn, lang: str | None = None) -> dict:
    try:
        return create_entry(ws, body)
    except (KeyError, ValueError) as e:
        raise _http_error(e) from e


@router.get("/{ws}/entries")
def api_list_entries(
    ws: str,
    from_: str | None = Depends(date_q("from")),
    to: str | None = Depends(date_q("to")),
    account_id: str | None = None,
    label_id: str | None = None,
    kind: EntryKind | None = None,
    q: str | None = None,
    commitment_id: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = None,
    lang: str | None = None,
) -> dict:
    try:
        return list_entries(
            ws,
            date_from=date.fromisoformat(from_) if from_ else None,
            date_to=date.fromisoformat(to) if to else None,
            account_id=account_id, label_id=label_id, kind=kind, q=q, limit=limit, cursor=cursor,
            commitment_id=commitment_id, lang=lang,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/{ws}/entries/{entry_id}")
def api_update_entry(ws: str, entry_id: str, body: EntryPatch, lang: str | None = None) -> dict:
    """Edit any subset of fields; the stored row fills in the rest. Nothing is written on a 4xx."""
    try:
        existing = _fetch_row(ws, entry_id)
        return update_entry(ws, entry_id, merge_patch(existing, body))
    except (KeyError, ValueError, PermissionError, EntryConflict) as e:
        raise _http_error(e) from e


@router.delete("/{ws}/entries/{entry_id}")
def api_delete_entry(ws: str, entry_id: str) -> dict:
    try:
        return delete_entry(ws, entry_id)
    except (KeyError, PermissionError, EntryConflict) as e:
        raise _http_error(e) from e


@router.post("/{ws}/entries/bulk")
def api_bulk_entries(ws: str, body: EntriesBulk) -> dict:
    try:
        result = bulk_create(ws, body.entries, atomic=True)
    except BulkError as e:
        raise HTTPException(400, {"index": e.index, "msg": e.msg}) from e
    return {"created": result["created"]}
