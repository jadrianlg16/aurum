-- "Mi dinero" money organizer (module: organizer).
-- Amounts are TEXT decimals (never REAL/float). Dates are ISO YYYY-MM-DD.

CREATE TABLE IF NOT EXISTS organizer_commitments (
    id                TEXT PRIMARY KEY,
    ws_id             TEXT NOT NULL,
    kind              TEXT NOT NULL,          -- subscription|bill|utility|rent|insurance|loan_payment|tax|income|transfer|other
    name              TEXT NOT NULL,
    merchant_patterns TEXT NOT NULL DEFAULT '[]',   -- JSON list[str] of normalized merchants
    amount            TEXT NOT NULL,
    currency          TEXT NOT NULL DEFAULT 'MXN',
    amount_variable   INTEGER NOT NULL DEFAULT 0,
    cadence           TEXT NOT NULL,          -- weekly|biweekly|monthly|bimonthly|quarterly|semiannual|annual|custom
    interval_days     INTEGER,
    anchor_day        INTEGER,
    weekday           INTEGER,
    next_due          TEXT NOT NULL,
    account           TEXT NOT NULL DEFAULT 'Assets:Bank',
    account_id        TEXT,                   -- pf_accounts.id (organizer migration v1; resolved server-side)
    label_id          TEXT,
    essential         TEXT NOT NULL DEFAULT 'needs',   -- needs|wants|savings|debt
    status            TEXT NOT NULL DEFAULT 'active',  -- active|paused|cancelled|trial
    trial_ends        TEXT,
    started           TEXT,
    ended             TEXT,
    auto_pay          INTEGER NOT NULL DEFAULT 0,
    cancel_notes      TEXT,
    linked_loan_id    TEXT,
    linked_card_id    TEXT,
    source            TEXT NOT NULL DEFAULT 'manual',  -- detected|manual|imported
    confidence        REAL NOT NULL DEFAULT 1.0,
    last_seen         TEXT,
    notes             TEXT,
    category_hint     TEXT,                   -- streaming|music|cloud|gym|telecom|utility|...
    reviewed_at       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_org_commitments_ws ON organizer_commitments(ws_id, status);

CREATE TABLE IF NOT EXISTS organizer_price_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ws_id         TEXT NOT NULL,
    commitment_id TEXT NOT NULL,
    observed      TEXT NOT NULL,              -- ISO date the amount was seen
    amount        TEXT NOT NULL,
    currency      TEXT NOT NULL DEFAULT 'MXN',
    source        TEXT NOT NULL DEFAULT 'detected',
    UNIQUE(commitment_id, observed, amount)
);
CREATE INDEX IF NOT EXISTS ix_org_price_hist ON organizer_price_history(ws_id, commitment_id, observed);

CREATE TABLE IF NOT EXISTS organizer_occurrences (
    id            TEXT PRIMARY KEY,
    ws_id         TEXT NOT NULL,
    commitment_id TEXT NOT NULL,
    due           TEXT NOT NULL,
    amount        TEXT NOT NULL,
    currency      TEXT NOT NULL DEFAULT 'MXN',
    status        TEXT NOT NULL DEFAULT 'upcoming',  -- upcoming|due|paid|missed|skipped
    txn_id        TEXT,
    marked_at     TEXT,
    entry_id      TEXT,                            -- pf_entries.id backing a "paid" mark (migration v2)
    auto_created  INTEGER NOT NULL DEFAULT 0,      -- 1 when the pf entry was created by the mark itself
    UNIQUE(ws_id, commitment_id, due)
);
CREATE INDEX IF NOT EXISTS ix_org_occurrences ON organizer_occurrences(ws_id, due);

CREATE TABLE IF NOT EXISTS organizer_rules (
    id         TEXT PRIMARY KEY,
    ws_id      TEXT NOT NULL,
    pattern    TEXT NOT NULL,                 -- normalized merchant / payee alias
    label_id   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    hits       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(ws_id, pattern)
);
CREATE INDEX IF NOT EXISTS ix_org_rules_ws ON organizer_rules(ws_id);

CREATE TABLE IF NOT EXISTS organizer_candidates (
    id           TEXT PRIMARY KEY,
    ws_id        TEXT NOT NULL,
    merchant     TEXT NOT NULL,
    preview_json TEXT NOT NULL,               -- Commitment preview, JSON
    evidence_json TEXT NOT NULL,              -- list[{date, amount, description}]
    confidence   REAL NOT NULL DEFAULT 0.0,
    status       TEXT NOT NULL DEFAULT 'open',  -- open|accepted|dismissed
    detected_at  TEXT NOT NULL,
    flags        TEXT NOT NULL DEFAULT '[]',   -- JSON list[str], e.g. ["cancelled_still_charging"] (migration v2)
    existing_commitment_id TEXT,               -- the cancelled commitment a flagged candidate resurfaces
    UNIQUE(ws_id, merchant)
);
CREATE INDEX IF NOT EXISTS ix_org_candidates_ws ON organizer_candidates(ws_id, status);

CREATE TABLE IF NOT EXISTS organizer_settings (
    ws_id       TEXT PRIMARY KEY,
    buffer      TEXT,                          -- Decimal string; NULL = 10% of monthly committed
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organizer_dismissed_alerts (
    ws_id        TEXT NOT NULL,
    alert_id     TEXT NOT NULL,
    dismissed_at TEXT NOT NULL,
    PRIMARY KEY (ws_id, alert_id)
);
