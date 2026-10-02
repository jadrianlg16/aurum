# creditreport — Buró de Crédito PDF import

Mounted at `/api/creditreport`. Descriptive/educational only — never a credit decision, never advice.

## Endpoints

- `POST /{ws}/import` (multipart `file`, PDF) → parses and stores; returns
  `{id, ws_id, filename, imported_at, score, accounts, warnings}`.
- `GET /{ws}` → `{imports: [...], latest: {...} | null}`.
- `GET /{ws}/explain` → `Explain` of what generally moves a Buró score (payment history, utilization,
  credit age/mix, recent inquiries) — cited to Buró de Crédito / CONDUSEF, all `(verify)`.

## Parsing (`aurum/creditreport/parser.py`)

Real "Reporte de Crédito Especial" layouts vary; the parser is a heuristic, not a guarantee:

1. **Labeled blocks** — `OTORGANTE`/`ACREEDOR` starts a new account; subsequent lines matching
   `TIPO DE CUENTA`, `LÍMITE DE CRÉDITO`, `SALDO (ACTUAL)`, `ESTATUS (DE CUENTA)`, `FECHA DE APERTURA`
   (accent-insensitive regex) fill that account's fields.
2. **Generic table fallback** — if no labeled block was found, rows separated by 2+ spaces or `|` are
   read with the header row mapping columns by keyword (`otorgante`→grantor, `limite`→limit, etc.).
3. A `SCORE`/`CALIFICACIÓN` followed by a 3-digit number anywhere in the text becomes `{value, bureau}`.
4. Every account missing a required field, and the overall document when nothing could be extracted at
   all, produces a warning string rather than a fabricated value — callers should surface `warnings` to
   the user as a confidence signal.

Text extraction is `pymupdf` (`fitz.open(stream=..., filetype="pdf")` → `page.get_text()`); a genuinely
unreadable/corrupt PDF raises and the router returns **400**, while a missing `pymupdf` install (it's a
hard project dependency, so this should never happen in practice) raises `MissingPdfEngine` → **500**.

## Storage

`creditreport_imports` (SQLite, `aurum/creditreport/schema.sql`): `id, ws_id, filename, imported_at,
score (JSON|null), accounts (JSON list), warnings (JSON list)`. One row per import; `GET /{ws}` returns
every import, newest first, plus `latest` as a convenience.

## Testing

`tests/creditreport/` builds a synthetic PDF with `reportlab` (`SAMPLE_LINES` in `conftest.py`) mimicking
a two-account labeled report, and a second "not a Buró report at all" PDF to exercise the low-confidence
path (empty `accounts`, both `no accounts` and `no score` warnings). No real Buró report is ever
committed to the repo.
