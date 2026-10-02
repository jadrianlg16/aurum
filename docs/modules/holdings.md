# holdings — investments, cost basis, contributions

Mounted at `/api/holdings`. Never recommends a security — every response is descriptive.

## Ledger integration (read this before touching cost basis)

`aurum.ledger.base.Posting` has no `cost`/`price` field, and `aurum.ledger.beancount_store.BeancountLedger`
only renders `account amount` per posting — it has no support for Beancount's `{units} SYM {price}` cost
syntax. Rather than extend the shared ledger layer for one module:

- `aurum/holdings/ledger_ext.py` writes each trade as a **plain balanced `Transaction`** through the
  public `LedgerStore.append()` API — units of the investment "commodity" account plus the offsetting
  cash/income account. No cost-basis syntax is written to `main.beancount`.
- `holdings_trades` (SQLite, `aurum/holdings/schema.sql`) is the actual source of truth for cost-basis
  lot math (positions, FIFO realized gains, unrealized gains). This keeps the computation deterministic
  and testable without Beancount inventory-booking semantics.
- If `cost`/`price` are ever added to `Posting` in `aurum/ledger/base.py`, `ledger_ext.write_trade_txn`
  can be re-pointed to emit real cost-basis postings without changing this module's public functions.

## Endpoints

- `POST /{ws}/trades` `{date, account, symbol, kind, units, price?, fees?, cash?, counter_account?, limit_key?}`
  → the stored trade row (`kind`: `buy|sell|dividend|interest|contribution`). `buy`/`sell` require
  `units` and `price`; `dividend`/`interest`/`contribution` require `cash`. `limit_key` (one of
  `401k|ira|hsa_self|hsa_family|ppr`) tags a contribution against `holdings_limits`.
- `GET /{ws}/trades?symbol=` → raw trade rows.
- `GET /{ws}?as_of=&year=&jurisdiction=MX|US` → `{positions, realized_gains, allocation, contributions,
  tax_explain, symbols, explain}`.
  - `positions[]`: `{symbol, account, units, cost_basis, market_value, unrealized_gain, asset_class,
    name, price_as_of}` — `market_value`/`unrealized_gain` are `null` when no price has been recorded.
  - `realized_gains[]`: one row per FIFO-matched sell fragment: `{date, symbol, units, proceeds, cost,
    gain, currency, lot_opened, holding_period_days}`.
  - `allocation.by_asset_class`: percentage of total market value per `holdings_symbols.asset_class`.
- `GET /{ws}/explain?jurisdiction=MX|US` → tax-lens `Explain` (informational, cited, never a filed number).
- `GET /{ws}/limits?year=` / `GET /{ws}/symbols` / `POST /{ws}/symbols`.
- `POST /{ws}/prices` `{symbol, date, price, source?}`; `GET /{ws}/prices/{symbol}`.
- `POST /{ws}/prices/fetch` `{symbols: [...]}` — guarded: returns `{"fetched": [], "warnings": [...]}`
  when `beanprice` isn't importable or fetching fails; never raises, never touches the network in tests.

## Lot method

FIFO (oldest lot consumed first) for realized-gain matching. This is the IRC § 1012 US default; whether
it matches the correct MX lot-method election for a given security/broker is **`(verify)`** — see the
citation gaps below.

## `holdings_symbols` seed

`CETES` (bond, MXN), `VOO` (equity, USD), `VTI` (equity, USD), `BTC` (crypto, USD) — seeded once per
workspace on first access, same pattern as `pf_labels`. `POST /{ws}/symbols` adds/overwrites entries.

## `holdings_limits` seed (2026, all `(verify)`)

| key | jurisdiction | amount | citation |
|---|---|---|---|
| `401k` | US | 23,500 USD | IRC § 402(g) |
| `ira` | US | 7,000 USD | IRC § 219 |
| `hsa_self` | US | 4,300 USD | IRC § 223 |
| `hsa_family` | US | 8,550 USD | IRC § 223 |
| `ppr` | MX | 152,331 MXN | LISR art. 151 (10% of income or 5 UMA/year, whichever is lower — verify) |

None of these are confirmed against the current-year IRS/SAT text; `verified: false` on every row until
a human review or a registry rule confirms them.

## Tax lens (`GET /{ws}/explain`)

MX: cites LISR arts. 129 (enajenación de acciones), 133 (intereses), 150 (declaración anual) — all
`(verify)`. US: cites IRC § 1(h) (capital gains rates) and § 1222 (short/long-term definitions) — both
`(verify)`. Informational only; never computes a filed liability.

## Testing

`tests/holdings/` uses `InMemoryLedger` (monkeypatched onto `aurum.holdings.ledger_ext.get_ledger`) and a
temp `AURUM_DATA_DIR` SQLite DB (autouse fixture in `tests/conftest.py`). No network, no beanprice.
