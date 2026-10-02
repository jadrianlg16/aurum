-- FX rate cache (module: fx). Source of truth for a given (base, quote, date) is whichever provider
-- filled it first; re-fetching does not overwrite a cached row.
CREATE TABLE IF NOT EXISTS fx_rates (
    id TEXT PRIMARY KEY,
    base TEXT NOT NULL,
    quote TEXT NOT NULL,
    date TEXT NOT NULL,             -- YYYY-MM-DD
    rate TEXT NOT NULL,             -- Decimal string: 1 base = rate quote
    source TEXT NOT NULL DEFAULT 'manual',
    UNIQUE(base, quote, date)
);
CREATE INDEX IF NOT EXISTS ix_fx_rates_pair_date ON fx_rates(base, quote, date);
