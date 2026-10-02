"""The MCP server's HTTP app: Host/Origin guard plus bearer auth.

``build_http_app()`` = ``mcp.http_app(path="/mcp")`` wrapped by
:class:`aurum.core.guards.HostOriginGuard` (Host allow-list in loopback mode, Origin check on POST,
bad-path 400) and :class:`MCPBearerMiddleware` (``Authorization: Bearer`` required whenever a secret
exists: ``AURUM_MCP_TOKEN`` if set, else the shared API token from ``resolve_api_token()``). With no
token and a loopback bind the MCP endpoint stays open to local clients.

Works on fastmcp 2.14.x and 3.x — ``FastMCP.http_app(path=, middleware=)`` has the same signature.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from starlette.datastructures import Headers
from starlette.middleware import Middleware

from ..core.config import settings
from ..core.guards import HostOriginGuard
from ..core.security import token_matches
from ..core.token import resolve_api_token

MCP_PATH = "/mcp"


def mcp_secret() -> str:
    """``AURUM_MCP_TOKEN`` when set, else the API token (which may itself be '' = open)."""
    return settings().mcp_token or resolve_api_token()


def mcp_auth_required() -> bool:
    return bool(mcp_secret())


async def _send_json(send, status: int, body: dict, extra: list[tuple[bytes, bytes]] | None = None) -> None:
    payload = json.dumps(body).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(payload)).encode("ascii")),
        (b"cache-control", b"no-store"),
        *(extra or []),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


class MCPBearerMiddleware:
    """Pure ASGI: every request needs ``Authorization: Bearer <secret>`` while a secret is configured."""

    def __init__(self, app, secret_fn: Callable[[], str] = mcp_secret) -> None:
        self.app = app
        self.secret_fn = secret_fn

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        secret = self.secret_fn()
        if not secret:
            await self.app(scope, receive, send)
            return
        auth = Headers(scope=scope).get("authorization", "")
        supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if not token_matches(supplied, secret):
            await _send_json(send, 401, {"error": "unauthorized"}, [(b"www-authenticate", b"Bearer")])
            return
        await self.app(scope, receive, send)


def build_http_app():
    """Starlette app serving streamable-HTTP MCP at ``/mcp`` behind the guard + bearer."""
    from .server import mcp

    return mcp.http_app(
        path=MCP_PATH,
        middleware=[
            Middleware(
                HostOriginGuard,
                allowed_hosts_fn=lambda: settings().allowed_hosts,
                allowed_origins_fn=lambda: settings().allowed_origins,
                auth_required_fn=mcp_auth_required,
                api_prefixes=(MCP_PATH,),
                public_paths=(),
            ),
            Middleware(MCPBearerMiddleware),
        ],
    )
