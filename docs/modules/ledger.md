# ledger — Beancount v3 store

`aurum/ledger/` holds the `LedgerStore` protocol and its in-memory fake (`base.py`), the Beancount
store (`beancount_store.py`), the parse cache (`cache.py`), financial statements (`statements.py`) and
the `/api/ledger` router. The ledger is the source of truth for every balance (see
[ARCHITECTURE.md](../ARCHITECTURE.md#principles)); SQLite only holds metadata.

## Model

`aurum/ledger/beancount_store.py` → `BeancountLedger`, a `LedgerStore` over plain-text files:

```
{AURUM_DATA_DIR}/workspaces/{ws}/
  accounts.beancount   option header + one `open` per account
  main.beancount       include of accounts.beancount, then appended transactions
  ledger.lock          transient write lock
```

* **Auto-open.** Any account used by an appended transaction is opened automatically, dated at its
  first use. If a later append carries an *earlier* date, the existing `open` is rewritten backwards,
  so the file always loads with zero errors.
* **Template.** `apply_template(ws, "mx_resico_pf")` opens the persona-física RESICO chart of accounts
  (`aurum/ledger/templates/mx_resico_pf.beancount`) at the `2000-01-01` floor. Idempotent.
* **Locking.** Writes take a per-workspace `threading.RLock` *and* an exclusive-create lock file, so
  the API and `python -m aurum.demo` cannot interleave appends. A lock older than 10 s is treated as
  stale and broken (a crashed process must not wedge the app).
* **Reads** go through `beancount.loader.load_file`, served from `aurum/ledger/cache.py` while the
  files are unchanged (below); `query()` goes through `beanquery.connect`. Values that are not
  JSON-native (`Inventory`, `Position`, `Decimal`, `date`) are returned as strings. When the loader
  reports errors, `load()` logs one WARNING (count + first `lineno` + message) and `/{ws}/health`
  lists them.
* **Workspace ids** are checked in `BeancountLedger.workspace_dir()` against
  `^[a-z0-9][a-z0-9-]{1,40}$` (`InvalidWorkspaceId` → `400 {"error":"invalid_workspace_id"}` via the
  app-level handler), so no path under `workspaces/` is ever built from an unchecked id.

### Validation and the render guard

Every write — `append()`, `replace_txn()`, `apply_template()`'s opens — goes through the same gate:

1. **Re-validate the model.** `Transaction.model_validate(txn.model_dump())` runs every validator
   again, because callers such as `ingest/inbox.py` and `organizer/organize.py` build postings with
   `model_copy(update=)`/`model_construct`, which skip them. A failure is a `pydantic.ValidationError`
   → `400 {"error":"validation","detail":[…]}`.
2. **Validators** (`aurum/ledger/base.py`, `aurum/core/money.py`): `Posting.account` →
   `validate_account` (Beancount grammar, root ∈ Assets/Liabilities/Equity/Income/Expenses, no control
   chars); `tags`/`links` items `^[A-Za-z0-9\-_/.]+$`; `payee`, `narration` and meta values carry no
   `[\x00-\x1f\x7f]`; `Amount.amount` accepts Decimal/int/str only (float, bool, NaN/Infinity and junk
   raise `ValueError` → 422 at the route boundary); `Amount.currency` is stripped, upper-cased and
   must match `^[A-Z]{3}$`.
3. **Render, then parse back.** `_render_checked()` renders the block and runs
   `beancount.parser.parser.parse_string` on it: exactly one entry, that entry a `Transaction`, and
   zero parser errors — otherwise `LedgerRenderError` (→ `400 {"detail": …}`) and **nothing is
   written**. An injected `option`/`plugin` line in an account or payee yields extra entries and
   errors; a lowercase currency yields zero entries. Amounts render through `q2` (HALF_UP, two
   decimals) and explicit postings are quantized *before* the balancing leg is computed so the
   rendered lines always sum to zero per currency.
4. **Locks.** The rendered text is written under the per-workspace `RLock` + the lock file;
   `_open_accounts` validates every account and rewrites `accounts.beancount` under the same locks.

`replace_txn(ws, txn_id, txn)` is the one in-place rewrite of `main.beancount` (PUT and void use it):
it finds the block whose header carries `^txn_id`, replaces it with the re-rendered body (same link
kept), opens any new accounts, and invalidates the cache — all inside the locks. A missing block is
`TxnNotFound` (`LookupError`), which the router maps to `404`.

### Parse cache (`aurum/ledger/cache.py`)

Process-wide dict keyed on the resolved `main.beancount` path (tests reuse `ws1` across temp dirs),
validated against `(main mtime_ns, main size, accounts mtime_ns, accounts size)` — size is part of the
key because Windows mtime resolution is 100 ns. Holds `(entries, errors, options)` under a
`threading.Lock`. The store calls `invalidate()` inside its write locks after every append, rewrite
and account open, so a reader in the same process never sees a stale parse; an external edit
(editor, another process) is caught by the stat key. `AURUM_LEDGER_CACHE=0` bypasses it. There is no
thread-local sqlite or any other per-thread state.

## Endpoints (`/api/ledger`)

| method | path | notes |
|---|---|---|
| GET | `/{ws}/journal?start=&end=&account_prefix=` | list of `Transaction` |
| GET | `/{ws}/balances?as_of=` | `{account: [Amount]}` |
| POST | `/{ws}/query` `{"bql": "..."}` | beanquery; 400 on a bad query |
| GET | `/{ws}/accounts` | opened + used accounts |
| GET | `/{ws}/health` | `{"txns":n,"errors":[{"lineno","message"}][:20],"error_count":k}` — loader errors on the file |
| POST | `/{ws}/transactions` | body = `Transaction`; returns `{"id": ...}` |
| GET | `/{ws}/statements/{period}?type=pnl\|balance\|cashflow` | `period` is `YYYY-MM` or `YYYY` |
| PUT | `/{ws}/transactions/{txn_id}` | rewrites the block for that `^link`; requires the Beancount store |
| DELETE | `/{ws}/transactions/{txn_id}` | void: tag `#voided` + append a reversing entry; never erases |

### Statements (`aurum/ledger/statements.py`)

`build_statement(store, ws, period, type, currency, lang)` →
`{"type","period","currency","sections":[{"title","rows":[{"account","label","amount"}],"total"}],"net","explain"}`.

* **pnl** — `Income:*` vs `Expenses:*` postings within the period (income sign flipped positive).
* **balance** — `Assets:*` / `Liabilities:*` / `Equity:*` balances as of the period end.
* **cashflow** — the net change in `Assets:Bank:*` + `Assets:Cash` postings per transaction, grouped by
  the transaction's other (non-cash) account.

`Explain.summary` describes the method, not a statutory figure, and is localized via
`aurum.core.i18n` (`Workspace.language` or `?lang=`).

### Editing transactions (`aurum/ledger/router.py`)

Both `PUT` and `DELETE` require `get_ledger()` to return a `BeancountLedger` instance — they rewrite
the plain-text ledger file directly (`main.beancount`), which the `InMemoryLedger` fallback cannot do;
that combination answers `501`.

* **PUT** calls `store.replace_txn(ws, txn_id, new_txn)`: the block whose header carries `^{txn_id}`
  is re-rendered with the *same* link and replaced in place, under the write locks and after the
  render guard. This is the one place the ledger file is rewritten rather than appended to — the
  prior text is not kept. The router only calls store methods; the block-splitting lives in the store.
* **DELETE (void)** never rewrites history that way: it re-renders the *original* transaction with an
  added `#voided` tag (same link, same postings — only the tag line changes) through `replace_txn`, and then **appends** a
  new reversing transaction (postings negated, tagged `#voided-reversal`, linked back to `txn_id` via
  `meta.reverses` and a second beancount `^link`). Voiding an already-`#voided` transaction is a `409`.
  Both operations call `aurum.core.audit.record` with the before/after transaction JSON.

## Env

`AURUM_DATA_DIR` (`BeancountLedger(data_dir=...)` overrides it for tests) and `AURUM_LEDGER_CACHE`
(default `1`; `0` re-parses on every read).

## Gotchas

* A transaction id is `links[0]` when present, else `txn-<hex>`; the id is always written as a `^link`.
* Meta keys that are not valid Beancount identifiers (`^[a-z][a-zA-Z0-9_-]+$` — at least two
  characters, the lexer rejects single-letter keys) are **dropped**, not escaped. Meta values are
  always written as quoted strings and must not contain control characters (validator).
* HALF_UP happens in `_quantized_postings` (before the balancing leg); `q2` in `_fmt_amount` is
  defence in depth. Removing the quantization step fails `tests/ledger/test_roundtrip_props.py`
  and `test_render_validation.py` (`1.005` renders `1.00` under `:.2f`'s HALF_EVEN instead of `1.01`);
  reverting only `_fmt_amount` to `:.2f` does not, because it then formats already-quantized values.
* `tests/ledger/test_render_validation.py` byte-compares `main.beancount` before/after every rejected
  append — the guard must never leave a partial block behind.
* At most one posting may omit its amount (`Transaction.balanced()` fills it in before writing).
* Unknown workspaces read as empty (`[]`/`{}`) rather than raising — the API must not 500 on a typo.
* The template file is package data; if wheels are ever built, check that
  `aurum/ledger/templates/*.beancount` ends up in the wheel.

## Tests

`tests/ledger/` — the store (`test_beancount_store.py`), account validation
(`test_validate_account.py`), write validation and the render guard (`test_render_validation.py`), a
round-trip property test (`test_roundtrip_props.py`), the parse cache (`test_cache.py`), and statements
plus the PUT/void endpoints (`test_statements_and_edits.py`).

## `(verify)`

Nothing in this module is a tax fact. The chart of accounts is a reasonable default, not an
authority; per-entity templates beyond persona física RESICO are still an open question.
