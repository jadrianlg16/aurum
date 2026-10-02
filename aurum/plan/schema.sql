-- Saved scenario runs (module: plan). Balances/tax figures are recomputed on demand, never cached here
-- as truth; this table only stores the user's named input sets so they can be reopened/rerun.
CREATE TABLE IF NOT EXISTS plan_saved (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    name TEXT NOT NULL,
    inputs TEXT NOT NULL,          -- JSON
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_plan_saved_ws ON plan_saved(ws_id);
