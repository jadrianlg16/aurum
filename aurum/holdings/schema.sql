-- Holdings metadata (module: holdings). Trades are the source of truth for positions/lots/realized
-- gains here; the same events are also appended to the ledger (aurum/holdings/ledger_ext.py) for the
-- "ledger is the truth" cash/asset balances, but cost-basis lot math is computed from this table
-- because base.py's Posting has no cost/price fields yet (see ledger_ext.py).
CREATE TABLE IF NOT EXISTS holdings_trades (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    date TEXT NOT NULL,                 -- YYYY-MM-DD
    account TEXT NOT NULL,              -- investment asset account, e.g. Assets:Investments:Brokerage:VOO
    symbol TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- buy|sell|dividend|interest|contribution
    units TEXT NOT NULL DEFAULT '0',    -- Decimal string, always positive
    price_amount TEXT,                  -- Decimal string, per-unit price (buy/sell)
    price_currency TEXT,
    fees_amount TEXT NOT NULL DEFAULT '0',
    fees_currency TEXT,
    cash_amount TEXT,                   -- Decimal string, cash moved (dividend/interest/contribution)
    cash_currency TEXT,
    counter_account TEXT NOT NULL DEFAULT 'Assets:Bank:Brokerage',
    limit_key TEXT,                     -- contribution kind only: 401k|ira|hsa_self|hsa_family|ppr
    txn_id TEXT,                        -- ledger transaction id, if the ledger write succeeded
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_holdings_trades_ws ON holdings_trades(ws_id, symbol, date);

CREATE TABLE IF NOT EXISTS holdings_symbols (
    ws_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    asset_class TEXT NOT NULL,          -- equity|bond|crypto|cash|other
    currency TEXT NOT NULL DEFAULT 'USD',
    PRIMARY KEY (ws_id, symbol)
);

CREATE TABLE IF NOT EXISTS holdings_prices (
    id TEXT PRIMARY KEY,
    ws_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    price_amount TEXT NOT NULL,
    price_currency TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    UNIQUE(ws_id, symbol, date)
);
CREATE INDEX IF NOT EXISTS ix_holdings_prices_ws_symbol ON holdings_prices(ws_id, symbol, date);

CREATE TABLE IF NOT EXISTS holdings_limits (
    ws_id TEXT NOT NULL,
    key TEXT NOT NULL,                  -- 401k|ira|hsa|ppr
    jurisdiction TEXT NOT NULL,         -- US|MX
    label TEXT NOT NULL,
    year INTEGER NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    citation_law TEXT,
    citation_article TEXT,
    citation_url TEXT,
    PRIMARY KEY (ws_id, key, year)
);
