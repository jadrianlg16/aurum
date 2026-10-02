# business — charts of accounts, payroll, invoicing register, KPIs

Mounted at `/api/business`. Nothing here files, stamps or sends: the payroll PDF is a watermarked
draft, and `POST .../invoices/remind` returns text for the user to send themselves. Tax figures come
only from rules (`aurum/rules/mx/nl.py`, `aurum/rules/mx/general.py`) — see
[rules-mx-nl.md](rules-mx-nl.md) for the constants table and what is `(verify)`.

## Chart of accounts

The two business templates live in `aurum/business/templates/`, next to the code that applies them
(the personal chart stays in `aurum/ledger/templates/`):

- `mx_persona_moral.beancount` (MXN) — régimen general PM, NL employer: payroll liabilities per
  institution (`Liabilities:Payroll:{Net,ISR-Retenido,IMSS-Obrero,IMSS-Patronal,INFONAVIT,ISN}`),
  IVA trasladado/acreditable, COGS, opex.
- `us_llc.beancount` (USD) — LLC, cash basis, Texas: FICA/FUTA/SUTA payroll liabilities, sales tax,
  franchise tax, member contributions/distributions.

Both obey one grouping contract that the KPI endpoint depends on: `Expenses:COGS:*`,
`Expenses:Payroll:*`, `Expenses:Opex:*`.

**How the template is applied.** `BeancountLedger.apply_template` resolves a template *by name inside
its own directory* and has no hook for an external path.
`aurum.business.chart.apply_business_template(ws, name, currency, store=)`
therefore reproduces that method's two public effects instead of reaching into it: it calls the store's
public `ensure_files(ws, currency)`, then merges the template's `open` directives into the file the
store's public `accounts_path(ws)` names — preserving accounts that are already open and never lowering
an existing open date. A store with neither method (`InMemoryLedger`) gets `open_account` calls. It is
idempotent, so re-applying a template to a live workspace is safe. If the store ever gains an
`apply_template(path=...)` overload, this function can delegate to it without changing its signature.

## Endpoints

- `GET /templates` → both charts with their currency and account list.
- `POST /{ws}/chart` `{name, currency?}` → `{accounts, count}`. 404 on an unknown template.
- `GET|POST /{ws}/payroll/employees`, `DELETE /{ws}/payroll/employees/{id}` — the register
  (`business_employees`). **Name and RFC are masked in every response, log line and audit record**
  (`E. U***`, `*********1000`); the unmasked values stay in SQLite and in the draft PDF.
- `POST /{ws}/payroll/run` `{period: "YYYY-MM", days?, post?, lang?, force?}` → the run (below).
- `GET /{ws}/payroll?period=&include_superseded=` → stored runs (superseded runs hidden by default);
  `GET /{ws}/payroll/{run_id}` → the full run; `GET /{ws}/payroll/{run_id}/draft.pdf` → the bilingual
  "NÓMINA — BORRADOR · DRAFT" PDF.
- `DELETE /{ws}/payroll/runs/{run_id}` → voids the run's ledger posting (if any) and marks it
  `voided_at`, so a mistaken run can be undone without editing the ledger by hand.
- `GET /{ws}/invoices?period=|start=&end=&as_of=` → issued vs collected, aging, top clients, DSO.
- `POST /{ws}/invoices/remind` `{uuid, as_of?, client_name?}` → `{text: {es, en}, sent: false, …}`.
- `GET /{ws}/kpis?period=YYYY-MM` → the KPI block (below).
- `GET /constants/mx-nl` → every NL/IMSS/INFONAVIT constant with citation, URL and `verified`.

## Payroll run

Per employee, from rules only:

| Figure | Rule / article |
|---|---|
| ISR retenido | LISR art. 96 tarifa — the **verified** Anexo 8 RMF 2026 table already registered by `mx.general`, less the subsidio al empleo `(verify)` |
| IMSS obrero | LSS arts. 25, 106 II, 107, 147, 168 II b) |
| IMSS patronal | `mx.imss.employer_quotas` — nine branches, each with its own step |
| INFONAVIT | `mx.infonavit.employer` — 5% |
| ISN | `mx.nl.isn` — 3%, once for the whole run's base |

Identities the tests assert: `net = gross − isr − imss_employee` and
`employer_cost = gross + imss_employer + infonavit + isn`.

The run posts **one accrual transaction** (`meta.source = "business.payroll"`, tag `payroll`):
`Expenses:Payroll:{Sueldos,IMSS-Patronal,INFONAVIT,ISN}` against `Liabilities:Payroll:*`. Zero-value
postings are dropped, and a run with no employees posts nothing. Runs are stored in
`business_payroll_runs` with the full per-employee detail (RFCs masked) so the PDF can be re-rendered.

### Idempotency, force, and void

`POST .../payroll/run` is idempotent per `(ws, period)`: re-running a period never duplicates its
ledger entries (otherwise three calls would triple `Expenses:Payroll:*` for the month).

- **Repeat call, same `(ws, period)`, `force` false (default):** no new run is computed or posted.
  The existing run is returned unchanged with `"already_ran": true` and the original `txn_id`. HTTP 200.
- **`force: true`:** the previous run's ledger transaction is voided (reusing the ledger's own
  `DELETE /api/ledger/{ws}/transactions/{txn_id}` function — a reversing entry plus the `#voided` tag
  on the original, so void semantics live in one place), the previous run row is marked
  `superseded_by=<new run id>`, and a fresh run is computed and posted. The response carries
  `"previous_txn_voided": true|false` — `false` (with a `previous_txn_void_reason`) when the ledger
  store is the `InMemoryLedger` fallback (no file to rewrite) or the previous transaction is missing.
- **`DELETE /{ws}/payroll/runs/{run_id}`:** voids that run's posting the same way and stamps the row
  `voided_at`, without needing `force` or a new run — for undoing a run made by mistake.
- **`GET /{ws}/payroll`** returns only non-superseded runs unless `?include_superseded=1` is passed.
  A superseded or voided run is still readable individually via `GET .../payroll/{run_id}` (which also
  reports its `superseded_by`/`voided_at`).

`superseded_by` and `voided_at` are added to `business_payroll_runs` with a guarded
`ALTER TABLE ... ADD COLUMN` (checked against `PRAGMA table_info`) at the top of every write/read path,
since `schema.sql` only ever runs `CREATE TABLE IF NOT EXISTS` and an older table on disk would
otherwise be missing them.

## Invoicing register

Reads `ingest_cfdi` / `ingest_cfdi_pagos` **defensively** — missing table, missing column or absent
ingest module all degrade to an empty register rather than an error; nothing is written. Payment
follows the same cash-basis rules as the tax module (SAT's prefill rules): **PUE** counts as collected on `fecha`, **PPD**
only through a REP whose `DoctoRelacionado` points back at the invoice (`imp_pagado`). Aging measures
the *unpaid balance* from the invoice date to `as_of` into 0-30 / 31-60 / 61-90 / 90+.
`DSO = receivables ÷ credit sales × days in the window`. Client RFCs are masked everywhere.

## KPIs

Revenue (`Income:*`), COGS (`Expenses:COGS:*`), gross profit and margin, operating expenses with a
by-group breakdown (`Expenses:Opex:<Group>`, plus `Payroll`), operating profit, cash
(`Assets:Bank:* + Assets:Cash`), receivables, payables, runway and tax reserve — each with its own
`Explain`.

- **Runway** = cash ÷ average monthly burn over the trailing 3 months, counting only months where
  expenses exceeded income. A profitable business gets `months: null` and the explain says why.
- **Tax reserve** imports `aurum.tax.month_close` **in process** for MX workspaces and falls back to the
  ledger's own `Liabilities:Taxes:{ISR,IVA}*` balances (saying so in `source` and `warnings`) when the
  tax module is absent or raises. `month_close` applies **RESICO** rules, so for a persona moral the
  reserve carries an explicit `(verify)` warning naming the declared regime.

## Demo

`aurum/business/demo_biz.py::build_demo_biz(data_dir)` creates `demo-biz` — a synthetic persona moral in
Nuevo León (`kind="business"`, RFC `XAXX010101000`, regime `GENERAL_PM`, state `NL`) with the quarter
2026-04…2026-06: 3 employees at different SBCs (so the cesantía bracket and the ISR tarifa differ per
row), 8 issued CFDIs (PUE collected on issue, PPD with and without a REP, one March invoice that ages
into 90+), COGS and opex in every month, an opening cash balance, and three posted payroll runs.
Everything is fake. `aurum.demo.extras` calls this builder when the demo workspaces are built (see
[demo.md](demo.md)).

## Tests

`tests/business/` — `test_rules_mx_nl.py` (rules and constants), `test_business.py` (chart, payroll,
invoices, KPIs against the demo quarter), `test_router.py` (TestClient). Every test runs against a
temporary `AURUM_DATA_DIR`.
