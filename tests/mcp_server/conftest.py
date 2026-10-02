from __future__ import annotations

import httpx
import pytest

from aurum.api.app import create_app
from aurum.mcp_server import server


@pytest.fixture(autouse=True)
def _mcp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AURUM_EMBED_MODEL", "hash")
    monkeypatch.setenv("AURUM_EMBED_DIM", "64")
    from aurum.core import db

    db.reset_for_tests()

    app = create_app()

    def _fake_client_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")

    monkeypatch.setattr(server, "_client_factory", _fake_client_factory)
    yield
    db.reset_for_tests()
