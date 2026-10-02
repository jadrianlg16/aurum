# plan — Planning & simulation

Mounted at `/api/plan` by `aurum/api/app.py`. Code lives in `aurum/plan/**`; the `regime_mx` scenario
uses the general-regime rule (`aurum/rules/mx/general.py`, documented in
[rules-mx-general.md](rules-mx-general.md)).

## Layout

- `aurum/plan/engine.py` — simulation primitives: a seeded PRNG (mulberry32) + Box-Muller normal
  transform for Monte Carlo, the `q(arr,p)` percentile helper, one-way sensitivity, a generic
  scenario-comparison table builder, and a faithful float port of `depreciation.js`'s
  `depreciatedValue` (declining/straight/realistic methods), adapted from
  the author's financial-sim project (https://github.com/jadrianlg16/financial-sim). See the module docstring for exactly what is and isn't ported and why (the reference Monte
  Carlo loop is domain-specific and unseeded; what's cross-checked bit-for-bit is the shared machinery).
- `aurum/plan/scenarios/*.py` — one module per scenario. Each exposes a pydantic `Inputs` model,
  `SCHEMA = Inputs.model_json_schema()`, `METRIC_PATH` (a tuple path into `results` used as the scalar
  objective for `/sensitivity`), and `run(inputs: Inputs) -> dict` returning
  `{"inputs": ..., "results": ..., "explain": Explain}`.
- `aurum/plan/router.py` — the six scenarios' catalog/run/sensitivity/montecarlo endpoints, plus saved
  scenario CRUD backed by `plan_saved` (`aurum/plan/schema.sql`).

## Scenarios

| id | what it compares | numbers come from |
|---|---|---|
| `regime_mx` | RESICO vs. Actividad Empresarial y Profesional, 12 months of a uniform income/expense mix | `mx.resico.isr_monthly` and `mx.general.isr_provisional` via `aurum.rules.registry` |
| `entity_us` | Sole proprietorship vs. single-member LLC vs. S-corp sketch (reasonable-salary split) | informational only, `(verify)` SE-tax/FICA constants, no rule registry dependency |
| `buy_vs_rent` | Buy (mortgage + carrying costs, net equity at horizon) vs. rent (growing rent, discounted) | `aurum/pf/finance.py`'s `build_amortization` |
| `cash_vs_credit` | Pay cash (with discount, minus opportunity cost) vs. finance | `aurum/pf/finance.py`'s `build_amortization` |
| `retirement` | Contributions + expected return + volatility + inflation over a horizon → p10/p50/p90 ending balance | `aurum/plan/engine.py`'s `run_monte_carlo_retirement` |
| `debt_payoff` | Avalanche (highest APR first) vs. snowball (smallest balance first) | month-by-month simulation in `debt_payoff.py` |

Every `run()` returns an `Explain` — a one-line summary in Spanish, worked steps, and
(where applicable) rule versions/citations. `regime_mx`'s explain includes a "what would flip the
answer" step: a bisected deduction-ratio breakeven between the two regimes at the given income level.

## Endpoints (relative to `/api/plan`)

- `GET /{ws}/scenarios` — catalog: `[{id, schema, metric_path}]` for all six scenarios.
- `POST /{ws}/scenarios/{id}/run` — body is the scenario's raw inputs dict (omitted fields use the
  pydantic defaults). For `regime_mx`, `monthly_income` is defensively pre-filled from
  `aurum.ledger.base.get_ledger()` when the ledger has any `Income:` postings for the workspace and the
  caller didn't supply it — wrapped in try/except so a missing/unwired ledger never 500s the endpoint.
- `POST /{ws}/scenarios/{id}/sensitivity` — body `{inputs, vary: [field, ...], range_pct}`. Perturbs each
  named input field ±`range_pct` around its value, re-runs the scenario, and reports the scalar metric at
  `METRIC_PATH` for each — `low/high/range` per field (the same shape as the reference
  `sensitivity.js`), sorted by `range` descending.
- `POST /{ws}/scenarios/{id}/montecarlo` — body `{inputs, n, seed}`. For `retirement`, calls its own
  `run()` with `iterations=n, seed=seed`; for any other scenario id, falls back to running the engine's
  generic retirement Monte Carlo directly over whatever `starting_balance`/`monthly_contribution`/etc.
  fields are present in `inputs` (400 if none of that shape is present).
- `GET/POST/PUT/DELETE /{ws}/saved[/{id}]` and `POST /{ws}/saved/{id}/run` — named, reusable input sets
  (`plan_saved` table: `id, ws_id, scenario_id, name, inputs (JSON), created_at, updated_at`).

## Sample `regime_mx` response (trimmed, default inputs: 30,000 MXN/mo income, 6,000 MXN/mo deductions)

```json
{
  "results": {
    "resico": {"annual_isr": "3960.00", "effective_rate": "0.011"},
    "general": {"annual_isr": "38856.65", "effective_rate": "0.1079351388888888888888888889"},
    "cheaper": "regime_mx.resico",
    "deduction_ratio_breakeven": "0.8084"
  },
  "explain": {
    "summary": "RESICO: 3960.00 MXN de ISR anual vs. Actividad Empresarial: 38856.65 MXN. Conviene regime_mx.resico."
  }
}
```

At this income level RESICO's flat rate on a much smaller base beats even generous deductions; the
general regime only wins if deductions exceed ~80.8% of income, which the "what would flip the answer"
step surfaces explicitly.

## Testing

- `tests/plan/test_engine.py` — cross-checks against real `node` runs: the seeded PRNG + Box-Muller
  formulas (mulberry32 is bit-identical to a JS mulberry32 for seed 42), the `q(arr,p)` percentile
  helper, and `depreciatedValue` against the *actual* reference `depreciation.js`
  (declining/straight/realistic methods) — see the test docstrings for the exact `node -e` commands run.
- `tests/plan/test_router.py` — FastAPI `TestClient` coverage of every endpoint, including 404/422 error
  paths and the saved-scenario CRUD round trip.

## Design notes

- The reference `monteCarlo.js` is a ride-share car simulator with an **unseeded** loop (`Math.random()`);
  there is no seeded algorithm in it to port verbatim. `engine.py` instead implements a standard seeded
  PRNG (mulberry32) driving the same Box-Muller transform the JS uses, so Aurum's Monte Carlo runs are
  reproducible and its core math is still cross-checked against real `node` output (see engine.py's
  module docstring for the reasoning).
- `sensitivity.js` and `compare.js` are domain-specific (ride-share car inputs); `one_way_sensitivity`
  and `compare_scenarios` in `engine.py` generalize their mechanics (perturb-and-measure; side-by-side
  rows) rather than porting their specific field lists.
