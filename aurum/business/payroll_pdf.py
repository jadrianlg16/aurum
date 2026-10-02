"""Bilingual DRAFT payroll PDF (reportlab). Never transmitted, never a CFDI de nómina.

Same posture as :mod:`aurum.tax.draft_pdf`: watermarked, bilingual, informational. Employee names and
RFCs arrive already masked from :mod:`aurum.business.payroll`, so the PDF carries no unmasked PII.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.colors import Color, black, grey
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas as pdf_canvas

WIDTH, HEIGHT = LETTER
MARGIN = 54
WATERMARK = "NÓMINA — BORRADOR · DRAFT"
FOOTER_ES = "Borrador. Aurum no timbra CFDI de nómina ni transmite nada al SAT o al IMSS."
FOOTER_EN = "Draft. Aurum does not stamp payroll CFDIs and transmits nothing to SAT or IMSS."

TOTAL_LABELS: list[tuple[str, str, str]] = [
    ("gross", "Percepciones brutas", "Gross wages"),
    ("isr", "ISR retenido", "Income tax withheld"),
    ("imss_employee", "Cuotas obreras IMSS", "Employee social security"),
    ("net", "Neto a pagar", "Net pay"),
    ("imss_employer", "Cuotas patronales IMSS", "Employer social security"),
    ("infonavit", "Aportaciones INFONAVIT", "Employer housing fund"),
    ("isn", "ISN Nuevo León", "Nuevo León payroll tax"),
    ("employer_cost", "Costo patronal total", "Total employer cost"),
]


def _money(amount: dict[str, Any] | None) -> str:
    if not amount:
        return "—"
    return f"{amount.get('amount', '0.00')} {amount.get('currency', 'MXN')}"


def _watermark(c: pdf_canvas.Canvas) -> None:
    c.saveState()
    c.setFillColor(Color(0.85, 0.1, 0.1, alpha=0.14))
    c.setFont("Helvetica-Bold", 40)
    c.translate(WIDTH / 2, HEIGHT / 2)
    c.rotate(38)
    c.drawCentredString(0, 0, WATERMARK)
    c.restoreState()


def _footer(c: pdf_canvas.Canvas) -> None:
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(grey)
    c.drawString(MARGIN, 42, FOOTER_ES)
    c.drawString(MARGIN, 32, FOOTER_EN)
    c.setFillColor(black)


def _page_break(c: pdf_canvas.Canvas) -> float:
    _footer(c)
    c.showPage()
    _watermark(c)
    return HEIGHT - MARGIN


def render(payload: dict[str, Any]) -> bytes:
    """``payload`` is a :func:`aurum.business.payroll.run_payroll` result."""
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=LETTER)
    period = payload.get("period", "")
    c.setTitle(f"Aurum nómina BORRADOR {payload.get('workspace', '')} {period}")
    _watermark(c)

    y = HEIGHT - MARGIN
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN, y, f"Nómina {period} — borrador / Payroll draft")
    y -= 18
    c.setFont("Helvetica", 9)
    c.setFillColor(grey)
    c.drawString(
        MARGIN,
        y,
        f"Workspace {payload.get('workspace', '')} · {payload.get('employees', 0)} empleado(s) · "
        f"{payload.get('days', '')} días · {payload.get('currency', 'MXN')}",
    )
    c.setFillColor(black)
    y -= 24

    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "Totales / Totals")
    y -= 14
    totals = payload.get("totals", {})
    c.setFont("Helvetica", 9)
    for key, es, en in TOTAL_LABELS:
        if y < 110:
            y = _page_break(c)
        c.drawString(MARGIN, y, f"{es} / {en}")
        c.drawRightString(WIDTH - MARGIN, y, _money(totals.get(key)))
        y -= 13
    y -= 10

    c.setFont("Helvetica-Bold", 11)
    if y < 130:
        y = _page_break(c)
    c.drawString(MARGIN, y, "Por empleado / Per employee")
    y -= 14
    c.setFont("Helvetica-Bold", 8)
    columns = [
        (MARGIN, "Empleado / Employee"),
        (MARGIN + 150, "Bruto"),
        (MARGIN + 225, "ISR"),
        (MARGIN + 290, "IMSS obr."),
        (MARGIN + 365, "Neto"),
        (MARGIN + 440, "Costo patronal"),
    ]
    for x, label in columns:
        c.drawString(x, y, label)
    y -= 11
    c.setFont("Helvetica", 8)
    for line in payload.get("lines", []):
        if y < 100:
            y = _page_break(c)
        employer_cost = (
            f"{line.get('imss_employer', {}).get('amount', '0')} + "
            f"{line.get('infonavit', {}).get('amount', '0')}"
        )
        cells = [
            (MARGIN, f"{line.get('name', '')} · {line.get('rfc') or ''}"),
            (MARGIN + 150, line.get("gross", {}).get("amount", "")),
            (MARGIN + 225, line.get("isr_retenido", {}).get("amount", "")),
            (MARGIN + 290, line.get("imss_employee", {}).get("amount", "")),
            (MARGIN + 365, line.get("net", {}).get("amount", "")),
            (MARGIN + 440, employer_cost),
        ]
        for x, text in cells:
            c.drawString(x, y, str(text))
        y -= 11

    y -= 12
    warnings = payload.get("warnings", [])
    if warnings:
        if y < 120:
            y = _page_break(c)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, "Avisos / Warnings")
        y -= 13
        c.setFont("Helvetica", 8)
        for warning in warnings:
            if y < 90:
                y = _page_break(c)
            for chunk in _wrap(warning, 110):
                c.drawString(MARGIN, y, chunk)
                y -= 10

    explain = payload.get("explain", {})
    if explain.get("rule_versions"):
        if y < 90:
            y = _page_break(c)
        y -= 6
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(grey)
        c.drawString(MARGIN, y, "Reglas: " + ", ".join(explain["rule_versions"]))
        c.setFillColor(black)

    _footer(c)
    c.showPage()
    c.save()
    return buffer.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]
