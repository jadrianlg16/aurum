"""Data adapter: where the tax layer gets CFDIs and bank lines from.

The ingest module owns the ``ingest_cfdi`` table and its shape may change, so nothing in
``aurum/rules`` or ``aurum/tax/prefill.py`` reads SQLite directly — everything goes through here and
degrades gracefully:

1. documents passed in explicitly (API query param / tests),
2. the ``ingest_cfdi`` table, read column-by-column with tolerant names,
3. ``{DATA_DIR}/workspaces/{ws}/docs/cfdi/index.json`` — the demo fixture index.

Bank lines always come from the ledger (`Assets:Bank:` postings): the ledger is the truth.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..core.config import settings
from ..core.db import connect
from ..ledger.base import get_ledger
from ..rules.mx.resico import period_bounds

BANK_PREFIX = "Assets:Bank:"

# CFDI field → the column/key names we accept for it.
_ALIASES: dict[str, tuple[str, ...]] = {
    "uuid": ("uuid", "cfdi_uuid", "id"),
    "tipo": ("tipo", "tipo_comprobante", "tipo_de_comprobante"),
    "fecha": ("fecha", "fecha_emision", "date"),
    "emisor_rfc": ("emisor_rfc", "rfc_emisor", "emisor"),
    "receptor_rfc": ("receptor_rfc", "rfc_receptor", "receptor"),
    "subtotal": ("subtotal",),
    "total": ("total",),
    "moneda": ("moneda", "currency"),
    "metodo_pago": ("metodo_pago", "metodopago"),
    "forma_pago": ("forma_pago", "formapago"),
    "uso_cfdi": ("uso_cfdi", "usocfdi", "uso"),
    "iva_trasladado": ("iva_trasladado", "impuestos_trasladados", "iva"),
    "impuestos_retenidos": ("impuestos_retenidos", "retenidos"),
    "isr_retenido": ("isr_retenido", "retencion_isr"),
    "iva_retenido": ("iva_retenido", "retencion_iva"),
    "direction": ("direction", "direccion", "sentido"),
    "raw_path": ("raw_path", "path", "xml_path"),
}


def _pick(row: dict[str, Any], field: str) -> Any:
    for name in _ALIASES[field]:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def normalize_cfdi(row: dict[str, Any]) -> dict[str, Any]:
    """Map any tolerated column naming onto the canonical CFDI field names."""
    doc = {field: _pick(row, field) for field in _ALIASES}
    pagos = row.get("pagos")
    if isinstance(pagos, str):
        try:
            pagos = json.loads(pagos)
        except json.JSONDecodeError:
            pagos = []
    doc["pagos"] = pagos or []
    doc["moneda"] = doc.get("moneda") or "MXN"
    doc["direction"] = doc.get("direction") or "emitido"
    return doc


def _from_table(ws_id: str) -> list[dict[str, Any]] | None:
    try:
        conn = connect()
    except sqlite3.Error:
        return None
    try:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ingest_cfdi'"
        ).fetchone()
        if not exists:
            return None
        columns = {r[1] for r in conn.execute("PRAGMA table_info(ingest_cfdi)")}
        where, params = ("WHERE ws_id = ?", (ws_id,)) if "ws_id" in columns else ("", ())
        rows = conn.execute(f"SELECT * FROM ingest_cfdi {where}", params).fetchall()  # noqa: S608
        out = []
        for r in rows:
            row = dict(r)
            blob = row.get("json")
            if isinstance(blob, str):
                try:
                    full = json.loads(blob)
                    if isinstance(full, dict):
                        full.update({k: v for k, v in row.items() if k != "json" and v not in (None, "")})
                        row = full
                except json.JSONDecodeError:
                    pass
            out.append(normalize_cfdi(row))
        return out
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def fixtures_path(ws_id: str) -> Path:
    return settings().workspace_dir(ws_id) / "docs" / "cfdi" / "index.json"


def _from_fixtures(ws_id: str) -> list[dict[str, Any]] | None:
    path = fixtures_path(ws_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("documents") if isinstance(data, dict) else data
    return [normalize_cfdi(dict(r)) for r in rows or []]


def load_cfdis(ws_id: str, documents: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], str]:
    """Return (documents, source) where source is ``"argument" | "ingest_cfdi" | "fixtures" | "none"``."""
    if documents is not None:
        return [normalize_cfdi(dict(d)) for d in documents], "argument"
    from_table = _from_table(ws_id)
    if from_table:
        return from_table, "ingest_cfdi"
    from_fixtures = _from_fixtures(ws_id)
    if from_fixtures:
        return from_fixtures, "fixtures"
    return [], "none"


@dataclass
class BankLine:
    date: date
    amount: Decimal  # positive = deposit
    account: str
    payee: str | None
    narration: str
    cfdi_uuid: str | None
    txn_id: str | None
    accounts: list[str]

    @property
    def is_opening(self) -> bool:
        """Opening balances are not income: they are booked against Equity."""
        return any(a.startswith("Equity:") for a in self.accounts)


def bank_lines(ws_id: str, period: str) -> list[BankLine]:
    """Bank postings for the period, straight from the ledger."""
    start, end = period_bounds(period)
    out: list[BankLine] = []
    for txn in get_ledger().journal(ws_id, start=start, end=end, account_prefix=BANK_PREFIX):
        for posting in txn.postings:
            if not posting.account.startswith(BANK_PREFIX) or posting.amount is None:
                continue
            out.append(
                BankLine(
                    date=txn.date,
                    amount=posting.amount.amount,
                    account=posting.account,
                    payee=txn.payee,
                    narration=txn.narration,
                    cfdi_uuid=txn.meta.get("cfdi_uuid"),
                    txn_id=txn.links[0] if txn.links else None,
                    accounts=[p.account for p in txn.postings],
                )
            )
    return out
