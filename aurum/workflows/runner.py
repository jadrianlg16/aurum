"""Executes a workflow's steps in order against the Aurum API.

By default the runner calls the API **in-process**: it builds ``create_app()`` once and
talks to it over ``httpx.ASGITransport`` (no socket, no separate server needed — this is
also what makes the test suite fast). Set ``AURUM_WORKFLOWS_API_URL`` (or pass
``api_url=``) to instead call a real running server over HTTP — useful when the workflow
needs to reach a differently-configured process.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..core import audit as audit_log
from ..core.config import env
from ..core.db import connect
from ..core.token import resolve_api_token
from .deny import is_denied, normalize_api_path
from .models import Step, WorkflowDef
from .store import get_def
from .templating import eval_when, render_value

MAX_EXCERPT = 2000


class WorkflowRunError(RuntimeError):
    pass


def _new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:16]


def _auth_headers() -> dict[str, str]:
    """Bearer for the API when a token is configured — the runner is the operator's own client."""
    token = resolve_api_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _client(api_url: str | None) -> tuple[httpx.Client, str]:
    """Returns (client, base_url). In-process by default; a real HTTP client if a URL is given.

    In-process uses Starlette's ``TestClient`` -- a real ``httpx.Client`` subclass that bridges
    to the ASGI app synchronously (via anyio), so the runner never needs its own event loop. Its
    base URL is ``http://localhost`` so the Host guard admits it in loopback mode.
    """
    url = api_url or env("AURUM_WORKFLOWS_API_URL", "")
    if url:
        return httpx.Client(base_url=url, timeout=30.0, headers=_auth_headers()), url
    from starlette.testclient import TestClient

    from ..api.app import create_app

    return TestClient(create_app(), base_url="http://localhost", headers=_auth_headers()), "in-process"


def _record_step(conn, run_id: str, index: int, step: Step, status_code: int | None, duration_ms: int,
                  excerpt: str, error: str | None) -> None:
    conn.execute(
        "INSERT INTO workflows_steps (run_id, step_index, step_id, method, path, status_code, "
        "duration_ms, response_excerpt, error) VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, index, step.id, step.method, step.path, status_code, duration_ms, excerpt, error),
    )
    conn.commit()


def run(ws: str, workflow_id: str, params: dict[str, Any] | None = None, api_url: str | None = None) -> dict[str, Any]:
    """Execute a workflow's steps in order. Returns a run summary dict."""
    wf = get_def(ws, workflow_id)
    return run_def(ws, wf, params, api_url=api_url)


def run_def(ws: str, wf: WorkflowDef, params: dict[str, Any] | None = None, api_url: str | None = None) -> dict[str, Any]:
    params = params or {}
    run_id = _new_run_id()
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    context: dict[str, Any] = {
        "ws": ws,
        "period": params.get("period") or date.today().strftime("%Y-%m"),
        "params": params,
        "steps": {},
    }

    conn = connect()
    try:
        conn.execute(
            "INSERT INTO workflows_runs (id, ws_id, workflow_id, started_at, status, params) VALUES (?,?,?,?,?,?)",
            (run_id, ws, wf.id, started_at, "running", __import__("json").dumps(params, default=str)),
        )
        conn.commit()

        status = "success"
        error_msg: str | None = None
        client, base = _client(api_url)
        try:
            for index, step in enumerate(wf.steps):
                if step.when is not None:
                    try:
                        should_run = eval_when(step.when, context)
                    except Exception as e:  # noqa: BLE001 - a bad `when` fails the step, not the process
                        _record_step(conn, run_id, index, step, None, 0, "", f"when-expression error: {e}")
                        status, error_msg = "failed", f"step {step.id}: when-expression error: {e}"
                        break
                    if not should_run:
                        _record_step(conn, run_id, index, step, None, 0, "", None)
                        continue

                rendered_path = render_value(step.path, context)
                rendered_body = render_value(step.body, context) if step.body else None

                norm = normalize_api_path(rendered_path)
                if is_denied(step.method, norm):
                    _record_step(conn, run_id, index, step, None, 0, "", "denied path")
                    status, error_msg = "failed", f"step {step.id}: path is on the deny-list: {rendered_path}"
                    if not (step.continue_on_error or wf.continue_on_error):
                        break
                    continue

                # Never trust the step's own "/api" prefix: dispatch the normalized path + original query.
                query = urlsplit(rendered_path).query
                url = "/api" + norm + (f"?{query}" if query else "")
                start = time.monotonic()
                try:
                    resp = client.request(step.method, url, json=rendered_body)
                    duration_ms = int((time.monotonic() - start) * 1000)
                    try:
                        body: Any = resp.json()
                    except ValueError:
                        body = resp.text
                    excerpt = str(body)[:MAX_EXCERPT]
                    context["steps"][step.id] = {"status": resp.status_code, "body": body}
                    step_ok = resp.status_code < 400
                    _record_step(conn, run_id, index, step, resp.status_code, duration_ms, excerpt,
                                 None if step_ok else f"HTTP {resp.status_code}")
                    if not step_ok:
                        status = "failed"
                        error_msg = f"step {step.id}: HTTP {resp.status_code}"
                        if not (step.continue_on_error or wf.continue_on_error):
                            break
                except httpx.HTTPError as e:
                    duration_ms = int((time.monotonic() - start) * 1000)
                    _record_step(conn, run_id, index, step, None, duration_ms, "", str(e))
                    status = "failed"
                    error_msg = f"step {step.id}: {e}"
                    if not (step.continue_on_error or wf.continue_on_error):
                        break
        finally:
            client.close()

        finished_at = datetime.now(UTC).isoformat(timespec="seconds")
        conn.execute(
            "UPDATE workflows_runs SET finished_at=?, status=?, error=? WHERE id=?",
            (finished_at, status, error_msg, run_id),
        )
        conn.commit()
    finally:
        conn.close()

    audit_log.record(
        ws,
        f"workflows.{wf.id}.run",
        {"params": params},
        {"run_id": run_id, "status": status, "steps": len(wf.steps)},
    )

    return get_run(ws, run_id)


def get_run(ws: str, run_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        run_row = conn.execute("SELECT * FROM workflows_runs WHERE id=? AND ws_id=?", (run_id, ws)).fetchone()
        if run_row is None:
            raise WorkflowRunError(f"run not found: {run_id}")
        step_rows = conn.execute(
            "SELECT * FROM workflows_steps WHERE run_id=? ORDER BY step_index", (run_id,)
        ).fetchall()
        return {
            "id": run_row["id"],
            "workspace": run_row["ws_id"],
            "workflow_id": run_row["workflow_id"],
            "started_at": run_row["started_at"],
            "finished_at": run_row["finished_at"],
            "status": run_row["status"],
            "error": run_row["error"],
            "steps": [dict(r) for r in step_rows],
        }
    finally:
        conn.close()


def list_runs(ws: str, workflow_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    conn = connect()
    try:
        if workflow_id:
            rows = conn.execute(
                "SELECT * FROM workflows_runs WHERE ws_id=? AND workflow_id=? ORDER BY started_at DESC LIMIT ?",
                (ws, workflow_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM workflows_runs WHERE ws_id=? ORDER BY started_at DESC LIMIT ?", (ws, limit)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
