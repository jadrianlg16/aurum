"""Shared fixtures: every test runs against a temporary AURUM_DATA_DIR with the security posture reset.

``AURUM_ALLOWED_HOSTS=testserver`` keeps Starlette's TestClient (Host: testserver) inside the
loopback-mode Host allow-list of ``aurum.core.guards.HostOriginGuard``; the guard's own tests
override it. The auth/bind/origin/cache variables are cleared so a developer's shell never
changes what a test sees.
"""

from __future__ import annotations

import pytest

_CLEARED = (
    "AURUM_API_TOKEN",
    "AURUM_BIND",
    "AURUM_REQUIRE_TOKEN",
    "AURUM_ALLOWED_ORIGINS",
    "AURUM_LEDGER_CACHE",
    "AURUM_MCP_TOKEN",
    "AURUM_MCP_HOST",
)


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AURUM_ALLOWED_HOSTS", "testserver")
    for name in _CLEARED:
        monkeypatch.delenv(name, raising=False)
    from aurum.core import db

    db.reset_for_tests()
    try:
        from aurum.ledger import cache as ledger_cache

        ledger_cache.clear()
    except ImportError:  # no ledger cache module
        pass
    yield
    db.reset_for_tests()
