"""Tax endpoints, mounted at ``/api/tax``."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from ..core import audit as audit_log
from ..core.i18n import ws_lang
from ..core.workspaces import WorkspaceNotFound, get_workspace
from . import draft_pdf
from .month_close import month_close

router = APIRouter(tags=["tax"])

PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _profile(ws: str) -> tuple[str | None, str]:
    """(rfc, currency) from the workspace file; unknown workspaces still compute from documents."""
    try:
        workspace = get_workspace(ws)
    except WorkspaceNotFound:
        return None, "MXN"
    return workspace.profile.get("rfc"), workspace.base_currency


def _documents(documents_json: str | None) -> list[dict[str, Any]] | None:
    if not documents_json:
        return None
    try:
        parsed = json.loads(documents_json)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"documents must be a JSON array: {e}") from e
    if not isinstance(parsed, list):
        raise HTTPException(400, "documents must be a JSON array of CFDI objects")
    return parsed


def _payload(ws: str, period: str, documents_json: str | None, lang: str | None = None) -> dict[str, Any]:
    if not PERIOD.match(period):
        raise HTTPException(400, "period must be YYYY-MM")
    rfc, currency = _profile(ws)
    return month_close(
        ws, period, documents=_documents(documents_json), rfc=rfc, currency=currency, lang=ws_lang(ws, lang)
    )


@router.get("/mx/resico/{ws}/{period}")
def resico_month(ws: str, period: str, documents: str | None = None, lang: str | None = None) -> dict:
    payload = _payload(ws, period, documents, lang)
    audit_log.record(
        ws,
        "tax.mx.resico.month_close",
        {"period": period},
        {"isr": payload["isr"]["value"], "iva_payable": payload["iva"]["payable"], "diffs": len(payload["diffs"])},
        rule_versions=payload["isr"]["explain"].get("rule_versions", []),
    )
    return payload


@router.get("/mx/resico/{ws}/{period}/draft.pdf")
def resico_month_pdf(ws: str, period: str, documents: str | None = None, lang: str | None = None) -> Response:
    payload = _payload(ws, period, documents, lang)
    pdf = draft_pdf.render(payload)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="aurum-{ws}-{period}-DRAFT.pdf"'},
    )
