from __future__ import annotations

from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.corpus.ingest import ingest_text
from aurum.corpus.store import open_store


def _client() -> TestClient:
    return TestClient(create_app())


# --- POST /ask as_of -------------------------------------------------------


def test_ask_as_of_abstains_before_effective_date():
    store = open_store()
    try:
        ingest_text(
            store,
            "mx-law",
            "Artículo 300. Nueva tasa especial de retención sobre pagos digitales fronterizos.",
            title="future rule",
            law="LISR",
            jurisdiction="MX",
            doc_type="statute",
            trust_tier="primary",
            effective_from="2030-01-01",
        )
    finally:
        store.close()

    client = _client()
    resp = client.post(
        "/api/research/ask",
        json={
            "question": "What is the special withholding rate on cross-border digital payments?",
            "jurisdiction": "MX",
            "lang": "en",
            "as_of": "2026-01-01",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["abstained"] is True


def test_ask_as_of_cites_after_effective_date():
    store = open_store()
    try:
        ingest_text(
            store,
            "mx-law",
            "Artículo 301. Tasa especial de retención sobre pagos digitales fronterizos vigente.",
            title="future rule 2",
            law="LISR",
            jurisdiction="MX",
            doc_type="statute",
            trust_tier="primary",
            effective_from="2030-01-01",
        )
    finally:
        store.close()

    client = _client()
    resp = client.post(
        "/api/research/ask",
        json={
            "question": "special withholding rate cross-border digital payments Artículo 301",
            "jurisdiction": "MX",
            "lang": "en",
            "as_of": "2031-01-01",
        },
    )
    body = resp.json()
    assert body["abstained"] is False
    assert body["citations"]


# --- GET /refs ---------------------------------------------------------


def test_refs_endpoint_returns_cites_and_cited_by():
    store = open_store()
    try:
        ingest_text(
            store, "mx-law",
            "Artículo 29. Los contribuyentes observarán la regla 2.7.2.4. de la RMF vigente.",
            title="CFF 29", law="CFF",
        )
        ingest_text(
            store, "guidance",
            "2.7.2.4. Para los efectos del artículo 29 del CFF, se aplicará este procedimiento.",
            title="RMF rule", law="RMF",
        )
    finally:
        store.close()

    client = _client()
    resp = client.get("/api/research/refs", params={"law": "CFF", "article": "29"})
    assert resp.status_code == 200
    body = resp.json()
    assert any(c["law"] == "RMF" for c in body["cites"])


def test_ask_citations_include_related():
    store = open_store()
    try:
        ingest_text(
            store,
            "mx-law",
            "Artículo 113-E. Las personas físicas que tributen en RESICO calcularán el ISR "
            "mensual, conforme a la regla 2.7.2.4. de la RMF.",
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
    body = resp.json()
    assert body["abstained"] is False
    assert "related" in body["citations"][0]


# --- POST /eval ----------------------------------------------------------


def test_eval_endpoint_runs_and_reports_precision():
    client = _client()
    resp = client.post("/api/research/eval")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 12
    assert 0.0 <= body["precision_at_1"] <= 1.0
    assert len(body["rows"]) == body["total"]
    assert body["correct"] + body["abstained"] <= body["total"]


def test_eval_endpoint_finds_ingested_answers():
    """With the fixtures actually ingested, at least the same-language questions resolve."""
    from pathlib import Path

    from scripts.ingest_law import SOURCES, ingest_offline

    store = open_store()
    try:
        fixtures_dir = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "law"
        for source in SOURCES:
            ingest_offline(store, source, fixtures_dir)
    finally:
        store.close()

    client = _client()
    resp = client.post("/api/research/eval")
    body = resp.json()
    assert body["correct"] >= 5  # same-language questions should resolve even with hash embeddings
