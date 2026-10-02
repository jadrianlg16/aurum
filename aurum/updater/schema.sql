-- Law/rule tracker metadata (module: updater). Never overwrites a corpus source version;
-- a change always creates a NEW corpus source for the fetched text.
CREATE TABLE IF NOT EXISTS updater_snapshots (
    source_id TEXT NOT NULL,              -- sources.yml id, e.g. "dof-daily"
    fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    PRIMARY KEY (source_id, fetched_at)
);
CREATE INDEX IF NOT EXISTS ix_updater_snapshots_source ON updater_snapshots(source_id);

CREATE TABLE IF NOT EXISTS updater_changes (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    summary TEXT NOT NULL,
    domains TEXT NOT NULL DEFAULT '[]',       -- JSON list[str] (RESICO, IVA, CFDI, ...)
    diff_excerpt TEXT NOT NULL DEFAULT '',
    corpus_source_id TEXT,                    -- the new aurum.corpus source this change was indexed as
    effective_from TEXT
);
CREATE INDEX IF NOT EXISTS ix_updater_changes_source ON updater_changes(source_id);
CREATE INDEX IF NOT EXISTS ix_updater_changes_detected ON updater_changes(detected_at);

CREATE TABLE IF NOT EXISTS updater_proposals (
    id TEXT PRIMARY KEY,
    change_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',  -- proposed|accepted|rejected — never auto-applied
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_updater_proposals_change ON updater_proposals(change_id);
