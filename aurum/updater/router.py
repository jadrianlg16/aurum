"""Law/rule tracker endpoints, mounted at ``/api/watch``.

``POST /run`` uses ``tracker.HttpFetcher`` by default; when ``AURUM_WATCH_FAKE_DIR``
points at a directory of ``<source_id>.txt`` files it uses ``tracker.FakeFetcher``
instead, so the whole fetch -> hash-diff -> reindex -> triage pipeline can be
exercised offline (tests, demos, CI).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..core.db import connect
from . import scheduler as scheduler_mod
from . import tracker

router = APIRouter(tags=["watch"])

#: Seeded once, on first read, so the UI has real content before any source has ever
#: actually been fetched. Reflects the 2026 CFF
#: art. 30-B reform: real-time SAT access to digital platforms.
_SEED_SOURCE_ID = "sat-rmf"
_SEED_SUMMARY = (
    "CFF art. 30-B: el SAT podrá tener acceso en tiempo real a los sistemas de las "
    "plataformas tecnológicas que prestan servicios digitales, vigente a partir del "
    "2026-04-01; el aviso correspondiente se presenta mediante la forma oficial "
    "168/CFF a más tardar el 2026-04-30 (RMF 2026, regla 2.9.21)."
)
_SEED_EXCERPT = (
    "Artículo 30-B. Los contribuyentes que operen como plataformas tecnológicas, "
    "aplicaciones informáticas y similares que presten servicios digitales deberán "
    "permitir al Servicio de Administración Tributaria el acceso en tiempo real a la "
    "información de sus sistemas conforme a la regla 2.9.21 de la RMF."
)


#: Sync endpoints run in a thread pool and the Watch screen reads /changes and /proposals at
#: once on first load, so the check-then-insert below must not interleave (it seeded twice).
_SEED_LOCK = threading.Lock()


def _ensure_seed() -> None:
    with _SEED_LOCK:
        _seed_if_empty()


def _seed_if_empty() -> None:
    conn = connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM updater_changes").fetchone()
        if row and row["n"]:
            return
    finally:
        conn.close()

    change = tracker.save_change(
        _SEED_SOURCE_ID,
        _SEED_SUMMARY,
        ["platform_withholding"],
        _SEED_EXCERPT,
        None,
        "2026-04-01",
    )
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO updater_proposals "
            "(id, change_id, rule_id, field, old_value, new_value, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"prop_{uuid.uuid4().hex[:12]}",
                change["id"],
                "mx.platform_withholding.sat_access",
                "requirement",
                "no real-time access requirement",
                "real-time SAT access required from 2026-04-01; notice via forma 168/CFF by 2026-04-30",
                "proposed",
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


class RunRequest(BaseModel):
    source_id: str | None = None


def _fetcher() -> tracker.Fetcher:
    return tracker.default_fetcher()


def _change_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["domains"] = json.loads(data.get("domains") or "[]")
    return data


@router.get("/changes")
def changes(since: str | None = None) -> list[dict[str, Any]]:
    _ensure_seed()
    conn = connect()
    try:
        if since:
            rows = conn.execute(
                "SELECT * FROM updater_changes WHERE detected_at >= ? ORDER BY detected_at DESC",
                (since,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM updater_changes ORDER BY detected_at DESC").fetchall()
    finally:
        conn.close()
    return [_change_row(row) for row in rows]


@router.post("/run")
def run(body: RunRequest | None = None) -> dict:
    body = body or RunRequest()
    return tracker.run(body.source_id, _fetcher())


@router.get("/sources")
def sources() -> list[dict]:
    return tracker.load_sources()


@router.get("/sources/{source_id}/history")
def source_history(source_id: str) -> dict[str, Any]:
    """Every snapshot and detected change ever recorded for one watched source."""

    conn = connect()
    try:
        snapshot_rows = conn.execute(
            "SELECT * FROM updater_snapshots WHERE source_id = ? ORDER BY fetched_at DESC",
            (source_id,),
        ).fetchall()
        change_rows = conn.execute(
            "SELECT * FROM updater_changes WHERE source_id = ? ORDER BY detected_at DESC",
            (source_id,),
        ).fetchall()
    finally:
        conn.close()
    return {
        "source_id": source_id,
        "snapshots": [dict(row) for row in snapshot_rows],
        "changes": [_change_row(row) for row in change_rows],
    }


class ScheduleRequest(BaseModel):
    enabled: bool
    sources: list[str] | None = None


@router.post("/schedule")
def schedule(body: ScheduleRequest) -> dict[str, Any]:
    """Start/stop the in-process per-source cadence scheduler.

    Gated by ``AURUM_WATCH_SCHEDULER=1``: with the gate unset, ``enabled: true`` is recorded
    but no background thread is actually started (``gated: true`` in the response says so).
    ``enabled: false`` always stops a running scheduler regardless of the gate.
    """

    sch = scheduler_mod.get_scheduler()
    gate_open = os.environ.get("AURUM_WATCH_SCHEDULER") == "1"
    if body.enabled and not gate_open:
        return {
            "enabled": False,
            "sources": body.sources,
            "gated": True,
            "reason": "AURUM_WATCH_SCHEDULER is not set to 1; scheduler was not started",
        }
    sch.configure(body.enabled, body.sources)
    return {"enabled": sch.enabled, "sources": sch.sources, "gated": False}


@router.get("/schedule")
def schedule_status() -> dict[str, Any]:
    return scheduler_mod.get_scheduler().status()


@router.get("/proposals")
def proposals() -> list[dict]:
    _ensure_seed()
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM updater_proposals ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]

