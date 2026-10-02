# organizer — "Mi dinero"

Subscriptions, bills, loan payments and paydays: detected from what is already in the ledger and the
bank tables, projected forward on a calendar and a 90-day cash-flow forecast, and organized into an
envelope spending plan.

**No LLM is used anywhere in this module.** Every figure is arithmetic over stored facts and every
endpoint that returns a number returns an `Explain` next to it. Money is `Decimal`, serialized as a
string with an explicit currency; dates are ISO.

## Files

| file | what it holds |
|---|---|
| `models.py` | `Commitment`, `CommitmentIn`, `Occurrence`, `Alert`, `Candidate`, `Evidence` |
| `normalize.py` | merchant normalization + the MX/US alias table |
| `cadence.py` | cadence inference, month-end-safe projection, `periods_per_year` |
| `detect.py` | event collection, grouping, candidate persistence, accept/dismiss |
| `commitments.py` | CRUD, PATCH-merge (`update_partial`), price history, `effective_next_due`, `find_duplicate` |
| `occurrences.py` | projected occurrences from the first evidence, void-aware matching, mark/unmark rules |
| `pf_bridge.py` | the ONE place pf/ledger are touched (lazy imports): `live_txns`, `pf_entry_row`, `create_pf_entry`, `void_pf_entry`, `accounts_index`, `budget_rows`, `base_currency` |
| `migrations.py` | organizer v1 (`commitments.account_id`) and v2 (`occurrences.entry_id/auto_created`, `candidates.flags/existing_commitment_id`) |
| `alerts.py` | the eight alert kinds and their thresholds; `compute_alerts()` |
| `calendar_view.py` | the merged bills calendar |
| `forecast.py` | liquid balance, 90-day series, safe-to-spend, buffer |
| `plan.py` | Needs/Wants/Savings/Debt plan, auto-plan, uncategorized list |
| `organize.py` | bulk relabel, `organizer_rules`, auto-label lookup |
| `summary.py` | `/summary` and the 3-step setup status/run |
| `demo_org.py` | `seed_demo_org(ws_id="demo-mx", today=None)` |
| `router.py` | every endpoint, mounted at `/api/organizer` |
| `schema.sql` | the seven `organizer_*` tables (final shape; migrations only ALTER older databases) |

## Model

```
Commitment{ id, ws_id, kind, name, merchant_patterns[], amount, amount_variable, cadence,
  interval_days, anchor_day, weekday, next_due, account, account_id, label_id, essential, status,
  trial_ends, started, ended, auto_pay, cancel_notes, linked_loan_id, linked_card_id, source,
  confidence, last_seen, notes, category_hint, reviewed_at, explain }
```

API rows (`with_explain`) add `account_name`, `stored_next_due`, `monthly_equivalent`,
`annual_equivalent`; their `next_due` is the **effective** one (see *Commitment details* below).

- `kind`: `subscription|bill|utility|rent|insurance|loan_payment|tax|income|transfer|other`
- `cadence`: `weekly|biweekly|monthly|bimonthly|quarterly|semiannual|annual|custom`
- `essential`: `needs|wants|savings|debt` — this is what the spending plan groups by
- `status`: `active|paused|cancelled|trial`. `DELETE` is a soft delete (`cancelled` + `ended`).

Tables: `organizer_commitments`, `organizer_price_history`, `organizer_occurrences` (overrides only),
`organizer_rules`, `organizer_candidates`, `organizer_settings`, `organizer_dismissed_alerts`.

An **occurrence is derived, never stored**: due dates come from the cadence, status from the ledger.
`organizer_occurrences` only holds a manual `paid`/`skipped` mark, so re-projection never loses a
user decision and never invents one.

## Merchant normalization

Applied in this exact order (`normalize.py`); each step is reproducible and unit-tested against a
table of ≥ 20 raw descriptions in `tests/organizer/test_normalize.py`:

1. uppercase, strip accents;
2. cut at the first `*` (`AMAZON PRIME*2X4Y5` → `AMAZON PRIME`), replace `,;:/\|` with spaces;
3. strip bank-noise prefixes at the start (`SPEI ENVIADO`, `PAGO TARJETA`, `COMPRA EN`,
   `DOMICILIACION`, `DEBIT CARD PURCHASE`, …), repeatedly;
4. strip URL suffixes (`NETFLIX.COM` → `NETFLIX`), then drop noise tokens: anything containing a
   digit, masks (`4152******1234`), phone numbers, branch/reference codes and city/country words;
5. match the alias table. **Priority first, then pattern length** — a brand (`GNP`) beats a category
   word (`SEGUROS`) even though the category word is longer. No match → the first three clean tokens.

| raw | merchant |
|---|---|
| `NETFLIX.COM 866-579-7172 CIUDAD DE MEX` | `NETFLIX` |
| `SPEI ENVIADO TELCEL 0341` | `TELCEL` |
| `PAGO TARJETA BBVA 4152******1234` | `BBVA` |
| `CFE SSC 9876543210` | `CFE` |
| `AMAZON PRIME*2X4Y5 MX` | `AMAZON PRIME` |
| `APPLE.COM/BILL ICLOUD 800-676-2775` | `ICLOUD` |
| `MICROSOFT 365 *G9K2L MSFT.COM` | `MICROSOFT 365` |

`classify()` returns the same merchant plus the alias row's `category_hint` (`streaming`, `music`,
`cloud`, `gym`, `telecom`, `utility`, `housing`, `insurance`, `loan`, `transport`, `tax`) and a
default `kind`/`essential`. The alias table only renames and classifies — it never invents an amount.

## Detection algorithm

1. **Events.** The ledger journal (`Expenses:*` / `Income:*` postings), `ingest_bank_lines` and
   `ingest_cfdi` recibidos each contribute `{date, amount>0, description, direction}` over the last
   550 days. Identical `(merchant, date, amount)` events are de-duplicated with bank evidence
   ranked first — the same charge sitting in both the ledger and the statement counts once.
2. **Group** by `(merchant, direction)`.
3. **Amount grouping.** One commitment when every amount is within **±10 %** of the group mean. This
   is what keeps a price increase together: Netflix 199, 199, 219 has a mean of 205.67 and all three
   are inside the band. Wider spreads split greedily by sorted amount. Merchants whose
   `category_hint` is `utility` are inherently variable: **±35 %** and `amount_variable = True`.
4. **Cadence** from the **median** consecutive interval, so one late payment cannot reclassify a
   monthly bill: `weekly 5–9 · biweekly 11–17 · monthly 28–33 · bimonthly 58–64 · quarterly 88–95 ·
   semiannual 178–190 · annual 355–375`; anything else is `custom` with `interval_days = median`
   (rejected outside 5–400 days). **≥ 2 occurrences, ≥ 3 for weekly.**
5. **Amount** = the most recent occurrence, not the average (that is what will be charged next).
6. **Anchors**: the modal day-of-month (ties broken towards the later day) for month cadences, the
   modal weekday for weekly/biweekly.
7. **Confidence** = `0.34·regularity + 0.33·amount_consistency + 0.33·count_factor`, where
   `regularity = 1 − max|interval − median| / median`, `amount_consistency = 1 − max|amount − mean| /
   mean` and `count_factor = min(1, (n−1)/3)`. Every term is a step in the candidate's `explain`.
8. **pf loans and cards** become `loan_payment` candidates carrying `linked_loan_id` /
   `linked_card_id` — loans use `pf.credit.loan_amortization`'s payment and the loan's start day,
   cards use `due_day` with `amount_variable = True`. When such a candidate lands on the same
   merchant key as a detected bank group the two are **merged**: pf is authoritative for the amount
   and the link, the bank rows keep the evidence, the dates and the cadence math in the explain.

Candidates persist in `organizer_candidates` (unique per workspace + merchant) so the setup wizard
can be resumed; a merchant that already has a commitment is never proposed again.

## Projection

`cadence.project_next` / `occurrences_between` keep the anchor day and **clamp to the length of the
target month**, so `anchor_day = 31` lands on 28/29/30/31 as the month allows and springs back to 31
the next long month. Weekly and biweekly keep the anchor's weekday; `custom` steps `interval_days`.

`build()` projects from the **earliest evidence** of the commitment — `floor = min(started, last_seen,
first price observation)` — clipped to `[max(start, floor − 3 d), end]`, never before `started − 3 d`,
never before `trial_ends` for a trial, never after `ended`. The stored `next_due` is not appended. One
void-aware ledger read per `build()` (`pf_bridge.live_txns`); callers share it with `txns=`.

An occurrence counts as **paid** when, first, a non-voided pf entry stamped with its `commitment_id`
falls within **±7 days** (amount ignored; needs pf migration v3's column), else when a live ledger
transaction whose normalized payee contains one of the commitment's normalized merchant patterns as
**whole words** falls within **±3 days** of the due date with an amount within **±10 %** of the expected
one (an `amount_variable` commitment matches on the date window alone). The nearest date wins. Past
due dates with no match become `missed` after **3 days**; `due` on or before today; otherwise `upcoming`.

## Alert thresholds

| kind | fires when | severity |
|---|---|---|
| `price_increase` / `price_decrease` | latest price vs the previous distinct price differs by **> 2 %** or **> 20** (skipped for `amount_variable`) | warn / info |
| `trial_ending` | `status = trial` and `trial_ends` within **7 days** | urgent ≤ 2 d, else warn |
| `missed_payment` | a due date **≥ 3 days** past with no matching transaction (60-day lookback) | urgent |
| `upcoming` | **effective** next due within **7 days** | info |
| `duplicate` | ≥ 2 active subscriptions share a `category_hint` in {streaming, music, cloud, gym} | info |
| `annual_renewal` | annual/semiannual renewing within **30 days** (never for income) | warn |
| `forgotten` | annual/semiannual not reviewed in **11 months** (never for income) | info |
| `income_expected` / `income_late` / `income_changed` | the upcoming / missed / price tests for `kind = income` — income never says "cargo", "pago no detectado" or "subió el precio" | info / warn / info |
| `cancelled_still_charging` | an open candidate flagged by detection: a cancelled commitment's merchant charged ≥ `min_occurrences` times after `ended` | warn |

Titles and bodies carry **pre-formatted** money and dates from `core.i18n.fmt_money` / `fmt_date`
(base currency `$1,234.56`, others `US$` / `MX$` / `EUR 12.00`; `12 sep 2026` / `Sep 12, 2026`) — never an
ISO date, never `249.00 MXN`. The `explain.steps` keep the raw figures.

Alerts are computed on every call, never stored. Ids are a stable hash of
`(workspace, kind, commitment, due/amount)`, so a dismissal in `organizer_dismissed_alerts` sticks
until the underlying fact changes — a *new* price increase gets a new id and fires again.

`aurum/insights/engine.py` imports `compute_alerts` defensively and re-wraps each alert as an insight
with kind `organizer_<kind>`, so Avisos and the Telegram digest carry them.

## Forecast and safe-to-spend

```
balance           = Σ balances(Assets:Bank:*) + balances(Assets:Cash), minus every pf account typed
                    `savings` (it shares the Assets:Bank prefix; set-aside money is not money to spend:
                    `pf_bridge.savings_accounts`, covered by test_safe_to_spend.py)
balance(d)        = balance(d−1) + Σ income due on d − Σ commitments due on d   (from day 0 = today)
fixed_pending     = unpaid (due | upcoming | missed ≤ 7 d back) occurrences of active non-income
                    commitments up to `until` (next projected income, else today + 30 d)
budgets_remaining = Σ max(0, effective − spent) over this month's pf budgets, excluding budgets whose
                    label is carried by an active non-income commitment
buffer            = organizer_settings.buffer, default 10 % of the monthly committed total
safe_to_spend     = balance − fixed_pending − budgets_remaining − buffer
```

`safe_to_spend` returns `{amount, until, currency, parts:{balance, fixed_pending, budgets_remaining,
buffer}, explain}`; `currency` is the workspace base currency and the explain steps are exactly
`liquid_balance, until, committed_until, budgeted_remaining, buffer, safe_to_spend` (ids the UI maps to
human labels) with human formulas (no ledger globs, no Σ). `monthly committed` normalizes every
cadence: `amount × periods_per_year / 12`. Nothing is smoothed or sampled — every movement in the
series is a projected occurrence the user can open.

## Spending plan

Planned amounts live in `pf_budgets` and are written **only** through `aurum.pf.budgets` public
functions. A label's envelope comes from the commitment attached to it (`Commitment.essential`) when
there is one, else from this account-prefix map (longest prefix wins, default `wants`):

`Assets:Investments`, `Assets:Transfers`, `Income:` → **savings** · `Liabilities:` → **debt** ·
`Expenses:{Housing, Food:Groceries, Health, Insurance, Education, Taxes, Transport, Fees, Work}` →
**needs** · everything else → **wants**.

`POST /plan/auto {months}` proposes `max(average spend over the last N months, Σ monthly equivalent
of that label's commitments)` and upserts one budget per label for the period.

A commitment is **nested** under the budget row that already covers the account its matched payments
hit (else its label's account) — `row["commitments"] = [{id, name, planned}]` — instead of becoming a
second row, so a group's `actual` counts the money once. Every row carries `commitments: []`.
`savings_rate = (income_actual − Σ positive Expenses:* live postings) / income_actual`; the payload also
carries `expenses_actual` and `currency` (workspace base currency).

## Endpoints (`/api/organizer/{ws}`)

| method | path | notes |
|---|---|---|
| GET | `/summary` | committed by kind, annual subscriptions, next 7 days, alerts count, safe-to-spend, uncategorized count, setup progress |
| GET/POST | `/commitments` | list (filters `kind`, `status`; ordered by effective `next_due`) / create (`account_id` resolved server-side, 404 unknown; duplicate live name/pattern → 409 `{code:"duplicate", existing_id, existing_name}` unless `force`) |
| GET/PUT/DELETE | `/commitments/{id}` | GET adds `price_history`, last 12 `occurrences` and the linked loan summary; PUT is a **PATCH-merge** (`CommitmentPatch`, only sent keys change); DELETE is a soft cancel |
| POST | `/commitments/{id}/review` | → `{"reviewed_at"}` |
| POST | `/commitments/{id}/{pause\|resume\|cancel}` | `cancel` accepts `cancel_notes` |
| POST | `/quickadd?save=0\|1` | rule-based ES/EN parse → preview or persisted commitment; amount = the last standalone number; no number → 400; save goes through the duplicate guard (`force` in the body) |
| POST/GET | `/detect` | run detection / list persisted candidates (`?status=`) |
| POST | `/detect/accept` `/detect/dismiss` | `{candidate_id, overrides?}` |
| GET | `/alerts` · POST `/alerts/{id}/dismiss` | |
| GET | `/calendar?from=&to=` | days with items (`account_id`, `account_name`, `entry_id`), `total_out`, `total_in`; dates validated (422), reversed → 400, span > 24 months → 422; tax rows only when `module_on(ws, "tax")` |
| POST | `/occurrences/mark` | `{commitment_id, date, status: paid\|skipped, entry_id?, log_entry?, amount?, account_id?}` → `{occurrence, entry_id}` (see *Mark paid* below) |
| DELETE | `/occurrences/mark?commitment_id=&date=` | → `{removed, voided_entry_id}`; voids only an auto-created, unedited entry |
| POST | `/occurrences/{commitment_id}/{due}/mark` | legacy alias `{status: paid\|skipped, txn_id?, amount?}` (never logs an entry); other statuses → 422 |
| GET | `/forecast?days=90` (≤ 400, else 422) · PUT `/forecast/buffer` | |
| GET/PUT | `/plan?period=` (422 on a bad period) · POST `/plan/auto` | |
| POST | `/organize` · GET `/rules` · DELETE `/rules/{id}` | |
| GET | `/setup/status` · POST `/setup/run` | |

All prose comes from `aurum.core.i18n` (`organizer.*` keys) at the workspace language, with `?lang=`
overriding. Every route also accepts `?today=YYYY-MM-DD` **only when `AURUM_TEST_CLOCK=1`** (else 422) —
the test clock, see below.

## Commitment details

**Migrations v1–v2** (`migrations.py`, `schema.sql` in lockstep so a fresh DB needs no ALTER): v1
`commitments_account_id` adds `organizer_commitments.account_id` and backfills it from `pf_accounts`
(same workspace, same ledger account, not archived); v2 `mark_links_and_candidate_flags` adds
`organizer_occurrences.entry_id` / `auto_created` and `organizer_candidates.flags` /
`existing_commitment_id`. Additive, only the received connection, never a delete. Covered by
`tests/organizer/test_migrations.py`, which opens a copy of the older schema.

**account_id.** `CommitmentIn.account_id` (a pf account) wins over `account` (a ledger name); a ledger
name alone is reverse-looked-up for its pf id (the income-streams path); neither → legacy `Assets:Bank`. Unknown
`account_id` → 404 `commitment account not found`. `merchant_patterns` are normalized on write. Rows and
calendar items carry `account_id` + `account_name` from one `pf_accounts` index per request.

**PUT = PATCH-merge.** `commitments.update_partial(ws, cid, CommitmentPatch, today=None)` applies only
the keys present in the body; `source, confidence, started, last_seen, ended, linked_*, category_hint,
account_id, reviewed_at` stay untouched when unset. A cadence/interval/anchor/weekday change without an
explicit `next_due` re-projects it from today; month cadences without `anchor_day` derive it from
`next_due.day` (10-31 → 11-30 → 12-31 → 01-31, no drift). An amount change wipes same-day (and
future-stamped) manual price rows before recording today's price, so a typo correction never fires
`price_increase`. `update()` is a thin full-body wrapper.

**History + effective next_due.** `get()` / `list_commitments()` return the STORED `next_due`
(`tests/pf/test_streams.py` pins it). `commitments.effective_next_due(ws, c, today, txns=None)` = first
projected due ≥ today whose status is not paid/skipped over `[today, today + 2 × nominal days]`
(paused/cancelled: first projected due ≥ today; nothing → cadence projection of the stored value). API
rows, list ordering, `upcoming` / `annual_renewal` alerts and the summary use it; list/get routes lazily
persist it (`UPDATE … WHERE next_due < today`, idempotent) and flip `trial → active` once `trial_ends`
is past.

**Mark paid.** `POST /occurrences/mark`: unknown commitment → 404; `skipped` → override with no
txn/entry (an earlier auto-created, unedited entry on that occurrence is voided first); `paid` +
`entry_id` → link that pf entry (404 when missing or voided), stamp `pf_entries.commitment_id` when the
column exists; `paid` alone → idempotent when a paid override already carries a live entry, else match
first (link, then payee), else with `log_entry` create the pf entry through
`pf.entries.create_entry(kind by commitment.kind, date, amount or commitment.amount, account_id or
commitment.account_id or the reverse lookup of its ledger account, label_id, payee=name, tags
[pago-fijo], source organizer, commitment_id when EntryIn has it)` — `transfer` → 400, amount 0 → 400
`Indica el monto`, no account → 400 `Primero elige una cuenta`, pf `KeyError` → 404, `ValueError` →
400 — and record `paid, txn_id, entry_id, auto_created=1`. `DELETE /occurrences/mark` drops the override
and voids the entry only when `auto_created`, not voided and `updated_at == created_at` (pf errors map
to 409/403/404); no override → `{removed:false}`. Covered by `tests/organizer/test_mark_logs_entry.py`
on the real Beancount ledger.

**Safe to spend** — one figure, see *Forecast and safe-to-spend*; `GET /summary` and `GET /forecast`
return the same object, `PUT /forecast/buffer` answers in the base currency. Covered by
`tests/organizer/test_safe_to_spend.py` (10,000 / rent 3,000 / income 8,000 / budget 2,000 with 500
spent / buffer 0 → `5500.00`).

**Tax gating.** `calendar_view._tax_items` is empty unless `module_on(ws, "tax")`; the insights
engine and calendar follow the same gate (see `docs/modules/insights.md`); the organizer is the one
source of "bill due" nudges (pf has no `recurring_bill_due` producer), and
`POST /api/insights/{ws}/{id}/dismiss` with an `org-…` id writes `organizer_dismissed_alerts`.

**Hygiene.** Bounds on `CommitmentIn`/`CommitmentPatch` (`anchor_day` 1..31, `weekday` 0..6,
`interval_days` ≥ 1, `amount` ≥ 0, `name` 1..120) → 422. `commitments.find_duplicate(ws, name,
patterns)` (accent/case-insensitive name or shared normalized pattern among active/trial/paused) → 409
unless `force` — router-level only, so `create()` calls from pf income streams never see it.
`detect._claimed_patterns` considers only active/trial/paused commitments; a cancelled merchant that
keeps charging resurfaces as a candidate with `flags=["cancelled_still_charging"]` + `existing_commitment_id` (its old candidate row
is reopened), and the alerts warn about it.

**Test clock.** `router._today` resolves every route's "today": the wall clock
(`router.wall_today()`, monkeypatchable) unless the request carries `?today=` **and**
`AURUM_TEST_CLOCK=1` (else 422). `tests/organizer/conftest.py` sets the env, keeps `TODAY = 2026-09-15`
and its `client` appends `today=TODAY` to every organizer URL (`ClockClient` — httpx ≥ 0.28 replaces a
URL's query string when `client.params` is set, so a wrapper is used instead).

**Currency.** Forecast, plan, summary, calendar and router use `pf_bridge.base_currency(ws)` (workspace
`base_currency`, `MXN` fallback for a bare workspace); no currency is hard-coded.

## Quick add

`POST /quickadd {"text": "netflix 219 mensual día 15"}` consumes the line in a fixed order so a day
number can never be read as the amount: **trial → "cada N días" → day-of-month → cadence keyword →
currency → amount → name (whatever is left)**. Recognized: `mensual/monthly`, `anual/yearly/annual`,
`semanal/weekly`, `quincenal/biweekly`, `bimestral/bimonthly`, `trimestral/quarterly`,
`semestral/semiannual`, `cada N días` / `every N days`, `día 15` / `el 15` / `on the 15th`, `USD`
(and MXN/EUR/CAD/GBP), `prueba hasta 2026-10-01` / `trial until …`. Every decision is an `explain`
step. See `tests/organizer/test_quickadd.py` for the 18-case table.

## Demo

`aurum.organizer.demo_org.seed_demo_org(ws_id="demo-mx", today=None)` writes the recurring movements
into **both** `ingest_bank_lines` and the ledger, anchored on `today` and idempotent: Netflix
(199 → 219, a price increase), Spotify, Telcel, CFE bimonthly 890/1,120, renta 12,000 on the 1st,
Smart Fit, iCloud, Amazon Prime annual 899, the car payment linked to the demo `Liabilities:Loans:Auto`
loan, salary on the 5th and freelance on the 20th, plus a `Max` commitment whose trial ends in 5 days.
Detection finds 11 seeded merchants plus the pf loan and card.

`python -m aurum.demo --organizer` runs it (through `aurum.demo.personal.seed_demo_organizer`); the tests
call `seed_demo_org` directly.

## Tests

`tests/organizer/`: `test_normalize.py` (alias table), `test_cadence.py` (bands + month ends),
`test_quickadd.py` (parser table), `test_detect.py`, `test_alerts.py`, `test_calendar.py`,
`test_forecast.py` (exact Decimals), `test_plan.py`, `test_organize.py`, `test_router.py`,
`test_migrations.py`, `test_mark_logs_entry.py` (real Beancount ledger),
`test_history_projection.py`, `test_next_due_rollforward.py`, `test_commitments_patch.py`,
`test_safe_to_spend.py`, `test_plan_dedupe.py`, `test_income_alerts.py`, `test_router_validation.py`.
The fixtures build the real `demo-mx` workspace and freeze "today" at **2026-09-15** (test clock) so
every asserted Decimal is reproducible.
