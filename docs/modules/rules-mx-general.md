# rules/mx/general — Régimen General ISR (pagos provisionales)

`aurum/rules/mx/general.py` registers one rule: `mx.general.isr_provisional@2026.1`, for personas
físicas con **Actividad Empresarial y Profesional** (LISR Título IV, Capítulo II, Sección I) — the
general regime, as opposed to RESICO (`aurum/rules/mx/resico.py`). Unlike RESICO, this regime **allows
deductions**.

## Inputs / outputs

`registry.get("mx.general.isr_provisional").compute(**inputs) -> RuleResult`

| input | meaning |
|---|---|
| `cumulative_income` | Ingresos acumulados del ejercicio a la fecha del periodo (sin IVA). Required. |
| `cumulative_deductions` | Deducciones autorizadas acumuladas del ejercicio a la fecha. Default 0. |
| `month_number` | Mes del periodo (1..12) — escala la tarifa acumulada. Required. |
| `prior_provisional_payments` | Suma de pagos provisionales de ISR ya enterados en el ejercicio. Default 0. |
| `retentions` | ISR retenido por clientes (personas morales) en el periodo. Default 0. |
| `currency` | Default `"MXN"`. |

Output `RuleResult.value` is the **payment due for the period** (never negative): the tarifa applied to
the cumulative taxable base, minus prior provisional payments, minus retentions. `RuleResult.explain`
carries the full worked calculation (base, bracket, marginal rate, tax before credits, and each credit
subtracted) plus citations.

## Mechanic: cumulative monthly tarifa

LISR art. 96's mechanic scales the single-month bracket table linearly by the number of elapsed months:
`cumulative_table_for_month(n)` multiplies every bracket's upper limit and cuota fija by `n` (rates are
unchanged), then `apply_table(base, table)` finds the bracket and applies
`cuota_fija + (base − limite_inferior) × tasa`.

## Verification status of the 2026 monthly table — **verified**

Verified on 2026-09-06 against the primary source:

- **Source**: SAT, *Anexo 8 de la Resolución Miscelánea Fiscal para 2026*, section **A.V — "Tarifa
  aplicable durante 2026 para el cálculo de los pagos provisionales mensuales a que se refieren los
  artículos 96 de la Ley del ISR y 175 de su Reglamento, así como la regla 3.12.2"**. Published in the
  DOF on **2025-12-28** — the anexo for a given fiscal year is published shortly before that year starts.
  URL: <https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rmf/anexos/Anexo-8-RMF-2026_DOF-28122025.pdf>
- **Accessed**: 2026-09-06, by fetching the PDF directly and reading table A.V on page 5 of the document.
- `aurum.rules.mx.general.TABLE_VERIFIED = True`, `TABLE_ACCESSED = date(2026, 9, 6)`, and the rule's
  `verified` attribute mirrors this. The rule's `explain.confidence` is left `None` (full confidence)
  rather than a `0.5` placeholder, because the table was read in the primary source.

The table (`ISR_TABLE_MONTHLY_2026` in `general.py`, límite inferior / límite superior / cuota fija / %
sobre excedente, MXN):

| límite inferior | límite superior | cuota fija | % excedente |
|---:|---:|---:|---:|
| 0.01 | 844.59 | 0.00 | 1.92% |
| 844.60 | 7,168.51 | 16.22 | 6.40% |
| 7,168.52 | 12,598.02 | 420.95 | 10.88% |
| 12,598.03 | 14,644.64 | 1,011.68 | 16.00% |
| 14,644.65 | 17,533.64 | 1,339.14 | 17.92% |
| 17,533.65 | 35,362.83 | 1,856.84 | 21.36% |
| 35,362.84 | 55,736.68 | 5,665.16 | 23.52% |
| 55,736.69 | 106,410.50 | 10,457.09 | 30.00% |
| 106,410.51 | 141,880.66 | 25,659.23 | 32.00% |
| 141,880.67 | 425,641.99 | 37,009.69 | 34.00% |
| 425,642.00 | en adelante | 133,488.54 | 35.00% |

If SAT republishes a corrected Anexo 8, or a later year's table is needed, add a new dated bracket set
and register a new rule **version** (2026.2, 2027.1, ...) rather than mutating `ISR_TABLE_MONTHLY_2026` —
per the registry's versioning contract (see [rules.md](rules.md)).

## What is still `(verify)`

Nothing in the bracket table itself. What remains unverified:

- Whether art. 106's "tarifa acumulada" mechanic (cumulative scaling of the single-month table) is
  applied exactly as coded here in every edge case (e.g., mid-year regime changes, part-year operations)
  — the general shape (scale by elapsed months) is standard practice but the primary LISR/RLISR text for
  art. 106 itself has not been re-read line by line, only art. 96's rate table.
- `entity_us.py` in the `plan` module (a different file, documented in
  [plan.md](plan.md)) carries its own, separate set of `(verify)` US SE-tax/FICA constants — unrelated to
  this MX rule.

## Test vectors

`aurum/rules/vectors/mx.general.isr_provisional.yaml` — 9 cases: zero income, a mid-bracket case, the
exact upper edge of the first bracket, a no-deductions case landing in a higher bracket, month-3 scaling
of the cumulative table, a case with a prior provisional payment already made, retentions bringing the
payment to zero, deductions exceeding income (base floors at zero, never negative), and the top
"en adelante" bracket. All run through `tests/rules/test_vectors.py` (the same harness every other rule's
vectors run through) — see that file for how vectors are parametrized and asserted.
