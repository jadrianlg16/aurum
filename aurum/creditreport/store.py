"""Persistence + explainer for creditreport imports."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from ..core.db import connect
from ..core.explain import Citation, Explain
from ..core.i18n import t
from .parser import ParsedReport


def db():
    return connect()


def save_import(ws_id: str, filename: str, report: ParsedReport) -> dict:
    conn = db()
    import_id = f"crimport-{uuid.uuid4().hex[:12]}"
    conn.execute(
        "INSERT INTO creditreport_imports (id, ws_id, filename, imported_at, score, accounts, warnings) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            import_id, ws_id, filename, datetime.now(UTC).isoformat(),
            json.dumps(report.score, ensure_ascii=False) if report.score else None,
            json.dumps(report.accounts, ensure_ascii=False),
            json.dumps(report.warnings, ensure_ascii=False),
        ),
    )
    conn.commit()
    return get_import(ws_id, import_id)


def _row(r) -> dict:
    d = dict(r)
    d["score"] = json.loads(d["score"]) if d.get("score") else None
    d["accounts"] = json.loads(d["accounts"])
    d["warnings"] = json.loads(d["warnings"])
    return d


def get_import(ws_id: str, import_id: str) -> dict:
    conn = db()
    row = conn.execute(
        "SELECT * FROM creditreport_imports WHERE ws_id=? AND id=?", (ws_id, import_id)
    ).fetchone()
    if row is None:
        raise KeyError(import_id)
    return _row(row)


def list_imports(ws_id: str) -> list[dict]:
    conn = db()
    rows = conn.execute(
        "SELECT * FROM creditreport_imports WHERE ws_id=? ORDER BY imported_at DESC", (ws_id,)
    ).fetchall()
    return [_row(r) for r in rows]


def latest_import(ws_id: str) -> dict | None:
    rows = list_imports(ws_id)
    return rows[0] if rows else None


def explain_score_factors(lang: str = "es") -> Explain:
    """Education only — never a diagnosis of *this user's* score, just what generally moves one."""
    explain = Explain(
        summary=t("creditreport.score_factors.summary", lang),
        citations=[
            Citation(
                law="Buró de Crédito", article="¿Cómo se calcula mi score?", trust_tier="official_guidance",
                url="https://www.burodecredito.com.mx", excerpt="(verify)",
            ),
            Citation(
                law="CONDUSEF", article="Reporte de Crédito Especial", trust_tier="official_guidance",
                url="https://www.condusef.gob.mx", excerpt="(verify)",
            ),
        ],
        confidence=0.4,
    )
    for key in ("payment_history", "utilization", "credit_age_mix", "recent_inquiries"):
        explain.add_step(
            t(f"creditreport.score_factors.step.{key}.label", lang),
            t(f"creditreport.score_factors.step.{key}.value", lang),
        )
    return explain
