"""CRUD for workflow definitions: ``workflows_defs`` table + a mirrored YAML file under
``{DATA_DIR}/workspaces/{ws}/workflows/{id}.yaml`` (the file is the human-editable source of
truth; the DB row is what the API/scheduler query quickly)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ..core.config import settings
from ..core.db import connect
from .deny import is_denied
from .models import WorkflowDef


class WorkflowNotFound(KeyError):
    pass


class WorkflowValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _dir(ws: str) -> Path:
    return settings().workspace_dir(ws) / "workflows"


def validate_yaml(raw_yaml: str) -> tuple[WorkflowDef | None, list[str], list[str]]:
    """Parse+validate a workflow YAML. Returns (definition_or_None, errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        return None, [f"invalid YAML: {e}"], warnings
    if not isinstance(data, dict):
        return None, ["workflow YAML must be a mapping"], warnings
    try:
        wf = WorkflowDef.model_validate(data)
    except Exception as e:  # noqa: BLE001 - surfaced as validation errors, not a crash
        return None, [str(e)], warnings
    if not wf.steps:
        warnings.append("workflow has no steps")
    seen_ids = set()
    for step in wf.steps:
        if step.id in seen_ids:
            errors.append(f"duplicate step id: {step.id}")
        seen_ids.add(step.id)
        if is_denied(step.method, step.path):
            errors.append(f"step {step.id!r} calls a denied path: {step.method} {step.path}")
    if errors:
        return None, errors, warnings
    return wf, errors, warnings


def save(ws: str, wf: WorkflowDef, raw_yaml: str) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    d = _dir(ws)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{wf.id}.yaml").write_text(raw_yaml, encoding="utf-8")

    conn = connect()
    try:
        existing = conn.execute(
            "SELECT created_at FROM workflows_defs WHERE ws_id=? AND id=?", (ws, wf.id)
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            "INSERT INTO workflows_defs (ws_id, id, name, yaml, schedule, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(ws_id, id) DO UPDATE SET name=excluded.name, yaml=excluded.yaml, "
            "schedule=excluded.schedule, updated_at=excluded.updated_at",
            (ws, wf.id, wf.name, raw_yaml, wf.schedule, created_at, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": wf.id, "name": wf.name, "workspace": ws, "created_at": created_at, "updated_at": now}


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "workspace": row["ws_id"],
        "name": row["name"],
        "schedule": row["schedule"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_defs(ws: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM workflows_defs WHERE ws_id=? ORDER BY id", (ws,)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_yaml(ws: str, workflow_id: str) -> str:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT yaml FROM workflows_defs WHERE ws_id=? AND id=?", (ws, workflow_id)
        ).fetchone()
        if row is None:
            raise WorkflowNotFound(workflow_id)
        return row["yaml"]
    finally:
        conn.close()


def get_def(ws: str, workflow_id: str) -> WorkflowDef:
    raw = get_yaml(ws, workflow_id)
    wf, errors, _ = validate_yaml(raw)
    if wf is None:
        raise WorkflowValidationError(errors)
    return wf


def delete(ws: str, workflow_id: str) -> None:
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM workflows_defs WHERE ws_id=? AND id=?", (ws, workflow_id))
        conn.commit()
        if cur.rowcount == 0:
            raise WorkflowNotFound(workflow_id)
    finally:
        conn.close()
    path = _dir(ws) / f"{workflow_id}.yaml"
    if path.exists():
        path.unlink()


def set_schedule(ws: str, workflow_id: str, cron_expr: str | None) -> dict[str, Any]:
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE workflows_defs SET schedule=?, updated_at=? WHERE ws_id=? AND id=?",
            (cron_expr, datetime.now(UTC).isoformat(timespec="seconds"), ws, workflow_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise WorkflowNotFound(workflow_id)
    finally:
        conn.close()
    return {"workspace": ws, "id": workflow_id, "schedule": cron_expr}


def all_scheduled() -> list[dict[str, Any]]:
    """Every (ws, id, schedule) with a non-null schedule, across all workspaces."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ws_id, id, schedule FROM workflows_defs WHERE schedule IS NOT NULL"
        ).fetchall()
        return [{"workspace": r["ws_id"], "id": r["id"], "schedule": r["schedule"]} for r in rows]
    finally:
        conn.close()
