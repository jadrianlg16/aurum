"""SQLite store for the corpus: connection, WAL, forward-only migrations, row helpers.

The corpus database is ``settings().corpus_db_path`` (``AURUM_DATA_DIR/corpus.db``). It is a
*second* database, separate from ``aurum.db``, because it holds law/guidance material rather
than ledger or workspace state — deleting a source must never touch financial data.

Migrations are forward-only. Add a new ``(version, statements)`` entry to ``MIGRATIONS``;
never edit an applied one. ``schema.sql`` is migration 1 and is idempotent.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core.config import Settings, settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_V2_PATH = Path(__file__).with_name("schema_v2.sql")


class CorpusError(Exception):
    """Any expected failure. Callers turn this into a 400/404 with {"error": ...}."""


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _schema_v2_sql() -> str:
    return SCHEMA_V2_PATH.read_text(encoding="utf-8")


#: version -> list of SQL scripts. Forward-only.
MIGRATIONS: list[tuple[int, list[str]]] = [
    (1, [_schema_sql()]),
    # Migration 2: as-of versioning (sources.supersedes) + the corpus_refs graph table.
    # SQLite has no `ADD COLUMN IF NOT EXISTS`; the ALTER is guarded in CorpusStore.migrate()
    # instead, then this script adds corpus_refs (plain CREATE TABLE IF NOT EXISTS).
    (2, [_schema_v2_sql()]),
]


def corpus_db_path(cfg: Settings | None = None) -> Path:
    cfg = cfg or settings()
    return cfg.corpus_db_path


def collection_sources_dir(collection_id: str, cfg: Settings | None = None) -> Path:
    """``AURUM_DATA_DIR/corpus_sources/<collection_id>/`` — uploaded documents live here."""

    cfg = cfg or settings()
    return cfg.data_dir / "corpus_sources" / collection_id


class CorpusStore:
    """Thin wrapper over a sqlite3 connection with WAL and migrations."""

    def __init__(self, cfg: Settings | None = None, *, db_path: Path | None = None) -> None:
        self.settings = cfg or settings()
        self.db_path = Path(db_path) if db_path else corpus_db_path(self.settings)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: one request may hop between the event loop and a
        # threadpool, and the store is opened/closed per request, so exactly one thread
        # uses it at a time.
        self.conn = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.migrate()

    # --- lifecycle -----------------------------------------------------
    def migrate(self) -> int:
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row[0] for row in self.conn.execute("SELECT version FROM schema_version")}
        for version, scripts in MIGRATIONS:
            if version in applied:
                continue
            if version == 2:
                self._add_column_if_missing("sources", "supersedes", "TEXT")
            for script in scripts:
                self.conn.executescript(script)
            self.conn.execute(
                "INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)",
                (version, utcnow()),
            )
        return self.schema_version()

    def _add_column_if_missing(self, table: str, column: str, decl: str) -> None:
        cols = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def schema_version(self) -> int:
        row = self.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        return int(row["v"] or 0)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> CorpusStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- query helpers -------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, tuple(params))

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, tuple(params)))

    def one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, tuple(params)).fetchone()

    def insert(self, table: str, values: dict[str, Any]) -> None:
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))

    def update(self, table: str, key: dict[str, Any], values: dict[str, Any]) -> None:
        sets = ", ".join(f"{c} = ?" for c in values)
        where = " AND ".join(f"{c} = ?" for c in key)
        self.conn.execute(
            f"UPDATE {table} SET {sets} WHERE {where}",
            (*values.values(), *key.values()),
        )


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def loads(value: str | None, default: Any) -> Any:
    """JSON columns are written by us, but a hand-edited db should not crash a read."""

    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def open_store(cfg: Settings | None = None) -> CorpusStore:
    cfg = cfg or settings()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    return CorpusStore(cfg)


# --- source / chunk reads used across the module -------------------------


def _source_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["meta"] = loads(data.get("meta"), {})
    return data


def chunk_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["locator"] = loads(data.get("locator"), {})
    data["flags"] = loads(data.get("flags"), [])
    return data


def get_source(store: CorpusStore, source_id: str) -> dict[str, Any] | None:
    row = store.one("SELECT * FROM sources WHERE source_id = ?", (source_id,))
    return _source_row(row) if row else None


def list_sources(store: CorpusStore, collection_id: str) -> list[dict[str, Any]]:
    # rowid, not ingested_at: two sources ingested in the same second must still come
    # back in insertion order.
    sql = "SELECT * FROM sources WHERE collection_id = ? ORDER BY rowid"
    return [_source_row(row) for row in store.query(sql, (collection_id,))]


def source_by_sha(store: CorpusStore, collection_id: str, sha256: str) -> dict[str, Any] | None:
    row = store.one(
        "SELECT * FROM sources WHERE collection_id = ? AND sha256 = ?",
        (collection_id, sha256),
    )
    return _source_row(row) if row else None


def latest_source_by_url(
    store: CorpusStore, collection_id: str, url: str, *, exclude_sha256: str | None = None
) -> dict[str, Any] | None:
    """The most recently ingested source in ``collection_id`` at the same ``url``.

    Used to auto-link ``supersedes`` when a re-fetch of the same law/guidance page produces
    new bytes ("as-of" versioning): the prior version at that URL is the
    one this new ingest supersedes.
    """

    if not url:
        return None
    sql = "SELECT * FROM sources WHERE collection_id = ? AND url = ?"
    params: list[Any] = [collection_id, url]
    if exclude_sha256:
        sql += " AND sha256 != ?"
        params.append(exclude_sha256)
    sql += " ORDER BY rowid DESC LIMIT 1"
    row = store.one(sql, params)
    return _source_row(row) if row else None


def source_chain(store: CorpusStore, source_id: str) -> list[dict[str, Any]]:
    """A source and every version it (transitively) supersedes, newest first."""

    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = get_source(store, source_id)
    while current and current["source_id"] not in seen:
        seen.add(current["source_id"])
        chain.append(current)
        prior_id = current.get("supersedes")
        current = get_source(store, prior_id) if prior_id else None
    return chain


CHUNK_SELECT = (
    "SELECT c.*, s.collection_id, s.kind, s.title, s.path_or_url, "
    "s.jurisdiction, s.doc_type, s.law, s.url AS source_url, s.trust_tier, "
    "s.effective_from, s.effective_to "
    "FROM chunks c JOIN sources s ON s.source_id = c.source_id"
)


def get_chunk(store: CorpusStore, chunk_id: str) -> dict[str, Any] | None:
    row = store.one(f"{CHUNK_SELECT} WHERE c.chunk_id = ?", (chunk_id,))
    return chunk_row(row) if row else None


def list_chunks(
    store: CorpusStore,
    collection_id: str,
    *,
    source_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    sql = f"{CHUNK_SELECT} WHERE s.collection_id = ?"
    params: list[Any] = [collection_id]
    if source_id:
        sql += " AND c.source_id = ?"
        params.append(source_id)
    sql += " ORDER BY s.rowid, c.ordinal"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return [chunk_row(row) for row in store.query(sql, params)]


def get_structure(
    store: CorpusStore, collection_id: str, *, source_id: str | None = None
) -> list[dict[str, Any]]:
    sql = (
        "SELECT st.*, s.title AS source_title, s.kind "
        "FROM structure st JOIN sources s ON s.source_id = st.source_id WHERE s.collection_id = ?"
    )
    params: list[Any] = [collection_id]
    if source_id:
        sql += " AND st.source_id = ?"
        params.append(source_id)
    sql += " ORDER BY s.rowid, st.ordinal"
    out: list[dict[str, Any]] = []
    for row in store.query(sql, params):
        data = dict(row)
        data["locator"] = loads(data.get("locator"), {})
        out.append(data)
    return out


def delete_source(store: CorpusStore, source_id: str) -> bool:
    """Cascades to chunks (and, via the FTS triggers, to the index) and structure."""

    cur = store.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))
    return cur.rowcount > 0
