from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from aurum.api.app import create_app

    return TestClient(create_app())
