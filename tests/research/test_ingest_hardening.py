"""Path traversal / validate-before-write / server-side filename, and the SSRF guard, on
POST /api/research/ingest. No test here ever opens a real socket: ``socket.getaddrinfo`` is
monkeypatched and every transport is an ``httpx.MockTransport``."""

from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core import netguard
from aurum.core.config import settings
from aurum.research import router as research_router

HEX32 = 32


def _client() -> TestClient:
    return TestClient(create_app())


def _files_under(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()} if root.exists() else set()


# ------------------------------------------------------------------------------ path handling


def test_escaping_filename_lands_as_hex_name_under_the_collection():
    client = _client()
    data_dir = settings().data_dir
    resp = client.post(
        "/api/research/ingest",
        files={"file": ("../../escaped.txt", b"Articulo 1. Texto.", "text/plain")},
        data={"collection": "mx-law"},
    )
    assert resp.status_code == 200, resp.text
    assert not (data_dir / "escaped.txt").exists()
    assert not (data_dir.parent / "escaped.txt").exists()
    written = _files_under(data_dir / "corpus_sources" / "mx-law")
    assert len(written) == 1
    (only,) = written
    assert only.suffix == ".txt"
    assert len(only.stem) == HEX32 and all(c in "0123456789abcdef" for c in only.stem)
    assert resp.json()["title"] == "escaped.txt" if "title" in resp.json() else True


def test_escaping_collection_400_and_nothing_written():
    client = _client()
    data_dir = settings().data_dir
    before = _files_under(data_dir)
    resp = client.post(
        "/api/research/ingest",
        files={"file": ("x.txt", b"hola", "text/plain")},
        data={"collection": "../../etc"},
    )
    assert resp.status_code == 400
    assert _files_under(data_dir) == before


@pytest.mark.parametrize("collection", ["Mx-Law", "a b", "ws:", "ws:A", "-x", "x" * 70, "a/b"])
def test_bad_collection_ids_400(collection):
    resp = _client().post(
        "/api/research/ingest", files={"file": ("x.txt", b"hola", "text/plain")}, data={"collection": collection}
    )
    assert resp.status_code == 400, collection


def test_unsupported_type_400_before_any_write():
    client = _client()
    data_dir = settings().data_dir
    for name in ("x.exe", "noext", "deck.pptx"):
        resp = client.post(
            "/api/research/ingest", files={"file": (name, b"MZ....", "application/octet-stream")}, data={"collection": "mx-law"}
        )
        assert resp.status_code == 400, name
    assert _files_under(data_dir / "corpus_sources") == set()


def test_failed_ingest_unlinks_the_file(monkeypatch):
    client = _client()
    data_dir = settings().data_dir

    def boom(*_a, **_k):
        raise research_router.CorpusError("synthetic failure")

    monkeypatch.setattr(research_router.ingest_mod, "ingest_file", boom)
    resp = client.post(
        "/api/research/ingest", files={"file": ("x.txt", b"hola", "text/plain")}, data={"collection": "mx-law"}
    )
    assert resp.status_code == 400
    assert _files_under(data_dir / "corpus_sources") == set()


# ------------------------------------------------------------------------------ SSRF guard


@pytest.fixture
def no_network(monkeypatch):
    """DNS answers are synthetic and any real transport use fails the test."""
    table = {
        "public.example": "93.184.216.34",
        "evil.example": "127.0.0.1",
        "mapped.example": "::ffff:10.0.0.5",
        "cloud.example": "169.254.169.254",
    }

    def fake_getaddrinfo(host, port, *a, **k):
        if host not in table:
            raise socket.gaierror(f"no such host {host}")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def must_not_be_called(request):
        raise AssertionError(f"outbound request attempted: {request.url}")

    guard_transport = httpx.MockTransport(must_not_be_called)
    monkeypatch.setattr(research_router, "_fetch_transport", lambda: guard_transport)
    return table


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:5041/api/health",
        "http://169.254.169.254/latest/meta-data/",
        "http://host.docker.internal:11434",
        "http://api:5041/api/health",
        "http://localhost/x",
        "http://foo.localhost/x",
        "http://10.0.0.5/",
        "http://192.168.1.20/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
        "http://evil.example/",
        "http://mapped.example/",
        "http://cloud.example/",
        "ftp://x/",
        "file:///etc/passwd",
        "http://user:pw@public.example/",
        "gopher://public.example/",
    ],
)
def test_blocked_urls_400_without_outbound_call(no_network, url):
    resp = _client().post("/api/research/ingest", json={"url": url, "collection": "guidance"})
    assert resp.status_code == 400, url
    assert resp.json()["detail"] == "url_not_allowed"


def test_redirect_to_loopback_is_blocked(no_network, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
        raise AssertionError("followed the redirect into loopback")

    monkeypatch.setattr(research_router, "_fetch_transport", lambda: httpx.MockTransport(handler))
    resp = _client().post("/api/research/ingest", json={"url": "http://public.example/doc", "collection": "guidance"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "url_not_allowed"


def test_public_url_is_fetched_and_ingested(no_network, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "public.example"
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<h1>RMF regla 2.9.21</h1><p>Contenido.</p>")

    monkeypatch.setattr(research_router, "_fetch_transport", lambda: httpx.MockTransport(handler))
    resp = _client().post(
        "/api/research/ingest",
        json={"url": "http://public.example/rmf", "collection": "guidance", "trust_tier": "official_guidance"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ingested"


def test_private_fetch_opt_in_reaches_the_transport(no_network, monkeypatch):
    monkeypatch.setenv("AURUM_ALLOW_PRIVATE_FETCH", "1")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="Articulo 1. Texto de la NAS.")

    monkeypatch.setattr(research_router, "_fetch_transport", lambda: httpx.MockTransport(handler))
    resp = _client().post("/api/research/ingest", json={"url": "http://10.0.0.5/doc.txt", "collection": "guidance"})
    assert resp.status_code == 200, resp.text
    assert seen == ["http://10.0.0.5/doc.txt"]
    # the host-name rules still apply even when private addresses are allowed
    resp = _client().post("/api/research/ingest", json={"url": "http://localhost/doc.txt", "collection": "guidance"})
    assert resp.status_code == 400


def test_oversized_body_400_fetch_too_large(no_network, monkeypatch):
    monkeypatch.setenv("AURUM_FETCH_MAX_MB", "1")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"x" * (20 * 1024 * 1024))

    monkeypatch.setattr(research_router, "_fetch_transport", lambda: httpx.MockTransport(handler))
    resp = _client().post("/api/research/ingest", json={"url": "http://public.example/big", "collection": "guidance"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "fetch_too_large"


def test_netguard_unit_rules(no_network):
    assert netguard.address_is_public(netguard.ipaddress.ip_address("93.184.216.34"))
    for bad in ("127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.0.1", "169.254.169.254", "::1", "::ffff:192.168.0.1", "0.0.0.0", "224.0.0.1", "fe80::1", "fc00::1"):
        assert not netguard.address_is_public(netguard.ipaddress.ip_address(bad)), bad
    with pytest.raises(netguard.FetchBlocked):
        netguard.check_url("http://unknown.example/")  # unresolvable → blocked, not 500
    netguard.check_url("https://public.example/x")
