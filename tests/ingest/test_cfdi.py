from decimal import Decimal

import pytest

from aurum.ingest.cfdi import CFDIParseError, parse_cfdi_xml, parse_upload
from tests.ingest.cfdi_builder import RFC_EMISOR, RFC_RECEPTOR, build_ingreso_pue_xml, build_pago_xml


def test_parse_ingreso_pue():
    xml = build_ingreso_pue_xml()
    doc = parse_cfdi_xml(xml, workspace_rfc=RFC_EMISOR)
    assert doc.uuid == "AAAAAAAA-1111-2222-3333-444444444444"
    assert doc.tipo == "I"
    assert doc.direction == "emitido"
    assert doc.emisor_rfc == RFC_EMISOR
    assert doc.receptor_rfc == RFC_RECEPTOR
    assert doc.subtotal == Decimal("1000.00")
    assert doc.total == Decimal("1160.00")
    assert doc.iva_trasladado == Decimal("160.00")
    assert doc.metodo_pago == "PUE"
    assert len(doc.conceptos) == 1
    assert doc.conceptos[0]["clave_prod_serv"] == "80131500"


def test_direction_recibido_when_workspace_is_receptor():
    xml = build_ingreso_pue_xml()
    doc = parse_cfdi_xml(xml, workspace_rfc=RFC_RECEPTOR)
    assert doc.direction == "recibido"


def test_parse_pago_complement():
    xml = build_pago_xml()
    doc = parse_cfdi_xml(xml, workspace_rfc=RFC_RECEPTOR)
    assert doc.tipo == "P"
    assert len(doc.pagos) == 1
    pago = doc.pagos[0]
    assert pago.monto == Decimal("1160.00")
    assert pago.uuid_relacionado == "CCCCCCCC-1111-2222-3333-444444444444"
    assert pago.imp_pagado == Decimal("1160.00")
    assert pago.fecha_pago.isoformat() == "2026-09-01T00:00:00"


def test_malformed_xml_raises():
    with pytest.raises(CFDIParseError):
        parse_cfdi_xml(b"<not-a-cfdi/>", workspace_rfc=RFC_EMISOR)


def test_missing_timbre_raises():
    xml = build_ingreso_pue_xml().decode().replace(
        '<tfd:TimbreFiscalDigital Version="1.1" UUID="AAAAAAAA-1111-2222-3333-444444444444" FechaTimbrado="2026-08-15T10:00:00"\n        SelloCFD="x" NoCertificadoSAT="00000000000000000000" SelloSAT="x" RfcProvCertif="SAT970701NN3"/>',
        "",
    ).encode()
    with pytest.raises(CFDIParseError):
        parse_cfdi_xml(xml, workspace_rfc=RFC_EMISOR)


def test_parse_upload_zip(tmp_path):
    import zipfile

    zip_path = tmp_path / "cfdis.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.xml", build_ingreso_pue_xml())
        zf.writestr("b.xml", build_pago_xml())
        zf.writestr("readme.txt", "not xml")
    docs = parse_upload("cfdis.zip", zip_path.read_bytes(), RFC_EMISOR)
    assert len(docs) == 2
    assert {d.tipo for d in docs} == {"I", "P"}


def test_parse_upload_single_xml():
    docs = parse_upload("one.xml", build_ingreso_pue_xml(), RFC_EMISOR)
    assert len(docs) == 1
