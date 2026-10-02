"""Small sqlite helpers shared by the pf module. Tables are prefixed ``pf_`` (aurum/pf/schema.sql)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..core.db import connect


def db() -> sqlite3.Connection:
    return connect()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def now() -> str:
    """UTC ISO timestamp with microseconds — ``pf_entries.created_at == updated_at`` means "never edited"
    (``entries.is_unedited``), so two writes in the same second must not look identical."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


def later_than(previous: str | None) -> str:
    """``now()`` guaranteed to differ from ``previous`` (monotonic on the same row)."""
    ts = now()
    if previous and ts <= previous:
        bumped = datetime.fromisoformat(previous) + timedelta(microseconds=1)
        ts = bumped.isoformat(timespec="microseconds")
    return ts


def iso(value: date | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def as_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def base_currency(ws_id: str) -> str:
    """The workspace's base currency; ``MXN`` when the workspace file does not exist (tests, fixtures)."""
    try:
        from ..core.workspaces import WorkspaceNotFound, get_workspace

        return get_workspace(ws_id).base_currency
    except (WorkspaceNotFound, ValueError):
        return "MXN"


def money(value, currency: str) -> dict[str, str]:
    """``{"amount": "12.50", "currency": "MXN"}`` — every pf payload renders money through here (q2)."""
    from decimal import Decimal

    from ..core.money import q2

    return {"amount": str(q2(Decimal(str(value)))), "currency": currency}
