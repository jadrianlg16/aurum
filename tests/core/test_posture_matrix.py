"""Posture matrix: bind × token source × request type.

    bind ∈ {127.0.0.1, 0.0.0.0} × token ∈ {none, env, file} × request ∈ {R1..R5} = 30 cases

    R1 same-origin POST  (Host localhost, Origin http://localhost, bearer when a token exists)
        → the route's own status (2xx/4xx), never 401/403                       [all six]
    R2 cross-origin POST (Origin http://evil.example, bearer when a token exists)
        → 403 origin_not_allowed — a valid bearer never overrides the Origin check [all six]
    R3 rebinding GET     (Host attacker.example, no bearer)
        → 403 host_not_allowed when no token, else 401
    R4 curl GET          (Host localhost, no headers)
        → 200 when no token, else 401
    R5 LAN bearer GET    (Host 192.168.1.20:5024, correct bearer)
        → 403 host_not_allowed when no token, else 200

Under bind 0.0.0.0 the "none" column behaves as "file": ``data/secrets/api_token`` is generated
(mode 0o600 on POSIX) on the first request that resolves the token, and is then required. This
mirrors the table in docs/SECURITY.md.
"""

from __future__ import annotations

import os
import stat

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core import token as token_mod

BINDS = ["127.0.0.1", "0.0.0.0"]
TOKENS = ["none", "env", "file"]
REQUESTS = ["R1", "R2", "R3", "R4", "R5"]

ENV_TOKEN = "env-s3cr3t"
FILE_TOKEN = "file-s3cr3t"
WS = {"id": "posture-ws", "name": "Posture", "kind": "personal", "country": "MX"}


def _setup(monkeypatch, bind: str, token: str) -> str:
    """Returns the bearer the client should send (or '' when the API is open)."""
    monkeypatch.delenv("AURUM_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("AURUM_BIND", bind)
    if token == "env":
        monkeypatch.setenv("AURUM_API_TOKEN", ENV_TOKEN)
        return ENV_TOKEN
    if token == "file":
        path = token_mod.token_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(FILE_TOKEN + "\n", encoding="utf-8")
        return FILE_TOKEN
    if bind == "0.0.0.0":
        # "none" behaves as "file": the token is generated lazily on first resolution
        return "GENERATED"
    return ""


def _resolve_bearer(bearer: str) -> str:
    if bearer == "GENERATED":
        return token_mod.resolve_api_token()
    return bearer


@pytest.mark.parametrize("request_kind", REQUESTS)
@pytest.mark.parametrize("token", TOKENS)
@pytest.mark.parametrize("bind", BINDS)
def test_posture(monkeypatch, bind: str, token: str, request_kind: str):
    bearer = _setup(monkeypatch, bind, token)
    client = TestClient(create_app())
    auth_required = bool(bearer)

    if request_kind == "R1":
        headers = {"Host": "localhost", "Origin": "http://localhost"}
        if auth_required:
            headers["Authorization"] = f"Bearer {_resolve_bearer(bearer)}"
        resp = client.post("/api/workspaces", json=WS, headers=headers)
        assert resp.status_code not in (401, 403), resp.text
        assert resp.status_code == 200
    elif request_kind == "R2":
        headers = {"Host": "localhost", "Origin": "http://evil.example"}
        if auth_required:
            headers["Authorization"] = f"Bearer {_resolve_bearer(bearer)}"
        resp = client.post("/api/workspaces", json=WS, headers=headers)
        assert resp.status_code == 403
        assert resp.json() == {"error": "origin_not_allowed"}
    elif request_kind == "R3":
        resp = client.get("/api/workspaces", headers={"Host": "attacker.example"})
        if auth_required:
            assert resp.status_code == 401
        else:
            assert resp.status_code == 403
            assert resp.json() == {"error": "host_not_allowed"}
    elif request_kind == "R4":
        resp = client.get("/api/workspaces", headers={"Host": "localhost"})
        assert resp.status_code == (401 if auth_required else 200)
    elif request_kind == "R5":
        headers = {"Host": "192.168.1.20:5024"}
        if auth_required:
            headers["Authorization"] = f"Bearer {_resolve_bearer(bearer)}"
        resp = client.get("/api/workspaces", headers=headers)
        if auth_required:
            assert resp.status_code == 200
        else:
            assert resp.status_code == 403
            assert resp.json() == {"error": "host_not_allowed"}

    if bind == "0.0.0.0" and token == "none":
        path = token_mod.token_path()
        assert path.exists(), "exposed bind without a token must generate the file token"
        if os.name != "nt":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        # ...and it is then required, exactly like the "file" column
        assert client.get("/api/workspaces", headers={"Host": "localhost"}).status_code == 401


def test_matrix_has_thirty_cases():
    assert len(BINDS) * len(TOKENS) * len(REQUESTS) == 30
