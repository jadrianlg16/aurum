from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _updater_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AURUM_EMBED_MODEL", "hash")
    monkeypatch.setenv("AURUM_EMBED_DIM", "64")
    monkeypatch.delenv("AURUM_WATCH_FAKE_DIR", raising=False)
    from aurum.core import db

    db.reset_for_tests()
    yield
    db.reset_for_tests()
