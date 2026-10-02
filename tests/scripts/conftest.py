from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ingest_law_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AURUM_EMBED_MODEL", "hash")
    monkeypatch.setenv("AURUM_EMBED_DIM", "64")
    yield
