"""Host / Origin / path guard — pure ASGI, shared by the API and the MCP HTTP app.

Three checks, in order, for every HTTP request:

(a) **PATH** — the decoded ``raw_path`` may not contain a ``.``/``..`` segment, a backslash, NUL or any
    C0 control character → ``400 {"error":"bad_path"}``. Applies to every path.
(b) **HOST** — for paths under ``api_prefixes`` (minus ``public_paths``): when no token is required the
    ``Host`` header (lower-cased, port and IPv6 brackets stripped) must be a loopback name/address, ``api``,
    ``host.docker.internal`` or one of ``allowed_hosts`` → else ``403 {"error":"host_not_allowed"}``.
    This is the DNS-rebinding defence for the token-less localhost posture. When a token IS required the
    Host check only runs when ``AURUM_ALLOWED_HOSTS`` is explicitly set.
(c) **ORIGIN** — for methods other than GET/HEAD/OPTIONS: ``Sec-Fetch-Site: cross-site`` → 403; if an
    ``Origin`` header is present its netloc (case-insensitive, port significant, scheme ignored) must equal
    the ``Host`` header or the full origin must be in ``allowed_origins`` → else
    ``403 {"error":"origin_not_allowed"}``; ``Origin: null`` → 403. No ``Origin`` (curl, httpx, MCP
    clients, the workflows runner) passes — non-browser clients are the operator's own tools.

A valid bearer never bypasses (b) or (c): the guard sits *outside* the bearer middleware. Every
``*_fn`` argument is called per request so ``settings()`` monkeypatching in tests takes effect.
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Callable, Iterable
from urllib.parse import unquote, urlsplit

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_BAD_CHARS = re.compile(r"[\x00-\x1f\x7f\\]")
_LOCAL_HOSTS = frozenset({"localhost", "0.0.0.0", "api", "host.docker.internal"})

API_PREFIXES: tuple[str, ...] = ("/api/", "/docs", "/openapi.json", "/redoc")
API_PUBLIC_PATHS: tuple[str, ...] = ("/api/health", "/")


def decoded_path(scope: dict) -> str:
    raw = scope.get("raw_path")
    if raw:
        return unquote(raw.decode("latin-1"))
    return scope.get("path", "/")


def path_is_safe(path: str) -> bool:
    if _BAD_CHARS.search(path):
        return False
    return not any(seg in (".", "..") for seg in path.split("/"))


def normalize_host(host_header: str) -> str:
    """``Host`` → lower-cased hostname without port or IPv6 brackets."""
    host = host_header.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end != -1 else host[1:]
    if host.count(":") == 1:  # hostname:port or v4:port; bare v6 has more colons
        host = host.rsplit(":", 1)[0]
    return host


def host_allowed(host_header: str, allowed_hosts: Iterable[str]) -> bool:
    host = normalize_host(host_header)
    if not host:
        return False
    if host in _LOCAL_HOSTS or host.endswith(".localhost"):
        return True
    if host in {h.strip().lower() for h in allowed_hosts}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback


def origin_allowed(origin: str, host_header: str, allowed_origins: Iterable[str]) -> bool:
    origin = origin.strip()
    if not origin or origin.lower() == "null":
        return False
    if origin in allowed_origins:
        return True
    netloc = urlsplit(origin).netloc.lower()
    return bool(netloc) and netloc == host_header.strip().lower()


async def _send_json(send, status: int, body: dict) -> None:
    payload = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class HostOriginGuard:
    def __init__(
        self,
        app,
        *,
        allowed_hosts_fn: Callable[[], Iterable[str]],
        allowed_origins_fn: Callable[[], Iterable[str]],
        auth_required_fn: Callable[[], bool],
        api_prefixes: Iterable[str] = API_PREFIXES,
        public_paths: Iterable[str] = API_PUBLIC_PATHS,
    ) -> None:
        self.app = app
        self.allowed_hosts_fn = allowed_hosts_fn
        self.allowed_origins_fn = allowed_origins_fn
        self.auth_required_fn = auth_required_fn
        self.api_prefixes = tuple(api_prefixes)
        self.public_paths = frozenset(public_paths)

    def _guarded(self, path: str) -> bool:
        return path not in self.public_paths and any(path.startswith(p) for p in self.api_prefixes)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = decoded_path(scope)
        if not path_is_safe(path):
            await _send_json(send, 400, {"error": "bad_path"})
            return
        if not self._guarded(path):
            await self.app(scope, receive, send)
            return

        headers: dict[bytes, bytes] = {}
        for k, v in scope.get("headers", ()):
            headers.setdefault(k, v)
        host = headers.get(b"host", b"").decode("latin-1")

        allowed_hosts = tuple(self.allowed_hosts_fn())
        if (not self.auth_required_fn() or allowed_hosts) and not host_allowed(host, allowed_hosts):
            await _send_json(send, 403, {"error": "host_not_allowed"})
            return

        if scope.get("method", "GET").upper() not in _SAFE_METHODS:
            if headers.get(b"sec-fetch-site", b"").decode("latin-1").strip().lower() == "cross-site":
                await _send_json(send, 403, {"error": "origin_not_allowed"})
                return
            origin = headers.get(b"origin")
            if origin is not None and not origin_allowed(
                origin.decode("latin-1"), host, tuple(self.allowed_origins_fn())
            ):
                await _send_json(send, 403, {"error": "origin_not_allowed"})
                return

        await self.app(scope, receive, send)
