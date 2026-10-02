-- ingest: CFDI store, bank lines, bank column mappings, and the review Inbox.
-- Amounts are stored as TEXT decimals (never REAL/float).

CREATE TABLE IF NOT EXISTS ingest_cfdi (
    uuid                TEXT PRIMARY KEY,
    ws_id               TEXT NOT NULL,
    tipo                TEXT NOT NULL,           -- I|E|P|N|T
    direction           TEXT NOT NULL,           -- emitido|recibido
    fecha               TEXT NOT NULL,           -- ISO datetime
    emisor_rfc          TEXT NOT NULL,
    receptor_rfc        TEXT NOT NULL,
    subtotal            TEXT NOT NULL,
    total               TEXT NOT NULL,
    moneda              TEXT NOT NULL,
    metodo_pago         TEXT,                    -- PUE|PPD
    forma_pago          TEXT,
    uso_cfdi            TEXT,
    iva_trasladado      TEXT NOT NULL DEFAULT '0',
    impuestos_retenidos TEXT NOT NULL DEFAULT '0',
    raw_path            TEXT,
    json                TEXT NOT NULL,           -- full CFDI model, JSON
    imported_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ingest_cfdi_ws_period ON ingest_cfdi (ws_id, fecha);

CREATE TABLE IF NOT EXISTS ingest_cfdi_pagos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid_pago       TEXT NOT NULL,               -- UUID of the Pago (P) CFDI this row belongs to
    ws_id           TEXT NOT NULL,
    fecha_pago      TEXT NOT NULL,
    monto           TEXT NOT NULL,
    uuid_relacionado TEXT NOT NULL,              -- DoctoRelacionado/@IdDocumento
    imp_pagado      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ingest_cfdi_pagos_rel ON ingest_cfdi_pagos (ws_id, uuid_relacionado);

CREATE TABLE IF NOT EXISTS ingest_bank_lines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ws_id           TEXT NOT NULL,
    bank            TEXT NOT NULL,
    date            TEXT NOT NULL,
    description     TEXT NOT NULL,
    amount          TEXT NOT NULL,               -- signed decimal, + = deposit, - = withdrawal
    currency        TEXT NOT NULL DEFAULT 'MXN',
    balance         TEXT,
    hash            TEXT NOT NULL UNIQUE,        -- dedupe key: ws+bank+date+description+amount
    matched_txn_id  TEXT,
    cfdi_uuid       TEXT,
    imported_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ingest_bank_lines_ws_date ON ingest_bank_lines (ws_id, date);

CREATE TABLE IF NOT EXISTS ingest_bank_mappings (
    ws_id           TEXT NOT NULL,
    bank            TEXT NOT NULL,
    mapping_json    TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (ws_id, bank)
);

CREATE TABLE IF NOT EXISTS ingest_inbox (
    id              TEXT PRIMARY KEY,
    ws_id           TEXT NOT NULL,
    kind            TEXT NOT NULL,               -- quickadd|cfdi|bank|photo
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|accepted|rejected
    proposed_json   TEXT NOT NULL,               -- Transaction, JSON
    confidence      REAL NOT NULL DEFAULT 1.0,
    source_ref      TEXT,
    created_at      TEXT NOT NULL,
    decided_at      TEXT
);
CREATE INDEX IF NOT EXISTS ingest_inbox_ws_status ON ingest_inbox (ws_id, status);

-- Receipt photos (receipts.py). The image itself lives at
-- workspaces/<ws>/docs/receipts/<id>.jpg (EXIF stripped) so both backups carry it; this row keeps what
-- the OCR read and what was suggested. A movement points at it through pf_entries.attachment.
CREATE TABLE IF NOT EXISTS ingest_receipts (
    id              TEXT PRIMARY KEY,            -- rcp-<12 hex>
    ws_id           TEXT NOT NULL,
    filename        TEXT,                        -- the name the phone sent (display only)
    path            TEXT NOT NULL,               -- relative to the workspace dir
    content_type    TEXT NOT NULL,
    size            INTEGER NOT NULL,
    sha256          TEXT NOT NULL,
    ocr_engine      TEXT,                        -- tesseract|ocr-engine|NULL (off)
    ocr_ok          INTEGER NOT NULL DEFAULT 0,
    ocr_error       TEXT,
    ocr_text        TEXT,
    suggestion      TEXT,                        -- JSON {suggestion, reasons}
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ingest_receipts_ws ON ingest_receipts (ws_id, created_at);
