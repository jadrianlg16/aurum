"""Inbox: proposed transactions awaiting human accept/reject."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..core import audit
from ..core.db import connect
from ..ledger.base import Posting, Transaction, get_ledger, validate_account


class InboxItem(BaseModel):
    id: str
    ws_id: str
    kind: Literal["quickadd", "cfdi", "bank", "photo"]
    status: Literal["pending", "accepted", "rejected"] = "pending"
    proposed: Transaction
    confidence: float = 1.0
    source_ref: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None


def _row_to_item(row) -> InboxItem:
    return InboxItem(
        id=row["id"],
        ws_id=row["ws_id"],
        kind=row["kind"],
        status=row["status"],
        proposed=Transaction.model_validate_json(row["proposed_json"]),
        confidence=row["confidence"],
        source_ref=row["source_ref"],
        created_at=datetime.fromisoformat(row["created_at"]),
        decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
    )


def create_inbox_item(
    ws_id: str,
    kind: Literal["quickadd", "cfdi", "bank", "photo"],
    proposed: Transaction,
    confidence: float = 1.0,
    source_ref: str | None = None,
) -> InboxItem:
    item = InboxItem(
        id=f"inbox-{uuid.uuid4().hex[:12]}",
        ws_id=ws_id,
        kind=kind,
        proposed=proposed,
        confidence=confidence,
        source_ref=source_ref,
    )
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO ingest_inbox (id, ws_id, kind, status, proposed_json, confidence, source_ref, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.ws_id,
                item.kind,
                item.status,
                item.proposed.model_dump_json(),
                item.confidence,
                item.source_ref,
                item.created_at.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return item


def list_inbox(ws_id: str, status: str | None = None) -> list[InboxItem]:
    conn = connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM ingest_inbox WHERE ws_id=? AND status=? ORDER BY created_at", (ws_id, status)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ingest_inbox WHERE ws_id=? ORDER BY created_at", (ws_id,)
            ).fetchall()
        return [_row_to_item(r) for r in rows]
    finally:
        conn.close()


def get_inbox_item(ws_id: str, item_id: str) -> InboxItem | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM ingest_inbox WHERE ws_id=? AND id=?", (ws_id, item_id)
        ).fetchone()
        return _row_to_item(row) if row else None
    finally:
        conn.close()


class InboxNotFound(KeyError):
    pass


class InboxAlreadyDecided(ValueError):
    pass


def accept_inbox_item(
    ws_id: str, item_id: str, label: str | None = None, account: str | None = None
) -> tuple[InboxItem, str]:
    """Accept a pending Inbox item: apply optional label/account overrides, append to the ledger."""
    item = get_inbox_item(ws_id, item_id)
    if item is None:
        raise InboxNotFound(item_id)
    if item.status != "pending":
        raise InboxAlreadyDecided(f"inbox item {item_id} already {item.status}")

    txn = item.proposed
    if label:
        txn.meta = {**txn.meta, "label": label}
    if account and txn.postings:
        # override the balancing (last) leg's account when explicitly requested — rebuilt through the
        # Posting constructor (never model_copy) so every validator runs; a bad name is a 400 with the
        # ledger untouched
        account = validate_account(account.strip())
        postings = list(txn.postings)
        postings[-1] = Posting(account=account, amount=postings[-1].amount)
        txn.postings = postings
    txn.meta = {**txn.meta, "inbox_id": item.id, "source": txn.meta.get("source", item.kind)}

    txn_id = get_ledger().append(ws_id, txn)

    conn = connect()
    try:
        conn.execute(
            "UPDATE ingest_inbox SET status='accepted', decided_at=?, proposed_json=? WHERE ws_id=? AND id=?",
            (datetime.now(UTC).isoformat(timespec="seconds"), txn.model_dump_json(), ws_id, item_id),
        )
        conn.commit()
    finally:
        conn.close()

    item.status = "accepted"
    item.proposed = txn
    audit.record(
        ws_id,
        "ingest.inbox.accept",
        {"inbox_id": item_id, "label": label, "account": account},
        {"txn_id": txn_id},
    )
    return item, txn_id


def reject_inbox_item(ws_id: str, item_id: str) -> InboxItem:
    item = get_inbox_item(ws_id, item_id)
    if item is None:
        raise InboxNotFound(item_id)
    if item.status != "pending":
        raise InboxAlreadyDecided(f"inbox item {item_id} already {item.status}")
    conn = connect()
    try:
        conn.execute(
            "UPDATE ingest_inbox SET status='rejected', decided_at=? WHERE ws_id=? AND id=?",
            (datetime.now(UTC).isoformat(timespec="seconds"), ws_id, item_id),
        )
        conn.commit()
    finally:
        conn.close()
    item.status = "rejected"
    audit.record(ws_id, "ingest.inbox.reject", {"inbox_id": item_id}, {})
    return item
