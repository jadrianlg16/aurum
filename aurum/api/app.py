"""Mounts every module router that exists. A missing module is skipped, never fatal."""

from __future__ import annotations

import importlib
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..core.config import InvalidWorkspaceId, settings
from ..core.security import install_middleware, install_pii_log_filter, uvicorn_log_config
from ..core.token import resolve_api_token

log = logging.getLogger("aurum.api")

# module → URL prefix. Order matters only for the docs page.
MOUNTS: list[tuple[str, str]] = [
    ("aurum.core.router", "/api"),
    ("aurum.ledger.router", "/api/ledger"),
    ("aurum.rules.router", "/api/rules"),
    ("aurum.tax.router", "/api/tax"),
    ("aurum.ingest.router", "/api/ingest"),
    ("aurum.satsync.router", "/api/satsync"),
    ("aurum.pf.router", "/api/pf"),
    ("aurum.research.router", "/api/research"),
    ("aurum.updater.router", "/api/watch"),
    ("aurum.taxus.router", "/api/tax/us"),
    ("aurum.crossborder.router", "/api/crossborder"),
    ("aurum.holdings.router", "/api/holdings"),
    ("aurum.fx.router", "/api/fx"),
    ("aurum.creditreport.router", "/api/creditreport"),
    ("aurum.plan.router", "/api/plan"),
    ("aurum.business.router", "/api/business"),
    ("aurum.insights.router", "/api/insights"),
    ("aurum.reports.router", "/api/reports"),
    ("aurum.workflows.router", "/api/workflows"),
    ("aurum.organizer.router", "/api/organizer"),
]


CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
CORS_HEADERS = ["Authorization", "Content-Type", "X-Aurum-Token", "X-Aurum-Workspace"]


def install_exception_handlers(app: FastAPI) -> None:
    """Middleware-shaped 4xx bodies for errors raised inside handlers."""
    from ..ingest.cfdi import ZipTooLarge
    from ..ledger.beancount_store import LedgerRenderError

    @app.exception_handler(InvalidWorkspaceId)
    async def _invalid_ws(_request: Request, _exc: InvalidWorkspaceId) -> JSONResponse:
        return JSONResponse({"error": "invalid_workspace_id"}, status_code=400)

    @app.exception_handler(ValidationError)
    async def _validation(_request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse({"error": "validation", "detail": exc.errors(include_url=False)}, status_code=400)

    @app.exception_handler(LedgerRenderError)
    async def _render(_request: Request, exc: LedgerRenderError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(ZipTooLarge)
    async def _zip(_request: Request, _exc: ZipTooLarge) -> JSONResponse:
        return JSONResponse({"detail": "zip too large after decompression"}, status_code=413)


def create_app() -> FastAPI:
    install_pii_log_filter()
    app = FastAPI(title="Aurum API", version="0.1.0")
    install_middleware(app)
    install_exception_handlers(app)
    allowed_origins = settings().allowed_origins
    if allowed_origins:
        # Only for an explicitly configured second origin (a dev server); the shipped UI is same-origin.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=CORS_METHODS,
            allow_headers=CORS_HEADERS,
            allow_credentials=False,
            max_age=600,
        )
    mounted: list[str] = []
    for module_name, prefix in MOUNTS:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as e:
            if e.name and module_name.startswith(e.name.split(".")[0]) and e.name in module_name:
                log.info("router %s not present, skipping", module_name)
                continue
            raise
        router = getattr(module, "router", None)
        if router is None:
            log.warning("%s has no `router`, skipping", module_name)
            continue
        app.include_router(router, prefix=prefix)
        mounted.append(prefix)
    app.state.mounted = mounted

    @app.get("/api/mounted")
    def mounted_routes() -> dict:
        return {"mounted": mounted}

    return app


app = create_app()


def main() -> None:
    s = settings()
    logging.basicConfig(level=logging.INFO)
    install_pii_log_filter()
    resolve_api_token()  # eager: generates the file token at boot when the bind is exposed
    log.info("aurum-api on %s:%s (bind=%s, auth=%s)", s.api_host, s.api_port, s.bind, "on" if resolve_api_token() else "off")
    uvicorn.run(
        "aurum.api.app:app",
        host=s.api_host,
        port=s.api_port,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips=s.forwarded_allow_ips,
        log_config=uvicorn_log_config(),
    )


if __name__ == "__main__":
    main()
