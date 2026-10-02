"""SQLite helpers for the organizer module. Tables are prefixed ``organizer_`` (schema.sql)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, date, datetime
from typing import Any

from ..core.db import connect


def db() -> sqlite3.Connection:
    return connect()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def iso(value: date | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def as_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
