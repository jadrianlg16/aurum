# fx — currency conversion

Mounted at `/api/fx`. Pure, offline-safe by default; Banxico is only consulted when explicitly enabled.

## `aurum.fx.rates.get_rate(base, quote, on) -> Decimal` lookup order

1. `base == quote` → `1`
2. `fx_rates` cache (SQLite, `aurum/fx/schema.sql`), exact `(base, quote, date)`, then exact inverse
3. `AURUM_FX_FAKE_DIR` fixture directory — one JSON file per pair, `BASE_QUOTE.json` =
   `{"YYYY-MM-DD": "rate", ...}`; nearest date on/before `on` if the exact date is missing; inverse file
   tried too. Used by every test in `tests/fx` — no network involved.
4. Banxico SIE (`aurum/fx/banxico.py`, series `SF43718` "FIX USD/MXN" — **`(verify)` series id against
   current SIE documentation**), only for the USD/MXN pair and only when `BANXICO_TOKEN` is set. A
   successful fetch is cached into `fx_rates` with `source="banxico"`.
5. Otherwise raises `FxRateNotFound`.

## `aurum.fx.rates.convert(amount: Amount, to: str, on: date | None) -> Amount`

Pure function, Decimal, quantized to cents (`aurum.core.money.q2`). Same-currency calls quantize without
a rate lookup.

## `aurum.fx.rates.net_worth_in(balances, currency, on) -> Amount`

Helper for other modules: takes the `{account: [Amount]}` shape from `LedgerStore.balances()`, converts
every currency into `currency`, and nets Assets minus Liabilities (same sign convention as
`aurum.pf.accounts.net_worth_as_of`). Raises `FxRateNotFound` if a currency present in the balances has
no path to `currency` — callers should pre-populate a rate or fixture rather than have this silently
drop a currency.

## Endpoints

- `GET /rate?base=&quote=&date=` → `{base, quote, date, rate}` or 404 (`FxRateNotFound`).
- `POST /rate` `{base, quote, date, rate}` → manual cache entry (`source="manual"`).
- `GET /rates?base=&quote=` → last 200 cached rows, most recent first.

## Env

`BANXICO_TOKEN` (empty by default — no network call is attempted without it), `AURUM_FX_FAKE_DIR` (empty
by default — no fixture lookup without it). Neither is in `aurum.core.config.Settings`; both are read
directly via `aurum.core.config.env()`, so the module stays self-contained.

## Testing

`tests/fx/` sets `AURUM_FX_FAKE_DIR` to a temp fixture dir with a synthetic `USD_MXN.json`; `BANXICO_TOKEN`
is left unset so `banxico.fetch_usd_mxn` always raises `FxLookupError` and is never actually exercised
over the network.
