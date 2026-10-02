-- satsync: job tracking. The vault itself lives on disk (encrypted blob), not in this DB.
CREATE TABLE IF NOT EXISTS satsync_jobs (
    id          TEXT PRIMARY KEY,
    ws_id       TEXT NOT NULL,
    kind        TEXT NOT NULL,           -- emitidos|recibidos
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|requested|verifying|ready|downloaded|error
    request_id  TEXT,
    downloaded  INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS satsync_jobs_ws ON satsync_jobs (ws_id, created_at);
