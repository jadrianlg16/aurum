-- Corpus store, migration 2: as-of versioning + the light cross-reference graph.
-- Idempotent: SQLite has no `ADD COLUMN IF NOT EXISTS`, so the `supersedes` column is added
-- via store.py's migration runner (see MIGRATIONS in store.py) with a guarded ALTER TABLE.
-- corpus_refs itself is a plain CREATE TABLE IF NOT EXISTS.

-- corpus_refs: cross-references detected in chunk text at ingest time (aurum.corpus.refs).
-- One row per reference *mention* found in a chunk, e.g. a chunk of RMF text that mentions
-- "artículo 29 del CFF" produces a row (source_chunk_id=<that chunk>, law='CFF', article='29',
-- kind='cites'). This is a light graph, built by regex over chunk text -- not a citation
-- parser -- good enough for "what else talks about this article" navigation.
CREATE TABLE IF NOT EXISTS corpus_refs (
    ref_id          TEXT PRIMARY KEY,
    source_chunk_id TEXT NOT NULL REFERENCES chunks (chunk_id) ON DELETE CASCADE,
    law             TEXT NOT NULL,   -- e.g. "LISR", "LIVA", "CFF", "RMF", "IRC", "Treas. Reg."
    article         TEXT NOT NULL,   -- e.g. "113-E", "2.7.2.4.", "1402", "1.1402(a)-1"
    kind            TEXT NOT NULL DEFAULT 'cites'  -- 'cites' (mentions another article) — the
                                                    -- only kind detected today; 'defines' is
                                                    -- reserved for a future, more precise pass
);

CREATE INDEX IF NOT EXISTS corpus_refs_chunk ON corpus_refs (source_chunk_id);
CREATE INDEX IF NOT EXISTS corpus_refs_law_article ON corpus_refs (law, article);
