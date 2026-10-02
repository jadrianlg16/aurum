# demo — the synthetic demo workspaces

`aurum/demo/` builds the synthetic workspaces every end-to-end check and screenshot runs on. Nothing
in them is real: no real RFC, CFDI, bank statement or person (synthetic fixtures only, see
[ARCHITECTURE.md](../ARCHITECTURE.md#principles)).

| workspace | built by | what it is |
|---|---|---|
| `demo-mx` | `aurum/demo/generate.py` | RESICO persona física, three months of CFDIs, bank CSVs and ledger |
| `demo-personal` | `aurum/demo/personal.py` | personal-only "Mi dinero" fixture, no tax data |
| `demo-us` | `aurum/taxus/demo_us.py` | Texas sole proprietor (see [taxus.md](taxus.md)) |
| `demo-biz` | `aurum/business/demo_biz.py` | persona moral in Nuevo León (see [business.md](business.md)) |

`aurum/demo/extras.py` wires them together: it registers the demo CFDIs in the ingest table, seeds the
pf tables, and calls the US and business builders. Every step is idempotent and defensive — if another
module is missing, its part is skipped and reported.

```
uv run python -m aurum.demo [--data-dir PATH] [--force] [--json]
python -c "from aurum.demo.generate import build_demo; build_demo(path)"   # for tests
```

Idempotent: if `docs/demo-manifest.json` already exists the workspace is returned untouched
(`--force` rebuilds).

## `demo-mx`: what it creates

Workspace `demo-mx` — personal, MX, `MXN`, `es`, profile `{rfc: XAXX010101000, regime: RESICO_PF,
state: NL}` — then, under `{AURUM_DATA_DIR}/workspaces/demo-mx/`:

* `docs/cfdi/*.xml` — 12 CFDI 4.0 documents across 2026-06…08: emitidos PUE and PPD, one REP
  complemento (`pago20`), recibidos including one paid in efectivo (`forma_pago=01`) and one
  investment (`UsoCFDI=I04`); plus `index.json`, the parsed index the tax layer falls back to.
* `docs/bank/bbva-2026-{06,07,08}.csv` — BBVA-shaped rows (`Fecha, Descripcion, Cargo, Abono, Referencia`).
* `main.beancount` / `accounts.beancount` — the RESICO chart of accounts plus 13 transactions:
  opening balances, every bank line, the cash-paid expense, and receivables for the two uncollected
  invoices.
* `docs/demo-manifest.json` — the **expected** audit result, so tests assert against a written
  expectation rather than against whatever the code happens to return.

All RFCs are fake: `XAXX010101000` (SAT's generic), `DPM010101AA1`, `DPF010101BB2`, `DPR010101CC3`.

### Expected result for `2026-08`

| figure | value |
|---|---|
| collected income (excl. IVA) | 37,000.00 |
| ISR (1.10%) | 407.00 |
| IVA trasladado / acreditable / a cargo | 5,920.00 / 800.00 / 5,120.00 |
| ISR retenido | 312.50 |

| diff | amount | documents |
|---|---|---|
| `pue_not_collected` | 13,920.00 | `AGO-PUE-E` |
| `ppd_missing_rep` | 9,280.00 | `AGO-PPD-F` |
| `deposit_without_cfdi` | 6,500.00 | — |
| `cash_paid_expense` | 160.00 | `REC-AGO-2` |
| `fixed_asset_iva` | 3,200.00 | `REC-AGO-3` |

June: 20,000.00 / 200.00 / 2,720.00. July (the REP month): 45,000.00 / 495.00 / 6,560.00.

### Gotchas

* Uncollected invoices are posted to `Assets:Receivable:Clients`, so `Income:Freelance` in the ledger
  is an **accrual** view while the tax layer is strictly cash-basis. Different numbers, on purpose.
* `generate.py` does not create labels, budgets, goals, the credit card or the loan; those live in the
  `pf_*` tables and are seeded by `aurum/demo/extras.py` (`seed_pf`) through the pf module.
* `build_demo(data_dir)` sets `AURUM_DATA_DIR` in the process environment.

### `(verify)`

The numbers above are internally consistent by construction. They are not a real SAT declaration.

## Boot-time commands

```
uv run python -m aurum.demo --personal        # seed demo-personal only
uv run python -m aurum.demo --stamp-demos     # profile.demo=true on every demo-* lacking it
uv run python -m aurum.demo --organizer       # demo-mx recurring bank lines + commitments + auto-accept
uv run python -m aurum.demo --refresh         # demo-mx pf_accounts + stamps + demo-personal (idempotent, every boot)
```

### `demo-personal` (`aurum/demo/personal.py`)

A from-scratch personal workspace seeded **only** through public pf/organizer functions
(`accounts_admin.create_account`, `pf.entries.create_entry`, `pf.budgets.create_budget`,
`pf.goals.create_goal`, `pf.streams.create_stream`, `organizer.commitments.create`) — never a direct
ledger append or raw SQL insert from this module. It exists so "Mi dinero" screens have a clean,
personal-only fixture that isn't tangled up with `demo-mx`'s RESICO tax data.

Seeded: 4 accounts (`BBVA Nómina` checking 18,500; `Efectivo` cash 1,200; `Ahorro viaje` savings
12,000 opened 95 days ago; `Nu` credit_card cut 15/due 5/limit 30,000 with **no** opening balance —
its balance is built entirely from the card entries below, so the sign is correct whether or not the
liability-sign migration (liabilities typed positive, stored signed) has run on the install); 1 income
stream (`Sueldo`, semimonthly [15, 30], 22,500); 4 non-income commitments (`Renta`, `Netflix`,
`Telcel`, `Gym`); 6 budgets (3 labels × previous + current period); 1 goal (`Viaje a Japón`, purchase,
target 60,000, linked to `Ahorro viaje`); ~48 deterministic entries over the last 3 months (rent,
weekly Súper, Comida fuera + Uber on the card, gasolina, Telcel, Gym, Netflix, 2 salary
deposits/month, 1 transfer/month to `Ahorro viaje`), future dates skipped when `today` is mid-month.

**Feature-detection:** three optional fields — `EntryIn.commitment_id`, `Goal.account_id`,
`CommitmentIn.account_id` — are checked in `model_fields` before use (falling back to `account`/tags),
so the seed still runs against a model that lacks one of them; the deterministic entry counts are the
same either way.

**Idempotent** on `workspace.json`'s `profile.demo_seed.version`: once a workspace is stamped, a
second call returns `{"status": "already-seeded"}` immediately without touching anything — this is
what lets `--refresh` run on every container boot without duplicating data. The seed keeps the
`today` it was first built with; it does not "catch up" as the calendar moves forward.

### `demo-mx` pf accounts (`demo/extras.register_pf_accounts`)

`demo-mx`'s ledger has real accounts (`Assets:Bank:BBVA`, `Assets:Cash`), and the "Mi dinero" screens
need matching `pf_accounts` registry rows to see them. `register_pf_accounts("demo-mx")` inserts three
rows keyed on `(ws_id, account)` via `INSERT OR IGNORE` against the *existing* ledger account strings —
**no ledger append**, so the balances `tests/demo/test_demo_workspace.py` pins
(`Assets:Bank:BBVA == 123217.50`) never move:

| pf_accounts row | ledger account | type |
|---|---|---|
| BBVA | `Assets:Bank:BBVA` | checking |
| Efectivo | `Assets:Cash` | cash |
| Tarjeta BBVA | `Liabilities:CreditCard:BBVA` | credit_card, cut 20 / due 10 / limit 60,000 / apr 0.42 |

It also re-points the two goals `seed_pf` creates (`Fondo de emergencia` → the BBVA row,
`Laptop nueva` → the Efectivo row) via `goals.update_goal` **unconditionally** — `seed_pf` only ever
creates goals once, so without this they would keep pointing at accounts (`Assets:Bank:Nu`,
`Assets:Bank:Banorte`) that don't exist as pf accounts. The demo loan stays on
`Liabilities:Loans:Auto`.

### `stamp_demos()`

Sets `profile.demo = true` on every `demo-*` workspace that lacks it, so `GET /api/workspaces` sorts
it into the "demos last" group. `demo-biz` is deliberately skipped — it ships
`profile.synthetic = true` instead, being a persona-moral business fixture rather than a personal
demo. `demo-mx` also gets `modules.tax` on, so tax nudges and calendar items stay visible for it.

### `docker/entrypoint.sh` order

1. `python -m aurum.core.db` — migrate the metadata db; **fails the boot** on a migration error rather
   than starting against a half-migrated database.
2. `python -m aurum.demo` — first-boot only (guarded by `workspaces/demo-mx/workspace.json` existing).
3. `python -m aurum.demo --organizer` — first-boot only (guarded by `docs/demo-org.json`).
4. `python -m aurum.demo --refresh` — every boot; all three of its steps are idempotent, so this never
   duplicates data. It only ever touches `demo-*` ids: a real workspace such as `personal` is never
   reset or reseeded on boot.

## Tests

`tests/demo/test_demo_workspace.py` (the `demo-mx` build, its manifest and pinned balances,
`register_pf_accounts`) and `tests/demo/test_personal_seed.py` (the `demo-personal` seed and its
idempotency).
