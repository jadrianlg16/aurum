from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

SAMPLE_LINES = [
    "REPORTE DE CREDITO ESPECIAL",
    "NOMBRE: JUAN PEREZ GARCIA",
    "SCORE: 720",
    "",
    "OTORGANTE: BANCO XYZ SA",
    "TIPO DE CUENTA: TARJETA DE CREDITO",
    "LIMITE DE CREDITO: $50,000.00",
    "SALDO ACTUAL: $12,345.00",
    "ESTATUS DE CUENTA: AL CORRIENTE",
    "FECHA DE APERTURA: 15/03/2020",
    "",
    "OTORGANTE: FINANCIERA ABC",
    "TIPO DE CUENTA: CREDITO PERSONAL",
    "LIMITE DE CREDITO: $20,000.00",
    "SALDO ACTUAL: $5,000.00",
    "ESTATUS DE CUENTA: AL CORRIENTE",
    "FECHA DE APERTURA: 01/06/2021",
]


def _make_pdf(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter
    y = height - 50
    for line in lines:
        c.drawString(50, y, line)
        y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture
def sample_report_pdf() -> bytes:
    return _make_pdf(SAMPLE_LINES)


@pytest.fixture
def blank_pdf() -> bytes:
    return _make_pdf(["This is not a Buro report at all."])


@pytest.fixture
def client() -> TestClient:
    from aurum.api.app import create_app

    return TestClient(create_app())
