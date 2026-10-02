"""Archives a rendered report under the workspace ``docs/reports/`` and records it in SQLite."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from ..core.config import settings
from ..core.db import connect


def _new_id() -> str:
    return "rpt_" + uuid.uuid4().hex[:16]


def store(ws_id: str, pack: str, period: str | None, fmt: str, content: bytes) -> dict:
    ws_dir = settings().workspace_dir(ws_id)
    reports_dir = ws_dir / "docs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()
    record_id = _new_id()
    suffix = "pdf" if fmt == "pdf" else "html"
    filename = f"{pack}-{period or 'na'}-{record_id}.{suffix}"
    path = reports_dir / filename
    path.write_bytes(content)

    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO reports_archive (id, ws_id, pack, period, format, path, sha256, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (record_id, ws_id, pack, period, fmt, str(path), digest, created_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "id": record_id,
        "workspace": ws_id,
        "pack": pack,
        "period": period,
        "format": fmt,
        "path": str(path),
        "sha256": digest,
        "created_at": created_at,
        "size": len(content),
    }


def list_archived(ws_id: str, pack: str | None = None) -> list[dict]:
    conn = connect()
    try:
        if pack:
            rows = conn.execute(
                "SELECT * FROM reports_archive WHERE ws_id=? AND pack=? ORDER BY created_at DESC",
                (ws_id, pack),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reports_archive WHERE ws_id=? ORDER BY created_at DESC", (ws_id,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
