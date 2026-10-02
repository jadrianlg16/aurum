"""Backup/export: per-workspace ``backup.zip``/``movimientos.csv`` and a
full-instance ``POST /api/backup``. Routes live in ``core/router.py``; this module holds the mechanics
so they can be unit-tested without an HTTP client.

Every sqlite read goes through a ``Connection.backup()`` snapshot (never the live handle a writer might
hold mid-transaction) so a concurrent insert never leaks a half-written row into a backup and a reader
never blocks a writer. Nothing is left on disk for the per-workspace zip (built in a
``SpooledTemporaryFile``); the full backup necessarily touches disk (``data/backups/``) because it is
meant to be downloaded and kept.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import SpooledTemporaryFile, TemporaryDirectory
from typing import Any

from .. import __version__
from .config import env_int, settings
from .db import applied_versions, connect
from .money import q2
from .workspaces import get_workspace

BACKUP_NAME_RE = re.compile(r"^aurum-\d{8}-\d{6}\.zip$")

CSV_HEADER = [
    "Fecha", "Tipo", "Monto", "Moneda", "Cuenta", "Cuenta destino", "Categoría", "Comercio", "Nota",
    "Etiquetas", "Origen",
]
_KIND_ES = {"expense": "Gasto", "income": "Ingreso", "transfer": "Transferencia"}


# --------------------------------------------------------------------------- sqlite snapshot helpers


def _metadata_snapshot() -> sqlite3.Connection:
    """In-memory ``Connection.backup()`` copy of the metadata db — reads never see a half-written write
    from another connection, and never hold a lock against one either."""
    src = connect()
    snap = sqlite3.connect(":memory:")
    snap.row_factory = sqlite3.Row
    src.backup(snap)
    return snap


def _ws_id_tables(conn: sqlite3.Connection) -> list[str]:
    """Every table that has a ``ws_id`` column, discovered via ``PRAGMA table_info`` (never hardcoded,
    so a new module's table is picked up automatically)."""
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    out = []
    for t in tables:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()}
        if "ws_id" in cols:
            out.append(t)
    return sorted(out)


def workspace_metadata(ws_id: str) -> dict[str, Any]:
    """``metadata.json`` payload: every row of every ``ws_id``-scoped table for this workspace, read
    from a snapshot so an uncommitted write elsewhere never appears."""
    snap = _metadata_snapshot()
    try:
        tables: dict[str, list[dict]] = {}
        for t in _ws_id_tables(snap):
            rows = snap.execute(f"SELECT * FROM {t} WHERE ws_id=?", (ws_id,)).fetchall()  # noqa: S608 — t is our own PRAGMA-discovered identifier
            tables[t] = [dict(r) for r in rows]
        return {
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "version": __version__,
            "schema": applied_versions(snap),
            "tables": tables,
        }
    finally:
        snap.close()


# --------------------------------------------------------------------------- movimientos.csv


def _iter_entries(ws_id: str, date_from: date | None, date_to: date | None) -> list[dict]:
    """``pf.entries.list_entries`` returns the ``{"entries", "next_cursor", "totals"}`` envelope; a plain
    list (the older shape) is tolerated too. Pages at 500 until ``next_cursor`` is null."""
    from ..pf import entries as pf_entries

    rows: list[dict] = []
    cursor: str | None = None
    while True:
        result = pf_entries.list_entries(
            ws_id, date_from=date_from, date_to=date_to, limit=500, cursor=cursor
        )
        if isinstance(result, dict):
            page = list(result.get("entries", []))
            rows.extend(page)
            cursor = result.get("next_cursor")
            if not cursor or not page:
                break
        else:
            rows.extend(result)
            break
    return rows


def _split_sign(kind: str) -> int:
    return 1 if kind == "income" else -1  # expense/transfer both draw the account down


def build_movimientos_csv(ws_id: str, date_from: date | None = None, date_to: date | None = None) -> bytes:
    rows = _iter_entries(ws_id, date_from, date_to)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for r in rows:
        if r.get("voided"):
            continue
        tipo = _KIND_ES.get(r.get("kind"), r.get("kind") or "")
        splits = r.get("splits") or []
        if splits:
            sign = _split_sign(r.get("kind"))
            for s in splits:
                mag = Decimal(str((s.get("amount") or {}).get("amount", "0")))
                currency = (s.get("amount") or {}).get("currency") or r.get("amount", {}).get("currency", "")
                tags = [*list(r.get("tags") or []), "parte"]
                writer.writerow(
                    [
                        r.get("date", ""), tipo, str(q2(sign * mag)), currency,
                        r.get("account_name", ""), r.get("to_account_name") or "",
                        s.get("label_name") or r.get("label_name") or "", r.get("payee") or "",
                        s.get("note") or r.get("note") or "", ",".join(tags), r.get("source", ""),
                    ]
                )
        else:
            amount = r.get("amount") or {}
            writer.writerow(
                [
                    r.get("date", ""), tipo, amount.get("amount", ""), amount.get("currency", ""),
                    r.get("account_name", ""), r.get("to_account_name") or "", r.get("label_name") or "",
                    r.get("payee") or "", r.get("note") or "", ",".join(r.get("tags") or []),
                    r.get("source", ""),
                ]
            )
    return "﻿".encode() + buf.getvalue().encode("utf-8")


# --------------------------------------------------------------------------- per-workspace backup.zip


def build_workspace_zip(ws_id: str) -> SpooledTemporaryFile:
    """A zip built entirely in memory (spilling past ``max_size`` only for a very large workspace) —
    nothing touches disk for this route."""
    get_workspace(ws_id)  # raises WorkspaceNotFound if unknown; caller maps that to 404

    from ..ledger.beancount_store import BeancountLedger

    ledger = BeancountLedger()
    ws_dir = settings().workspace_dir(ws_id)

    fh = SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    with zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zf:
        wj = ws_dir / "workspace.json"
        if wj.exists():
            zf.writestr("workspace.json", wj.read_bytes())
        main_path = ledger.main_path(ws_id)
        if main_path.exists():
            zf.writestr("main.beancount", main_path.read_bytes())
        accounts_path = ledger.accounts_path(ws_id)
        if accounts_path.exists():
            zf.writestr("accounts.beancount", accounts_path.read_bytes())
        docs_dir = ws_dir / "docs"
        if docs_dir.exists():
            for p in sorted(docs_dir.rglob("*")):
                if p.is_file() and p.suffix != ".lock":
                    zf.writestr(f"docs/{p.relative_to(docs_dir).as_posix()}", p.read_bytes())
        zf.writestr(
            "metadata.json", json.dumps(workspace_metadata(ws_id), indent=2, ensure_ascii=False, default=str)
        )
        zf.writestr("movimientos.csv", build_movimientos_csv(ws_id))
    fh.seek(0)
    return fh


def stream_file(fh: SpooledTemporaryFile, chunk_size: int = 65536):
    try:
        fh.seek(0)
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        fh.close()


# --------------------------------------------------------------------------- full instance backup


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _prune_backups(backups_dir: Path) -> None:
    keep = env_int("AURUM_BACKUP_KEEP", 10)
    files = sorted(
        (p for p in backups_dir.glob("*.zip") if BACKUP_NAME_RE.match(p.name)),
        key=lambda p: p.name, reverse=True,
    )
    for p in files[keep:]:
        p.unlink(missing_ok=True)


def create_full_backup() -> dict[str, Any]:
    """``aurum.db`` (and ``corpus.db`` when present) copied through the sqlite backup API into a temp
    dir, then zipped with ``workspaces/**`` (minus ``*.lock``) and a ``manifest.json`` carrying a sha256
    per file. Prunes to the newest ``AURUM_BACKUP_KEEP`` (default 10) matching backups; touches nothing
    else in ``data/backups/``."""
    s = settings()
    backups_dir = s.data_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    name = f"aurum-{ts}.zip"
    dest = backups_dir / name

    src = connect()
    try:
        schema = applied_versions(src)
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_copy = tmp_path / "aurum.db"
            dst = sqlite3.connect(db_copy)
            try:
                src.backup(dst)
            finally:
                dst.close()

            corpus_copy: Path | None = None
            if s.corpus_db_path.exists():
                corpus_copy = tmp_path / "corpus.db"
                csrc = sqlite3.connect(s.corpus_db_path)
                cdst = sqlite3.connect(corpus_copy)
                try:
                    csrc.backup(cdst)
                finally:
                    cdst.close()
                    csrc.close()

            files: dict[str, str] = {}
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(db_copy, "aurum.db")
                files["aurum.db"] = _sha256(db_copy)
                if corpus_copy is not None:
                    zf.write(corpus_copy, "corpus.db")
                    files["corpus.db"] = _sha256(corpus_copy)
                ws_root = s.workspaces_dir
                if ws_root.exists():
                    for p in sorted(ws_root.rglob("*")):
                        if p.is_file() and p.suffix != ".lock":
                            arcname = f"workspaces/{p.relative_to(ws_root).as_posix()}"
                            zf.write(p, arcname)
                            files[arcname] = _sha256(p)
                manifest = {
                    "version": __version__,
                    "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "schema": schema,
                    "files": files,
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    finally:
        src.close()

    _prune_backups(backups_dir)
    return {"path": f"backups/{name}", "name": name, "size": dest.stat().st_size, "sha256": _sha256(dest)}


def list_backups() -> list[dict[str, Any]]:
    backups_dir = settings().data_dir / "backups"
    if not backups_dir.exists():
        return []
    rows = []
    for p in backups_dir.glob("*.zip"):
        if not BACKUP_NAME_RE.match(p.name):
            continue
        st = p.stat()
        rows.append(
            {
                "name": p.name,
                "size": st.st_size,
                "created_at": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds"),
            }
        )
    rows.sort(key=lambda r: r["name"], reverse=True)
    return rows


def backup_path(name: str) -> Path | None:
    """Resolves a backup filename to its path, refusing anything that is not an exact
    ``aurum-<ts>.zip`` match (no path traversal, no arbitrary reads from ``data/backups/``)."""
    if not BACKUP_NAME_RE.match(name):
        return None
    path = settings().data_dir / "backups" / name
    return path if path.exists() else None
