"""Builds the catalog of endpoints a workflow step (or the ``propose`` LLM) may call.

Generated live from ``create_app().routes`` so it can never drift from the real API
surface, then filtered through the deny-list.
"""

from __future__ import annotations

from typing import Any

from .deny import DENY_DESCRIPTIONS, is_denied


def build_catalog() -> list[dict[str, Any]]:
    """Built from the generated OpenAPI schema rather than walking router internals --
    ``app.openapi()`` always resolves each route to its final, fully-prefixed path
    regardless of how ``include_router``/mounting is implemented in the installed
    FastAPI/Starlette version."""
    from ..api.app import create_app

    app = create_app()
    schema = app.openapi()
    entries: list[dict[str, Any]] = []
    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            method_upper = method.upper()
            if method_upper not in ("GET", "POST", "PUT", "DELETE"):
                continue
            if is_denied(method_upper, path.removeprefix("/api")):
                continue
            entries.append(
                {
                    "method": method_upper,
                    "path": path,
                    "summary": op.get("summary") or op.get("operationId", ""),
                }
            )
    entries.sort(key=lambda e: (e["path"], e["method"]))
    return entries


def catalog_payload() -> dict[str, Any]:
    return {"endpoints": build_catalog(), "deny_list": DENY_DESCRIPTIONS}
