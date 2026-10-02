from __future__ import annotations

from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.corpus.ingest import ingest_text
from aurum.corpus.store import open_store


def _client() -> TestClient:
    return TestClient(create_app())


def test_mounted_at_research_prefix():
    app = create_app()
    assert "/api/research" in app.state.mounted


def test_ask_abstains_with_empty_corpus():
    client = _client()
    resp = client.post(
        "/api/research/ask",
        json={"question": "What is the RESICO ISR rate?", "jurisdiction": "MX", "lang": "en"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["abstained"] is True
    assert body["citations"] == []
    assert body["confidence"] == 0.0
    assert "not tax" in body["answer"].lower() or "not advice" in body["answer"].lower() or "advice" in body["answer"].lower()


def test_ask_cites_when_corpus_supports_the_claim():
    store = open_store()
    try:
        ingest_text(
            store,
            "mx-law",
            "Artículo 113-E. Las personas físicas que tributen en el Régimen Simplificado de "
            "Confianza (RESICO) calcularán el ISR mensual aplicando la tabla de tasas sobre los "
            "ingresos efectivamente cobrados, sin deducciones.",
            title="LISR",
            law="LISR",
            jurisdiction="MX",
            doc_type="statute",
            trust_tier="primary",
        )
    finally:
        store.close()

    client = _client()
    resp = client.post(
        "/api/research/ask",
        json={
            "question": "How is ISR calculated monthly under RESICO article 113-E?",
            "jurisdiction": "MX",
            "lang": "en",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["abstained"] is False
    assert body["citations"], "expected at least one citation"
    assert body["citations"][0]["law"] == "LISR"
    assert body["confidence"] > 0
    assert "advice" in body["answer"].lower()


def test_ask_abstains_when_only_low_trust_source_matches():
    store = open_store()
    try:
        ingest_text(
            store,
            "guidance",
            "Artículo 113-E. RESICO ISR se calcula mensualmente sobre ingresos cobrados según un "
            "blog fiscal no oficial que resume el régimen simplificado de confianza.",
            title="blog post",
            law="Blog",
            jurisdiction="MX",
            doc_type="blog",
            trust_tier="blog",
        )
    finally:
        store.close()

    client = _client()
    resp = client.post(
        "/api/research/ask",
        json={
            "question": "How is ISR calculated monthly under RESICO article 113-E?",
            "jurisdiction": "MX",
            "lang": "en",
        },
    )
    body = resp.json()
    assert body["abstained"] is True
    assert body["citations"] == []


def test_ingest_json_url(monkeypatch):
    """The URL branch goes through ``aurum.core.netguard.fetch_public_url``; the
    resolver and the transport are the seams, not ``httpx.get``."""
    import socket

    import httpx

    from aurum.research import router as research_router

    def fake_getaddrinfo(host, port, *a, **k):
        assert host == "example.mx"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<h1>RMF regla 2.9.21</h1><p>Contenido de la regla.</p>")

    monkeypatch.setattr(research_router, "_fetch_transport", lambda: httpx.MockTransport(handler))

    client = _client()
    resp = client.post(
        "/api/research/ingest",
        json={"url": "https://example.mx/rmf", "collection": "guidance", "trust_tier": "official_guidance"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ingested"
    assert body["collection_id"] == "guidance"


def test_collections_endpoint_lists_counts():
    store = open_store()
    try:
        ingest_text(store, "mx-law", "Artículo 1. Texto de prueba.", title="t", law="LISR")
    finally:
        store.close()
    client = _client()
    resp = client.get("/api/research/collections")
    assert resp.status_code == 200
    ids = {c["collection_id"] for c in resp.json()["collections"]}
    assert "mx-law" in ids


def test_ask_falls_back_to_extractive_answer_when_the_model_refuses(monkeypatch):
    """A provider refusal (Claude ``stop_reason: refusal``) still yields a cited, extractive answer."""
    from aurum.llm.exceptions import ProviderRefused
    from aurum.research import router as research_router

    def refuse(*_args, **_kwargs):
        raise ProviderRefused("Claude declined to answer this request (stop_reason=refusal)")

    monkeypatch.setattr(research_router, "generate_text", refuse)
    store = open_store()
    try:
        ingest_text(
            store,
            "mx-law",
            "Artículo 113-E. Las personas físicas que tributen en el Régimen Simplificado de "
            "Confianza (RESICO) calcularán el ISR mensual aplicando la tabla de tasas sobre los "
            "ingresos efectivamente cobrados, sin deducciones.",
            title="LISR",
            law="LISR",
            jurisdiction="MX",
            doc_type="statute",
            trust_tier="primary",
        )
    finally:
        store.close()

    resp = _client().post(
        "/api/research/ask",
        json={"question": "How is ISR calculated monthly under RESICO article 113-E?", "jurisdiction": "MX", "lang": "en"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["abstained"] is False
    assert body["citations"] and body["citations"][0]["law"] == "LISR"
    assert "extractive" in body["answer"].lower()
    assert "ProviderRefused" in body["answer"]
