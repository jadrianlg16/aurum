"""Hardening primitives: bearer token, security headers,
streamed request-size cap, per-IP rate limit with bucket eviction, PII log masking, demo (read-only)
mode, and the middleware wiring that puts ``HostOriginGuard`` between the bearer and the headers.

The bare localhost install stays token-less: the Host/Origin guard is what protects it. A token is
required automatically once ``AURUM_BIND`` is not loopback (see ``aurum.core.token``).
"""

from __future__ import annotations

import copy
import hmac
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware

from .audit import mask
from .config import settings
from .guards import API_PREFIXES, API_PUBLIC_PATHS, HostOriginGuard
from .token import auth_required, resolve_api_token

log = logging.getLogger("aurum.security")

#: Paths that never require the token. ``/docs``, ``/openapi.json`` and ``/redoc`` are guarded.
PUBLIC_PATHS = frozenset({"/api/health", "/"})

UNAUTHORIZED_BODY = {
    "error": "unauthorized",
    "hint": "Set the token in Ajustes › Avanzado (Token de la API) or run: python -m aurum.core.token show",
}

#: (method, path-regex) allow-listed to mutate even in demo mode — the "let people try the
#: interesting parts without letting them wreck shared data" set.
DEMO_ALLOW = [
    re.compile(r"^POST /api/ingest/[^/]+/quickadd$"),
    re.compile(r"^POST /api/ingest/[^/]+/inbox/[^/]+/(accept|reject)$"),
    re.compile(r"^POST /api/research/ask$"),
    re.compile(r"^POST /api/plan/[^/]+/scenarios/[^/]+/(run|montecarlo|sensitivity)$"),
    re.compile(r"^POST /api/workflows/[^/]+/propose$"),
]

DEMO_MESSAGE = {
    "en": "Demo mode is read-only; this action is disabled on the public demo.",
    "es": "El modo demo es de solo lectura; esta acción está deshabilitada en la demo pública.",
}


def _is_demo_mutation_allowed(method: str, path: str) -> bool:
    key = f"{method} {path}"
    return any(pattern.match(key) for pattern in DEMO_ALLOW)


async def _send_json(send, status: int, body: dict, extra_headers: list[tuple[bytes, bytes]] | None = None) -> None:
    payload = json.dumps(body).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(payload)).encode("ascii")),
        (b"cache-control", b"no-store"),
        *(extra_headers or []),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


def supplied_token(headers: Headers) -> str:
    """``Authorization: Bearer <t>`` or ``X-Aurum-Token: <t>`` (the former wins when both are sent)."""
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return headers.get("x-aurum-token", "").strip()


def token_matches(supplied: str, expected: str) -> bool:
    return bool(supplied) and bool(expected) and hmac.compare_digest(supplied.encode(), expected.encode())


class BearerTokenMiddleware:
    """When ``resolve_api_token()`` is non-empty every path but ``PUBLIC_PATHS`` requires it (pure ASGI)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = resolve_api_token()
        path = scope.get("path", "/")
        if not token or path in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        if not token_matches(supplied_token(Headers(scope=scope)), token):
            await _send_json(send, 401, UNAUTHORIZED_BODY, [(b"www-authenticate", b"Bearer")])
            return
        await self.app(scope, receive, send)


class DemoModeMiddleware(BaseHTTPMiddleware):
    """When ``AURUM_DEMO_MODE=1``, block non-GET requests outside a small allow-list."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        s = settings()
        path = request.url.path
        if (
            s.demo_mode
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and path.startswith("/api/")
            and not _is_demo_mutation_allowed(request.method, path)
        ):
            lang = "es" if "es" in (request.headers.get("accept-language", "")) else "en"
            body = {"error": "demo_mode_read_only", "message": f"{DEMO_MESSAGE['en']} / {DEMO_MESSAGE['es']}" if lang == "en" else DEMO_MESSAGE["es"]}
            return JSONResponse(body, status_code=403)
        return await call_next(request)


class _BodyTooLarge(Exception):
    pass


class MaxBodySizeMiddleware:
    """Rejects a request body larger than ``AURUM_MAX_UPLOAD_MB`` (default 25MB), pure ASGI.

    ``Content-Length`` is pre-checked, and the ``receive`` channel is wrapped so a chunked upload
    (no Content-Length) is counted as it streams: on overflow a 413 is sent if the response has not
    started yet, otherwise the request is simply abandoned (the server closes the connection).
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = settings().max_upload_mb * 1024 * 1024
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    await _send_json(send, 413, {"error": "payload_too_large"})
                    return
            except ValueError:
                pass

        received = 0
        response_started = False

        async def wrapped_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def wrapped_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except* _BodyTooLarge:
            # ``except*``: BaseHTTPMiddleware layers below us re-raise inside an ExceptionGroup.
            if not response_started:
                await _send_json(send, 413, {"error": "payload_too_large"})


class _TokenBucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, tokens: float, updated: float) -> None:
        self.tokens = tokens
        self.updated = updated


_MAX_BUCKETS = 1000
_IDLE_SECONDS = 600.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP token-bucket. ``AURUM_RATE_LIMIT_PER_MIN`` (default 600); 0 disables it.

    The bucket table is bounded: past ``_MAX_BUCKETS`` entries, buckets idle for more than
    ``_IDLE_SECONDS`` are dropped, then the oldest-updated ones until the table fits.
    """

    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)
        self._buckets: dict[str, _TokenBucket] = {}

    def _evict(self, now: float) -> None:
        if len(self._buckets) <= _MAX_BUCKETS:
            return
        for ip in [ip for ip, b in self._buckets.items() if now - b.updated > _IDLE_SECONDS]:
            del self._buckets[ip]
        if len(self._buckets) > _MAX_BUCKETS:
            by_age = sorted(self._buckets.items(), key=lambda kv: kv[1].updated)
            for ip, _bucket in by_age[: len(self._buckets) - _MAX_BUCKETS]:
                del self._buckets[ip]

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        per_min = settings().rate_limit_per_min
        if per_min <= 0 or not request.url.path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = self._buckets.get(client_ip)
        if bucket is None:
            bucket = _TokenBucket(float(per_min), now)
            self._buckets[client_ip] = bucket
            self._evict(now)
        refill = (now - bucket.updated) * (per_min / 60.0)
        bucket.tokens = min(float(per_min), bucket.tokens + refill)
        bucket.updated = now
        if bucket.tokens < 1.0:
            return JSONResponse({"error": "rate_limited"}, status_code=429)
        bucket.tokens -= 1.0
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Standard hardening headers on every response; no-store cache on ``/api/*``."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


# ------------------------------------------------------------------------------- PII in logs

_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*")
_TOKEN_HEADER = re.compile(r"(?i)(x-aurum-token\s*[:=]\s*)[A-Za-z0-9._~+/-]+=*")


def _mask_value(text: str) -> str:
    text = _BEARER.sub("Bearer ***MASKED***", text)
    text = _TOKEN_HEADER.sub(r"\1***MASKED***", text)
    return mask(text)


def _mask_args(args):
    if isinstance(args, dict):
        return {k: (_mask_value(v) if isinstance(v, str) else v) for k, v in args.items()}
    if isinstance(args, tuple):
        return tuple(_mask_value(a) if isinstance(a, str) else a for a in args)
    return args


class PiiLogFilter(logging.Filter):
    """Masks RFC/CURP/SSN/account numbers and bearer tokens on a handler (uvicorn's log_config uses it)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = _mask_value(record.msg)
            record.args = _mask_args(record.args)
        except Exception:  # noqa: BLE001 - logging must never raise
            return True
        return True


def install_pii_log_filter() -> None:
    """Installs an idempotent ``LogRecordFactory`` wrapper so EVERY record — from any child logger,
    to any handler installed later (uvicorn's, basicConfig's) — is masked at creation time.
    Attaching a filter to the root logger is not enough: filters on loggers are not consulted for
    records that propagate up from child loggers."""

    current = logging.getLogRecordFactory()
    if getattr(current, "_aurum_pii", False):
        return

    def factory(*args, **kwargs):
        record = current(*args, **kwargs)
        try:
            if isinstance(record.msg, str):
                record.msg = _mask_value(record.msg)
            record.args = _mask_args(record.args)
        except Exception:  # noqa: BLE001 - logging must never raise
            pass
        return record

    factory._aurum_pii = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


def uvicorn_log_config() -> dict:
    """uvicorn's default LOGGING_CONFIG with the PII filter on its ``default`` and ``access`` handlers."""
    from uvicorn.config import LOGGING_CONFIG

    cfg = copy.deepcopy(LOGGING_CONFIG)
    cfg.setdefault("filters", {})["pii"] = {"()": "aurum.core.security.PiiLogFilter"}
    for name in ("default", "access"):
        handler = cfg.get("handlers", {}).get(name)
        if handler is not None:
            handler["filters"] = [*handler.get("filters", []), "pii"]
    return cfg


# ------------------------------------------------------------------------------------ wiring


def install_middleware(app: FastAPI) -> None:
    """Wires every hardening middleware onto ``app`` in the order that matters.

    Starlette runs middleware in reverse of add order (last added = outermost): request flow is
    SecurityHeaders → HostOriginGuard → BearerToken → Demo → MaxBody → RateLimit → routes. The guard
    sits outside the bearer so a valid token never bypasses the Host/Origin checks; headers are
    outermost so they land on every response, including 401/403/413/429. CORS (added by
    ``create_app`` only when ``AURUM_ALLOWED_ORIGINS`` is set) wraps all of it.
    """

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(DemoModeMiddleware)
    app.add_middleware(BearerTokenMiddleware)
    app.add_middleware(
        HostOriginGuard,
        allowed_hosts_fn=lambda: settings().allowed_hosts,
        allowed_origins_fn=lambda: settings().allowed_origins,
        auth_required_fn=auth_required,
        api_prefixes=API_PREFIXES,
        public_paths=API_PUBLIC_PATHS,
    )
    app.add_middleware(SecurityHeadersMiddleware)
