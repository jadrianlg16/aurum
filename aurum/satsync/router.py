"""SAT sync endpoints, mounted at /api/satsync."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..core import audit
from ..core.config import settings
from ..core.db import connect
from . import vault as vault_mod
from .client import FakeSAT, SatcfdiClient

router = APIRouter()


@router.post("/{ws}/vault")
async def store_vault(
    ws: str,
    password: str = Form(...),
    passphrase: str = Form(...),
    cer: UploadFile = File(...),  # noqa: B008
    key: UploadFile = File(...),  # noqa: B008
) -> dict:
    cer_bytes = await cer.read()
    key_bytes = await key.read()
    result = vault_mod.store(ws, cer_bytes, key_bytes, password, passphrase)
    audit.record(ws, "satsync.vault.store", {}, {"present": result.get("present")})
    return result


@router.get("/{ws}/vault")
def vault_status(ws: str) -> dict:
    return vault_mod.status(ws)


@router.delete("/{ws}/vault")
def delete_vault(ws: str) -> dict:
    purged = vault_mod.purge(ws)
    audit.record(ws, "satsync.vault.purge", {}, {"purged": purged})
    return {"purged": purged}


class SyncBody(BaseModel):
    start: date
    end: date
    kind: Literal["emitidos", "recibidos"]
    passphrase: str


def _job_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "ws_id": row["ws_id"],
        "kind": row["kind"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "status": row["status"],
        "request_id": row["request_id"],
        "downloaded": row["downloaded"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _insert_job(job_id: str, ws: str, body: SyncBody) -> None:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO satsync_jobs (id, ws_id, kind, start_date, end_date, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (job_id, ws, body.kind, body.start.isoformat(), body.end.isoformat(), "pending", now, now),
        )
        conn.commit()
    finally:
        conn.close()


def _update_job(job_id: str, **fields) -> None:
    fields["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    cols = ", ".join(f"{k}=?" for k in fields)
    conn = connect()
    try:
        conn.execute(f"UPDATE satsync_jobs SET {cols} WHERE id=?", (*fields.values(), job_id))
        conn.commit()
    finally:
        conn.close()


@router.post("/{ws}/sync")
def start_sync(ws: str, body: SyncBody) -> dict:
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    _insert_job(job_id, ws, body)

    fake_dir = os.environ.get("AURUM_SAT_FAKE_DIR")
    try:
        if fake_dir:
            client = FakeSAT(fake_dir)
        else:
            creds = vault_mod.open_vault(ws, body.passphrase)
            download_dir = settings().workspace_dir(ws) / "satsync_downloads"
            client = SatcfdiClient(creds, download_dir)

        request_id = client.request(ws, body.start.isoformat(), body.end.isoformat(), body.kind)
        _update_job(job_id, status="requested", request_id=request_id)
        state = client.verify(request_id)
        _update_job(job_id, status=state if state == "ready" else "verifying")
        if state == "ready":
            paths = client.download(request_id)
            _update_job(job_id, status="downloaded", downloaded=len(paths))
    except vault_mod.VaultNotFound as e:
        _update_job(job_id, status="error", error="vault not found")
        raise HTTPException(400, "e.firma vault not found for this workspace") from e
    except vault_mod.VaultBadPassphrase as e:
        _update_job(job_id, status="error", error="bad passphrase")
        raise HTTPException(401, "incorrect vault passphrase") from e
    except NotImplementedError as e:
        _update_job(job_id, status="error", error=str(e))
        raise HTTPException(501, str(e)) from e

    audit.record(ws, "satsync.sync", {"kind": body.kind, "start": str(body.start), "end": str(body.end)}, {"job_id": job_id})
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM satsync_jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    return _job_row_to_dict(row)


@router.get("/{ws}/jobs")
def list_jobs(ws: str) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM satsync_jobs WHERE ws_id=? ORDER BY created_at DESC", (ws,)).fetchall()
        return [_job_row_to_dict(r) for r in rows]
    finally:
        conn.close()
