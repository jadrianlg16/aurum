# rules — the cited rule registry

`aurum/rules/` is the registry every tax figure comes from: code + citation + effective range + test
vectors. The product-level description of the registry is in [SPEC.md](../SPEC.md). **No model ever
produces a number here** (math lives in code, see [ARCHITECTURE.md](../ARCHITECTURE.md#principles)).

This page covers the registry and the RESICO/IVA rules. Other rule families have their own pages:
[rules-mx-general.md](rules-mx-general.md) (Régimen General), [rules-mx-nl.md](rules-mx-nl.md)
(Nuevo León payroll, IMSS, INFONAVIT) and [rules-us.md](rules-us.md) (US federal, Texas, cross-border).

## Model

```python
registry.get("mx.resico.isr_monthly", on=date(2026, 8, 31)).compute(collected_income="37000.00")
# -> RuleResult(value=Amount, explain=Explain)
```

A rule is `id · version · jurisdiction · citation · effective_from/to · compute(**inputs)`.
`registry.get` accepts either a bare id (newest, or the version in force `on` a date) or a pinned
`id@version`. `registry.describe()` powers `GET /api/rules`.

## RESICO and IVA rules (all `2026.1`)

| id | inputs | value | citation |
|---|---|---|---|
| `mx.resico.income_cash_basis` | `documents[]`, `period`, `rfc?` | collected income excl. IVA | RMF 2026 prefill rules (official_guidance) |
| `mx.resico.isr_monthly` | `collected_income` | monthly ISR | LISR art. 113-E (primary) |
| `mx.resico.retention_pm` | `amount`, `receptor_is_persona_moral` | 1.25% ISR withheld | LISR art. 113-J (primary) — **(verify)** |
| `mx.iva.monthly` | `documents[]`, `period`, `rfc?` | IVA a cargo (negative = saldo a favor) | LIVA art. 5 (primary) |

**ISR table (LISR art. 113-E, 2026)** — a *tiered flat* rate on the whole month's collected income,
**no deductions**: 1.00% ≤ 25,000 · 1.10% ≤ 50,000 · 1.50% ≤ 83,333.33 · 2.00% ≤ 208,333.33 ·
2.50% ≤ 3,500,000. Due the 17th of the following month.

**Cash basis** (`classify_income`): PUE counts in the issue month; a payment complement (tipo P)
counts in the month of each `FechaPago`; a PPD with no REP counts nowhere and is reported as
`ppd_missing_rep`. `tipo E` (nota de crédito) reduces the month. REP amounts are netted of IVA using
the related invoice's `subtotal/total` ratio (or an explicit `subtotal`/`iva` on the payment).

**IVA** (`classify_iva`): trasladado = the IVA inside what was collected; acreditable = received CFDIs
in the month that pass every check — receptor RFC is ours, actually paid (PUE, or PPD with a REP),
`forma_pago` is not `01`, and `UsoCFDI` in `{G01, G03}`. Exclusion reasons: `rfc_mismatch`,
`not_paid`, `cash_paid_expense`, `fixed_asset_iva`, `uso_cfdi_not_allowed`, `no_iva_on_document`.

## Test vectors

`aurum/rules/vectors/<rule_id>.yaml` — `{rule, version, cases: [{name, inputs, expect{amount,
currency}, explain_contains?, steps_contain?}]}`. `tests/rules/test_vectors.py` runs every case and
asserts that every registered rule has a vector file. Money is always a **string** in YAML, never a
float.

## Endpoints (`/api/rules`)

`GET /` → rules with versions + citations. `POST /{rule_id}/compute` (body = inputs, optional `?on=`).

## Env

None.

## `(verify)` — do not treat as settled

* **`mx.resico.retention_pm`** — the 1.25% rate, its base, and whether it credits against the monthly
  payment have not been read in LISR art. 113-J. Flagged in `explain.summary`, `confidence=0.5`.
* **Cumulative vs. per-month.** One secondary source describes the RESICO monthly computation as
  cumulative Jan→month. Aurum implements it per month, as the spec does. Unresolved.
* **Fixed-asset IVA.** The law does allow crediting IVA on investments; we exclude `UsoCFDI I0x`
  because that is what the SAT prefill does. Surfaced as a *difference*, never as advice.
* **`forma_pago` traceability.** Only `01` (efectivo) is treated as non-traceable; the long tail
  (compensación etc.) is accepted and flagged.
* **No vector from a real SAT prefill yet.** All vectors derive from the statute table and the spec,
  not from an observed declaration.

## Tests

`tests/rules/test_vectors.py` (every YAML vector), `tests/rules/test_registry_and_router.py` (registry
protocol, versioning, `/api/rules`).
