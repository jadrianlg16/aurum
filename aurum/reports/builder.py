"""A small report DSL rendered to PDF (reportlab) and HTML (same content, for preview).

Every pack in :mod:`aurum.reports.packs` builds a :class:`Report` — a title, a list of
:class:`Section`, and flags (``draft``, ``watermark_text``) — and this module turns it into bytes.
Neither format computes a figure: everything already arrived as a string from the source endpoint.

Every page carries: the fixed bilingual footer, a DRAFT watermark when ``draft`` is set (or a custom
``watermark_text`` for the client pack), page numbers, and a "generated at / rules used" line built
from ``generated_at`` and ``rule_versions``.
"""

from __future__ import annotations

import html as _html
import io
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from reportlab.lib.colors import Color, black, grey
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas as pdf_canvas

WIDTH, HEIGHT = LETTER
MARGIN = 50
FOOTER_LINE = "Aurum — decision support, not advice / no es asesoría"
DEFAULT_WATERMARK = "BORRADOR · DRAFT"


class KPI(BaseModel):
    label: str
    value: str
    note: str | None = None


class Table(BaseModel):
    title: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class ExplainBlock(BaseModel):
    summary: str
    steps: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class Section(BaseModel):
    title: str
    kpis: list[KPI] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    explains: list[ExplainBlock] = Field(default_factory=list)


class Report(BaseModel):
    title: str
    workspace: str
    period: str | None = None
    lang: str = "es"
    draft: bool = False
    watermark_text: str | None = None
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    rule_versions: list[str] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def effective_watermark(self) -> str | None:
        if self.watermark_text:
            return self.watermark_text
        if self.draft:
            return DEFAULT_WATERMARK
        return None


# --------------------------------------------------------------------------- PDF


def _watermark(c: pdf_canvas.Canvas, text: str) -> None:
    c.saveState()
    c.setFillColor(Color(0.85, 0.1, 0.1, alpha=0.14))
    c.setFont("Helvetica-Bold", 46)
    c.translate(WIDTH / 2, HEIGHT / 2)
    c.rotate(38)
    c.drawCentredString(0, 0, text)
    c.restoreState()


def _footer(c: pdf_canvas.Canvas, report: Report, page: int) -> None:
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(grey)
    c.drawCentredString(WIDTH / 2, MARGIN - 20, FOOTER_LINE)
    meta = f"Generated {report.generated_at}"
    if report.rule_versions:
        meta += "  ·  rules: " + ", ".join(report.rule_versions[:6])
        if len(report.rule_versions) > 6:
            meta += f" (+{len(report.rule_versions) - 6} more)"
    c.drawCentredString(WIDTH / 2, MARGIN - 30, meta[:180])
    c.drawRightString(WIDTH - MARGIN, MARGIN - 20, f"p. {page}")
    c.setFillColor(black)


def render_pdf(report: Report) -> bytes:
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=LETTER)
    c.setTitle(f"Aurum — {report.title} — {report.workspace}")
    watermark = report.effective_watermark()
    page = 1

    def new_page() -> float:
        if watermark:
            _watermark(c, watermark)
        c.setFillColor(black)
        return HEIGHT - MARGIN

    def break_page() -> float:
        nonlocal page
        _footer(c, report, page)
        c.showPage()
        page += 1
        return new_page()

    y = new_page()
    c.setFont("Helvetica-Bold", 17)
    c.drawString(MARGIN, y, report.title)
    y -= 18
    c.setFont("Helvetica", 9)
    sub = f"Workspace: {report.workspace}"
    if report.period:
        sub += f"    Period: {report.period}"
    c.drawString(MARGIN, y, sub)
    y -= 22

    for section in report.sections:
        if y < MARGIN + 90:
            y = break_page()
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGIN, y, section.title)
        y -= 6
        c.setStrokeColor(grey)
        c.line(MARGIN, y, WIDTH - MARGIN, y)
        y -= 15

        for kpi in section.kpis:
            if y < MARGIN + 60:
                y = break_page()
            c.setFont("Helvetica", 9)
            c.drawString(MARGIN, y, kpi.label)
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(WIDTH - MARGIN, y, kpi.value)
            y -= 12
            if kpi.note:
                c.setFont("Helvetica-Oblique", 7)
                c.setFillColor(grey)
                c.drawString(MARGIN + 8, y, kpi.note[:130])
                c.setFillColor(black)
                y -= 11

        for table in section.tables:
            if y < MARGIN + 80:
                y = break_page()
            c.setFont("Helvetica-Bold", 9)
            c.drawString(MARGIN, y, table.title)
            y -= 12
            col_w = (WIDTH - 2 * MARGIN) / max(len(table.columns), 1)
            c.setFont("Helvetica-Bold", 7.5)
            for i, col in enumerate(table.columns):
                c.drawString(MARGIN + i * col_w, y, col[:28])
            y -= 10
            c.setFont("Helvetica", 7.5)
            for row in table.rows:
                if y < MARGIN + 40:
                    y = break_page()
                    c.setFont("Helvetica", 7.5)
                for i, cell in enumerate(row):
                    c.drawString(MARGIN + i * col_w, y, str(cell)[:28])
                y -= 10
            y -= 8

        for note in section.notes:
            if y < MARGIN + 40:
                y = break_page()
            c.setFont("Helvetica-Oblique", 7.5)
            c.drawString(MARGIN, y, f"· {note[:150]}")
            y -= 10

        for block in section.explains:
            if y < MARGIN + 50:
                y = break_page()
            c.setFont("Helvetica-Oblique", 7.5)
            c.setFillColor(grey)
            c.drawString(MARGIN, y, f"Explain: {block.summary[:150]}")
            c.setFillColor(black)
            y -= 10

        y -= 8

    if report.warnings:
        if y < MARGIN + 60:
            y = break_page()
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, "Warnings / Avisos")
        y -= 12
        c.setFont("Helvetica", 7.5)
        for w in report.warnings:
            if y < MARGIN + 30:
                y = break_page()
                c.setFont("Helvetica", 7.5)
            c.drawString(MARGIN, y, f"· {w[:150]}")
            y -= 10

    _footer(c, report, page)
    c.showPage()
    c.save()
    return buffer.getvalue()


# --------------------------------------------------------------------------- HTML


def _esc(value: Any) -> str:
    return _html.escape(str(value))


def render_html(report: Report) -> str:
    watermark = report.effective_watermark()
    parts: list[str] = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{_esc(report.title)}</title>",
        "<style>",
        "body{font-family:Helvetica,Arial,sans-serif;color:#1a1a1a;margin:2rem;position:relative;}",
        "h1{font-size:1.4rem;margin-bottom:.2rem;}",
        "h2{font-size:1.05rem;border-bottom:1px solid #ccc;padding-bottom:.2rem;margin-top:1.6rem;}",
        "table{border-collapse:collapse;width:100%;margin:.5rem 0;font-size:.85rem;}",
        "th,td{border-bottom:1px solid #eee;text-align:left;padding:.25rem .4rem;}",
        ".kpi{display:flex;justify-content:space-between;padding:.15rem 0;font-size:.9rem;}",
        ".kpi b{font-weight:600;}",
        ".note{font-size:.78rem;color:#666;margin:.15rem 0;}",
        ".explain{font-size:.78rem;color:#555;font-style:italic;margin:.2rem 0;}",
        ".footer{margin-top:2rem;border-top:1px solid #ccc;padding-top:.5rem;font-size:.72rem;color:#777;}",
        (
            ".watermark{position:fixed;top:40%;left:10%;font-size:4rem;color:rgba(217,26,26,.14);"
            "transform:rotate(-20deg);font-weight:bold;z-index:-1;}"
        ),
        "</style></head><body>",
    ]
    if watermark:
        parts.append(f"<div class='watermark'>{_esc(watermark)}</div>")
    parts.append(f"<h1>{_esc(report.title)}</h1>")
    sub = f"Workspace: {_esc(report.workspace)}"
    if report.period:
        sub += f" &middot; Period: {_esc(report.period)}"
    parts.append(f"<p>{sub}</p>")

    for section in report.sections:
        parts.append(f"<h2>{_esc(section.title)}</h2>")
        for kpi in section.kpis:
            note = f"<div class='note'>{_esc(kpi.note)}</div>" if kpi.note else ""
            parts.append(
                f"<div class='kpi'><span>{_esc(kpi.label)}</span><b>{_esc(kpi.value)}</b></div>{note}"
            )
        for table in section.tables:
            parts.append(f"<p><strong>{_esc(table.title)}</strong></p><table><thead><tr>")
            parts.extend(f"<th>{_esc(c)}</th>" for c in table.columns)
            parts.append("</tr></thead><tbody>")
            for row in table.rows:
                parts.append("<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>")
            parts.append("</tbody></table>")
        for note in section.notes:
            parts.append(f"<div class='note'>&middot; {_esc(note)}</div>")
        for block in section.explains:
            parts.append(f"<div class='explain'>Explain: {_esc(block.summary)}</div>")

    if report.warnings:
        parts.append("<h2>Warnings / Avisos</h2>")
        for w in report.warnings:
            parts.append(f"<div class='note'>&middot; {_esc(w)}</div>")

    meta = f"Generated {_esc(report.generated_at)}"
    if report.rule_versions:
        meta += " &middot; rules: " + _esc(", ".join(report.rule_versions))
    parts.append(f"<div class='footer'>{_esc(FOOTER_LINE)}<br>{meta}</div>")
    parts.append("</body></html>")
    return "".join(parts)
