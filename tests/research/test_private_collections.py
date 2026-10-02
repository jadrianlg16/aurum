"""Per-workspace private corpus collections: ``ws:{id}`` is only searched
or listed when the request names that workspace, and cannot be ingested into for another one.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.corpus.ingest import ingest_text
from aurum.corpus.store import open_store

PRIVATE_TEXT = (
    "Nota privada del cliente Acme: el flujo de efectivo de julio bajó 12% por un litigio "
    "confidencial que no debe compartirse fuera del despacho."
)


def _client() -> TestClient:
    return TestClient(create_app())


def _seed_private(ws_id: str) -> None:
    store = open_store()
    try:
        ingest_text(
            store,
            f"ws:{ws_id}",
            PRIVATE_TEXT,
            title="private note",
            law="Nota",
            jurisdiction="MX",
            doc_type="note",
            trust_tier="primary",
        )
    finally:
        store.close()


def test_ask_without_workspace_never_sees_a_private_collection():
    _seed_private("ws-a")
    client = _client()
    resp = client.post(
        "/api/research/ask",
        json={"question": "flujo de efectivo litigio confidencial Acme", "jurisdiction": "MX", "lang": "es"},
    )
    assert resp.status_code == 200
    assert resp.json()["abstained"] is True


def test_ask_from_owning_workspace_can_see_its_own_private_collection():
    _seed_private("ws-a")
    client = _client()
    resp = client.post(
        "/api/research/ask",
        json={
            "question": "flujo de efectivo litigio confidencial Acme",
            "jurisdiction": "MX",
            "lang": "es",
            "workspace": "ws-a",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["abstained"] is False


def test_ask_from_a_different_workspace_cannot_see_anothers_private_collection():
    _seed_private("ws-a")
    client = _client()
    resp = client.post(
        "/api/research/ask",
        json={
            "question": "flujo de efectivo litigio confidencial Acme",
            "jurisdiction": "MX",
            "lang": "es",
            "workspace": "ws-b",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["abstained"] is True


def test_collections_endpoint_hides_private_collection_from_other_workspaces():
    _seed_private("ws-a")
    client = _client()
    resp = client.get("/api/research/collections")
    ids = {c["collection_id"] for c in resp.json()["collections"]}
    assert "ws:ws-a" not in ids

    resp = client.get("/api/research/collections", headers={"X-Aurum-Workspace": "ws-b"})
    ids = {c["collection_id"] for c in resp.json()["collections"]}
    assert "ws:ws-a" not in ids

    resp = client.get("/api/research/collections", headers={"X-Aurum-Workspace": "ws-a"})
    ids = {c["collection_id"] for c in resp.json()["collections"]}
    assert "ws:ws-a" in ids


def test_ingest_into_someone_elses_private_collection_is_forbidden():
    client = _client()
    resp = client.post(
        "/api/research/ingest",
        data={"collection": "ws:ws-a"},
        files={"file": ("note.txt", b"secret", "text/plain")},
        headers={"X-Aurum-Workspace": "ws-b"},
    )
    assert resp.status_code == 403


def test_ingest_into_own_private_collection_succeeds():
    client = _client()
    resp = client.post(
        "/api/research/ingest",
        data={"collection": "ws:ws-a"},
        files={"file": ("note.txt", PRIVATE_TEXT.encode("utf-8"), "text/plain")},
        headers={"X-Aurum-Workspace": "ws-a"},
    )
    assert resp.status_code == 200
