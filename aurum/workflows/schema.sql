-- Workflow definitions, runs, and per-run steps (module: workflows).
CREATE TABLE IF NOT EXISTS workflows_defs (
    ws_id TEXT NOT NULL,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    yaml TEXT NOT NULL,
    schedule TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (ws_id, id)
);

CREATE TABLE IF NOT EXISTS workflows_runs (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    params TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_workflows_runs_ws_wf ON workflows_runs (ws_id, workflow_id);

CREATE TABLE IF NOT EXISTS workflows_steps (
    run_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    step_id TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    response_excerpt TEXT,
    error TEXT,
    PRIMARY KEY (run_id, step_index)
);
