"""Ingest endpoints, mounted at /api/ingest."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core import audit
from ..core.db import connect
from ..core.i18n import ws_lang
from ..core.workspaces import WorkspaceNotFound, get_workspace
from . import bank_csv, inbox, quickadd, reconcile
from .cfdi import CFDI, CFDIParseError, parse_upload

router = APIRouter()


def _workspace_rfc(ws_id: str) -> str:
    try:
        ws = get_workspace(ws_id)
    except WorkspaceNotFound:
        return ""
    return str(ws.profile.get("rfc", ""))


def _base_currency(ws_id: str) -> str:
    try:
        return get_workspace(ws_id).base_currency
    except WorkspaceNotFound:
        return "MXN"


def _store_cfdi(ws_id: str, doc: CFDI) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_cfdi (uuid, ws_id, tipo, direction, fecha, emisor_rfc, receptor_rfc, "
            "subtotal, total, moneda, metodo_pago, forma_pago, uso_cfdi, iva_trasladado, impuestos_retenidos, "
            "raw_path, json, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                doc.uuid,
                ws_id,
                doc.tipo,
                doc.direction,
                doc.fecha.isoformat(),
                doc.emisor_rfc,
                doc.receptor_rfc,
                str(doc.subtotal),
                str(doc.total),
                doc.moneda,
                doc.metodo_pago,
                doc.forma_pago,
                doc.uso_cfdi,
                str(doc.iva_trasladado),
                str(doc.impuestos_retenidos),
                doc.raw_path,
                doc.model_dump_json(),
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        for pago in doc.pagos:
            conn.execute(
                "INSERT INTO ingest_cfdi_pagos (uuid_pago, ws_id, fecha_pago, monto, uuid_relacionado, imp_pagado) "
                "VALUES (?,?,?,?,?,?)",
                (
                    doc.uuid,
                    ws_id,
                    pago.fecha_pago.isoformat(),
                    str(pago.monto),
                    pago.uuid_relacionado,
                    str(pago.imp_pagado),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _proposal_for_cfdi(ws_id: str, doc: CFDI):
    from ..core.money import Amount
    from ..ledger.base import Posting, Transaction

    if doc.direction == "recibido":
        # expense CFDI: money owed/paid to the vendor
        postings = [
            Posting(account="Expenses:Uncategorized", amount=Amount(amount=doc.total, currency=doc.moneda)),
            Posting(account="Liabilities:AccountsPayable", amount=None),
        ]
        kind_meta = "expense"
    else:
        # income CFDI issued by the workspace: receivable until collected (PUE/PPD/REP semantics)
        postings = [
            Posting(account="Assets:Receivable", amount=Amount(amount=doc.total, currency=doc.moneda)),
            Posting(account="Income:Uncategorized", amount=None),
        ]
        kind_meta = "income"

    meta = {
        "source": "cfdi",
        "cfdi_uuid": doc.uuid,
        "metodo_pago": doc.metodo_pago or "",
        "flow": kind_meta,
    }
    txn = Transaction(
        date=doc.fecha.date(),
        payee=doc.emisor_nombre if doc.direction == "recibido" else doc.receptor_nombre,
        narration=f"CFDI {doc.uuid}",
        postings=postings,
        meta=meta,
    )
    confidence = 0.95 if doc.metodo_pago == "PUE" or doc.direction == "recibido" else 0.7
    return txn, confidence


@router.post("/{ws}/cfdi")
async def upload_cfdi(ws: str, file: UploadFile = File(...)) -> dict:  # noqa: B008
    data = await file.read()
    rfc = _workspace_rfc(ws)
    try:
        docs = parse_upload(file.filename or "upload.xml", data, rfc)
    except CFDIParseError as e:
        raise HTTPException(400, f"CFDI parse error: {e}") from e

    stored: list[dict] = []
    inbox_items: list[dict] = []
    for doc in docs:
        _store_cfdi(ws, doc)
        txn, confidence = _proposal_for_cfdi(ws, doc)
        item = inbox.create_inbox_item(ws, kind="cfdi", proposed=txn, confidence=confidence, source_ref=doc.uuid)
        stored.append(doc.model_dump(mode="json"))
        inbox_items.append(item.model_dump(mode="json"))

    audit.record(ws, "ingest.cfdi.upload", {"filename": file.filename, "count": len(docs)}, {"uuids": [d.uuid for d in docs]})
    return {"imported": len(docs), "cfdis": stored, "inbox_items": inbox_items}


@router.get("/{ws}/cfdi")
def list_cfdi(ws: str, period: str | None = None) -> list[dict]:
    conn = connect()
    try:
        if period:
            rows = conn.execute(
                "SELECT * FROM ingest_cfdi WHERE ws_id=? AND fecha LIKE ? ORDER BY fecha", (ws, f"{period}%")
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ingest_cfdi WHERE ws_id=? ORDER BY fecha", (ws,)).fetchall()
        return [json.loads(r["json"]) for r in rows]
    finally:
        conn.close()


@router.post("/{ws}/bank/csv")
async def upload_bank_csv(
    ws: str,
    bank: str = Form(...),  # noqa: B008
    account_id: str = Form(...),  # noqa: B008
    file: UploadFile = File(...),  # noqa: B008
) -> dict:
    """Lines become ordinary pf entries on ``account_id`` (required; unknown → 404). No inbox items."""
    data = await file.read()
    try:
        result = bank_csv.import_csv(ws, bank, data, account_id=account_id, base_currency=_base_currency(ws))
    except KeyError as e:
        raise HTTPException(404, f"account {account_id} not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    audit.record(
        ws, "ingest.bank.csv", {"bank": bank, "filename": file.filename, "account_id": account_id},
        {"imported": result.get("imported"), "skipped_duplicates": result.get("skipped_duplicates"),
         "errors": len(result.get("errors", []))},
    )
    return result


@router.post("/{ws}/receipts")
async def upload_receipt(ws: str, file: UploadFile = File(...)) -> dict:  # noqa: B008
    """Keep a receipt photo (EXIF stripped), OCR it and suggest {amount, date, payee, label}
    with the reasons. No ledger write — + Agregar shows the suggestion, the person confirms, and the
    saved movement's ``attachment`` is this receipt's id."""
    from . import receipts

    data = await file.read()
    try:
        return receipts.scan(ws, data, file.filename)
    except WorkspaceNotFound as e:
        raise HTTPException(404, f"workspace {ws} not found") from e
    except receipts.ReceiptError as e:
        raise HTTPException(400, {"code": e.code, "message": str(e)}) from e


@router.get("/{ws}/receipts/{receipt_id}")
def get_receipt(ws: str, receipt_id: str) -> dict:
    from . import receipts

    found = receipts.get_receipt(ws, receipt_id)
    if found is None:
        raise HTTPException(404, f"receipt {receipt_id} not found")
    return found


@router.get("/{ws}/receipts/{receipt_id}/image")
def receipt_image(ws: str, receipt_id: str) -> FileResponse:
    from . import receipts

    found = receipts.image_file(ws, receipt_id)
    if found is None:
        raise HTTPException(404, f"receipt {receipt_id} not found")
    path, content_type = found
    return FileResponse(path, media_type=content_type, headers={"Cache-Control": "private, max-age=86400"})


class QuickAddBody(BaseModel):
    text: str
    account_id: str | None = None
    commit: bool = False


@router.post("/{ws}/quickadd")
def quickadd_endpoint(ws: str, body: QuickAddBody) -> dict:
    """Preview (default) or commit a quick-add as a real, editable pf entry. No inbox row either way."""
    from ..pf import entries as pf_entries

    try:
        preview = quickadd.parse_entry(ws, body.text, account_id=body.account_id)
    except quickadd.NoAccount as e:
        raise HTTPException(400, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, f"account {body.account_id} not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    entry_in = preview.entry
    proposed = quickadd.transaction_for(preview, body.text)
    entry = None
    if body.commit:
        try:
            entry = pf_entries.create_entry(ws, entry_in)
        except KeyError as e:
            raise HTTPException(404, str(e).strip("'")) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    audit.record(
        ws, "ingest.quickadd", {"text": body.text, "account_id": body.account_id, "commit": body.commit},
        {"entry_id": entry["id"] if entry else None, "warnings": preview.warnings},
    )
    return {
        "id": entry["id"] if entry else None,
        "kind": "quickadd",
        "status": "committed" if entry else "preview",
        "proposed": proposed.model_dump(mode="json"),
        "confidence": preview.confidence,
        "warnings": preview.warnings,
        "preview": {
            "kind": entry_in.kind,
            "amount": entry_in.amount.model_dump(mode="json"),
            "account_id": entry_in.account_id,
            "account_name": preview.account_name,
            "label_id": entry_in.label_id,
            "label_name": preview.label_name,
            "payee": entry_in.payee,
            "date": entry_in.date,
        },
        "entry": entry,
    }


@router.get("/{ws}/inbox")
def get_inbox(ws: str, status: str | None = None) -> list[dict]:
    return [i.model_dump(mode="json") for i in inbox.list_inbox(ws, status)]


class AcceptBody(BaseModel):
    label: str | None = None
    account: str | None = None


@router.post("/{ws}/inbox/{item_id}/accept")
def accept_inbox(ws: str, item_id: str, body: AcceptBody | None = None) -> dict:
    body = body or AcceptBody()
    try:
        item, txn_id = inbox.accept_inbox_item(ws, item_id, label=body.label, account=body.account)
    except inbox.InboxNotFound as e:
        raise HTTPException(404, f"inbox item {item_id} not found") from e
    except inbox.InboxAlreadyDecided as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"item": item.model_dump(mode="json"), "txn_id": txn_id}


@router.post("/{ws}/inbox/{item_id}/reject")
def reject_inbox(ws: str, item_id: str) -> dict:
    try:
        item = inbox.reject_inbox_item(ws, item_id)
    except inbox.InboxNotFound as e:
        raise HTTPException(404, f"inbox item {item_id} not found") from e
    except inbox.InboxAlreadyDecided as e:
        raise HTTPException(409, str(e)) from e
    return item.model_dump(mode="json")


@router.get("/{ws}/reconcile")
def get_reconcile(ws: str, period: str, lang: str | None = None) -> dict:
    try:
        return reconcile.reconcile_period(ws, period, lang=ws_lang(ws, lang))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class MatchBody(BaseModel):
    bank_line_id: int
    txn_id: str | None = None
    cfdi_uuid: str | None = None


@router.post("/{ws}/reconcile/match")
def post_reconcile_match(ws: str, body: MatchBody) -> dict:
    try:
        row = reconcile.match(ws, body.bank_line_id, txn_id=body.txn_id, cfdi_uuid=body.cfdi_uuid)
    except reconcile.MatchNotFound as e:
        raise HTTPException(404, f"bank line {body.bank_line_id} not found") from e
    audit.record(ws, "ingest.reconcile.match", body.model_dump(), {"matched": True})
    return row


class UnmatchBody(BaseModel):
    bank_line_id: int


@router.post("/{ws}/reconcile/unmatch")
def post_reconcile_unmatch(ws: str, body: UnmatchBody) -> dict:
    try:
        row = reconcile.unmatch(ws, body.bank_line_id)
    except reconcile.MatchNotFound as e:
        raise HTTPException(404, f"bank line {body.bank_line_id} not found") from e
    audit.record(ws, "ingest.reconcile.unmatch", body.model_dump(), {"unmatched": True})
    return row
