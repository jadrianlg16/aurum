from __future__ import annotations

from aurum.pf import accounts


def test_get_accounts_summary_localizes_with_lang_override(ledger):
    es = accounts.get_accounts("ws")
    en = accounts.get_accounts("ws", lang="en")
    assert "Net worth" in en["explain"]["summary"]
    assert "Patrimonio" in es["explain"]["summary"]


def test_router_accounts_endpoint_lang_query(client):
    es = client.get("/api/pf/ws/accounts").json()
    en = client.get("/api/pf/ws/accounts", params={"lang": "en"}).json()
    assert "Patrimonio" in es["explain"]["summary"]
    assert "Net worth" in en["explain"]["summary"]


def test_router_recurring_endpoint_lang_query(client):
    en = client.get("/api/pf/ws/recurring", params={"lang": "en"}).json()
    assert "Recurring bills" in en["explain"]["summary"]
