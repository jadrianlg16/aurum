from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _research_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AURUM_EMBED_MODEL", "hash")
    monkeypatch.setenv("AURUM_EMBED_DIM", "64")
    # Point the LLM at a provider that cannot possibly answer in tests, so /ask always
    # exercises the extractive fallback deterministically (no Ollama dependency here).
    monkeypatch.setenv("AURUM_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("AURUM_LLM_TIMEOUT_S", "1")
    from aurum.core import db

    db.reset_for_tests()
    yield
    db.reset_for_tests()
