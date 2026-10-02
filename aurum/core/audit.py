"""Immutable audit log: inputs, outputs, model, rule versions. PII is masked before it is written."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from .db import connect

_RFC = re.compile(r"\b([A-ZÑ&]{3,4})\d{6}[A-Z0-9]{3}\b")
_CURP = re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_ACCOUNT = re.compile(r"\b\d{10,18}\b")


def mask(text: str) -> str:
    text = _RFC.sub(lambda m: m.group(1) + "******" + "***", text)
    text = _CURP.sub("CURP-MASKED", text)
    text = _SSN.sub("***-**-****", text)
    text = _ACCOUNT.sub(lambda m: "*" * (len(m.group(0)) - 4) + m.group(0)[-4:], text)
    return text


def _dump(value: Any) -> str:
    return mask(json.dumps(value, default=str, ensure_ascii=False))


def record(
    ws_id: str | None,
    action: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    model: str | None = None,
    rule_versions: list[str] | None = None,
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO core_audit (ts, ws_id, action, inputs, outputs, model, rule_versions) VALUES (?,?,?,?,?,?,?)",
            (
                datetime.now(UTC).isoformat(timespec="seconds"),
                ws_id,
                action,
                _dump(inputs),
                _dump(outputs),
                model,
                json.dumps(rule_versions or []),
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def recent(ws_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    conn = connect()
    try:
        if ws_id:
            rows = conn.execute(
                "SELECT * FROM core_audit WHERE ws_id=? ORDER BY id DESC LIMIT ?", (ws_id, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM core_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
