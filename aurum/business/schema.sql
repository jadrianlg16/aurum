-- business: employee register and payroll runs (module: business).
-- Amounts are stored as TEXT decimals (never REAL/float). RFC and name are PII: they are stored here
-- because payroll needs them, but every log line, audit record and API response masks them.

CREATE TABLE IF NOT EXISTS business_employees (
    id            TEXT PRIMARY KEY,
    ws_id         TEXT NOT NULL,
    name          TEXT NOT NULL,             -- PII: masked in logs and in audit records
    rfc           TEXT,                      -- PII: masked everywhere except the payroll PDF
    curp          TEXT,                      -- PII
    nss           TEXT,                      -- PII: IMSS number
    daily_salary  TEXT NOT NULL DEFAULT '0', -- salario diario (cash wage)
    sbc_daily     TEXT NOT NULL DEFAULT '0', -- salario base de cotización (integrated, LSS art. 27)
    state         TEXT NOT NULL DEFAULT 'NL',-- payroll-tax state; drives which ISN rule applies
    currency      TEXT NOT NULL DEFAULT 'MXN',
    hired_on      TEXT,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_business_employees_ws ON business_employees(ws_id, active);

CREATE TABLE IF NOT EXISTS business_payroll_runs (
    id            TEXT PRIMARY KEY,
    ws_id         TEXT NOT NULL,
    period        TEXT NOT NULL,             -- YYYY-MM
    days          TEXT NOT NULL DEFAULT '30',
    currency      TEXT NOT NULL DEFAULT 'MXN',
    gross         TEXT NOT NULL DEFAULT '0',
    net           TEXT NOT NULL DEFAULT '0',
    isr_retenido  TEXT NOT NULL DEFAULT '0',
    imss_employee TEXT NOT NULL DEFAULT '0',
    imss_employer TEXT NOT NULL DEFAULT '0',
    infonavit     TEXT NOT NULL DEFAULT '0',
    isn           TEXT NOT NULL DEFAULT '0',
    employer_cost TEXT NOT NULL DEFAULT '0',
    txn_id        TEXT,                      -- ledger transaction id, when the ledger write succeeded
    detail_json   TEXT NOT NULL,             -- full per-employee result with Explain, RFC masked
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_business_payroll_runs_ws ON business_payroll_runs(ws_id, period);
