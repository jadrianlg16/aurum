"""DRAFT US tax organizer (reportlab) — a summary sheet for a preparer, never a return.

Same posture as ``aurum/tax/draft_pdf.py``: a red DRAFT watermark on every page and a footer that says,
in both languages, that Aurum neither files nor signs. The organizer summarises Schedule C, SE tax,
income tax and the quarterly estimate, then lists the constants that are still unverified.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.colors import Color, black, grey
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas as pdf_canvas

WIDTH, HEIGHT = LETTER
MARGIN = 54
WATERMARK = "DRAFT · BORRADOR"
HEADLINE = "For your preparer — this is not a tax return."
FOOTER_EN = "Draft organizer. Aurum never files, signs or transmits anything to the IRS."
FOOTER_ES = "Borrador. Aurum nunca presenta, firma ni transmite nada ante el IRS."

ROWS: list[tuple[str, str, str]] = [
    ("schedule_c.gross_receipts", "Gross receipts (Sch. C line 1)", "Ingresos brutos"),
    ("schedule_c.returns_and_allowances", "Returns and allowances (line 2)", "Devoluciones y descuentos"),
    ("schedule_c.cost_of_goods_sold", "Cost of goods sold (line 4)", "Costo de lo vendido"),
    ("schedule_c.expenses", "Total expenses (line 28)", "Gastos totales"),
    ("schedule_c.net", "Net profit or loss (line 31)", "Utilidad o pérdida neta"),
    ("se_tax.value", "Self-employment tax (Sch. SE)", "Impuesto por cuenta propia"),
    ("se_tax.deductible_half", "Deductible half of SE tax (§ 164(f))", "Mitad deducible"),
    ("income_tax.value", "Federal income tax (§ 1)", "ISR federal"),
    ("total_tax", "Total federal tax", "Impuesto federal total"),
    ("quarterly.amount_each", "Each quarterly installment (§ 6654)", "Cada pago estimado trimestral"),
]


def _dig(payload: dict[str, Any], path: str) -> Any:
    node: Any = payload
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _money(amount: Any) -> str:
    if not isinstance(amount, dict):
        return "—"
    return f"{amount.get('amount', '0.00')} {amount.get('currency', 'USD')}"


def _watermark(c: pdf_canvas.Canvas) -> None:
    c.saveState()
    c.setFillColor(Color(0.85, 0.1, 0.1, alpha=0.14))
    c.setFont("Helvetica-Bold", 60)
    c.translate(WIDTH / 2, HEIGHT / 2)
    c.rotate(38)
    c.drawCentredString(0, 0, WATERMARK)
    c.restoreState()
    c.setFillColor(black)


def _footer(c: pdf_canvas.Canvas) -> None:
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(grey)
    c.drawCentredString(WIDTH / 2, MARGIN - 22, FOOTER_EN)
    c.drawCentredString(WIDTH / 2, MARGIN - 32, FOOTER_ES)
    c.setFillColor(black)


class _Page:
    """Cursor that starts a new watermarked page whenever the content runs off the bottom."""

    def __init__(self, c: pdf_canvas.Canvas) -> None:
        self.c = c
        self.y = HEIGHT - MARGIN

    def space(self, needed: float = 16) -> None:
        if self.y - needed < MARGIN + 50:
            _footer(self.c)
            self.c.showPage()
            _watermark(self.c)
            self.y = HEIGHT - MARGIN

    def heading(self, text: str) -> None:
        self.space(34)
        self.y -= 12
        self.c.setFont("Helvetica-Bold", 11)
        self.c.drawString(MARGIN, self.y, text)
        self.y -= 6
        self.c.setStrokeColor(grey)
        self.c.line(MARGIN, self.y, WIDTH - MARGIN, self.y)
        self.y -= 16

    def row(self, left: str, sub: str, right: str, bold: bool = False) -> None:
        self.space()
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        self.c.drawString(MARGIN, self.y, left)
        if sub:
            self.c.setFillColor(grey)
            self.c.setFont("Helvetica-Oblique", 8)
            self.c.drawString(MARGIN + 230, self.y, sub)
            self.c.setFillColor(black)
        self.c.setFont("Helvetica-Bold", 10)
        self.c.drawRightString(WIDTH - MARGIN, self.y, right)
        self.y -= 15

    def note(self, text: str, size: int = 8) -> None:
        self.space(12)
        self.c.setFont("Helvetica", size)
        self.c.drawString(MARGIN, self.y, text[:150])
        self.y -= 11


def render(payload: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=LETTER)
    c.setTitle(f"Aurum US organizer DRAFT {payload.get('workspace', '')} {payload.get('year', '')}")
    _watermark(c)
    page = _Page(c)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN, page.y, "US tax organizer · Organizador fiscal EE. UU.")
    page.y -= 18
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(Color(0.7, 0.1, 0.1))
    c.drawString(MARGIN, page.y, HEADLINE)
    c.setFillColor(black)
    page.y -= 16
    c.setFont("Helvetica", 10)
    profile = payload.get("profile") or {}
    c.drawString(
        MARGIN,
        page.y,
        f"Year: {payload.get('year', '')}    Workspace: {payload.get('workspace', '')}    "
        f"Filing status: {profile.get('filing_status', '')}    "
        f"Entity: {profile.get('entity_type', '')}    State: {profile.get('state', '')}",
    )
    page.y -= 10

    if not payload.get("applicable", False):
        page.heading("Not applicable")
        page.note(str(payload.get("reason", "")), size=10)
        _footer(c)
        c.showPage()
        c.save()
        return buffer.getvalue()

    page.heading("Figures / Cifras")
    for path, en, es in ROWS:
        page.row(en, es, _money(_dig(payload, path)))

    breakdown = _dig(payload, "schedule_c.expenses_by_account") or {}
    if breakdown:
        page.heading("Expense breakdown / Desglose de gastos")
        for account, amount in breakdown.items():
            page.row(account, "", _money(amount))

    income = _dig(payload, "schedule_c.income_by_account") or {}
    if income:
        page.heading("Income accounts / Cuentas de ingreso")
        for account, amount in income.items():
            page.row(account, "", _money(amount))

    page.heading("Quarterly estimates / Pagos estimados")
    each = _money(_dig(payload, "quarterly.amount_each"))
    for due in _dig(payload, "quarterly.due_dates") or []:
        page.row(f"Due {due}", "", each)

    page.heading("How each figure was reached / Cómo se obtuvo cada cifra")
    for section in ("schedule_c", "se_tax", "income_tax", "quarterly"):
        explain = _dig(payload, f"{section}.explain") or {}
        if explain.get("summary"):
            page.note(f"{section}: {explain['summary']}")
        for citation in explain.get("citations", [])[:3]:
            page.note(f"    cite: {citation.get('law', '')} {citation.get('article', '')}", size=7)

    unverified = payload.get("unverified_constants") or []
    if unverified:
        page.heading("Constants still marked (verify)")
        for key in unverified:
            page.note(f"· {key}")

    warnings = payload.get("warnings") or []
    if warnings:
        page.heading("Warnings / Avisos")
        for warning in warnings:
            page.note(f"· {warning}")

    page.heading("Disclaimer")
    disclaimer = str(payload.get("disclaimer", ""))
    for chunk in (disclaimer[i : i + 110] for i in range(0, len(disclaimer), 110)):
        page.note(chunk)

    _footer(c)
    c.showPage()
    c.save()
    return buffer.getvalue()
