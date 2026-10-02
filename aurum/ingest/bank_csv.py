"""Bank CSV import with auto-detected/remembered column mapping, dedupe, and pf entries.

Every new line becomes a real, editable movement through ``pf.entries.bulk_create(atomic=False)`` on the
pf account the caller names (``account_id`` is required): kind by sign, ``source="import"``, tags
``[import, csv-<bank>]``, the category from ``pf.labels.match_label`` when its kind matches. Lines are
still recorded in ``ingest_bank_lines`` (dedupe on the existing ``line_hash``) — only the ones whose entry
was created, so a rejected line can be fixed and re-imported. No inbox items.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from ..core.db import connect
from ..core.money import Amount

# Candidate header names (lowercased) we try to auto-detect, in priority order.
_DATE_KEYS = ["date", "fecha", "fecha operacion", "fecha de operacion", "transaction date"]
_DESC_KEYS = ["description", "descripcion", "concepto", "detalle", "referencia"]
_AMOUNT_KEYS = ["amount", "monto", "importe", "cargo/abono"]
_DEBIT_KEYS = ["debit", "cargo", "egreso", "retiro"]
_CREDIT_KEYS = ["credit", "abono", "ingreso", "deposito"]
_BALANCE_KEYS = ["balance", "saldo"]


@dataclass
class ColumnMapping:
    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None
    balance: str | None = None

    def to_json(self) -> str:
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, s: str) -> ColumnMapping:
        return cls(**json.loads(s))


def _find(headers: list[str], keys: list[str]) -> str | None:
    lower = {h.lower().strip(): h for h in headers}
    for k in keys:
        if k in lower:
            return lower[k]
    return None


def detect_mapping(headers: list[str]) -> ColumnMapping | None:
    date_col = _find(headers, _DATE_KEYS)
    desc_col = _find(headers, _DESC_KEYS)
    if not date_col or not desc_col:
        return None
    amount_col = _find(headers, _AMOUNT_KEYS)
    debit_col = _find(headers, _DEBIT_KEYS)
    credit_col = _find(headers, _CREDIT_KEYS)
    balance_col = _find(headers, _BALANCE_KEYS)
    if not amount_col and not (debit_col or credit_col):
        return None
    return ColumnMapping(date=date_col, description=desc_col, amount=amount_col, debit=debit_col, credit=credit_col, balance=balance_col)


def load_mapping(ws_id: str, bank: str) -> ColumnMapping | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT mapping_json FROM ingest_bank_mappings WHERE ws_id=? AND bank=?", (ws_id, bank)
        ).fetchone()
        return ColumnMapping.from_json(row["mapping_json"]) if row else None
    finally:
        conn.close()


def save_mapping(ws_id: str, bank: str, mapping: ColumnMapping) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO ingest_bank_mappings (ws_id, bank, mapping_json, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(ws_id, bank) DO UPDATE SET mapping_json=excluded.mapping_json, updated_at=excluded.updated_at",
            (ws_id, bank, mapping.to_json(), datetime.now(UTC).isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def _parse_amount(raw: str) -> Decimal:
    cleaned = (raw or "").replace(",", "").replace("$", "").strip()
    if cleaned in ("", "-"):
        return Decimal("0")
    neg = cleaned.startswith("(") and cleaned.endswith(")")
    if neg:
        cleaned = cleaned[1:-1]
    try:
        val = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"amount {raw!r} is not a number") from exc
    return -val if neg else val


def _parse_date(raw: str) -> date:
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"date {raw!r} not recognised (use YYYY-MM-DD or DD/MM/YYYY)") from exc


def line_hash(ws_id: str, bank: str, d: date, description: str, amount: Decimal) -> str:
    key = f"{ws_id}|{bank}|{d.isoformat()}|{description.strip().lower()}|{amount}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _bank_tag(bank: str) -> str:
    from ..pf.accounts_admin import slugify

    return f"csv-{slugify(bank).lower()}"


@dataclass
class _Line:
    line: int
    date: date
    description: str
    amount: Decimal
    balance: str | None
    hash: str


def import_csv(
    ws_id: str,
    bank: str,
    raw: bytes,
    *,
    account_id: str,
    base_currency: str = "MXN",
    mapping: ColumnMapping | None = None,
) -> dict:
    """→ ``{"created": [entry ids], "imported": n, "skipped_duplicates": n, "errors": [{line, detail}]}``.
    ``KeyError`` when ``account_id`` is unknown (nothing written)."""
    from ..pf import accounts_admin, entries, labels

    account = accounts_admin.get_row(ws_id, account_id)  # KeyError → 404
    if account["archived"]:
        raise ValueError(f"account {account_id} is archived")
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []

    mapping = mapping or load_mapping(ws_id, bank) or detect_mapping(headers)
    if mapping is None:
        return {"error": "could not detect column mapping", "headers": headers, "created": [], "imported": 0,
                "skipped_duplicates": 0, "errors": []}
    save_mapping(ws_id, bank, mapping)

    errors: list[dict] = []
    candidates: list[_Line] = []
    skipped_dupe = 0
    seen: set[str] = set()
    conn = connect()
    try:
        for row in reader:
            line_no = reader.line_num
            try:
                d = _parse_date(row.get(mapping.date) or "")
                description = (row.get(mapping.description) or "").strip()
                if mapping.amount:
                    amount = _parse_amount(row.get(mapping.amount) or "0")
                else:
                    debit = _parse_amount(row.get(mapping.debit) or "0") if mapping.debit else Decimal("0")
                    credit = _parse_amount(row.get(mapping.credit) or "0") if mapping.credit else Decimal("0")
                    amount = credit - debit if debit >= 0 else credit + debit
            except ValueError as exc:
                errors.append({"line": line_no, "detail": str(exc)})
                continue
            if amount == 0:
                errors.append({"line": line_no, "detail": "amount is zero"})
                continue
            balance = row.get(mapping.balance) if mapping.balance else None
            h = line_hash(ws_id, bank, d, description, amount)
            if h in seen or conn.execute("SELECT 1 FROM ingest_bank_lines WHERE hash=?", (h,)).fetchone():
                skipped_dupe += 1
                continue
            seen.add(h)
            candidates.append(_Line(line_no, d, description, amount, str(balance) if balance not in (None, "") else None, h))
    finally:
        conn.close()

    tag = _bank_tag(bank)
    bodies: list[entries.EntryIn] = []
    for c in candidates:
        kind = "income" if c.amount > 0 else "expense"
        label = labels.match_label(ws_id, c.description, kind=kind)
        bodies.append(
            entries.EntryIn(
                kind=kind,
                date=c.date.isoformat(),
                amount=Amount(amount=abs(c.amount), currency=base_currency),
                account_id=account_id,
                label_id=label["id"] if label else None,
                payee=c.description[:120] or None,
                note=None,
                tags=["import", tag],
                source="import",
            )
        )
    result = entries.bulk_create(ws_id, bodies, atomic=False) if bodies else {"created": [], "errors": []}
    failed = {e["index"] for e in result["errors"]}
    for e in result["errors"]:
        errors.append({"line": candidates[e["index"]].line, "detail": e["msg"]})

    conn = connect()
    try:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        for i, c in enumerate(candidates):
            if i in failed:
                continue
            conn.execute(
                "INSERT INTO ingest_bank_lines (ws_id, bank, date, description, amount, currency, balance, "
                "hash, imported_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (ws_id, bank, c.date.isoformat(), c.description, str(c.amount), base_currency, c.balance, c.hash, now),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "created": result["created"],
        "imported": len(result["created"]),
        "skipped_duplicates": skipped_dupe,
        "errors": sorted(errors, key=lambda e: e["line"]),
    }
