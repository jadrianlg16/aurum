-- core: audit log. Append-only; never UPDATE or DELETE.
CREATE TABLE IF NOT EXISTS core_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    ws_id       TEXT,
    action      TEXT NOT NULL,
    inputs      TEXT NOT NULL,   -- JSON, PII masked
    outputs     TEXT NOT NULL,   -- JSON
    model       TEXT,            -- provider:model if an LLM was involved, else NULL
    rule_versions TEXT           -- JSON list
);
CREATE INDEX IF NOT EXISTS core_audit_ws_ts ON core_audit (ws_id, ts);
