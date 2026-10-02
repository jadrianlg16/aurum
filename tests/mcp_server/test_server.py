from __future__ import annotations

import pytest
from fastmcp import Client

from aurum.mcp_server import server


@pytest.mark.asyncio
async def test_lists_all_expected_tools():
    # fastmcp 3.x: list_tools() returns Tool objects (2.x had get_tools() → dict by name)
    tools = {t.name for t in await server.mcp.list_tools()}
    expected = {
        "search_law",
        "get_law_changes",
        "calc_tax",
        "prefill_diff",
        "quick_add",
        "post_entry",
        "balances",
        "financial_statement",
        "goal_status",
        "budget_status",
    }
    assert expected <= set(tools)


@pytest.mark.asyncio
async def test_balances_tool_calls_ledger_api():
    async with Client(server.mcp) as client:
        result = await client.call_tool("balances", {"workspace": "demo-mx"})
    assert result.structured_content == {}  # empty in-memory ledger for a workspace with no transactions


@pytest.mark.asyncio
async def test_post_entry_then_balances_round_trip():
    txn = {
        "date": "2026-08-01",
        "payee": "Test",
        "narration": "quick add",
        "postings": [
            {"account": "Expenses:Comida", "amount": {"amount": "100.00", "currency": "MXN"}},
            {"account": "Assets:Cash", "amount": {"amount": "-100.00", "currency": "MXN"}},
        ],
    }
    async with Client(server.mcp) as client:
        posted = await client.call_tool("post_entry", {"workspace": "demo-mx", "txn": txn})
        assert "id" in posted.data
        bal = await client.call_tool("balances", {"workspace": "demo-mx"})
    assert "Expenses:Comida" in bal.data
    assert "Assets:Cash" in bal.data


@pytest.mark.asyncio
async def test_search_law_calls_research_ask_and_abstains_on_empty_corpus():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_law", {"query": "RESICO ISR monthly rate", "jurisdiction": "MX"})
    assert result.data["abstained"] is True
    assert result.data["citations"] == []


@pytest.mark.asyncio
async def test_get_law_changes_returns_seeded_fixture():
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_law_changes", {})
    changes = result.structured_content["result"]
    assert len(changes) >= 1
    assert changes[0]["domains"]


@pytest.mark.asyncio
async def test_financial_statement_pnl_sums_postings_in_period():
    txn = {
        "date": "2026-08-05",
        "payee": "Cliente",
        "narration": "venta",
        "postings": [
            {"account": "Income:Ventas", "amount": {"amount": "-500.00", "currency": "MXN"}},
            {"account": "Assets:Cash", "amount": {"amount": "500.00", "currency": "MXN"}},
        ],
    }
    async with Client(server.mcp) as client:
        await client.call_tool("post_entry", {"workspace": "demo-mx", "txn": txn})
        result = await client.call_tool(
            "financial_statement", {"workspace": "demo-mx", "period": "2026-08", "type": "pnl"}
        )
    assert "Income:Ventas" in result.data["accounts"]


@pytest.mark.asyncio
async def test_goal_status_and_budget_status_are_reachable():
    async with Client(server.mcp) as client:
        goals = await client.call_tool("goal_status", {"workspace": "demo-mx"})
        budgets = await client.call_tool("budget_status", {"workspace": "demo-mx", "period": "2026-08"})
    assert isinstance(goals.structured_content["result"], list)
    assert "budgets" in budgets.structured_content

@pytest.mark.asyncio
async def test_quick_add_previews_then_commits_a_pf_entry_on_an_account():
    """Quick-add through MCP: preview by default (no write), commit=True writes the movement."""
    from aurum.core.money import Amount
    from aurum.pf import accounts_admin

    acct = accounts_admin.create_account(
        "demo-mx",
        accounts_admin.AccountIn(name="Efectivo", type="cash", opening_balance=Amount(amount="1000", currency="MXN")),
    )
    async with Client(server.mcp) as client:
        preview = await client.call_tool("quick_add", {"workspace": "demo-mx", "text": "250 tacos comida", "account_id": acct["id"]})
        assert preview.data["status"] == "preview" and preview.data["id"] is None
        committed = await client.call_tool(
            "quick_add", {"workspace": "demo-mx", "text": "250 tacos comida", "account_id": acct["id"], "commit": True}
        )
        assert committed.data["status"] == "committed" and committed.data["id"]
        bal = await client.call_tool("balances", {"workspace": "demo-mx"})
    assert any(k.startswith("Expenses:") for k in bal.data)

