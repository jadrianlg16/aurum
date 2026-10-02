"""Keyword receipt reader (aurum/ingest/receipt_parse.py) on synthetic OCR text — how much, when,
where and what. Texts imitate what Tesseract returns for Mexican tickets (split columns, O/0 swaps,
folded accents, noise lines)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from aurum.ingest.receipt_parse import amounts_in, read_receipt

TODAY = date(2026, 9, 23)

OXXO = """OXXO
CADENA COMERCIAL OXXO SA DE CV
RFC XAXX010101000
SUC. CENTRO 0001
FECHA: 21/09/2026 18:42
TICKET 004512
1COCACOLAGOOML 22.00
1 SABRITAS ORIGINAL 19.50
2GALLETAS EMPERADOR 38.00
SUBTOTAL 68.53
IVA 16% 10.97
TOTAL 79.50
EFECTIVO 100.00
CAMBIO 20.50
GRACIAS POR SU COMPRA"""

GAS = """ESTACION DE SERVICIO 5421
GASOLINERA LOS PINOS SA DE CV
Av. Constitución 200 Col. Centro
Fecha 20-09-2026 07:15
Bomba 3 Despachador: JUAN
Producto MAGNA
Litros 32.450
Precio 23.49
Importe
762.25
Forma de pago: TARJETA DEBITO 762.25"""

RESTAURANT = """La Nacional
Restaurante - Bar
Mesa 12 Mesero: Pedro Comensales 4
2 Tacos al pastor 180.00
1 Agua de horchata 45.00
Subtotal 450.00
IVA 72.00
Total 522.00
Propina sugerida 10% 52.20
Total con propina 574.20
12 SEP 2026"""

CARD_SLIP = """BBVA
VENTA
COMERCIO: TAQUERIA EL GUERO
AFILIACION 1234567
TARJETA ************4321
IMPORTE $ 1,245.50 MXN
AUTORIZACION 654321
15/09/26"""

PHARMACY = """FARMACIAS GUADALAJARA
RFC FGU830930PD3
PARACETAMOL 500MG TABLETAS 45.00
T0TAL $ 45.00
TARJETA 45.00
2026-09-18"""

NO_TOTAL_WORD = """PAPELERIA LA ESTRELLA
CUADERNO 35.00
PLUMAS 18.50
53.50"""


def test_amounts_in_handles_separators() -> None:
    assert amounts_in("TOTAL 1,245.50") == [Decimal("1245.50")]
    assert amounts_in("TOTAL 79,50") == [Decimal("79.50")]
    assert amounts_in("TOTAL 1.234,56") == [Decimal("1234.56")]
    assert amounts_in("TOTAL $ 80") == [Decimal("80")]
    assert amounts_in("LITROS 32.450") == []  # three decimals is not money


def test_oxxo_total_date_merchant_category() -> None:
    r = read_receipt(OXXO, TODAY)
    assert r.amount is not None and r.amount.value == Decimal("79.50")
    assert r.amount.confidence == "high"
    assert "subtotal_iva" in r.amount.checks  # 68.53 + 10.97 = 79.50
    assert r.date is not None and r.date.value == date(2026, 9, 21) and r.date.confidence == "high"
    assert r.merchant is not None and r.merchant.name == "OXXO" and r.merchant.source == "known"
    assert r.merchant.category == "Súper"


def test_gas_station_amount_on_next_line_and_keywords() -> None:
    r = read_receipt(GAS, TODAY)
    assert r.amount is not None and r.amount.value == Decimal("762.25")
    assert "card_match" in r.amount.checks
    assert r.date is not None and r.date.value == date(2026, 9, 20)
    assert r.category is not None and r.category.name == "Transporte/Gasolina"
    assert "MAGNA" in r.category.words
    assert r.merchant is not None and r.merchant.source == "header"
    assert "Gasolinera Los Pinos" in r.merchant.name  # company suffix dropped


def test_restaurant_prefers_total_with_tip_and_month_name_date() -> None:
    r = read_receipt(RESTAURANT, TODAY)
    assert r.amount is not None and r.amount.value == Decimal("574.20")
    assert r.date is not None and r.date.value == date(2026, 9, 12)
    assert r.category is not None and r.category.name == "Comida fuera"
    assert r.merchant is not None and r.merchant.name == "La Nacional"


def test_card_slip_importe_two_digit_year_and_currency() -> None:
    r = read_receipt(CARD_SLIP, TODAY)
    assert r.amount is not None and r.amount.value == Decimal("1245.50")
    assert r.currency == "MXN"
    assert r.date is not None and r.date.value == date(2026, 9, 15)
    assert r.category is not None and r.category.name == "Comida fuera"  # TAQUERIA
    assert r.merchant is not None and r.merchant.name == "Taqueria El Guero"  # COMERCIO:, not the bank


def test_pharmacy_ocr_zero_in_total_and_iso_date() -> None:
    r = read_receipt(PHARMACY, TODAY)
    assert r.amount is not None and r.amount.value == Decimal("45.00")
    assert r.merchant is not None and r.merchant.name == "Farmacias Guadalajara"
    assert r.merchant.category == "Medicinas"
    assert r.date is not None and r.date.value == date(2026, 9, 18)


def test_no_keyword_falls_back_to_largest_with_low_confidence() -> None:
    r = read_receipt(NO_TOTAL_WORD, TODAY)
    assert r.amount is not None and r.amount.value == Decimal("53.50")
    assert r.amount.confidence == "low" and r.amount.reason == "largest"


def test_future_and_ancient_dates_are_ignored() -> None:
    r = read_receipt("TOTAL 10.00\nFECHA 01/01/2031\nFECHA 01/01/2019", TODAY)
    assert r.date is None


def test_us_receipt_month_first_when_not_day_first() -> None:
    r = read_receipt("TARGET\nTOTAL 23.10 USD\n09/05/2026", TODAY, day_first=False)
    assert r.date is not None and r.date.value == date(2026, 9, 5)
    assert r.currency == "USD"


def test_empty_text_reads_nothing() -> None:
    r = read_receipt("", TODAY)
    assert r.amount is None and r.date is None and r.merchant is None and r.category is None
