"""Report endpoints, mounted at ``/api/reports``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ..core import audit as audit_log
from ..core.i18n import ws_lang
from . import archive as archive_mod
from . import packs
from .builder import render_html, render_pdf

router = APIRouter(tags=["reports"])


def _build(pack: str, ws: str, period: str | None, lang: str | None, reviewer: str | None):
    if pack not in packs.PACKS:
        raise HTTPException(404, f"unknown report pack '{pack}'")
    try:
        return packs.build(pack, ws, period, ws_lang(ws, lang), reviewer=reviewer)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/{ws}")
def api_catalog(ws: str) -> dict:
    return packs.catalog(ws)


@router.get("/{ws}/{pack}/preview")
def api_preview(ws: str, pack: str, period: str | None = None, lang: str | None = None) -> dict:
    report = _build(pack, ws, period, lang, None)
    return report.model_dump(mode="json")


@router.get("/{ws}/{pack}")
def api_report(
    ws: str,
    pack: str,
    period: str | None = None,
    lang: str | None = None,
    format: str = "pdf",
    reviewer: str | None = None,
) -> Response:
    if format not in ("pdf", "html"):
        raise HTTPException(400, "format must be 'pdf' or 'html'")
    report = _build(pack, ws, period, lang, reviewer)
    audit_log.record(
        ws,
        f"reports.{pack}",
        {"period": period, "format": format},
        {"sections": len(report.sections), "warnings": len(report.warnings)},
        rule_versions=report.rule_versions,
    )
    if format == "html":
        return Response(content=render_html(report), media_type="text/html")
    pdf_bytes = render_pdf(report)
    disposition = f'inline; filename="aurum-{ws}-{pack}-{period or "current"}.pdf"'
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": disposition})


@router.post("/{ws}/{pack}/archive")
def api_archive(
    ws: str,
    pack: str,
    period: str | None = None,
    lang: str | None = None,
    format: str = "pdf",
    reviewer: str | None = None,
) -> dict:
    if format not in ("pdf", "html"):
        raise HTTPException(400, "format must be 'pdf' or 'html'")
    report = _build(pack, ws, period, lang, reviewer)
    content = render_pdf(report) if format == "pdf" else render_html(report).encode("utf-8")
    record = archive_mod.store(ws, pack, period, format, content)
    audit_log.record(
        ws,
        f"reports.{pack}.archive",
        {"period": period, "format": format},
        {"id": record["id"], "sha256": record["sha256"]},
        rule_versions=report.rule_versions,
    )
    return record


@router.get("/{ws}/{pack}/archive")
def api_list_archive(ws: str, pack: str) -> list[dict]:
    return archive_mod.list_archived(ws, pack)
