"""Tests for aurum.core.security: bearer (env + file token,
/docs guarded, 401 shape), headers, streamed body cap, rate limit behind a proxy with bucket eviction,
demo mode, and the PII LogRecord factory seen through a child logger."""

from __future__ import annotations

import logging

import anyio
from fastapi import Request, Response
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from aurum.api.app import create_app
from aurum.core import token as token_mod
from aurum.core.audit import mask
from aurum.core.security import UNAUTHORIZED_BODY, PiiLogFilter, RateLimitMiddleware, install_pii_log_filter


def _client() -> TestClient:
    return TestClient(create_app())


def _write_file_token(value: str) -> None:
    path = token_mod.token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------- bearer


def test_health_is_always_public(monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    client = _client()
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["demo_mode"] is False


def test_token_required_when_set_401_shape(monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    client = _client()
    resp = client.get("/api/workspaces")
    assert resp.status_code == 401
    assert resp.json() == UNAUTHORIZED_BODY
    assert resp.headers["www-authenticate"] == "Bearer"
    assert "s3cr3t" not in resp.text
    assert resp.headers["x-content-type-options"] == "nosniff"  # headers land on 401 too


def test_docs_and_openapi_guarded_when_token_set(monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    client = _client()
    for path in ("/docs", "/openapi.json", "/redoc", "/api/mounted"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers={"Authorization": "Bearer s3cr3t"}).status_code == 200, path


def test_token_accepted_with_correct_bearer(monkeypatch):
    monkeypatch.setenv("AURUM_API_TOKEN", "s3cr3t")
    client = _client()
    assert client.get("/api/workspaces", headers={"Authorization": "Bearer s3cr3t"}).status_code == 200
    assert client.get("/api/workspaces", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/workspaces", headers={"X-Aurum-Token": "s3cr3t"}).status_code == 200


def test_file_token_is_honoured_by_the_bearer_check():
    _write_file_token("f1l3t0k3n")
    client = _client()
    assert client.get("/api/workspaces").status_code == 401
    assert client.get("/api/workspaces", headers={"Authorization": "Bearer f1l3t0k3n"}).status_code == 200
    assert client.get("/api/workspaces", headers={"X-Aurum-Token": "f1l3t0k3n"}).status_code == 200
    assert client.get("/api/health").status_code == 200


def test_token_off_by_default_matches_prior_behavior():
    client = _client()
    resp = client.get("/api/workspaces")
    assert resp.status_code == 200


def test_create_app_never_generates_a_token(monkeypatch):
    monkeypatch.setenv("AURUM_BIND", "0.0.0.0")
    create_app()
    assert not token_mod.token_path().exists()


# ------------------------------------------------------------------------------ headers


def test_security_headers_present():
    client = _client()
    resp = client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["cache-control"] == "no-store"


def test_no_cors_headers_by_default():
    client = _client()
    resp = client.options(
        "/api/workspaces", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in resp.headers
    resp = client.get("/api/workspaces", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


def test_cors_only_for_allowed_origins(monkeypatch):
    monkeypatch.setenv("AURUM_ALLOWED_ORIGINS", "http://localhost:3000")
    client = _client()
    ok = client.options(
        "/api/workspaces", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    evil = client.options(
        "/api/workspaces", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in evil.headers


# ------------------------------------------------------------------------------ body cap


def _app_with_sink():
    app = create_app()

    @app.post("/api/_sink")
    async def _sink(request: Request) -> dict:
        body = await request.body()
        return {"received": len(body)}

    return app


def test_max_upload_rejects_oversized_content_length(monkeypatch):
    monkeypatch.setenv("AURUM_MAX_UPLOAD_MB", "1")
    client = _client()
    big = b"x" * (2 * 1024 * 1024)
    resp = client.post(
        "/api/research/ingest",
        files={"file": ("law.txt", big, "text/plain")},
        data={"collection": "mx-law"},
    )
    assert resp.status_code == 413
    assert resp.json() == {"error": "payload_too_large"}


def test_max_upload_counts_streamed_chunks(monkeypatch):
    monkeypatch.setenv("AURUM_MAX_UPLOAD_MB", "1")
    client = TestClient(_app_with_sink())
    resp = client.post(
        "/api/_sink", content=iter([b"x" * 524288] * 4), headers={"Content-Type": "application/octet-stream"}
    )
    assert resp.status_code == 413
    assert resp.json() == {"error": "payload_too_large"}
    ok = client.post(
        "/api/_sink", content=iter([b"x" * 524288]), headers={"Content-Type": "application/octet-stream"}
    )
    assert ok.status_code == 200
    assert ok.json() == {"received": 524288}


# ---------------------------------------------------------------------------- rate limit


def test_rate_limit_returns_429_when_exhausted(monkeypatch):
    monkeypatch.setenv("AURUM_RATE_LIMIT_PER_MIN", "2")
    client = _client()
    codes = [client.get("/api/health").status_code for _ in range(5)]
    assert 429 in codes


def test_rate_limit_off_when_zero(monkeypatch):
    monkeypatch.setenv("AURUM_RATE_LIMIT_PER_MIN", "0")
    client = _client()
    codes = [client.get("/api/health").status_code for _ in range(20)]
    assert all(c == 200 for c in codes)


def test_rate_limit_buckets_follow_x_forwarded_for_behind_proxy(monkeypatch):
    monkeypatch.setenv("AURUM_RATE_LIMIT_PER_MIN", "2")
    app = create_app()
    client = TestClient(ProxyHeadersMiddleware(app, trusted_hosts="*"))
    a = {"X-Forwarded-For": "10.0.0.1"}
    b = {"X-Forwarded-For": "10.0.0.2"}
    assert client.get("/api/health", headers=a).status_code == 200
    assert client.get("/api/health", headers=a).status_code == 200
    assert client.get("/api/health", headers=a).status_code == 429
    assert client.get("/api/health", headers=b).status_code == 200


def test_rate_limit_bucket_table_is_bounded(monkeypatch):
    monkeypatch.setenv("AURUM_RATE_LIMIT_PER_MIN", "600")
    limiter = RateLimitMiddleware(create_app())
    scopes = []
    for i in range(5000):
        ip = f"10.{(i >> 16) & 255}.{(i >> 8) & 255}.{i & 255}"
        scopes.append({"type": "http", "method": "GET", "path": "/api/health", "headers": [], "client": (ip, 1)})

    async def _drive():
        async def call_next(_request):
            return Response("ok")

        for scope in scopes:
            await limiter.dispatch(Request(scope), call_next)

    anyio.run(_drive)
    assert len(limiter._buckets) <= 1000  # noqa: SLF001
    assert len(limiter._buckets) > 0  # noqa: SLF001


# ----------------------------------------------------------------------------- demo mode


def test_demo_mode_blocks_mutations(monkeypatch):
    monkeypatch.setenv("AURUM_DEMO_MODE", "1")
    client = _client()
    resp = client.post("/api/workspaces", json={"ws_id": "blocked", "name": "x", "kind": "personal", "country": "MX"})
    assert resp.status_code == 403
    assert client.get("/api/health").json()["demo_mode"] is True


def test_demo_mode_allows_quickadd(monkeypatch):
    monkeypatch.setenv("AURUM_DEMO_MODE", "1")
    client = _client()
    resp = client.post("/api/ingest/demo-mx/quickadd", json={"text": "100 tacos"})
    assert resp.status_code != 403


def test_demo_mode_allows_research_ask(monkeypatch):
    monkeypatch.setenv("AURUM_DEMO_MODE", "1")
    client = _client()
    resp = client.post("/api/research/ask", json={"question": "hola", "jurisdiction": "MX", "lang": "es"})
    assert resp.status_code != 403


# ------------------------------------------------------------------------------------ PII

_PII_LINE = "RFC FAKE900101AB1 CURP FAKE900101HDFXXX09 acct 1234567890123456 Authorization: Bearer secrettoken123"


def test_pii_log_filter_masks_rfc_and_bearer_tokens(caplog):
    logger = logging.getLogger("aurum.security.test")
    logger.addFilter(PiiLogFilter())
    with caplog.at_level(logging.INFO, logger="aurum.security.test"):
        logger.info("user rfc GONZ800101ABC and Authorization: Bearer abcDEF123.xyz")
    assert "GONZ800101ABC" not in caplog.text
    assert "abcDEF123.xyz" not in caplog.text


def test_pii_masked_through_child_logger(caplog):
    install_pii_log_filter()
    install_pii_log_filter()  # idempotent: the factory is wrapped once
    assert getattr(logging.getLogRecordFactory(), "_aurum_pii", False)
    with caplog.at_level(logging.WARNING):
        logging.getLogger("aurum.ingest").warning(_PII_LINE)
        logging.getLogger("aurum.ingest.cfdi").warning("rfc=%s bearer=%s", "FAKE900101AB1", "Bearer secrettoken123")
    text = caplog.text
    for literal in ("FAKE900101AB1", "FAKE900101HDFXXX09", "1234567890123456", "secrettoken123"):
        assert literal not in text, literal
    assert "MASKED" in text


def test_mask_still_masks_account_numbers():
    assert "1234567890123456" not in mask("account 1234567890123456 flagged")


# ------------------------------------------------------------------- exception handlers


def test_invalid_workspace_id_400():
    client = _client()
    resp = client.get("/api/pf/A_B/accounts")
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid_workspace_id"}
    assert client.get("/api/workspaces/a%20b").status_code == 400


def test_pydantic_validation_error_inside_handler_400():
    from pydantic import BaseModel

    app = create_app()

    class _M(BaseModel):
        n: int

    @app.get("/api/_boom")
    def _boom() -> dict:
        _M(n="x")  # type: ignore[arg-type]
        return {}

    resp = TestClient(app).get("/api/_boom")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "validation"
    assert body["detail"][0]["loc"] == ["n"]
    assert "url" not in body["detail"][0]
