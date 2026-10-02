"""CFDI zip caps are enforced while streaming (a deflate bomb never lands in memory)."""

from __future__ import annotations

import io
import tracemalloc
import zipfile

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.workspaces import Workspace, save_workspace
from aurum.ingest.cfdi import CFDIParseError, ZipTooLarge, parse_upload
from tests.ingest.cfdi_builder import RFC_EMISOR, build_ingreso_pue_xml, build_pago_xml


def _bomb(size_mb: int = 30) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.xml", b" " * (size_mb * 1024 * 1024))
    return buf.getvalue()


def _many(n: int = 600) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(n):
            zf.writestr(f"{i}.xml", b"<x/>")
    return buf.getvalue()


def _good() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.xml", build_ingreso_pue_xml())
        zf.writestr("sub/b.xml", build_pago_xml())
        zf.writestr("readme.txt", "not xml")
    return buf.getvalue()


def test_member_cap_streams_and_stays_small(monkeypatch):
    monkeypatch.setenv("AURUM_ZIP_MAX_MEMBER_MB", "1")
    bomb = _bomb(30)
    assert len(bomb) < 100 * 1024  # ~30 KB compressed
    tracemalloc.start()
    try:
        with pytest.raises(ZipTooLarge):
            parse_upload("bomb.zip", bomb, RFC_EMISOR)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 5 * 1024 * 1024, peak


def test_total_cap(monkeypatch):
    monkeypatch.setenv("AURUM_ZIP_MAX_MEMBER_MB", "3")
    monkeypatch.setenv("AURUM_ZIP_MAX_TOTAL_MB", "4")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(3):
            zf.writestr(f"{i}.xml", build_ingreso_pue_xml() + b" " * (2 * 1024 * 1024))  # valid XML, padded
    with pytest.raises(ZipTooLarge):
        parse_upload("x.zip", buf.getvalue(), RFC_EMISOR)


def test_member_count_cap():
    with pytest.raises(ZipTooLarge):
        parse_upload("many.zip", _many(600), RFC_EMISOR)


def test_unsafe_member_names_rejected():
    for name in ("../evil.xml", "/abs.xml", "C:\\win.xml"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(name, b"<x/>")
        with pytest.raises(CFDIParseError):
            parse_upload("x.zip", buf.getvalue(), RFC_EMISOR)


def test_normal_zip_still_parses():
    docs = parse_upload("cfdis.zip", _good(), RFC_EMISOR)
    assert len(docs) == 2
    assert {d.tipo for d in docs} == {"I", "P"}


def test_api_maps_zip_too_large_to_413(monkeypatch):
    monkeypatch.setenv("AURUM_ZIP_MAX_MEMBER_MB", "1")
    save_workspace(Workspace(id="zip-ws", name="Zip", base_currency="MXN"))
    client = TestClient(create_app())
    resp = client.post("/api/ingest/zip-ws/cfdi", files={"file": ("bomb.zip", _bomb(30), "application/zip")})
    assert resp.status_code == 413, resp.text
    assert resp.json() == {"detail": "zip too large after decompression"}
