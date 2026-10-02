"""Bilingual DRAFT month-close PDF (reportlab). Never transmitted, never signed."""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.colors import Color, black, grey
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas as pdf_canvas

WIDTH, HEIGHT = LETTER
MARGIN = 54
WATERMARK = "BORRADOR · DRAFT"
FOOTER_ES = "Borrador. Aurum nunca transmite ni firma una declaración ante el SAT."
FOOTER_EN = "Draft. Aurum never transmits or signs a filing with the SAT."

LABELS: list[tuple[str, str, str]] = [
    ("income.collected", "Ingreso cobrado (sin IVA)", "Collected income (excl. VAT)"),
    ("isr.value", "ISR del mes (RESICO)", "Monthly income tax (RESICO)"),
    ("iva.trasladado", "IVA trasladado", "VAT charged"),
    ("iva.acreditable", "IVA acreditable", "VAT creditable"),
    ("iva.payable", "IVA a cargo", "VAT payable"),
    ("retentions.isr", "ISR retenido", "Income tax withheld"),
    ("retentions.iva", "IVA retenido", "VAT withheld"),
    ("prefill_expected.income", "Prellenado SAT: ingreso", "SAT prefill: income"),
    ("prefill_expected.isr", "Prellenado SAT: ISR", "SAT prefill: income tax"),
    ("prefill_expected.iva_acreditable", "Prellenado SAT: IVA acreditable", "SAT prefill: creditable VAT"),
]

DIFF_LABELS: dict[str, tuple[str, str]] = {
    "pue_not_collected": ("PUE facturado pero no cobrado", "PUE invoiced but never collected"),
    "ppd_missing_rep": ("PPD sin complemento de pago", "PPD with no payment complement"),
    "deposit_without_cfdi": ("Depósito sin CFDI", "Deposit with no CFDI"),
    "cash_paid_expense": ("Gasto pagado en efectivo", "Expense paid in cash"),
    "fixed_asset_iva": ("IVA de activo fijo", "Fixed-asset VAT"),
}


def _dig(payload: dict[str, Any], path: str) -> dict[str, Any] | None:
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


def _money(amount: dict[str, Any] | None) -> str:
    if not amount:
        return "—"
    return f"{amount.get('amount', '0.00')} {amount.get('currency', 'MXN')}"


def _watermark(c: pdf_canvas.Canvas) -> None:
    c.saveState()
    c.setFillColor(Color(0.85, 0.1, 0.1, alpha=0.14))
    c.setFont("Helvetica-Bold", 62)
    c.translate(WIDTH / 2, HEIGHT / 2)
    c.rotate(38)
    c.drawCentredString(0, 0, WATERMARK)
    c.restoreState()


def render(payload: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=LETTER)
    c.setTitle(f"Aurum DRAFT {payload.get('workspace', '')} {payload.get('period', '')}")
    _watermark(c)

    y = HEIGHT - MARGIN
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN, y, "Cierre mensual · Monthly close — RESICO persona física")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(
        MARGIN,
        y,
        f"Periodo / Period: {payload.get('period', '')}    "
        f"Espacio / Workspace: {payload.get('workspace', '')}    "
        f"Fecha límite / Deadline: {payload.get('deadline', '')}",
    )
    y -= 26

    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "Cifras / Figures")
    y -= 6
    c.setStrokeColor(grey)
    c.line(MARGIN, y, WIDTH - MARGIN, y)
    y -= 16
    for path, es, en in LABELS:
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, y, es)
        c.setFillColor(grey)
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(MARGIN + 200, y, en)
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(WIDTH - MARGIN, y, _money(_dig(payload, path)))
        y -= 15

    y -= 12
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "Diferencias contra el prellenado / Differences vs. the SAT prefill")
    y -= 6
    c.line(MARGIN, y, WIDTH - MARGIN, y)
    y -= 16
    diffs = payload.get("diffs") or []
    if not diffs:
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(MARGIN, y, "Sin diferencias / No differences.")
        y -= 15
    for diff in diffs:
        es, en = DIFF_LABELS.get(diff.get("kind", ""), (diff.get("kind", ""), diff.get("kind", "")))
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, y, es)
        c.setFillColor(grey)
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(MARGIN + 200, y, en)
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(WIDTH - MARGIN, y, _money(diff.get("amount")))
        y -= 13
        docs = diff.get("documents") or []
        if docs:
            c.setFont("Helvetica", 7)
            c.setFillColor(grey)
            c.drawString(MARGIN + 12, y, "CFDI: " + ", ".join(docs[:6]))
            c.setFillColor(black)
            y -= 13
        if y < MARGIN + 90:
            _page_break(c)
            y = HEIGHT - MARGIN

    y -= 12
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "Avisos / Warnings")
    y -= 14
    c.setFont("Helvetica", 8)
    for warning in payload.get("warnings") or []:
        c.drawString(MARGIN, y, f"· {warning[:150]}")
        y -= 11
        if y < MARGIN + 60:
            _page_break(c)
            y = HEIGHT - MARGIN

    _footer(c)
    c.showPage()
    c.save()
    return buffer.getvalue()


def _page_break(c: pdf_canvas.Canvas) -> None:
    _footer(c)
    c.showPage()
    _watermark(c)
    c.setFillColor(black)


def _footer(c: pdf_canvas.Canvas) -> None:
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(grey)
    c.drawCentredString(WIDTH / 2, MARGIN - 22, FOOTER_ES)
    c.drawCentredString(WIDTH / 2, MARGIN - 32, FOOTER_EN)
    c.setFillColor(black)
