-- Personal finance metadata tables (module: pf). Balances always come from the ledger, never stored here.
CREATE TABLE IF NOT EXISTS pf_labels (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',   -- JSON list[str]
    account TEXT NOT NULL,
    icon TEXT,
    tax TEXT NOT NULL DEFAULT '{}',       -- JSON {"MX": {...}, "US": {...}}
    sort INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'expense', -- expense|income|transfer (pf migration v1)
    archived INTEGER NOT NULL DEFAULT 0   -- pf migration v1
);
CREATE INDEX IF NOT EXISTS ix_pf_labels_ws ON pf_labels(ws_id);

CREATE TABLE IF NOT EXISTS pf_budgets (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    label_id TEXT NOT NULL,
    period TEXT NOT NULL,                 -- YYYY-MM
    amount TEXT NOT NULL,                 -- Decimal string
    currency TEXT NOT NULL DEFAULT 'MXN',
    rollover INTEGER NOT NULL DEFAULT 0,
    UNIQUE(ws_id, label_id, period)
);
CREATE INDEX IF NOT EXISTS ix_pf_budgets_ws_period ON pf_budgets(ws_id, period);

CREATE TABLE IF NOT EXISTS pf_goals (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    kind TEXT NOT NULL,                   -- savings|emergency|debt|purchase
    name TEXT NOT NULL,
    target TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'MXN',
    target_date TEXT,                     -- YYYY-MM-DD
    account TEXT NOT NULL,
    created_at TEXT NOT NULL,
    account_id TEXT                       -- pf_accounts.id (pf migration v2)
);
CREATE INDEX IF NOT EXISTS ix_pf_goals_ws ON pf_goals(ws_id);

CREATE TABLE IF NOT EXISTS pf_credit_cards (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    account TEXT NOT NULL,
    name TEXT NOT NULL,
    cut_day INTEGER NOT NULL,
    due_day INTEGER NOT NULL,
    limit_amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'MXN',
    apr TEXT
);
CREATE INDEX IF NOT EXISTS ix_pf_cards_ws ON pf_credit_cards(ws_id);

CREATE TABLE IF NOT EXISTS pf_loans (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    account TEXT NOT NULL,
    name TEXT NOT NULL,
    principal TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'MXN',
    annual_rate TEXT NOT NULL,
    months INTEGER NOT NULL,
    start TEXT NOT NULL                   -- YYYY-MM-DD
);
CREATE INDEX IF NOT EXISTS ix_pf_loans_ws ON pf_loans(ws_id);

CREATE TABLE IF NOT EXISTS pf_msi (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    card_id TEXT NOT NULL,
    purchase TEXT NOT NULL,               -- description
    amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'MXN',
    months INTEGER NOT NULL,
    started TEXT NOT NULL,                -- YYYY-MM-DD, first installment month
    paid_months INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_pf_msi_card ON pf_msi(card_id);

CREATE TABLE IF NOT EXISTS pf_credit_scores (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    bureau TEXT NOT NULL,
    score INTEGER NOT NULL,
    date TEXT NOT NULL                    -- YYYY-MM-DD
);
CREATE INDEX IF NOT EXISTS ix_pf_scores_ws ON pf_credit_scores(ws_id);

-- Manual-first personal finance -------------------------------------------------------------------

-- Friendly account registry: id <-> ledger account. Balances are never stored here, only in the ledger.
CREATE TABLE IF NOT EXISTS pf_accounts (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,                   -- checking|savings|cash|credit_card|loan|investment|other
    institution TEXT,
    currency TEXT NOT NULL DEFAULT 'MXN',
    account TEXT NOT NULL,                -- derived ledger account name, e.g. Assets:Bank:BbvaNomina
    credit_limit TEXT,
    cut_day INTEGER,
    due_day INTEGER,
    apr TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pf_accounts_ws ON pf_accounts(ws_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pf_accounts_ledger ON pf_accounts(ws_id, account);

-- The human transaction API. Ledger stays the store of record; this table maps a friendly entry to
-- the ledger transaction(s) that implement it (``txn_id`` links into ``Transaction.links``).
CREATE TABLE IF NOT EXISTS pf_entries (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    kind TEXT NOT NULL,                   -- expense|income|transfer
    date TEXT NOT NULL,
    amount TEXT NOT NULL,                 -- Decimal string, always the positive magnitude
    currency TEXT NOT NULL DEFAULT 'MXN',
    account_id TEXT NOT NULL,
    to_account_id TEXT,
    label_id TEXT,
    payee TEXT,
    note TEXT,
    tags TEXT NOT NULL DEFAULT '[]',      -- JSON list[str]
    splits TEXT NOT NULL DEFAULT '[]',    -- JSON list[{label_id, amount, note?}]
    source TEXT NOT NULL DEFAULT 'manual', -- manual|quickadd|import|cfdi|payroll|organizer
    txn_id TEXT NOT NULL,
    voided INTEGER NOT NULL DEFAULT 0,
    editable INTEGER NOT NULL DEFAULT 1,
    non_editable_reason TEXT,
    attachment TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    commitment_id TEXT                    -- organizer_commitments.id (pf migration v3)
);
CREATE INDEX IF NOT EXISTS ix_pf_entries_ws_date ON pf_entries(ws_id, date);
CREATE INDEX IF NOT EXISTS ix_pf_entries_ws_account ON pf_entries(ws_id, account_id);
-- ix_pf_entries_ws_commitment is created by pf migration v3 (schemas run before migrations on old DBs).

-- Income streams a person sets up by hand. Mirrored 1:1 (or 2:1 for semimonthly, one per anchor day)
-- into organizer commitments of kind "income" so the calendar/forecast pick them up for free.
CREATE TABLE IF NOT EXISTS pf_income_streams (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,            -- salary|freelance|rent|pension|investment|other
    amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'MXN',
    gross_amount TEXT,
    cadence TEXT NOT NULL,                -- monthly|semimonthly|biweekly|weekly|annual|irregular
    anchor_days TEXT NOT NULL DEFAULT '[]', -- JSON list[int], 31 = last day of month
    weekday INTEGER,
    next_expected TEXT,
    account_id TEXT NOT NULL,
    label_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    commitment_ids TEXT NOT NULL DEFAULT '[]', -- JSON list[str] of mirrored organizer_commitments.id
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pf_income_streams_ws ON pf_income_streams(ws_id);
