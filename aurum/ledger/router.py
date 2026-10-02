"""Ledger endpoints, mounted at ``/api/ledger``."""

from __future__ import annotations

import re
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import audit as audit_log
from ..core.i18n import t, ws_lang
from ..core.money import Amount
from ..core.workspaces import WorkspaceNotFound, get_workspace
from . import statements as statements_mod
from .base import Posting, Transaction, get_ledger
from .beancount_store import TxnNotFound

router = APIRouter(tags=["ledger"])

_PERIOD = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")


def _currency(ws: str) -> str:
    try:
        return get_workspace(ws).base_currency
    except WorkspaceNotFound:
        return "MXN"


class QueryBody(BaseModel):
    bql: str


@router.get("/{ws}/journal")
def journal(
    ws: str,
    start: date | None = None,
    end: date | None = None,
    account_prefix: str | None = None,
) -> list[dict]:
    txns = get_ledger().journal(ws, start=start, end=end, account_prefix=account_prefix)
    return [t.model_dump(mode="json") for t in txns]


@router.get("/{ws}/balances")
def balances(ws: str, as_of: date | None = None) -> dict[str, list[dict]]:
    raw = get_ledger().balances(ws, as_of=as_of)
    return {account: [a.model_dump(mode="json") for a in amounts] for account, amounts in raw.items()}


@router.post("/{ws}/query")
def query(ws: str, body: QueryBody) -> list[dict]:
    try:
        return get_ledger().query(ws, body.bql)
    except NotImplementedError as e:
        raise HTTPException(501, "BQL requires the Beancount ledger store") from e
    except Exception as e:  # beanquery raises a family of parse/compile errors
        raise HTTPException(400, f"query failed: {e}") from e


@router.get("/{ws}/accounts")
def accounts(ws: str) -> list[str]:
    return get_ledger().accounts(ws)


@router.get("/{ws}/health")
def ledger_health(ws: str) -> dict:
    """``{"txns": n, "errors": [{"lineno","message"}][:20], "error_count": k}`` — loader errors on the ledger file."""
    store = get_ledger()
    health = getattr(store, "health", None)
    if health is None:  # InMemoryLedger fallback: nothing on disk can be broken
        return {"txns": len(store.journal(ws)), "errors": [], "error_count": 0}
    return health(ws)


@router.post("/{ws}/transactions")
def append_transaction(ws: str, txn: Transaction) -> dict:
    try:
        txn_id = get_ledger().append(ws, txn)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"id": txn_id}


@router.get("/{ws}/statements/{period}")
def statement(ws: str, period: str, type: str = "pnl", lang: str | None = None) -> dict:  # noqa: A002
    if not _PERIOD.match(period):
        raise HTTPException(400, "period must be YYYY-MM or YYYY")
    if type not in statements_mod.VALID_TYPES:
        raise HTTPException(400, f"type must be one of {statements_mod.VALID_TYPES}")
    try:
        return statements_mod.build_statement(
            get_ledger(), ws, period, type, currency=_currency(ws), lang=ws_lang(ws, lang)
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _find_txn(ws: str, txn_id: str) -> Transaction:
    for txn in get_ledger().journal(ws):
        if txn_id in txn.links:
            return txn
    raise HTTPException(404, f"transaction {txn_id} not found")


def _require_beancount_store():
    """PUT/DELETE rewrite the ledger file directly; only the Beancount store supports that."""
    from .beancount_store import BeancountLedger

    store = get_ledger()
    if not isinstance(store, BeancountLedger):
        raise HTTPException(501, "editing transactions requires the Beancount ledger store")
    return store


@router.put("/{ws}/transactions/{txn_id}")
def update_transaction(ws: str, txn_id: str, txn: Transaction) -> dict:
    """Rewrite the transaction carrying link ``txn_id`` with the new body (same link kept)."""
    store = _require_beancount_store()
    original = _find_txn(ws, txn_id)
    new_txn = txn.model_copy(update={"links": sorted({txn_id, *txn.links})})
    try:
        store.replace_txn(ws, txn_id, new_txn)
    except TxnNotFound as e:
        raise HTTPException(404, f"transaction {txn_id} not found in ledger file") from e
    audit_log.record(
        ws, "ledger.transaction.update", {"txn_id": txn_id, "before": original.model_dump(mode="json")},
        {"after": new_txn.model_dump(mode="json")},
    )
    return {"id": txn_id, "explain": {"summary": t("ledger.txn.updated", ws_lang(ws), txn_id=txn_id)}}


def _reversal(original: Transaction, txn_id: str) -> Transaction:
    reversed_postings = [
        Posting(account=p.account, amount=Amount(amount=-p.amount.amount, currency=p.amount.currency))
        for p in original.postings
        if p.amount is not None
    ]
    return Transaction(
        date=original.date,
        payee=original.payee,
        narration=f"Reversa de {txn_id}: {original.narration}",
        postings=reversed_postings,
        tags=["voided-reversal"],
        links=[f"{txn_id}-void-{uuid.uuid4().hex[:8]}", txn_id],
        meta={**original.meta, "reverses": txn_id},
    )


@router.delete("/{ws}/transactions/{txn_id}")
def void_transaction(ws: str, txn_id: str) -> dict:
    """Void = tag the original ``#voided`` (text kept) + append a reversing entry. Never erased."""
    store = _require_beancount_store()
    original = _find_txn(ws, txn_id)
    if "voided" in original.tags:
        raise HTTPException(409, f"transaction {txn_id} is already voided")

    voided = original.model_copy(update={"tags": sorted({*original.tags, "voided"})})
    try:
        store.replace_txn(ws, txn_id, voided)
    except TxnNotFound as e:
        raise HTTPException(404, f"transaction {txn_id} not found in ledger file") from e

    reversal = _reversal(original, txn_id)
    reversal_id = store.append(ws, reversal)

    audit_log.record(
        ws, "ledger.transaction.void", {"txn_id": txn_id, "original": original.model_dump(mode="json")},
        {"reversal_id": reversal_id},
    )
    return {
        "id": txn_id,
        "reversal_id": reversal_id,
        "explain": {"summary": t("ledger.txn.voided", ws_lang(ws), txn_id=txn_id)},
    }
