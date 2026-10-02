-- Corpus store: the law/guidance material Aurum cites against.
-- Migration 1. Idempotent: every statement is CREATE ... IF NOT EXISTS.
--
-- NOTE: this schema lives in its own database (settings().corpus_db_path), opened directly
-- by aurum.corpus.store.CorpusStore. It is NOT meant to be applied to aurum.db, but
-- aurum.core.db.schema_files() globs every "aurum/*/schema.sql" it finds and applies it to
-- the shared metadata db as well; that is harmless here (idempotent CREATE IF NOT EXISTS,
-- and nothing else in aurum ever queries these tables from aurum.db).

CREATE TABLE IF NOT EXISTS sources (
    source_id      TEXT PRIMARY KEY,
    collection_id  TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('pdf', 'md', 'txt', 'html')),
    title          TEXT NOT NULL,
    path_or_url    TEXT NOT NULL,
    sha256         TEXT NOT NULL,
    ingested_at    TEXT NOT NULL,
    -- Defaults applied to every chunk of this source unless the chunk overrides them
    -- (e.g. `article`, tagged per-chunk by the statute/rule splitter at ingest time).
    jurisdiction   TEXT NOT NULL DEFAULT '',
    doc_type       TEXT NOT NULL DEFAULT '',
    law            TEXT NOT NULL DEFAULT '',
    url            TEXT NOT NULL DEFAULT '',
    trust_tier     TEXT NOT NULL DEFAULT 'primary',
    effective_from TEXT,
    effective_to   TEXT,
    meta           TEXT NOT NULL DEFAULT '{}'
);

-- Dedupe key: the same bytes ingested twice for one collection is one source.
CREATE UNIQUE INDEX IF NOT EXISTS sources_collection_sha256 ON sources (collection_id, sha256);
CREATE INDEX IF NOT EXISTS sources_collection ON sources (collection_id);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id   TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES sources (source_id) ON DELETE CASCADE,
    ordinal    INTEGER NOT NULL,
    locator    TEXT NOT NULL DEFAULT '{}',  -- JSON: {"page":14} {"heading":"..."} {"para":3}
    text       TEXT NOT NULL,
    tokens_est INTEGER NOT NULL DEFAULT 0,
    flags      TEXT NOT NULL DEFAULT '[]',  -- JSON array from sanitize.scan()
    -- Citation fields resolved onto aurum.core.explain.Citation. `article`/`section` are
    -- per-chunk (tagged by the statute/RMF-rule splitter, see ingest.detect_article);
    -- everything else falls back to the parent source's default when NULL/empty.
    article    TEXT NOT NULL DEFAULT '',
    section    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS chunks_source ON chunks (source_id, ordinal);
CREATE INDEX IF NOT EXISTS chunks_article ON chunks (article);

-- External-content FTS5: the text lives in `chunks`, the index mirrors it via triggers.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5 (
    text,
    content = 'chunks',
    content_rowid = 'rowid',
    tokenize = 'unicode61'
);

CREATE TRIGGER IF NOT EXISTS chunks_fts_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts (rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO chunks_fts (rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT NOT NULL REFERENCES chunks (chunk_id) ON DELETE CASCADE,
    model    TEXT NOT NULL,
    dim      INTEGER NOT NULL,
    vec      BLOB NOT NULL,      -- float32 little-endian, `dim` values
    PRIMARY KEY (chunk_id, model)
);

-- The document's own outline (headings / pages); kept because it is cheap and useful for a
-- sources browser UI.
CREATE TABLE IF NOT EXISTS structure (
    source_id TEXT NOT NULL REFERENCES sources (source_id) ON DELETE CASCADE,
    ordinal   INTEGER NOT NULL,
    level     INTEGER NOT NULL,
    title     TEXT NOT NULL,
    locator   TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (source_id, ordinal)
);
