"""Receipt photos: keep the picture, read it, suggest the movement.

``scan()`` is the whole path behind ``POST /api/ingest/{ws}/receipts``:

1. **Keep the photo** — sniffed as JPEG / PNG / WebP (anything else is a 400 with a plain message),
   re-encoded to a JPEG of at most 2400 px **without EXIF** (so no GPS or phone metadata is kept) under
   ``workspaces/<ws>/docs/receipts/<id>.jpg`` — inside ``docs/``, so both backups carry it.
2. **Read it** — ``receipt_ocr.ocr_image`` (Tesseract, or an external OCR service, or off).
3. **Suggest** — ``receipt_parse.read_receipt`` finds how much / when / where / what; the category name
   becomes one of the workspace's own categories, in this order: what the person chose the **last
   time** for the same shop (``pf_entries`` by payee — so a correction teaches it), the known chain's
   category, the keyword rules, the category aliases on the shop name.

Nothing is written to the ledger: + Agregar shows the suggestion, the person fixes what is wrong and
saves an ordinary movement whose ``attachment`` is the receipt id (``pf/entries.py``). OCR text never
goes to a log or the audit trail.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..core import audit
from ..core.config import settings
from ..core.db import connect
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from ..core.workspaces import get_workspace
from . import receipt_ocr
from .receipt_parse import ReceiptReading, fold, read_receipt

RECEIPT_ID_RE = re.compile(r"^rcp-[0-9a-f]{12}$")
MAX_SIDE = 2400
JPEG_QUALITY = 85
TEXT_KEEP = 8000  # chars of OCR text kept on the row and returned (a ticket is ~1-2k)


class ReceiptError(ValueError):
    """A 4xx for the router: ``code`` is the stable error id, ``args[0]`` the human message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "image/heic"
    return None


def receipts_dir(ws_id: str) -> Path:
    return settings().workspace_dir(ws_id) / "docs" / "receipts"


def _encode(data: bytes, content_type: str) -> tuple[bytes, str, str]:
    """→ (bytes to store, content type, extension). Upright RGB JPEG ≤ MAX_SIDE with no EXIF; when
    Pillow cannot decode it, the original bytes (already sniffed as an image) are kept as they came."""
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data)) as im:
            img = ImageOps.exif_transpose(im).convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)  # no exif= → metadata dropped
        return buf.getvalue(), "image/jpeg", "jpg"
    except Exception:  # noqa: BLE001 - a picture Pillow can't read is stored untouched
        ext = {"image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
        return data, content_type, ext


def save_receipt(ws_id: str, data: bytes, filename: str | None) -> dict[str, Any]:
    lang = ws_lang(ws_id)
    if not data:
        raise ReceiptError("empty_file", i18n_t("receipt.err.empty", lang))
    kind = sniff(data)
    if kind == "image/heic":
        raise ReceiptError("unsupported_image", i18n_t("receipt.err.heic", lang))
    if kind is None:
        raise ReceiptError("unsupported_image", i18n_t("receipt.err.type", lang))
    stored, content_type, ext = _encode(data, kind)
    rid = f"rcp-{uuid.uuid4().hex[:12]}"
    folder = receipts_dir(ws_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{rid}.{ext}"
    path.write_bytes(stored)
    row = {
        "id": rid,
        "ws_id": ws_id,
        "filename": (filename or "")[:120] or None,
        "path": path.relative_to(settings().workspace_dir(ws_id)).as_posix(),
        "content_type": content_type,
        "size": len(stored),
        "sha256": hashlib.sha256(stored).hexdigest(),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO ingest_receipts (id, ws_id, filename, path, content_type, size, sha256, created_at) "
            "VALUES (:id, :ws_id, :filename, :path, :content_type, :size, :sha256, :created_at)",
            row,
        )
        conn.commit()
    finally:
        conn.close()
    return row


def _row(ws_id: str, rid: str) -> dict | None:
    if not RECEIPT_ID_RE.match(rid or ""):
        return None
    conn = connect()
    try:
        r = conn.execute("SELECT * FROM ingest_receipts WHERE ws_id=? AND id=?", (ws_id, rid)).fetchone()
    finally:
        conn.close()
    return dict(r) if r else None


def exists(ws_id: str, rid: str) -> bool:
    return _row(ws_id, rid) is not None


def image_file(ws_id: str, rid: str) -> tuple[Path, str] | None:
    row = _row(ws_id, rid)
    if row is None:
        return None
    root = settings().workspace_dir(ws_id).resolve()
    path = (root / row["path"]).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path, row["content_type"]


# ---------------------------------------------------------------------------------- suggestion


def _learned_label(ws_id: str, payee: str) -> dict | None:
    """The category of the newest live expense whose payee folds to the same text."""
    from ..pf import labels as pf_labels

    key = fold(payee).strip()
    if not key:
        return None
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT payee, label_id FROM pf_entries WHERE ws_id=? AND voided=0 AND kind='expense' "
            "AND label_id IS NOT NULL AND payee IS NOT NULL ORDER BY date DESC, updated_at DESC LIMIT 500",
            (ws_id,),
        ).fetchall()
    finally:
        conn.close()
    live = {lbl["id"]: lbl for lbl in pf_labels.list_labels(ws_id, kind="expense")}
    for r in rows:
        if fold(r["payee"]).strip() == key and r["label_id"] in live:
            return live[r["label_id"]]
    return None


def _category(ws_id: str, reading: ReceiptReading, lang: str) -> tuple[dict | None, str | None, str | None]:
    """→ (label row, confidence, reason sentence)."""
    from ..pf import labels as pf_labels

    merchant = reading.merchant
    if merchant is not None:
        learned = _learned_label(ws_id, merchant.name)
        if learned is not None:
            return learned, "high", i18n_t("receipt.why.cat.learned", lang, label=learned["name"], payee=merchant.name)
    by_name = {lbl["name"]: lbl for lbl in pf_labels.list_labels(ws_id, kind="expense")}
    if merchant is not None and merchant.category and merchant.category in by_name:
        lbl = by_name[merchant.category]
        return lbl, "high", i18n_t("receipt.why.cat.merchant", lang, label=lbl["name"], name=merchant.name)
    if reading.category is not None and reading.category.name in by_name:
        lbl = by_name[reading.category.name]
        words = ", ".join(w.lower() for w in reading.category.words)
        return lbl, "medium", i18n_t("receipt.why.cat.words", lang, label=lbl["name"], words=words)
    if merchant is not None:
        lbl = pf_labels.match_label(ws_id, merchant.name, kind="expense")
        if lbl is not None:
            return lbl, "medium", i18n_t("receipt.why.cat.alias", lang, label=lbl["name"])
    return None, None, None


def suggest(ws_id: str, text: str, today: date) -> tuple[dict[str, Any], list[str]]:
    """OCR text → (suggestion, reasons). Pure apart from reading labels and past entries."""
    lang = ws_lang(ws_id)
    ws = get_workspace(ws_id)
    day_first = ws.jurisdictions != ["US"]
    reading = read_receipt(text, today, day_first=day_first)
    reasons: list[str] = []
    currency = reading.currency or ws.base_currency

    amount = None
    if reading.amount is not None:
        amount = {"amount": str(q2(reading.amount.value)), "currency": currency}
        key = "receipt.why.amount.largest" if reading.amount.reason == "largest" else (
            "receipt.why.amount.card" if reading.amount.reason == "card_line" else "receipt.why.amount.line"
        )
        reasons.append(i18n_t(key, lang, line=reading.amount.line))
        for check in reading.amount.checks:
            reasons.append(i18n_t(f"receipt.why.check.{check}", lang))
    if reading.date is not None:
        reasons.append(i18n_t("receipt.why.date", lang, line=reading.date.line))
    payee = reading.merchant.name if reading.merchant else None
    if reading.merchant is not None:
        key = "receipt.why.merchant.known" if reading.merchant.source == "known" else "receipt.why.merchant.header"
        reasons.append(i18n_t(key, lang, name=reading.merchant.name))
    label, label_conf, why = _category(ws_id, reading, lang)
    if why:
        reasons.append(why)

    suggestion = {
        "amount": amount,
        "date": reading.date.value.isoformat() if reading.date else None,
        "payee": payee,
        "label_id": label["id"] if label else None,
        "label_name": label["name"] if label else None,
        "confidence": {
            "amount": reading.amount.confidence if reading.amount else None,
            "date": reading.date.confidence if reading.date else None,
            "payee": reading.merchant.confidence if reading.merchant else None,
            "label": label_conf,
        },
    }
    return suggestion, reasons


def possible_duplicate(ws_id: str, row: dict, suggestion: dict | None) -> dict | None:
    """A live expense this receipt may already be: one whose photo is byte-identical (same sha256), else
    one on the suggested date with the suggested amount (and the same shop when both have one). Only a
    warning for the person — nothing is blocked."""
    conn = connect()
    try:
        same_photo = conn.execute(
            "SELECT e.id, e.date, e.amount, e.currency, e.payee FROM pf_entries e JOIN ingest_receipts r "
            "ON r.ws_id = e.ws_id AND r.id = e.attachment WHERE e.ws_id=? AND e.voided=0 AND r.sha256=? AND r.id<>? "
            "ORDER BY e.date DESC LIMIT 1",
            (ws_id, row["sha256"], row["id"]),
        ).fetchone()
        hit = dict(same_photo) if same_photo else None
        if hit is None and suggestion and suggestion.get("amount") and suggestion.get("date"):
            want = Decimal(suggestion["amount"]["amount"])
            payee = fold(suggestion.get("payee") or "").strip()
            for r in conn.execute(
                "SELECT id, date, amount, currency, payee FROM pf_entries WHERE ws_id=? AND voided=0 "
                "AND kind='expense' AND date=?",
                (ws_id, suggestion["date"]),
            ).fetchall():
                other = fold(r["payee"] or "").strip()
                if Decimal(str(r["amount"]).lstrip("-")) == want and (not payee or not other or payee == other):
                    hit = dict(r)
                    break
    finally:
        conn.close()
    if hit is None:
        return None
    return {
        "entry_id": hit["id"],
        "date": hit["date"],
        "amount": {"amount": str(q2(Decimal(str(hit["amount"]).lstrip("-")))), "currency": hit["currency"]},
        "payee": hit["payee"],
        "same_photo": same_photo is not None,
    }


def _public(ws_id: str, row: dict) -> dict[str, Any]:
    return {
        "id": row["id"],
        "url": f"/ingest/{ws_id}/receipts/{row['id']}/image",
        "content_type": row["content_type"],
        "size": row["size"],
        "created_at": row["created_at"],
    }


def scan(ws_id: str, data: bytes, filename: str | None, today: date | None = None) -> dict[str, Any]:
    get_workspace(ws_id)  # WorkspaceNotFound → 404 in the router
    lang = ws_lang(ws_id)
    today = today or date.today()
    row = save_receipt(ws_id, data, filename)
    path = settings().workspace_dir(ws_id) / row["path"]
    ocr = receipt_ocr.ocr_image(path)
    text = ocr.text[:TEXT_KEEP]

    suggestion: dict[str, Any] | None = None
    reasons: list[str] = []
    message: str | None = None
    if not ocr.ok:
        message = i18n_t("receipt.msg.ocr_off" if ocr.error in ("ocr_off", "tesseract_not_found")
                         else "receipt.msg.ocr_failed", lang)
    else:
        suggestion, reasons = suggest(ws_id, text, today)
        if suggestion["amount"] is None:
            message = i18n_t("receipt.msg.no_total", lang)

    conn = connect()
    try:
        conn.execute(
            "UPDATE ingest_receipts SET ocr_engine=?, ocr_ok=?, ocr_error=?, ocr_text=?, suggestion=? "
            "WHERE ws_id=? AND id=?",
            (ocr.engine, int(ocr.ok), ocr.error, text or None,
             json.dumps({"suggestion": suggestion, "reasons": reasons}, ensure_ascii=False), ws_id, row["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    duplicate = possible_duplicate(ws_id, row, suggestion)
    found = [k for k in ("amount", "date", "payee", "label_id") if suggestion and suggestion.get(k)]
    audit.record(ws_id, "ingest.receipt.scan", {"receipt_id": row["id"], "size": row["size"]},
                 {"engine": ocr.engine, "ok": ocr.ok, "error": ocr.error, "found": found,
                  "duplicate_of": duplicate["entry_id"] if duplicate else None})
    return {
        "receipt": _public(ws_id, row),
        "ocr": {"engine": ocr.engine, "ok": ocr.ok, "error": ocr.error, "chars": len(text),
                "seconds": round(ocr.seconds, 2), "text": text},
        "suggestion": suggestion,
        "reasons": reasons,
        "message": message,
        "duplicate": duplicate,
    }


def get_receipt(ws_id: str, rid: str) -> dict[str, Any] | None:
    row = _row(ws_id, rid)
    if row is None:
        return None
    saved = json.loads(row.get("suggestion") or "{}") or {}
    return {
        "receipt": _public(ws_id, row),
        "ocr": {"engine": row["ocr_engine"], "ok": bool(row["ocr_ok"]), "error": row["ocr_error"],
                "chars": len(row["ocr_text"] or ""), "text": row["ocr_text"] or ""},
        "suggestion": saved.get("suggestion"),
        "reasons": saved.get("reasons", []),
    }


def amount_decimal(suggestion: dict | None) -> Decimal | None:
    """Test helper: the suggested amount as a Decimal."""
    if not suggestion or not suggestion.get("amount"):
        return None
    return Decimal(suggestion["amount"]["amount"])
