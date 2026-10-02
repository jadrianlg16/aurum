
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.workspaces import Workspace, save_workspace


def _client() -> TestClient:
    save_workspace(Workspace(id="demo-mx", name="Demo"))
    return TestClient(create_app())


def test_vault_store_status_delete():
    client = _client()
    resp = client.post(
        "/api/satsync/demo-mx/vault",
        data={"password": "ciec", "passphrase": "pp"},
        files={"cer": ("e.cer", b"CER", "application/octet-stream"), "key": ("e.key", b"KEY", "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["present"] is True

    status = client.get("/api/satsync/demo-mx/vault").json()
    assert status["present"] is True
    assert "CER" not in str(status) and "KEY" not in str(status) and "pp" not in str(status)

    deleted = client.delete("/api/satsync/demo-mx/vault").json()
    assert deleted["purged"] is True
    assert client.get("/api/satsync/demo-mx/vault").json()["present"] is False


def test_sync_with_fake_sat(tmp_path, monkeypatch):
    fixtures = tmp_path / "fixtures"
    (fixtures / "recibidos").mkdir(parents=True)
    (fixtures / "recibidos" / "a.xml").write_text("<x/>", encoding="utf-8")
    monkeypatch.setenv("AURUM_SAT_FAKE_DIR", str(fixtures))

    client = _client()
    resp = client.post(
        "/api/satsync/demo-mx/sync",
        json={"start": "2026-08-01", "end": "2026-08-31", "kind": "recibidos", "passphrase": "unused"},
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "downloaded"
    assert job["downloaded"] == 1

    jobs = client.get("/api/satsync/demo-mx/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job["id"]


def test_sync_without_vault_400(monkeypatch):
    monkeypatch.delenv("AURUM_SAT_FAKE_DIR", raising=False)
    client = _client()
    resp = client.post(
        "/api/satsync/demo-mx/sync",
        json={"start": "2026-08-01", "end": "2026-08-31", "kind": "emitidos", "passphrase": "pp"},
    )
    assert resp.status_code == 400
