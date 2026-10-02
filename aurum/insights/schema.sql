-- Insights metadata (module: insights). Insight figures are never stored here -- they're recomputed
-- on every request from the ledger/pf/tax data; only dismissal state persists.
CREATE TABLE IF NOT EXISTS insights_dismissed (
    ws_id TEXT NOT NULL,
    insight_id TEXT NOT NULL,
    dismissed_at TEXT NOT NULL,
    PRIMARY KEY (ws_id, insight_id)
);
CREATE INDEX IF NOT EXISTS ix_insights_dismissed_ws ON insights_dismissed(ws_id);
