"""Fetch a watched source, hash it against the last snapshot, and act on a real change.

On a change: the fetched text is ingested into ``aurum.corpus`` as a brand-new source
version (never overwriting the previous one — the "nothing is deleted" principle
extends here: old law stays retrievable with its own effective range), and a row is
recorded in ``updater_changes``. ``triage`` then tags it with domains and, if it looks
like a rate/threshold changed, drafts a proposal — never applies one.

``Fetcher`` is a tiny protocol so tests (and ``AURUM_WATCH_FAKE_DIR``) never need the
network: ``FakeFetcher`` returns canned text per source id.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
import yaml

from ..core.db import connect
from ..corpus.ingest import ingest_text
from ..corpus.store import open_store
from . import triage

SOURCES_PATH = Path(__file__).with_name("sources.yml")


def load_sources() -> list[dict[str, Any]]:
    return yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8")) or []


def source_by_id(source_id: str) -> dict[str, Any] | None:
    for source in load_sources():
        if source["id"] == source_id:
            return source
    return None


class Fetcher(Protocol):
    def fetch(self, source: dict[str, Any]) -> str: ...


class HttpFetcher:
    """A polite, honest GET: identifying User-Agent, 20s timeout, one URL per source.

    This does NOT enumerate "today's DOF entries" or paginate a bulk index — for
    ``fetch_method: bulk``/``scrape`` sources it only detects "the index page changed",
    which is enough to raise a flag for a human, not enough to auto-extract which
    specific document changed. A real per-source scraper is future work (see
    ``docs/modules/updater.md``).
    """

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def fetch(self, source: dict[str, Any]) -> str:
        resp = httpx.get(
            source["url"],
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "aurum-updater/0.1 (self-hosted personal finance tool; low volume)"},
        )
        resp.raise_for_status()
        return resp.text


class FakeFetcher:
    """Test/offline fetcher: source id -> canned text. Never touches the network."""

    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts

    def fetch(self, source: dict[str, Any]) -> str:
        return self.texts.get(source["id"], "")


def fake_fetcher_from_dir(directory: Path) -> FakeFetcher:
    """Builds a FakeFetcher from ``<directory>/<source_id>.txt`` files (AURUM_WATCH_FAKE_DIR)."""

    texts: dict[str, str] = {}
    if directory.is_dir():
        for path in directory.glob("*.txt"):
            texts[path.stem] = path.read_text(encoding="utf-8")
    return FakeFetcher(texts)


def default_fetcher() -> Fetcher:
    """The same "fake dir if set, else real HTTP" choice ``router.run`` and the scheduler
    both make: ``AURUM_WATCH_FAKE_DIR`` keeps every automatic/background code path offline
    in tests without threading a fetcher through every caller."""

    fake_dir = os.environ.get("AURUM_WATCH_FAKE_DIR")
    if fake_dir:
        return fake_fetcher_from_dir(Path(fake_dir))
    return HttpFetcher()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def last_snapshot(source_id: str) -> dict[str, Any] | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM updater_snapshots WHERE source_id = ? ORDER BY fetched_at DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_snapshot(source_id: str, content_hash: str, size: int) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO updater_snapshots (source_id, fetched_at, content_hash, bytes) "
            "VALUES (?, ?, ?, ?)",
            # Microsecond precision: `(source_id, fetched_at)` is the primary key, and two
            # fetches of the same source in the same second (as in a fast test loop) must
            # not collide and silently overwrite each other's snapshot row.
            (source_id, datetime.now(UTC).isoformat(timespec="microseconds"), content_hash, size),
        )
        conn.commit()
    finally:
        conn.close()


def save_change(
    source_id: str,
    summary: str,
    domains: list[str],
    diff_excerpt: str,
    corpus_source_id: str | None,
    effective_from: str | None,
) -> dict[str, Any]:
    change_id = f"chg_{uuid.uuid4().hex[:12]}"
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO updater_changes "
            "(id, source_id, detected_at, summary, domains, diff_excerpt, corpus_source_id, effective_from) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                change_id,
                source_id,
                datetime.now(UTC).isoformat(timespec="seconds"),
                summary,
                json.dumps(domains),
                diff_excerpt,
                corpus_source_id,
                effective_from,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": change_id,
        "source_id": source_id,
        "summary": summary,
        "domains": domains,
        "diff_excerpt": diff_excerpt,
        "corpus_source_id": corpus_source_id,
        "effective_from": effective_from,
    }


def _collection_for(source: dict[str, Any]) -> str:
    if source.get("doc_type") == "statute" and source.get("jurisdiction") == "MX":
        return "mx-law"
    if source.get("doc_type") == "statute" and source.get("jurisdiction") == "US":
        return "us-law"
    return "guidance"


def run_one(source: dict[str, Any], fetcher: Fetcher) -> dict[str, Any] | None:
    """Fetch one source. Returns the change dict if the content actually changed,
    else ``None`` (first-ever fetch just lays down the baseline snapshot)."""

    text = fetcher.fetch(source)
    digest = _hash(text)
    previous = last_snapshot(source["id"])
    save_snapshot(source["id"], digest, len(text.encode("utf-8")))
    if previous is None or previous["content_hash"] == digest:
        return None

    collection = _collection_for(source)
    store = open_store()
    try:
        ingested = ingest_text(
            store,
            collection,
            text,
            title=f"{source['name']} ({datetime.now(UTC).date().isoformat()})",
            kind="html" if "<html" in text[:500].lower() or "<h1" in text[:500].lower() else "txt",
            path_or_url=source["url"],
            jurisdiction=source.get("jurisdiction", ""),
            doc_type=source.get("doc_type", ""),
            law=source["name"],
            url=source["url"],
            trust_tier=source.get("trust_tier", "primary"),
        )
    finally:
        store.close()

    domains = triage.detect_domains(text)
    summary = triage.summarize(source, text, domains)
    change = save_change(
        source["id"],
        summary,
        domains,
        text[:280],
        ingested.get("source_id"),
        None,
    )
    triage.propose_from_change(change["id"], text, domains)
    return change


def run(source_id: str | None, fetcher: Fetcher) -> dict[str, Any]:
    sources = load_sources()
    if source_id:
        sources = [s for s in sources if s["id"] == source_id]
        if not sources:
            raise ValueError(f"unknown source {source_id!r}")

    ran: list[str] = []
    changed: list[dict[str, Any]] = []
    for source in sources:
        ran.append(source["id"])
        change = run_one(source, fetcher)
        if change:
            changed.append(change)
    return {"ran": ran, "changed": changed}
