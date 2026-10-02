# pf — Personal finance

Everyday tracking surface: accounts/net worth, income, two-layer labels, budgets, goals, credit/loans.
Balances are **never stored** — every figure is read live from `aurum.ledger.base.get_ledger()`.
Metadata (labels, budgets, goals, cards, loans, MSI, scores) lives in SQLite tables prefixed `pf_`
(`aurum/pf/schema.sql`), applied automatically by `aurum.core.db.connect()`.

All endpoints are mounted at `/api/pf` by `aurum/api/app.py`; routes below are relative to that
(`aurum/pf/router.py` wires each sub-router).

## Localization

Every `Explain.summary` produced in this module goes through `aurum.core.i18n.t(key, lang)`. Each
GET endpoint takes an optional `?lang=es|en`; when omitted the language is
`aurum.core.i18n.ws_lang(ws_id)` — `Workspace.language`, defaulting to `es` for an unknown workspace.
Numbers, formulas (`Step.formula`), and response shapes never change with language — only the prose.
Domain functions (`get_accounts`, `budget_status`, `goal_with_progress`, `projection`, `debt_whatif`,
`card_status`, `loan_amortization`, `loan_whatif`, `get_income`, `monthly_review`) accept an optional
`lang` parameter for callers that already know it (e.g. `monthly_review` threading it into
`goal_with_progress`).

## Models

- `Label`: `id, ws_id, name, aliases: list[str], account: str|None (derived when omitted), icon, tax: {"MX": {...}, "US": {...}}, sort, kind: expense|income|transfer|None (derived from the account root), archived: bool, parent: str|None (input only)`; `LabelPatch`: `{name?, icon?, aliases?, archived?, tax?, sort?}` (route `PUT`)
- `Budget`: `id, ws_id, label_id, period (YYYY-MM, validated), amount (> 0), currency (default = workspace base currency), rollover: bool`
- `Goal`: `id, ws_id, kind (savings|emergency|debt|purchase), name, target, currency, target_date (IsoDate), account?, account_id?` (one of the two required); `GoalPatch` for `PUT`
- `CreditCard`: `id, ws_id, account, name, cut_day, due_day, limit_amount, currency, apr`
- `Loan`: `id, ws_id, account, name, principal, currency, annual_rate, months, start`
- `MSI` (meses sin intereses): `id, ws_id, card_id, purchase, amount, currency, months, started, paid_months`
- `CreditScore`: `id, ws_id, bureau, score, date`

## `pf_labels` table shape (stable — the ingest module reads this table directly)

```sql
pf_labels(id TEXT PK, ws_id TEXT, name TEXT, aliases TEXT /*JSON list[str]*/, account TEXT,
          icon TEXT, tax TEXT /*JSON {"MX": {...}, "US": {...}}*/, sort INTEGER,
          kind TEXT /*expense|income|transfer, pf migration v1*/, archived INTEGER /*pf migration v1*/)
```

`tax.MX` = `{isr_deductible, iva_creditable, requires_cfdi, personal_deduction}`;
`tax.US` = `{schedule_c, itemized}`. `POST /{ws}/labels/match {text}` returns the label whose name/alias
is the longest **whole-word, accent-insensitive** match found in `text` (deterministic, no LLM; `viaje a
europa` never matches `Ropa`) — `labels.match_label(ws, text, kind=None)` is what quickadd and the CSV
import call, scoped to the workspace.

### Kind, archived, server-side accounts

- `kind` is `expense` for `Expenses:` accounts, `income` for `Income:`, `transfer` for anything else (the
  backfilled `Assets:` labels "Ahorro/Inversión" and "Transferencia", hidden from pickers).
- `GET /labels?kind=expense|income|transfer&include_archived=0` filters; archived labels stay
  readable by id (entries keep their names) but are out of the pickers.
- `POST /labels {name, kind: expense|income, parent?: label_id, icon?, aliases?}` derives the ledger
  account server-side: `Expenses:<Slug>` / `Income:<Slug>` via `accounts_admin.slugify` (parent →
  `<parent.account>:<Slug>`, inheriting the parent's kind), numeric suffix on collision (`Expenses:Gimnasio2`),
  validated with `ledger.base.validate_account` (Beancount grammar; a bad explicit `account` → 400,
  a kind/root mismatch → 400, unknown parent → 404). Advanced callers may still send `account`.
- `PUT /labels/{id}` takes `LabelPatch`; `update_label(ws, id, Label|LabelPatch)` keeps accepting the
  full `Label` (organizer's alias teaching builds it).
- `DELETE /labels/{id}` → **409** (`LabelInUse`) when any non-voided entry or split references it —
  archive instead.
- Income entries with an expense label (and vice versa) are rejected by `pf.entries` with 400.

## Default MX personal label set (seeded once per workspace, on first `list_labels`/`GET labels`)

30 labels (the 25 below + 5 income seeds: Sueldo/Nómina → `Income:Salary`, Renta cobrada →
`Income:Rent`, Intereses → `Income:Interest`, Dividendos → `Income:Dividends`, Otros ingresos →
`Income:Other`), seeded **idempotently by name** so an existing workspace gains only the missing ones.
`(verify)` marks a tax flag that is a reasonable default but not confirmed against current
LISR/LIVA/IRC text — a human/rule-registry pass should confirm before it drives a filed number.

| Label | Account | MX isr_deductible | MX iva_creditable | MX requires_cfdi | MX personal_deduction | US schedule_c | US itemized |
|---|---|---|---|---|---|---|---|
| Comida fuera | Expenses:Food:DiningOut | – | – | – | – | – | – |
| Súper | Expenses:Food:Groceries | – | – | – | – | – | – |
| Renta/Hipoteca | Expenses:Housing:RentMortgage | – | – | – | – | – | – |
| Servicios (luz/agua/gas) | Expenses:Housing:Utilities | – | ✓ | ✓ | – | – | – |
| Internet/Teléfono | Expenses:Housing:Internet | ✓ (verify) | ✓ | ✓ | – | – | – |
| Transporte/Gasolina | Expenses:Transport:Fuel | ✓ (verify) | ✓ | ✓ | – | – | – |
| Uber/Taxi | Expenses:Transport:Rideshare | – | – | ✓ | – | – | – |
| Salud/Médico | Expenses:Health:Medical | – | – | ✓ | ✓ (verify) | – | ✓ (verify) |
| Medicinas | Expenses:Health:Medicine | – | – | ✓ | ✓ (verify) | – | ✓ (verify) |
| Educación/Colegiaturas | Expenses:Education:Tuition | – | – | ✓ | ✓ (verify, capped) | – | – |
| Software/Suscripciones | Expenses:Work:Software | ✓ | ✓ | ✓ | – | ✓ | – |
| Equipo de trabajo | Expenses:Work:Equipment | ✓ | ✓ | ✓ | – | ✓ | – |
| Ropa | Expenses:Personal:Clothing | – | – | – | – | – | – |
| Entretenimiento | Expenses:Personal:Entertainment | – | – | – | – | – | – |
| Viajes | Expenses:Personal:Travel | – | – | – | – | – | – |
| Seguros | Expenses:Insurance | – | – | ✓ | ✓ (verify, GMM only) | – | – |
| Mascotas | Expenses:Personal:Pets | – | – | – | – | – | – |
| Regalos | Expenses:Personal:Gifts | – | – | – | – | – | – |
| Impuestos | Expenses:Taxes | – | – | – | – | – | – |
| Comisiones bancarias | Expenses:Fees:Bank | ✓ (verify) | – | – | – | – | – |
| Ahorro/Inversión | Assets:Investments:General | – | – | – | – (see note) | – | – |
| Transferencia | Assets:Transfers | – | – | – | – | – | – |
| Ingreso freelance | Income:Freelance | – | – | – | – | ✓ | – |
| Ingreso plataforma | Income:Platform | – | – | – | – | ✓ | – |
| Otros | Expenses:Other | – | – | – | – | – | – |

Note: PPR/Afore voluntary-contribution deductibility (art. 151 LISR) is real but depends on which
sub-account receives the transfer, not the generic "Ahorro/Inversión" label — flagged `(verify)` and left
`false` by default to avoid overstating a deduction; a future PPR-specific label should carry the flag.

## Endpoints (all under `/api/pf/{ws}`)

- `GET/POST /labels`, `PUT/DELETE /labels/{id}`, `POST /labels/match {text}` (shapes above and in
  `docs/modules/pf-personal.md`)
- `GET /accounts` → grouped balances (bank, cash, credit_cards, loans, investments, receivables,
  other_assets/other_liabilities) + `net_worth` + 12-month `net_worth_series`, each with `explain`.
- `GET /recurring` → payees with a 20-40 day cadence and ≤15% amount variance → next expected date.
- `GET /income?months=6` → per-month gross/retained/net by source; `by_source`; a defensive read of the
  ingest module's `ingest_cfdi` table for issued-vs-pending-PPD (returns `null` if that table doesn't
  exist yet — ledger-only view still works); `smoothed_average` (mean gross over the window).
- `GET/POST /budgets`, `PUT/DELETE /budgets/{id}`, `POST /budgets/copy {from, to}` (idempotent
  carry-forward), `GET /budgets/status?period=YYYY-MM` → per-budget spent/remaining/`pct` (percent
  number)/`state` (`ok|warn|over`) + compat `alert` (`none`/`80`/`100`), carried rollover from the unspent
  prior-period budget, `deductible_share` when the label's MX tax has `isr_deductible` or
  `personal_deduction`, `totals`, `has_previous`/`previous_period` and `safe_to_spend` (sum of positive
  remaining; UI labels it "Presupuesto restante"). Spent is void-aware (`ledger_view`). Details: the
  Budgets section of `docs/modules/pf-personal.md`.
- `GET/POST /goals`, `PUT/DELETE /goals/{id}` (`account_id` preferred; rows carry `account_id`,
  `account_name`, `pct`, `target_date_invalid`; list includes computed `progress`/`monthly_required`/
  `months_of_spend_covered` for `emergency` goals; debt progress = target − owed), `GET /goals/{id}/projection` (month-by-month path at
  the current required contribution), `POST /goals/{id}/whatif {extra_monthly}` (debt goals: interest
  saved via `finance.py` amortization, matched to a `pf_loans` row sharing the goal's account).
- `GET/POST /credit/cards`, `POST /credit/cards/{id}/msi` (months ≥ 1) → card status includes the signed
  `balance`/`balance_signed`, `owed` (positive; liabilities are stored signed), utilization (owed / limit), next cut/due dates
  (`core.dates.clamp_day`), `pago_no_intereses` (= owed); cards/loans of archived `pf_accounts` rows are
  omitted and a documented
  `minimum_payment_note` `(verify)` since minimum-payment formulas are issuer-specific and not public.
- `GET/POST /credit/loans`, `GET /credit/loans/{id}/amortization`, `POST /credit/loans/{id}/whatif
  {extra_monthly}`.
- `GET/POST /credit/scores`, `DELETE /credit/scores/{id}` — manual entries only; no bureau integration.
- `GET /review/{period}` → income/expense/net, deltas vs. previous month, top 10 labels, anomalies
  (label spend > 2× its trailing 3-month average), goals progress, `upcoming_bills` (organizer calendar
  items going out in the next 30 days, not paid/skipped, tax items excluded), interest paid (any live
  `Expenses:` posting to an account containing `Interest`). Every figure is a signed, void-aware sum from
  `ledger_view`; bad period → 422; money rendered with q2 in the workspace base currency.

## `finance.py` — Decimal financial math

`pmt`, `build_amortization`, `build_balloon_amortization`, `npv`, `irr`, `solve_periodic_rate`,
`equivalent_annual_cost`, ported to `Decimal` from
the author's financial-sim project (https://github.com/jadrianlg16/financial-sim) (`src/domain/finance.js`).
Cross-checked against that JavaScript with `node` on 2026-09-05 (see
`tests/pf/test_finance.py` docstring for the exact command and outputs): `pmt(100000, 0.12, 12) =
8884.87886783416`; amortization row 1 interest `1000`, principal `7884.878867834161`, total interest
`6618.546414009936`; `npv(0.01, [-1000,300,300,300,300]) = 170.5896655155114`; `irr(...) =
0.07713847298437035`; `equivalentAnnualCost(10000, 0.08, 5) = 2504.564545668364`. All four match to
within rounding tolerance.

## Assumptions and limitations

- `pago_no_intereses` = the full statement (cut-date) balance. Minimum-payment formulas vary by issuer
  and are not standardized in public law — no number is computed for it, only a note. `(verify)` if a
  concrete formula is ever added.
- `net_worth` = Σ Assets + Σ Liabilities as signed balances, base-currency lots only (no FX conversion
  yet); multi-currency accounts each report their own `Amount` list. Cross-currency
  net worth needs an FX rate source (Banxico / US Treasury); it is not wired into this figure.
- Recurring detection and budget rollover are heuristics (cadence window, ±15% amount tolerance) chosen
  to be simple and explainable, not tuned on real data — documented here rather than silently guessed.
- No endpoints in this module call an LLM; quick-add and receipt-photo parsing live in the ingest
  module, which calls `labels.match_label` (also exposed as `POST labels/match`).

## Testing

`tests/pf/*` runs every test twice: `ledger[memory]` (`aurum.ledger.base.InMemoryLedger` monkeypatched
onto each pf module's `get_ledger` import) and `ledger[beancount]` (the real store under the tmp
`AURUM_DATA_DIR`), plus a real (tmp-dir) SQLite for the `pf_*` tables (see `tests/pf/conftest.py`).
Covers CRUD, computed figures (budget status, goal projection, amortization, whatif, review anomalies),
the finance.py numeric cross-checks and the files listed in `docs/modules/pf-personal.md`.
