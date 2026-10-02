"""FastMCP server exposing Aurum's API as MCP tools.

Every tool is a plain HTTP call to ``settings().api_url`` — this module never imports
another module's Python code, only its HTTP API. ``_client_factory`` is the single
seam tests replace with an ``httpx.ASGITransport`` bound to ``aurum.api.app.create_app()``
so the whole tool surface is testable with no server process running.

``main()``: stdio transport by default (for a local MCP client such as Claude Desktop);
``--http`` serves streamable-HTTP on ``AURUM_MCP_HOST:AURUM_MCP_PORT`` (default 127.0.0.1:5042)
through :func:`aurum.mcp_server.http.build_http_app` — Host/Origin guard + bearer whenever a
token is configured.
"""

from __future__ import annotations

import argparse
import logging
from decimal import Decimal
from typing import Any

import httpx
from fastmcp import FastMCP

from ..core.config import settings
from ..core.token import resolve_api_token

log = logging.getLogger("aurum.mcp_server")

mcp = FastMCP("aurum")


def _client_factory() -> httpx.AsyncClient:
    """Builds the HTTP client used by every tool. The one seam tests monkeypatch.

    Sends ``Authorization: Bearer <token>`` with the resolved API token (env or
    ``data/secrets/api_token``); empty means the API has no token check, so no header is sent.
    """
    token = resolve_api_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(base_url=settings().api_url, timeout=30.0, headers=headers)


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    async with _client_factory() as client:
        resp = await client.get(path, params={k: v for k, v in (params or {}).items() if v is not None})
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, body: dict[str, Any] | None = None) -> Any:
    async with _client_factory() as client:
        resp = await client.post(path, json=body or {})
        resp.raise_for_status()
        return resp.json()


@mcp.tool
async def search_law(query: str, jurisdiction: str = "MX") -> dict:
    """Ask Aurum's cited legal/tax research over MX/US law and guidance. Cites or abstains."""
    lang = "en" if jurisdiction == "US" else "es"
    return await _post("/api/research/ask", {"question": query, "jurisdiction": jurisdiction, "lang": lang})


@mcp.tool
async def get_law_changes(since: str | None = None, domain: str | None = None) -> list[dict]:
    """List tracked law/guidance changes (optionally since a timestamp, or filtered by domain)."""
    changes = await _get("/api/watch/changes", {"since": since})
    if domain:
        changes = [c for c in changes if domain in (c.get("domains") or [])]
    return changes


@mcp.tool
async def calc_tax(workspace: str, period: str) -> dict:
    """Compute the MX RESICO month-close (income, ISR, IVA, prefill diffs) for period YYYY-MM."""
    return await _get(f"/api/tax/mx/resico/{workspace}/{period}")


@mcp.tool
async def prefill_diff(workspace: str, period: str) -> list[dict]:
    """The prefill-vs-books diffs (uncollected PUE, missing REP, cash-paid expenses, ...)."""
    data = await _get(f"/api/tax/mx/resico/{workspace}/{period}")
    return data.get("diffs", [])


@mcp.tool
async def quick_add(workspace: str, text: str, account_id: str | None = None, commit: bool = False) -> dict:
    """Parse a free-text expense/income line (e.g. '250 tacos comida') into a movement preview on a
    personal account (no Inbox row). ``account_id`` picks the pf account (omit it when the
    workspace has one obvious account or the text names it); ``commit=True`` writes the movement to the
    ledger and returns it with ``status: committed`` — the default is a preview the person confirms."""
    body: dict[str, Any] = {"text": text, "commit": commit}
    if account_id:
        body["account_id"] = account_id
    return await _post(f"/api/ingest/{workspace}/quickadd", body)


@mcp.tool
async def post_entry(workspace: str, txn: dict) -> dict:
    """Append a fully-formed transaction (``aurum.ledger.base.Transaction`` shape) to the ledger."""
    return await _post(f"/api/ledger/{workspace}/transactions", txn)


@mcp.tool
async def balances(workspace: str) -> dict:
    """Current account balances for a workspace, account -> list of {amount, currency}."""
    return await _get(f"/api/ledger/{workspace}/balances")


def _period_bounds(period: str) -> tuple[str, str]:
    year_str, month_str = period.split("-")
    year, month = int(year_str), int(month_str)
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year + 1:04d}-01-01" if month == 12 else f"{year:04d}-{month + 1:02d}-01"
    return start, end


@mcp.tool
async def financial_statement(workspace: str, period: str, type: str = "pnl") -> dict:
    """A P&L or balance-sheet summary for a period, derived from ledger balances/journal.

    ``type="pnl"`` sums Income/Expenses postings that fall inside the period (from the
    journal). ``type="balance_sheet"`` reads Assets/Liabilities/Equity balances as of the
    period's last day.
    """
    start, end = _period_bounds(period)
    if type == "balance_sheet":
        raw = await _get(f"/api/ledger/{workspace}/balances", {"as_of": end})
        accounts = {a: amts for a, amts in raw.items() if a.split(":")[0] in ("Assets", "Liabilities", "Equity")}
        return {"workspace": workspace, "period": period, "type": type, "accounts": accounts}

    txns = await _get(f"/api/ledger/{workspace}/journal", {"start": start, "end": end})
    totals: dict[str, dict[str, Decimal]] = {}
    for txn in txns:
        for posting in txn.get("postings", []):
            account = str(posting.get("account", ""))
            if account.split(":")[0] not in ("Income", "Expenses"):
                continue
            amount = posting.get("amount")
            if not amount:
                continue
            currency = str(amount.get("currency", "MXN"))
            bucket = totals.setdefault(account, {})
            bucket[currency] = bucket.get(currency, Decimal("0")) + Decimal(str(amount.get("amount", "0")))
    accounts = {
        account: [{"amount": str(value), "currency": currency} for currency, value in currencies.items()]
        for account, currencies in totals.items()
    }
    return {"workspace": workspace, "period": period, "type": type, "accounts": accounts}


@mcp.tool
async def goal_status(workspace: str) -> list[dict]:
    """Savings/emergency/debt/purchase goals and their progress for a workspace."""
    return await _get(f"/api/pf/{workspace}/goals")


@mcp.tool
async def budget_status(workspace: str, period: str) -> dict:
    """Budget-vs-actual for a workspace's labels in period YYYY-MM (budgets + safe-to-spend)."""
    return await _get(f"/api/pf/{workspace}/budgets/status", {"period": period})


def main() -> None:
    parser = argparse.ArgumentParser(prog="aurum-mcp")
    parser.add_argument("--http", action="store_true", help="serve streamable-HTTP instead of stdio")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    from ..core.security import install_pii_log_filter, uvicorn_log_config

    install_pii_log_filter()
    resolve_api_token()  # eager: the file token is generated at boot when the bind is exposed
    if args.http:
        import uvicorn

        from .http import build_http_app, mcp_auth_required

        s = settings()
        log.info("aurum-mcp serving streamable-HTTP on %s:%s (auth=%s)", s.mcp_host, s.mcp_port, "on" if mcp_auth_required() else "off")
        uvicorn.run(
            build_http_app(),
            host=s.mcp_host,
            port=s.mcp_port,
            proxy_headers=True,
            forwarded_allow_ips=s.forwarded_allow_ips,
            log_config=uvicorn_log_config(),
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
