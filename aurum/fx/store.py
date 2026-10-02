"""Small sqlite helpers for the fx module. Table is ``fx_rates`` (aurum/fx/schema.sql)."""

from __future__ import annotations

import sqlite3
import uuid

from ..core.db import connect


def db() -> sqlite3.Connection:
    return connect()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
