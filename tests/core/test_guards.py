"""aurum.core.guards.HostOriginGuard — the Host/Origin/path acceptance cases.

These tests clear ``AURUM_ALLOWED_HOSTS`` (conftest sets it to ``testserver`` for everybody else) and
send explicit ``Host`` headers.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.guards import host_allowed, normalize_host, origin_allowed, path_is_safe

WS = {"id": "guard-ws", "name": "Guard", "kind": "personal", "country": "MX"}


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AURUM_ALLOWED_HOSTS", raising=False)
    return TestClient(create_app())


def test_same_origin_post_passes_guard(client):
    resp = client.post("/api/workspaces", json=WS, headers={"Host": "localhost", "Origin": "http://localhost"})
    assert resp.status_code not in (401, 403), resp.text
    assert resp.status_code == 200


def test_same_origin_with_port_passes(client):
    resp = client.post(
        "/api/workspaces", json=WS, headers={"Host": "localhost:5024", "Origin": "http://localhost:5024"}
    )
    assert resp.status_code == 200


def test_origin_port_is_significant(client):
    resp = client.post(
        "/api/workspaces", json=WS, headers={"Host": "localhost:5024", "Origin": "http://localhost:3000"}
    )
    assert resp.status_code == 403
    assert resp.json() == {"error": "origin_not_allowed"}


def test_cross_origin_post_403(client):
    resp = client.post("/api/workspaces", json=WS, headers={"Host": "localhost", "Origin": "http://evil.example"})
    assert resp.status_code == 403
    assert resp.json() == {"error": "origin_not_allowed"}


def test_origin_null_403(client):
    resp = client.post("/api/workspaces", json=WS, headers={"Host": "localhost", "Origin": "null"})
    assert resp.status_code == 403


def test_sec_fetch_site_cross_site_403(client):
    resp = client.post(
        "/api/workspaces",
        content=b"x",
        headers={"Host": "localhost", "Content-Type": "text/plain", "Sec-Fetch-Site": "cross-site"},
    )
    assert resp.status_code == 403
    assert resp.json() == {"error": "origin_not_allowed"}


def test_get_with_foreign_origin_passes_guard(client):
    # Reads are not CSRF; the browser cannot read the response without CORS anyway.
    resp = client.get("/api/workspaces", headers={"Host": "localhost", "Origin": "http://evil.example"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


def test_rebinding_host_403_without_token(client):
    resp = client.get("/api/workspaces", headers={"Host": "attacker.example"})
    assert resp.status_code == 403
    assert resp.json() == {"error": "host_not_allowed"}


def test_allowed_hosts_env_admits_the_host(monkeypatch):
    monkeypatch.setenv("AURUM_ALLOWED_HOSTS", "attacker.example")
    resp = TestClient(create_app()).get("/api/workspaces", headers={"Host": "attacker.example"})
    assert resp.status_code == 200


def test_lan_host_with_bearer_200_when_token_required(monkeypatch, client):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    resp = client.get(
        "/api/workspaces", headers={"Host": "192.168.1.20", "Authorization": "Bearer s3cr3t"}
    )
    assert resp.status_code == 200
    # ...but the bearer never overrides the Origin check
    resp = client.post(
        "/api/workspaces",
        json=WS,
        headers={"Host": "192.168.1.20", "Authorization": "Bearer s3cr3t", "Origin": "http://evil.example"},
    )
    assert resp.status_code == 403
    assert resp.json() == {"error": "origin_not_allowed"}


def test_token_required_and_allowed_hosts_set_still_checks_host(monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    monkeypatch.setenv("AURUM_ALLOWED_HOSTS", "good.example")
    c = TestClient(create_app())
    ok = c.get("/api/workspaces", headers={"Host": "good.example", "Authorization": "Bearer s3cr3t"})
    assert ok.status_code == 200
    bad = c.get("/api/workspaces", headers={"Host": "bad.example", "Authorization": "Bearer s3cr3t"})
    assert bad.status_code == 403


def test_bad_path_400(client):
    resp = client.get("/api/pf/..%2F..%2Fx/accounts", headers={"Host": "localhost"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "bad_path"}
    assert client.get("/api/pf/a%5Cb/accounts", headers={"Host": "localhost"}).status_code == 400
    assert client.get("/api/pf/a%00b/accounts", headers={"Host": "localhost"}).status_code == 400
    assert client.get("/api/pf/%2E/accounts", headers={"Host": "localhost"}).status_code == 400  # httpx collapses a literal /./


def test_no_origin_header_passes(client):
    # httpx / curl / MCP tools / the workflows runner send no Origin at all
    resp = client.post("/api/workspaces", json=WS, headers={"Host": "localhost"})
    assert resp.status_code == 200


def test_public_paths_skip_the_host_check(client):
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 200


def test_loopback_hosts_and_docker_names_allowed():
    for host in ("localhost", "LOCALHOST:5024", "app.localhost", "127.0.0.1:5041", "127.5.4.3", "[::1]:5041", "::1",
                 "0.0.0.0", "api:5041", "host.docker.internal"):
        assert host_allowed(host, ()), host
    for host in ("attacker.example", "192.168.1.20", "", "10.0.0.1:80", "evil.localhost.example"):
        assert not host_allowed(host, ()), host
    assert host_allowed("Nas.Home:5024", ("nas.home",))


def test_helpers():
    assert normalize_host("[::1]:5041") == "::1"
    assert normalize_host("Localhost:5024") == "localhost"
    assert path_is_safe("/api/pf/demo-mx/accounts")
    assert not path_is_safe("/api/../x")
    assert origin_allowed("http://LOCALHOST:5024", "localhost:5024", ())
    assert not origin_allowed("https://localhost", "localhost:5024", ())
    assert origin_allowed("http://localhost:3000", "localhost:5024", ("http://localhost:3000",))
    assert not origin_allowed("null", "localhost", ())
