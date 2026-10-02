from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fake_fx_dir(tmp_path, monkeypatch):
    d = tmp_path / "fx_fixtures"
    d.mkdir()
    (d / "USD_MXN.json").write_text(
        json.dumps({"2026-01-02": "17.10", "2026-01-10": "17.35"}), encoding="utf-8"
    )
    monkeypatch.setenv("AURUM_FX_FAKE_DIR", str(d))
    return d


@pytest.fixture
def client() -> TestClient:
    from aurum.api.app import create_app

    return TestClient(create_app())
