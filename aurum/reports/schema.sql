CREATE TABLE IF NOT EXISTS reports_archive (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    pack TEXT NOT NULL,
    period TEXT,
    format TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_archive_ws_pack ON reports_archive (ws_id, pack);
