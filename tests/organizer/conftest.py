"""Organizer fixtures: the real ``demo-mx`` workspace plus the organizer's own seeded movements.

Every router test freezes "today" at ``TODAY`` through the test clock: the fixture sets
``AURUM_TEST_CLOCK=1`` and the ``client`` sends ``?today=2026-09-15`` on every request, so the asserted
Decimals never drift with the wall clock. (``httpx.Client.params`` cannot be used for that: since
httpx 0.28 it *replaces* a query string already present in the URL, so ``?kind=income`` would be lost.)
"""

from __future__ import annotations

from datetime import date

import pytest

TODAY = date(2026, 9, 15)  # fixed "now" so every asserted Decimal is reproducible
WS = "demo-mx"


@pytest.fixture()
def demo(tmp_path, monkeypatch):
    """Build ``demo-mx`` in a temp data dir and seed the organizer movements at ``TODAY``."""
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AURUM_TEST_CLOCK", "1")
    from aurum.core import db

    db.reset_for_tests()
    from aurum.demo.generate import build_demo

    build_demo(tmp_path / "data")
    from aurum.organizer.demo_org import seed_demo_org

    seed_demo_org(WS, today=TODAY)
    return WS


class ClockClient:
    """A TestClient wrapper that appends ``today=TODAY`` to every organizer request URL."""

    def __init__(self, app, today: date = TODAY) -> None:
        from fastapi.testclient import TestClient

        self._client = TestClient(app)
        self._today = today.isoformat()

    def _with_today(self, url: str) -> str:
        import httpx

        u = httpx.URL(url)
        if "today" in u.params or not str(u.path).startswith("/api/organizer/"):
            return url
        return str(u.copy_merge_params({"today": self._today}))

    def request(self, method: str, url: str, **kwargs):
        return self._client.request(method, self._with_today(url), **kwargs)

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)


@pytest.fixture()
def client(demo):
    """Every request carries ``today=TODAY`` (organizer routes only — insights routes take no clock)."""
    from aurum.api.app import create_app

    return ClockClient(create_app())
