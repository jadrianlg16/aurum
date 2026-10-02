from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.ledger.base import InMemoryLedger


@pytest.fixture
def ledger(monkeypatch):
    led = InMemoryLedger()
    monkeypatch.setattr("aurum.holdings.ledger_ext.get_ledger", lambda led=led: led)
    return led


@pytest.fixture
def client(ledger) -> TestClient:
    from aurum.api.app import create_app

    return TestClient(create_app())
