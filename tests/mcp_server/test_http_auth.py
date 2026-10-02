"""MCP over HTTP: open on loopback without a token, bearer required once
one exists (AURUM_MCP_TOKEN or the API token), Host guard in loopback mode."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.mcp_server.http import build_http_app

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "c", "version": "1"}},
}
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("AURUM_ALLOWED_HOSTS", raising=False)
    with TestClient(build_http_app()) as c:
        yield c


def _init(client: TestClient, **headers) -> object:
    return client.post("/mcp", json=INIT, headers={**ACCEPT, "Host": "localhost", **headers})


def test_initialize_open_without_token(client):
    resp = _init(client)
    assert resp.status_code == 200, resp.text
    assert "serverInfo" in resp.text


def test_env_token_required(client, monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    resp = _init(client)
    assert resp.status_code == 401
    assert resp.json() == {"error": "unauthorized"}
    assert resp.headers["www-authenticate"] == "Bearer"
    assert _init(client, Authorization="Bearer s3cr3t").status_code == 200
    assert _init(client, Authorization="Bearer nope").status_code == 401


def test_mcp_token_overrides_api_token(client, monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "apitoken")
    monkeypatch.setenv("AURUM_MCP_TOKEN", "mcptoken")
    assert _init(client, Authorization="Bearer apitoken").status_code == 401
    assert _init(client, Authorization="Bearer mcptoken").status_code == 200


def test_host_guard_in_loopback_mode(client):
    resp = _init(client, Host="attacker.example")
    assert resp.status_code == 403
    assert resp.json() == {"error": "host_not_allowed"}
    assert _init(client, Host="127.0.0.1:5042").status_code == 200
    assert _init(client, Host="api:5042").status_code == 200


def test_cross_origin_post_blocked(client):
    resp = _init(client, Origin="http://evil.example")
    assert resp.status_code == 403
    assert resp.json() == {"error": "origin_not_allowed"}


def test_bad_path_400(client):
    resp = client.get("/mcp/%2E%2E/x", headers={"Host": "localhost"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "bad_path"}


def test_lan_host_with_bearer_when_token_required(client, monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    assert _init(client, Host="192.168.1.20:5042", Authorization="Bearer s3cr3t").status_code == 200
    assert _init(client, Host="192.168.1.20:5042").status_code == 401
