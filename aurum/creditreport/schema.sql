-- Credit report imports (module: creditreport). One row per uploaded PDF; parsed accounts/score are
-- stored as JSON since Buró de Crédito layouts vary and this is descriptive, never a filed number.
CREATE TABLE IF NOT EXISTS creditreport_imports (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    score TEXT,                 -- JSON {"value": int, "bureau": str} or null
    accounts TEXT NOT NULL,     -- JSON list[{grantor, type, limit, balance, status, opened}]
    warnings TEXT NOT NULL DEFAULT '[]'  -- JSON list[str]
);
CREATE INDEX IF NOT EXISTS ix_creditreport_imports_ws ON creditreport_imports(ws_id, imported_at);
