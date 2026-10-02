"""Merchant normalization table — the behavior the whole detector rests on."""

from __future__ import annotations

import pytest

from aurum.organizer import normalize

# raw bank/ledger description -> normalized merchant
CASES: list[tuple[str, str]] = [
    ("NETFLIX.COM 866-579-7172 CIUDAD DE MEX", "NETFLIX"),
    ("SPEI ENVIADO TELCEL 0341", "TELCEL"),
    ("PAGO TARJETA BBVA 4152******1234", "BBVA"),
    ("CFE SSC 9876543210", "CFE"),
    ("AMAZON PRIME*2X4Y5 MX", "AMAZON PRIME"),
    ("SPOTIFY P0A1B2C3 MX", "SPOTIFY"),
    ("APPLE.COM/BILL ICLOUD 800-676-2775", "ICLOUD"),
    ("SMART FIT CENTRO SUC 0001", "SMART FIT"),
    ("compra en TOTALPLAY SERVICIOS 55123", "TOTALPLAY"),
    ("DOMICILIACION IZZI TELECOM REF 99881", "IZZI"),
    ("CARGO RECURRENTE YOUTUBE PREMIUM MX", "YOUTUBE PREMIUM"),
    ("HBO MAX HELP.MAX.COM", "MAX"),
    ("DISNEY PLUS MX 5566", "DISNEY+"),
    ("PAGO SERVICIO AGUA Y DRENAJE CDMX", "AGUA Y DRENAJE"),
    ("GAS NATURAL FENOSA 00123", "GAS NATURAL"),
    ("MICROSOFT 365 *G9K2L MSFT.COM", "MICROSOFT 365"),
    ("ADOBE  *CREATIVE CLOUD 408-536-6000", "ADOBE"),
    ("OPENAI *CHATGPT SUBSCR", "OPENAI"),
    ("UBER ONE MX HELP.UBER.COM", "UBER ONE"),
    ("PAGO RENTA DEPARTAMENTO 12B", "RENTA"),
    ("INFONAVIT CREDITO 2938471", "INFONAVIT"),
    ("SEGUROS GNP POLIZA 5512", "GNP"),
    ("DEPOSITO NOMINA ACME SA DE CV", "NOMINA ACME"),
    ("CARGO CREDITO AUTOMOTRIZ BBVA", "CREDITO AUTOMOTRIZ"),
    ("PANADERIA LA ESPIGA 4471 CDMX", "PANADERIA LA ESPIGA"),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_normalize_table(raw: str, expected: str) -> None:
    assert normalize.normalize(raw) == expected


def test_table_is_large_enough() -> None:
    assert len(CASES) >= 15


def test_normalization_is_idempotent() -> None:
    for raw, expected in CASES:
        assert normalize.normalize(normalize.normalize(raw)) == expected


def test_classify_carries_category_and_defaults() -> None:
    netflix = normalize.classify("NETFLIX.COM 866-579-7172 CIUDAD DE MEX")
    assert netflix["category_hint"] == "streaming"
    assert netflix["kind"] == "subscription"
    assert netflix["essential"] == "wants"

    cfe = normalize.classify("CFE SSC 9876543210")
    assert cfe["category_hint"] == "utility"
    assert cfe["kind"] == "utility"
    assert cfe["essential"] == "needs"


def test_unknown_merchant_keeps_clean_tokens_without_a_hint() -> None:
    info = normalize.classify("PANADERIA LA ESPIGA 4471 MEXICO")
    assert info["merchant"] == "PANADERIA LA ESPIGA"
    assert info["category_hint"] is None


def test_accents_and_case_are_normalized() -> None:
    assert normalize.normalize("cargo teléfono TELCEL") == "TELCEL"


def test_empty_description_does_not_raise() -> None:
    assert normalize.normalize("") == ""
