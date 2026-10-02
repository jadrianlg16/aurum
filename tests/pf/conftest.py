"""pf tests run twice: ``ledger[memory]`` monkeypatches an InMemoryLedger onto every pf
module that calls ``get_ledger()``; ``ledger[beancount]`` leaves ``get_ledger()`` alone so the real
``BeancountLedger`` writes under the autouse tmp ``AURUM_DATA_DIR`` (tests/conftest.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.ledger.base import InMemoryLedger, get_ledger

# every pf module with a module-level ``from ..ledger.base import get_ledger``
PF_LEDGER_MODULES = (
    "accounts", "accounts_admin", "budgets", "entries", "goals", "income", "review", "credit", "streams",
    "ledger_view", "migrations", "onboarding",
)


@pytest.fixture(params=["memory", "beancount"])
def ledger(request, monkeypatch):
    if request.param == "memory":
        led = InMemoryLedger()
        for mod in PF_LEDGER_MODULES:
            monkeypatch.setattr(f"aurum.pf.{mod}.get_ledger", lambda led=led: led, raising=False)
        return led
    return get_ledger()


@pytest.fixture
def client(ledger):
    from aurum.api.app import create_app

    return TestClient(create_app())


@pytest.fixture
def ws(client) -> str:
    """A fresh personal workspace created through the API (so base_currency/language resolve)."""
    r = client.post("/api/workspaces", json={"id": "t-personal", "name": "Test personal", "kind": "personal"})
    assert r.status_code == 200, r.text
    return "t-personal"
