from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from aurum.api.app import create_app

    return TestClient(create_app())


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """The synthetic ``demo-biz`` quarter, built into this test's own data dir."""
    from aurum.business.demo_biz import build_demo_biz

    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    return build_demo_biz(tmp_path / "data")
