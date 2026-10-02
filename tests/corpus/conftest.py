"""Corpus test fixtures: a temp AURUM_DATA_DIR and the offline hash embedding backend.

Mirrors ``tests/conftest.py``'s ``_tmp_data_dir`` pattern. ``AURUM_EMBED_MODEL=hash`` means
no test in this package ever needs a running Ollama.
"""

from __future__ import annotations

import pytest

from aurum.corpus.store import CorpusStore, open_store


@pytest.fixture(autouse=True)
def _tmp_corpus_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AURUM_EMBED_MODEL", "hash")
    monkeypatch.setenv("AURUM_EMBED_DIM", "64")
    yield


@pytest.fixture
def store() -> CorpusStore:
    st = open_store()
    yield st
    st.close()
