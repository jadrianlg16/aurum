# pf-personal — Manual-first personal finance

Manual entry is the primary path, detection/AI is secondary. This file documents the personal surface of
`aurum/pf` (accounts, entries, income streams, onboarding, budgets, goals, migrations) plus the two
shortcut writers in `aurum/ingest` (quickadd, bank CSV). `docs/modules/pf.md` covers labels, credit,
finance and the older read endpoints; `docs/modules/ingest.md` the ingest package.

No accounting vocabulary leaves any endpoint here: no `postings`, no `debit`/`credit`, no balancing leg.
Every response is a flat, human row. The ledger (`aurum.ledger.base.get_ledger()`) stays the only store of
record; everything in this file is either a thin registry (`pf_accounts`, `pf_entries` mapping a friendly
row to a ledger transaction) or a translator that builds a balanced Beancount transaction from a plain
`{kind, amount, account, category}` shape and never exposes the postings back.

The response shapes below are stable; this file documents them and the rules behind them.

## 0. Void semantics — `aurum/pf/ledger_view.py`

The ledger never erases anything. A pf edit/delete appends a reversal tagged `#entry-reversal` whose
`meta.reverses` names the original transaction; `ledger/router.void_transaction` tags the original
`#voided` and appends a `#voided-reversal`. **Every pf aggregate reads the ledger through `ledger_view`**:

- `live_txns(ws_id, start=None, end=None)` — transactions in the window minus anything tagged
  `entry-reversal|voided-reversal|voided` and minus any transaction whose links intersect the
  `meta.reverses` set of the window (both conventions date the reversal on the original's date, so a
  window is self-contained and costs one journal load).
- `live_postings(ws_id, start, end, account_prefix=None) -> list[(Transaction, Posting)]` — signed
  postings with an amount (balancing legs are skipped).
- `sum_by_account(ws_id, start, end, account_prefix, currency=None) -> {account: Decimal}` and
  `sum_under(totals, account)` (an account plus its children) — the helpers budgets/review/goals use.

Consumers: `budgets._spent_for_account`, `review._spend_by_label/_income_expense_totals/_interest_paid/
_anomalies`, `goals._avg_monthly_spend`, `income.income_by_month`, `accounts.detect_recurring`,
`accounts_admin.has_movements`, `entries._foreign_entries`, and the organizer's occurrence matching
(lazy import). Sums are **signed**: nothing in `aurum/pf` filters on `amount > 0` / `amount <= 0`.
Covered by `tests/pf/test_voids.py` on both ledgers (log 250 → delete → spent `0.00`; edit to 300 → `300.00`).

## 1. Accounts — `aurum/pf/accounts_admin.py`, `aurum/pf/accounts.py`

`pf_accounts(id, ws_id, name, type, institution, currency, account, credit_limit, cut_day, due_day, apr,
archived, created_at, updated_at)`. `account` is the derived Beancount account name; balances are never
stored, always read live from the ledger. `apr` is stored as a **fraction** string (`0.14`).

**AccountRow** (every accounts endpoint): `{id, name, type, institution, currency, account,
ledger_account (= account), archived, balance: Money, balance_signed: Money, owed: bool, opening_balance:
Money|null, opening_date: str|null, credit_limit: Money|null, cut_day, due_day, apr (fraction str)|null,
apr_percent|null, loan_months|null}`. For `credit_card|loan` rows `owed` is true, `balance` is what is owed
(positive) and `balance_signed` is the ledger number (negative); for assets both are the same.
`opening_balance/opening_date` come from the `#opening-balance` transaction carrying `meta.pf_account_id`.
`list_accounts(ws, include_archived=False, balances=None)` loads the ledger once for the whole list;
`list_rows(ws, include_archived=True)` returns registry rows with no ledger load at all (used by the
entries listing and quickadd).

- `POST /api/pf/{ws}/accounts` `{name (1–80, stripped, no control chars), type, institution?,
  currency (^[A-Z]{3}$, upper-cased), opening_balance?: Money, opening_date?, credit_limit?, cut_day?
  (1..31), due_day? (1..31), apr_percent? | apr?, loan_months? (≥1), loan_principal?}`.
  **Liabilities are typed positive and stored signed: the person types what they owe as a positive
  number; a negative `opening_balance` on a card/loan is a 422 and the server negates on write.** The name check
  (case-insensitive, non-archived, across all types) and the insert run in one `BEGIN IMMEDIATE`; a
  duplicate is **409 `{"detail", "existing_id"}`**.
  `credit_card` rows also insert/sync `pf_credit_cards`; `loan` rows sync `pf_loans` (principal from
  `loan_principal` or `|opening_balance|`, `months` from `loan_months`).
- `GET /api/pf/{ws}/accounts/{id}`; `PUT .../{id}` partial (`name, institution, credit_limit, cut_day,
  due_day, apr_percent|apr, archived (both ways), loan_months, loan_principal`) — syncs
  `pf_credit_cards`/`pf_loans` by `(ws_id, account)`; renaming onto another live name → 409.
- `DELETE .../{id}` archives when the account has no **live** movements other than
  `#opening-balance/#balance-adjustment/#sign-migration` rows (voided entries do not count); otherwise
  **409 `{"detail", "hint": "archive"}`**.
- `POST .../{id}/adjust` `{balance: Money, date?, note?}` — for liabilities `balance` is what is owed
  (≥ 0, else 422); the server posts the signed delta against `Equity:Opening` (`#balance-adjustment`).
- `GET /api/pf/{ws}/accounts?include_archived=0` → `{groups, accounts: [AccountRow], net_worth: Money,
  net_worth_series (12 rows, kept), explain}`. **`net_worth` = Σ Assets + Σ Liabilities as signed
  ledger balances, base-currency lots only**, currency = `workspace.base_currency`.
- Cards/loans whose `pf_accounts` row is archived drop out of `GET /credit/cards` and `/credit/loans`;
  `credit._next_day` uses `core.dates.clamp_day` (31 → month end, never the 28th). `card_status` returns
  `balance`/`balance_signed` (ledger, negative when owed) and `owed` (positive) and computes utilization
  and `pago_no_intereses` from `owed`.

### Ledger account name derivation

`derive_ledger_account(ws_id, type, name)` maps `type` to a root (`checking|savings` → `Assets:Bank:`,
`cash` → `Assets:Cash` (singleton, then `Assets:Cash:<Slug>`), `credit_card` → `Liabilities:CreditCard:`,
`loan` → `Liabilities:Loans:`, `investment` → `Assets:Investments:`, `other` → `Assets:Other:`) plus
`slugify(name)` (accent-stripped, alnum-only, CamelCase, never empty). It is a pure function of the
existing registry + `(type, name)`; two different names that slugify the same way get a numeric suffix.
Renaming a friendly account never renames the ledger account.

## 2. Entries — `aurum/pf/entries.py`

`pf_entries(id, ws_id, kind, date, amount, currency, account_id, to_account_id, label_id, payee, note,
tags JSON, splits JSON, source, txn_id, voided, editable, non_editable_reason, attachment, created_at,
updated_at, commitment_id)`. `amount` is stored as the positive magnitude (q2); the sign on the way out is
**income positive, expense negative, transfer negative** (from the paying account's side).

**Entry row**: `{id, kind, date, amount: Money (signed), account_id, account_name, to_account_id,
to_account_name, label_id, label_name, payee, note, tags, splits: [{label_id, label_name, amount, note}],
source: manual|quickadd|import|cfdi|payroll|organizer, txn_id, editable, non_editable_reason: str|null,
commitment_id: str|null, voided, attachment}`.

`attachment` is a receipt photo id (`rcp-…`, `aurum/ingest/receipts.py`):
accepted on `EntryIn`/`EntryPatch`, validated to exist in the same workspace (unknown → 404), kept across
edits by `merge_patch`, cleared by sending `null`. Metadata only — it never touches the ledger.

- `POST /api/pf/{ws}/entries` `EntryIn = {kind, date (IsoDate), amount: Money (> 0), account_id,
  to_account_id?, label_id?, payee?, note?, tags?, splits?: [{label_id (required), amount, note?}],
  source?, commitment_id?}`. Rules (all checked **before** the ledger is touched): amount ≤ 0 / float /
  text → 422; bad date → 422; currency upper-cased and must match `^[A-Z][A-Z0-9]{2}$` (400 otherwise);
  tags `^[A-Za-z0-9_-]{1,40}$` → 400; unknown account or label → **404** (no silent
  `Expenses:Other` fallback for unknown ids — only a missing `label_id` uses `Expenses:Other`/
  `Income:Other`); archived source/destination → 400; transfer needs `to_account_id ≠ account_id` (400),
  no splits on transfers (400); `label.kind ≠ kind` → 400 (`pf.entry.label_kind_mismatch`, e.g. "Esa
  categoría es de gastos; elige una de ingresos."); splits must sum exactly (400). Transactions carry
  `meta = {pf_entry_id, commitment_id?}`.
- `GET /api/pf/{ws}/entries?from&to&kind&account_id&label_id&q&commitment_id&limit=100(≤500)&cursor` →
  **`{"entries": [Entry], "next_cursor": str|null, "totals": {"in": Money, "out": Money, "net": Money,
  "count": int}}`**. Totals cover the FULL filtered set (voids excluded, foreign rows included); transfers
  and rows in a non-base currency are counted but never summed; `currency` = base currency. Rows are
  ordered `(date desc, id desc)`; the cursor is an opaque urlsafe-base64 `date|id` of the last row and a
  page is the rows strictly after it; an undecodable cursor → 400; `limit` outside 1..500 → 422;
  `from`/`to` not ISO → 422. Lookup maps (`accounts_by_id`, `accounts_by_ledger`, `labels_by_id`,
  `labels_by_account`) are built once per call; `_to_human_row` never loads the ledger.
- `PUT /api/pf/{ws}/entries/{id}` partial body (`EntryPatch`, merged over the stored row) —
  **validate-then-write**: the new transaction is built and validated first; then, under the
  per-workspace `entries._write_lock`, the reversal of the current transaction and the new one are
  appended and the row is updated in one `UPDATE`; if the `UPDATE` raises, the new transaction is
  reversed again and the error re-raised. Missing ledger transaction → **409**; already voided → 409;
  not editable → 403. `updated_at` is strictly later than `created_at` after an edit.
- `DELETE /api/pf/{ws}/entries/{id}` → `{"id", "voided": true}`: one reversal + `UPDATE voided=1`;
  a second delete → 409.
- `POST /api/pf/{ws}/entries/bulk` `{entries: [EntryIn]}` → `{"created": [ids]}`; all-or-nothing: every
  item is validated before the first write, and a write failure at index k reverses the k transactions
  already written, voids their rows and returns **400 `{"detail": {"index": k, "msg": …}}`**.
  Python: `bulk_create(ws, entries, *, atomic=True)`; `atomic=False` (CSV import) returns
  `{"created": [ids], "errors": [{"index", "msg"}]}`.
- Helpers exported for the organizer: `entries.create_entry(ws, EntryIn(source="organizer", …))`,
  `entries.delete_entry(ws, id)`, `entries.is_unedited(ws, id)` (`created_at == updated_at`),
  `entries.find_by_commitment(ws, commitment_id, due, window_days=3) -> row|None`, and
  `ledger_view.live_txns/live_postings` for void-aware matching.

### Entries from other subsystems

Every transaction this module writes carries `meta.pf_entry_id`. `list_entries` also scans the **live**
journal (`ledger_view.live_txns`) for transactions without that key (and without `meta.pf_account_id` or
one of the internal tags `opening-balance`, `balance-adjustment`, `sign-migration`, `voided-reversal`,
`entry-reversal`) and synthesizes a flat row per transaction: kind from which leg is `Income:`/`Expenses:`/
asset-only (transfer); **amount = Σ Assets/Liabilities legs on the primary side (the money that hit the
account)**; `account_id` via the `ledger account → pf_accounts` map (transfer `to_account_id` = the inflow
leg); label by ledger account; `source` guessed from tags/`meta.source` (`cfdi|payroll|quickadd|organizer`,
default `import`); `txn_id` = the link; `editable: false` with `non_editable_reason =
t("pf.entry.external_source")`. This is how a CFDI import or a payroll run still shows up in
`GET /entries`, read-only, without being edited into a wrong tax figure by this screen.

## 3. Income streams — `aurum/pf/streams.py`

`pf_income_streams(id, ws_id, name, source_type, amount, currency, gross_amount, cadence, anchor_days
JSON, weekday, next_expected, account_id, label_id, active, notes, commitment_ids JSON, created_at,
updated_at)`. Rows add `account_name`; money is rendered as Money.

- `POST /api/pf/{ws}/income/streams` `{name, source_type: salary|freelance|rent|pension|investment|other,
  amount: Money (> 0), gross_amount?, cadence: monthly|semimonthly|biweekly|weekly|annual|irregular,
  anchor_days?: [1..31], weekday?: 0..6, next_expected?, account_id, label_id? (kind income, else 400),
  active, notes?}`. The account and label are validated **first** (404 with nothing written).
- **`PUT .../{id}` is a partial merge and updates in place** (id/created_at kept). Mirrored commitments
  are patched through `organizer.commitments.update` when the new spec count equals the stored
  `commitment_ids` and they all resolve (same ids, `created_at` untouched); otherwise the old ones are
  removed (`organizer.commitments.soft_delete`, or a `hard_delete` when the organizer provides one) and new
  ones created.
  `active=false` → commitments `status="paused"` (and back to `active`).
- Mirrored commitments: `kind="income"`, `status`, `merchant_patterns = [normalize(name), name.upper()]`,
  `weekday`, `label_id`, `category_hint = source_type`. Semimonthly pay mirrors into **one monthly
  commitment per anchor day** (the organizer has no semimonthly cadence; two monthly commitments clamped
  at month end are equivalent for forecasting). `irregular` is approximated as a 30-day `custom` step.
- `DELETE .../{id}` removes the mirrored commitments (`hard_delete` when it exists, else `soft_delete`)
  and deletes the stream row (setup metadata, not ledger history).
- `GET .../{id}/history` → per projected occurrence `{due, expected, received, status, entry_id}`: a pf
  entry stamped with the `commitment_id` (`entries.find_by_commitment`, ±3 days) wins; otherwise the
  organizer's own matching (`occurrences.recent`) decides.

## 4. Onboarding — `aurum/pf/onboarding.py`

`GET /api/pf/{ws}/onboarding` → `{"steps": [{"id": "accounts"}, {"id": "income"}, {"id": "recurring"},
{"id": "first_entries", "done", "count", "hint"}], "done": accounts.done && first_entries.done}`.
`first_entries` counts non-voided `pf_entries` with `source in (manual, quickadd)`. `import` is not a
step (a shortcut card on the done screen); categories are pre-seeded, so they are not a step.

## 5. Budgets — `aurum/pf/budgets.py`

- `GET /budgets?period` → `[{id, label_id, label_name, period, amount: Money, currency, rollover}]`
  (python `list_budgets` keeps `amount` as the stored decimal string for `organizer/plan.py`).
- `POST /budgets` `{label_id, period (YYYY-MM), amount (> 0), currency? (default base), rollover?}`:
  unknown label → 404, duplicate `(label_id, period)` → **409** (`BudgetExists`), bad period → 422.
- `POST /budgets/copy` `{"from": "YYYY-MM", "to": "YYYY-MM"}` → `{"created", "skipped", "period"}`,
  idempotent: labels already budgeted in `to` (or archived) are skipped.
- `GET /budgets/status?period` → `{period, currency, budgets: [{budget_id, label_id, label_name, icon,
  budget, carried, effective, spent, remaining: Money, pct: number (percent, 1 decimal), state:
  ok|warn|over (≥80 % / ≥100 %), rollover, alert ("none"|"80"|"100", compat), account, rollover_applied,
  deductible_share, explain}], totals: {budget, spent, remaining}, has_previous, previous_period,
  safe_to_spend: Money (compat, label "Presupuesto restante"), explain}`. Spent = `ledger_view` sums under
  the label's account for the month (one ledger load per status call). Bad period → 422.

## 6. Goals — `aurum/pf/goals.py`

`pf_goals` gained `account_id` (migration v2). Row: `{id, kind: savings|emergency|debt|purchase, name,
target: Money, currency, target_date, account, account_id, account_name, progress: Money, remaining:
Money, pct (percent number), monthly_required: Money|null, target_date_invalid?: true, explain,
months_of_spend_covered? (emergency)}`.

- `POST /goals` `{kind, name, target, target_date?, account_id (preferred) | account (advanced ledger
  string)}` — `account`/`currency` derived from `pf_accounts` (unknown `account_id` → 404, neither →
  400, bad kind → 422, `target_date < today` → 422 at the route only, so `demo/extras.py` can seed
  historical goals). `PUT` is a partial merge (`GoalPatch`); `update_goal(ws, id, Goal)` still works.
- Progress: savings/emergency/purchase = the account's signed balance; **debt = `target − owed`
  (owed = −signed) clamped at 0**. A stored `target_date` that fails to parse never raises: the row
  carries `target_date_invalid: true` and no `monthly_required`. Contributions are ordinary transfers.

## 7. Migrations — `aurum/pf/migrations.py`

| v | name | what |
|---|---|---|
| 1 | `labels_kind_archived` | `pf_labels.kind` (`expense|income|transfer`, backfilled from the account root) + `archived` |
| 2 | `goals_account_id` | `pf_goals.account_id`, backfilled from `pf_accounts` by `(ws_id, account)` |
| 3 | `entries_commitment_id` | `pf_entries.commitment_id` + `ix_pf_entries_ws_commitment` (index lives here, not in `schema.sql`, because schemas run before migrations on old DBs) |
| 4 | `liability_sign` | every `credit_card|loan` row whose ledger balance (in its currency) is > 0 gets a correction transaction (`−2·balance` vs `Equity:Opening`, tag `sign-migration`, `meta.pf_account_id`) and a WARNING log; **raises `RuntimeError` (migration aborted, v1–v3 kept) when the workspace is in `AURUM_PROTECTED_WORKSPACES` (default `personal`) unless `AURUM_MIGRATE_PROTECTED=1`** |

A migration uses only the connection it receives plus ledger calls (never `store.db()`/`connect()` —
the runner holds a non-reentrant lock). `schema.sql` already carries the final columns for fresh DBs.
On a database with no card/loan rows, v4 is a no-op. Covered by `tests/pf/test_migrations_pf.py`.

## 8. Shortcuts that write real entries — `aurum/ingest/quickadd.py`, `aurum/ingest/bank_csv.py`

Shortcuts create ordinary editable entries: nothing they write is special or locked.

- `POST /api/ingest/{ws}/quickadd` `{"text", "account_id"?, "commit"?: false}` → `{"id": null|entry_id,
  "kind": "quickadd", "status": "preview"|"committed", "proposed": Transaction, "confidence", "warnings":
  [str], "preview": {kind, amount: Money, account_id, account_name, label_id, label_name, payee, date},
  "entry": Entry|null}`. Account resolution: `account_id` (404 when unknown) → a whole-word match on a pf
  account's name/institution words → the single non-archived cash/checking account → **400
  `pf.quickadd.no_account`** ("Primero agrega una cuenta…"). Kind is income on a negative amount or a
  word in `{ingreso, deposito, depósito, cobro, income}`; the label comes from `labels.match_label`
  (whole-word, accent-insensitive, scoped to the workspace) and is dropped with a warning when its kind
  differs; date = today. **Commit → `pf.entries.create_entry(source="quickadd")`, editable, no inbox
  row**, audit recorded. The legacy `parse_quickadd(text, ws_id, base_currency)` wrapper (Telegram)
  returns a `Transaction` proposal that uses the resolved pf account when one exists and the old
  `Assets:Cash` fallback otherwise.
- `POST /api/ingest/{ws}/bank/csv` (multipart `bank`, **`account_id` (required → 422 when missing, 404
  when unknown)**, `file`) → `{"created": [ids], "imported": n, "skipped_duplicates": n, "errors":
  [{"line", "detail"}]}`. Lines are deduped by the existing `line_hash`; each new line becomes
  `EntryIn(kind by sign, amount=|x|, account_id, label_id=match_label when the kind matches,
  payee=description[:120], source="import", tags=["import", "csv-<slug(bank)>"])` through
  `bulk_create(atomic=False)`; unparsable dates/amounts and zero amounts are reported per line and their
  bank line is **not** recorded (fix and re-import). No inbox items.

## Design notes and limitations

- Transfers are signed negative, from the paying account's side.
- Opening-balance / adjust / sign-migration rows are ledger-only (`meta.pf_account_id`) and never appear
  in `GET /entries`; they show in the balance immediately. Showing them as read-only rows is a possible
  improvement.
- Foreign-row synthesis is a heuristic: multiple Income/Expenses legs collapse to the first one found.
- `tags` are validated in code (400) rather than through `core.validation.Tag` (422), so a bad tag is
  rejected like the other entry rules: 400, with the ledger byte-identical.
- `aurum/pf/types.py` (`MoneyIn`, `PositiveMoney`) pre-checks the raw money payload so every pf body fails
  with a field-level 422 and a plain message ("send money as a string", "not a number").
- `streams._remove_commitments` calls `organizer.commitments.hard_delete` when it exists and otherwise
  `soft_delete` (the organizer currently provides only `soft_delete`).
- `budget_status`'s `pct` is already a percent number (`spent / effective * 100`); the insights
  budget-alert nudge shows it unscaled.

## Tests

`tests/pf/conftest.py` runs every pf test twice — `ledger[memory]` (InMemoryLedger monkeypatched onto
every pf module) and `ledger[beancount]` (the real store under the tmp `AURUM_DATA_DIR`) — and offers a
`ws` fixture that creates a workspace through the API. Files: `test_voids.py`, `test_liabilities.py`,
`test_update_atomic.py`, `test_validation_http.py` (table-driven, every row asserts the journal length is
unchanged), `test_entries_paging.py`, `test_labels_kind.py`, `test_budgets_copy.py`,
`test_goals_account.py`, `test_accounts_archive_and_credit.py`, `test_streams_update.py`,
`test_migrations_pf.py` (a legacy DDL fixture upgraded through `connect()`), and
`test_http_personal_flow.py` (the whole personal flow over HTTP on a fresh Beancount workspace, asserting
`beancount.loader.load_file(main)[1] == []` and `/api/ledger/{ws}/balances == /accounts` after every
write, plus one exact rendered expense block).
