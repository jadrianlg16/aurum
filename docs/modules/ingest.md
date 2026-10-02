# ingest

CFDI XML/ZIP parsing, bank CSV import, quick-add parsing, and the review Inbox that feeds the
Beancount ledger.

## Files

- `aurum/ingest/cfdi.py` — CFDI 4.0 parser. lxml + explicit namespaces (`cfdi` 4.0, `tfd` 1.1,
  `pago20`) is the parser of record; deterministic and fully covered by synthetic fixtures. `satcfdi`
  is in the dependency set for `satsync` but is not used here — a first pass tried it and its
  `CFDI` object's key structure (mirroring raw XML attribute names) added indirection without adding
  robustness, so the lxml path is what ships. `parse_cfdi_xml(data, workspace_rfc)` raises
  `CFDIParseError` on malformed/unstamped input. `parse_upload(filename, data, workspace_rfc)` accepts
  a single XML or a ZIP of XMLs. **Tax note:** comprobante-level `cfdi:Impuestos/cfdi:Traslados` are
  summed, not the per-concepto `Impuestos` blocks (which repeat the same figures) — this bit us once
  in testing (see `tests/ingest/test_cfdi.py::test_parse_ingreso_pue`, doubled IVA before the xpath
  was scoped to `cfdi:Impuestos` as a direct child of the root).
- `aurum/ingest/schema.sql` — `ingest_cfdi`, `ingest_cfdi_pagos`, `ingest_bank_lines`,
  `ingest_bank_mappings`, `ingest_inbox`, `ingest_receipts`. Amounts are TEXT decimals throughout.
- **Receipt photos** — three modules, no ledger write anywhere:
  - `receipts.py` — `scan(ws, bytes, filename)`: sniff JPEG/PNG/WebP (HEIC and non-images → 400
    `unsupported_image` with a plain sentence), re-encode to an upright JPEG ≤ 2400 px **without EXIF**
    (no GPS kept) at `workspaces/<ws>/docs/receipts/<rcp-id>.jpg` (inside `docs/`, so both backups carry
    it), OCR, suggest, store `{ocr_text, suggestion, reasons}` on the `ingest_receipts` row, audit without
    the text. Category order: the person's **last choice for the same shop** (newest live expense whose
    payee folds equal) → the known chain's category → keyword rules → `match_label` on the shop name
    only (whole-ticket alias matching would turn every "IVA" line into Impuestos). `possible_duplicate`
    flags a byte-identical photo already on a movement, else a live expense with the same date + amount
    (+ shop) — a warning, never a block.
  - `receipt_ocr.py` — `ocr_image(path)`: `AURUM_OCR_BACKEND=auto|tesseract|ocr-engine|off`. Tesseract
    CLI found via `AURUM_TESSERACT_CMD` → PATH → the Windows installer path; `--psm 4`, languages
    `AURUM_OCR_LANGS` (`spa+eng`) ∩ installed; the image is cleaned for OCR only (EXIF rotation,
    grayscale, resize to ~1400–3200 px, autocontrast). `ocr-engine` (an optional external OCR HTTP
    service at `AURUM_OCR_URL`) = create job → poll → text output. Off / missing / timeout
    (`AURUM_OCR_TIMEOUT`, 30 s) never raises: the photo is kept and the UI asks for the amount by hand.
    Tesseract takes roughly 0.3–0.4 s per ticket on a desktop machine.
  - `receipt_parse.py` — pure keyword reader: amount from the strongest TOTAL-like line (never
    SUBTOTAL/IVA/CAMBIO/EFECTIVO/ARTÍCULOS; next line when OCR split the columns; cross-checked with
    subtotal + IVA and the card line), date (FECHA line wins; day-first unless the workspace is US-only;
    month names ENE…DIC/JAN…DEC; nothing future or older than 400 days), shop (known MX/US chains →
    `COMERCIO:` line on card slips → first header line that is not an address/RFC/folio/bank), category
    (chain table, then keyword tables such as MAGNA/LITROS, PROPINA/MESA, FARMACIA). Every guess carries a
    reason; the tables are plain lists at the top of the file.
- `aurum/ingest/bank_csv.py` — column auto-detection (date/description + amount, or
  debit/credit) with per-(ws, bank) mapping remembered in `ingest_bank_mappings`; dedupe via a SHA-256
  hash of `ws|bank|date|description|amount`. `import_csv(ws, bank, raw, *, account_id, base_currency,
  mapping=None)` **writes a real pf entry per new line** on the pf account the caller names
  (`KeyError` when unknown, nothing written): kind by sign, `amount=|x|`, `label_id` from
  `pf.labels.match_label` when the label kind matches, `payee=description[:120]`, `source="import"`,
  tags `["import", "csv-<slug(bank)>"]`, through `pf.entries.bulk_create(atomic=False)`. Unparsable
  dates/amounts and zero amounts are reported as `errors[{line, detail}]` and their bank line is not
  recorded (fix + re-import). Result `{"created": [ids], "imported": n, "skipped_duplicates": n,
  "errors": [...]}`; no inbox items (imports, like other shortcuts, create ordinary editable entries).
- `aurum/ingest/quickadd.py` — rule-based `250 tacos comida` / `1,200 uber trabajo` /
  `-500 cliente pago factura` / `viaje a europa 900` parser. `parse_text` finds the first numeric token
  anywhere (comma thousands, optional `$`, optional cents, optional 3-letter currency after it); a
  leading `-` or a word in `{ingreso, deposito, depósito, cobro, income}` means income.
  `parse_entry(ws, text, account_id=None) -> QuickAddPreview{entry: pf.entries.EntryIn, account_name,
  label_name, confidence, warnings}` resolves the pf account (`account_id` → 404 when unknown → a
  whole-word match on a pf account's name/institution → the single non-archived cash/checking
  account → `NoAccount`), the category via `pf.labels.match_label` (whole-word, accent-insensitive,
  scoped to the workspace; dropped with a warning when its kind differs), and leaves the rest as the
  payee; date = today. `transaction_for(preview, text)` renders the `proposed` Transaction. The legacy
  `parse_quickadd(text, ws_id, base_currency) -> QuickAddResult{transaction, confidence, warnings}`
  (Telegram / inbox path) uses the resolved pf account when one exists and otherwise the old
  `Assets:Cash` proposal. `AURUM_LLM_QUICKADD=1` routes through `llm_quickadd_hook`, which imports
  `aurum.llm` if present and otherwise raises `NotImplementedError` — no LLM quick-add path is
  implemented yet.
- `aurum/ingest/inbox.py` — `InboxItem` CRUD (`ingest_inbox` table) and `accept_inbox_item` /
  `reject_inbox_item`. Accept applies optional `label`/`account` overrides — the `account` override is
  rebuilt as `Posting(account=validate_account(account), amount=...)` so every validator runs (a bad
  name → `ValueError` → 400, ledger untouched) — appends the transaction via
  `aurum.ledger.base.get_ledger()`, stamps `meta.source`/`meta.inbox_id` (and `meta.cfdi_uuid` when the
  item originated from a CFDI), and writes an `aurum.core.audit` record. Accepting/rejecting a
  non-pending item raises `InboxAlreadyDecided` (→ HTTP 409).
- `aurum/ingest/router.py` — the endpoints below, mounted at `/api/ingest`.
- `aurum/ingest/reconcile.py` — matches `ingest_bank_lines` against ledger
  transactions and CFDIs. `reconcile_period(ws, period, lang)` reads bank lines for the period plus
  every CFDI in it; a line already carrying `matched_txn_id`/`cfdi_uuid` gets no suggestions (it is
  already reconciled). Otherwise `suggestions_for` proposes up to 5 candidates sorted by score:
  ledger transactions with a posting on `Assets:Bank:*`/`Assets:Cash` within ±1% amount and ±3 days,
  and CFDIs — `recibido` direction for a negative (outflow) line, `emitido` for a positive (inflow)
  line — same tolerance. Score = `0.6 * (1 - amount_pct_diff/1%) + 0.4 * (1 - date_diff_days/3)`,
  clamped to `[0, 1]`. `match`/`unmatch` write directly to `ingest_bank_lines.matched_txn_id` /
  `.cfdi_uuid` (whichever field is passed; the other keeps its current value) — no separate table.

## Endpoints

| Method & path | Notes |
|---|---|
| `POST /{ws}/cfdi` | multipart `file` (XML or ZIP). Stores every CFDI + one Inbox item each: `recibido` → expense proposal (`Expenses:Uncategorized` / `Liabilities:AccountsPayable`), `emitido` → receivable/income proposal (`Assets:Receivable` / `Income:Uncategorized`), with `meta.metodo_pago` and `meta.flow` carrying PUE/PPD context for the tax module to read later. |
| `GET /{ws}/cfdi?period=YYYY-MM` | filters `ingest_cfdi.fecha LIKE 'YYYY-MM%'`. |
| `POST /{ws}/bank/csv` | multipart `file` + form fields `bank`, **`account_id`** (required → 422 when missing, 404 when unknown) → `{"created", "imported", "skipped_duplicates", "errors"}`; lines become editable pf entries (`source: import`), no inbox items. |
| `POST /{ws}/receipts` | multipart `file` (photo) → `{receipt: {id, url, content_type, size, created_at}, ocr: {engine, ok, error, chars, seconds, text}, suggestion: {amount, date, payee, label_id, label_name, confidence{amount,date,payee,label}} \| null, reasons: [str], message: str \| null, duplicate: {entry_id, date, amount, payee, same_photo} \| null}`. Nothing is saved as a movement; `POST /pf/{ws}/entries {…, attachment: id}` links it. |
| `GET /{ws}/receipts/{id}` | the stored scan (same shape minus `duplicate`) — 404 for an unknown / other-workspace id |
| `GET /{ws}/receipts/{id}/image` | the stored JPEG (`Cache-Control: private`); the UI fetches it through the request layer so the bearer token is sent |
| `POST /{ws}/quickadd` | JSON `{"text", "account_id"?, "commit"?: false}` → `{"id": null|entry_id, "kind": "quickadd", "status": "preview"|"committed", "proposed": Transaction, "confidence", "warnings", "preview": {kind, amount, account_id, account_name, label_id, label_name, payee, date}, "entry": Entry|null}`. No account resolvable → 400 ("Primero agrega una cuenta…"); commit → `pf.entries.create_entry(source="quickadd")`, editable, no inbox row, audit recorded. |
| `GET /{ws}/inbox?status=` | `pending`/`accepted`/`rejected`, or all. |
| `POST /{ws}/inbox/{id}/accept` | optional JSON `{"label", "account"}` overrides. |
| `POST /{ws}/inbox/{id}/reject` | — |
| `GET /{ws}/reconcile?period=YYYY-MM&lang=` | bank lines + suggestions + `unmatched_bank`/`unmatched_cfdi` counts |
| `POST /{ws}/reconcile/match` | JSON `{"bank_line_id", "txn_id"?, "cfdi_uuid"?}` |
| `POST /{ws}/reconcile/unmatch` | JSON `{"bank_line_id"}` — clears both `matched_txn_id` and `cfdi_uuid` |

## Design notes

- The CFDI parser uses lxml as the primary (not fallback) path — see the note above; `satcfdi` remains
  a dependency used by `satsync`.
- Quick-add and the bank CSV import do not create inbox items: they write ordinary, editable pf entries.
  The inbox remains for CFDI proposals and the Telegram quick-add path.

## Tests

`tests/ingest/` — `cfdi_builder.py` builds synthetic CFDI 4.0 XML (Ingreso/PUE and Pago/REP) with fake
RFCs (`XAXX010101000`, `EKU9003173C9`); `test_cfdi.py`, `test_bank_csv.py`, `test_quickadd.py`,
`test_router.py`, `test_reconcile.py` (FastAPI `TestClient` against `aurum.api.app.create_app()`).
`test_quickadd.py` covers account resolution (id / word match / single default / `NoAccount`), whole-word
labels and the legacy wrapper; `test_bank_csv.py` the entry write path, dedupe, per-line errors and the
unknown-account no-write; `test_router.py` preview → commit with no inbox row and the `account_id`
requirement; `test_zip_caps.py` the CFDI zip limits. Receipts: `test_receipt_parse.py` (10 synthetic MX tickets — OXXO, gas station with the
amount on the next line, restaurant with tip, card slip with `COMERCIO:`, pharmacy with `T0TAL`, no-TOTAL
fallback, date bounds, US month-first) and `test_receipts.py` (9: suggestion + confidence, EXIF/GPS strip
and resize, refusals, last-choice learning, `attachment` kept across edits and validated per workspace,
duplicate warning, backup zip carries the photo, OCR off, and a **real Tesseract** read of a drawn ticket —
skipped where Tesseract is not installed). Run: `uv run pytest -q tests/ingest`.
