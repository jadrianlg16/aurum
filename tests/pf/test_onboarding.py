from __future__ import annotations

from datetime import date

from aurum.core.money import Amount
from aurum.pf import accounts_admin, entries, onboarding, streams


def test_fresh_workspace_is_not_done(ledger):
    out = onboarding.get_onboarding("ws")
    assert [s["id"] for s in out["steps"]] == ["accounts", "income", "recurring", "first_entries"]
    by_id = {s["id"]: s for s in out["steps"]}
    assert by_id["accounts"]["done"] is False
    assert by_id["income"]["done"] is False
    assert by_id["first_entries"]["done"] is False
    assert out["done"] is False


def test_done_once_an_account_and_a_first_entry_exist(ledger):
    """done = accounts && first_entries; an income stream alone is not enough."""
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Cuenta", type="checking"))
    streams.create_stream(
        "ws",
        streams.IncomeStreamIn(
            name="Sueldo", source_type="salary", amount=Amount(amount="10000"), cadence="monthly",
            anchor_days=[1], account_id=acct["id"],
        ),
        today=date(2026, 1, 1),
    )
    out = onboarding.get_onboarding("ws")
    assert out["done"] is False
    entries.create_entry(
        "ws", entries.EntryIn(kind="expense", date="2026-01-05", amount=Amount(amount="55"), account_id=acct["id"]),
    )
    out = onboarding.get_onboarding("ws")
    assert out["done"] is True
    assert {s["id"]: s["count"] for s in out["steps"]}["first_entries"] == 1


def test_router_onboarding_endpoint(client):
    r = client.get("/api/pf/ws/onboarding")
    assert r.status_code == 200
    body = r.json()
    assert "steps" in body and "done" in body
    assert ["accounts", "income", "recurring", "first_entries"] == [s["id"] for s in body["steps"]]
