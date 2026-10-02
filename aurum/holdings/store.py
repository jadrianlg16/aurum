"""Small sqlite helpers for the holdings module. Tables are prefixed ``holdings_``."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from ..core.db import connect


def db() -> sqlite3.Connection:
    return connect()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)
