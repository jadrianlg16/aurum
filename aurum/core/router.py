"""Core endpoints: health, workspaces, audit."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from .. import __version__
from . import audit, backup, token
from .config import env, settings
from .db import applied_versions, connect
from .validation import date_q
from .workspaces import (
    Workspace,
    WorkspaceNotFound,
    get_workspace,
    ordered_workspaces,
    protected_workspace_ids,
    save_workspace,
)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    s = settings()
    conn = connect()
    try:
        schema = applied_versions(conn)
    finally:
        conn.close()
    return {
        "ok": True,
        "version": __version__,
        "llm": {"provider": s.llm_provider, "model": s.llm_model, "cloud_opt_in": s.cloud_opt_in},
        "demo_mode": s.demo_mode,
        "auth": {"required": token.auth_required(), "source": token.auth_source()},
        "bind": env("AURUM_BIND", "127.0.0.1"),
        "schema": schema,
    }


@router.get("/workspaces")
def workspaces(include_hidden: bool = False) -> list[dict]:
    return [w.masked() for w in ordered_workspaces(include_hidden=include_hidden)]


@router.post("/workspaces")
def create_workspace(ws: Workspace) -> dict:
    try:
        return save_workspace(ws).masked()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/workspaces/{ws_id}")
def workspace(ws_id: str) -> dict:
    try:
        return get_workspace(ws_id).masked()
    except WorkspaceNotFound as e:
        raise HTTPException(404, f"workspace {ws_id} not found") from e


class WorkspaceUpdate(BaseModel):
    """PATCH-like body for PUT /workspaces/{ws_id}: every field optional, id is never accepted here."""

    name: str | None = None
    kind: Literal["personal", "business", "advisory"] | None = None
    jurisdictions: list[Literal["MX", "US"]] | None = None
    base_currency: str | None = None
    language: Literal["es", "en"] | None = None
    profile: dict[str, Any] | None = None
    ui_mode: Literal["simple", "advanced"] | None = None
    modules: dict[str, bool] | None = None
    hidden: bool | None = None
    protected: bool | None = None


@router.put("/workspaces/{ws_id}")
def update_workspace(ws_id: str, body: WorkspaceUpdate) -> dict:
    """Update name/language/base_currency/profile (merged, not replaced). The id is immutable. Trying to
    unset ``protected`` on an env-protected id (``personal`` by default) is
    rejected outright rather than silently ignored."""
    if body.protected is False and ws_id in protected_workspace_ids():
        raise HTTPException(400, f"workspace {ws_id} is protected")
    try:
        ws = get_workspace(ws_id)
    except WorkspaceNotFound as e:
        raise HTTPException(404, f"workspace {ws_id} not found") from e

    data = ws.model_dump(mode="json")
    if body.name is not None:
        data["name"] = body.name
    if body.kind is not None:
        data["kind"] = body.kind
    if body.jurisdictions is not None:
        data["jurisdictions"] = body.jurisdictions
    if body.base_currency is not None:
        data["base_currency"] = body.base_currency
    if body.language is not None:
        data["language"] = body.language
    if body.profile is not None:
        data["profile"] = {**data.get("profile", {}), **body.profile}
    if body.ui_mode is not None:
        data["ui_mode"] = body.ui_mode
    if body.modules is not None:
        data["modules"] = {**data.get("modules", {}), **body.modules}
    if body.hidden is not None:
        data["hidden"] = body.hidden
    if body.protected is not None:
        data["protected"] = body.protected
    data["id"] = ws_id  # id is immutable regardless of what the body claims

    updated = Workspace.model_validate(data)
    try:
        return save_workspace(updated).masked()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/audit")
def audit_log(ws: str | None = None, limit: int = 50) -> list[dict]:
    return audit.recent(ws, min(limit, 500))


# --- backup / export ---------------------------------------------------------------------------


@router.get("/workspaces/{ws_id}/backup.zip")
def workspace_backup_zip(ws_id: str):
    try:
        fh = backup.build_workspace_zip(ws_id)
    except WorkspaceNotFound as e:
        raise HTTPException(404, f"workspace {ws_id} not found") from e
    filename = f"aurum-{ws_id}-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}.zip"
    audit.record(ws_id, "core.backup.workspace", {}, {"filename": filename})
    return StreamingResponse(
        backup.stream_file(fh),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/workspaces/{ws_id}/movimientos.csv")
def workspace_movimientos_csv(
    ws_id: str,
    date_from: str | None = Depends(date_q("from")),
    date_to: str | None = Depends(date_q("to")),
):
    try:
        get_workspace(ws_id)
    except WorkspaceNotFound as e:
        raise HTTPException(404, f"workspace {ws_id} not found") from e
    from datetime import date as _date

    data = backup.build_movimientos_csv(
        ws_id,
        _date.fromisoformat(date_from) if date_from else None,
        _date.fromisoformat(date_to) if date_to else None,
    )
    audit.record(ws_id, "core.backup.csv", {"from": date_from, "to": date_to}, {"bytes": len(data)})
    return Response(content=data, media_type="text/csv; charset=utf-8")


@router.post("/backup")
def create_backup() -> dict:
    result = backup.create_full_backup()
    audit.record(None, "core.backup.full", {}, {"name": result["name"], "size": result["size"]})
    return result


@router.get("/backups")
def list_backups() -> list[dict]:
    return backup.list_backups()


@router.get("/backups/{name}")
def download_backup(name: str):
    path = backup.backup_path(name)
    if path is None:
        raise HTTPException(404, "backup not found")
    audit.record(None, "core.backup.download", {"name": name}, {})
    return FileResponse(path, media_type="application/zip", filename=name)
