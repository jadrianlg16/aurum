"""``/api/workflows``."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import runner, seed, store
from .catalog import catalog_payload
from .propose import propose as propose_fn
from .store import WorkflowNotFound, WorkflowValidationError

router = APIRouter(tags=["workflows"])


@router.get("/catalog")
def api_catalog() -> dict:
    return catalog_payload()


@router.get("/{ws}")
def api_list(ws: str) -> list[dict]:
    seed.ensure_seeded(ws)
    return store.list_defs(ws)


class YamlIn(BaseModel):
    yaml: str


@router.post("/{ws}")
def api_create(ws: str, body: YamlIn) -> dict:
    seed.ensure_seeded(ws)
    wf, errors, warnings = store.validate_yaml(body.yaml)
    if wf is None:
        raise HTTPException(400, {"errors": errors, "warnings": warnings})
    return store.save(ws, wf, body.yaml)


@router.get("/{ws}/{workflow_id}")
def api_get(ws: str, workflow_id: str) -> dict:
    seed.ensure_seeded(ws)
    try:
        raw = store.get_yaml(ws, workflow_id)
    except WorkflowNotFound as e:
        raise HTTPException(404, str(e)) from e
    wf, errors, warnings = store.validate_yaml(raw)
    return {
        "workspace": ws,
        "id": workflow_id,
        "yaml": raw,
        "valid": wf is not None,
        "errors": errors,
        "warnings": warnings,
        "definition": wf.model_dump(mode="json") if wf else None,
    }


@router.put("/{ws}/{workflow_id}")
def api_update(ws: str, workflow_id: str, body: YamlIn) -> dict:
    wf, errors, warnings = store.validate_yaml(body.yaml)
    if wf is None:
        raise HTTPException(400, {"errors": errors, "warnings": warnings})
    if wf.id != workflow_id:
        raise HTTPException(400, f"YAML id {wf.id!r} does not match URL id {workflow_id!r}")
    return store.save(ws, wf, body.yaml)


@router.delete("/{ws}/{workflow_id}")
def api_delete(ws: str, workflow_id: str) -> dict:
    try:
        store.delete(ws, workflow_id)
    except WorkflowNotFound as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "workspace": ws, "id": workflow_id}


@router.post("/{ws}/{workflow_id}/run")
def api_run(ws: str, workflow_id: str, params: dict[str, Any] | None = None) -> dict:
    seed.ensure_seeded(ws)
    try:
        return runner.run(ws, workflow_id, params or {})
    except WorkflowNotFound as e:
        raise HTTPException(404, str(e)) from e
    except WorkflowValidationError as e:
        raise HTTPException(400, {"errors": e.errors}) from e


@router.get("/{ws}/{workflow_id}/runs")
def api_runs(ws: str, workflow_id: str, limit: int = 50) -> list[dict]:
    return runner.list_runs(ws, workflow_id, limit)


@router.get("/{ws}/{workflow_id}/runs/{run_id}")
def api_run_detail(ws: str, workflow_id: str, run_id: str) -> dict:
    try:
        return runner.get_run(ws, run_id)
    except runner.WorkflowRunError as e:
        raise HTTPException(404, str(e)) from e


class ScheduleIn(BaseModel):
    cron: str


@router.post("/{ws}/{workflow_id}/schedule")
def api_schedule(ws: str, workflow_id: str, body: ScheduleIn) -> dict:
    from .cron import CronError, parse

    try:
        parse(body.cron)
    except CronError as e:
        raise HTTPException(400, str(e)) from e
    try:
        result = store.set_schedule(ws, workflow_id, body.cron)
    except WorkflowNotFound as e:
        raise HTTPException(404, str(e)) from e
    result["gated"] = os.environ.get("AURUM_WORKFLOWS_SCHEDULER") != "1"
    return result


@router.delete("/{ws}/{workflow_id}/schedule")
def api_unschedule(ws: str, workflow_id: str) -> dict:
    try:
        return store.set_schedule(ws, workflow_id, None)
    except WorkflowNotFound as e:
        raise HTTPException(404, str(e)) from e


@router.get("/{ws}/{workflow_id}/schedule")
def api_schedule_status(ws: str, workflow_id: str) -> dict:
    defs = {d["id"]: d for d in store.list_defs(ws)}
    if workflow_id not in defs:
        raise HTTPException(404, workflow_id)
    return {"workspace": ws, "id": workflow_id, "schedule": defs[workflow_id]["schedule"]}


class ProposeIn(BaseModel):
    description: str


@router.post("/{ws}/propose")
def api_propose(ws: str, body: ProposeIn) -> dict:
    return propose_fn(ws, body.description)
