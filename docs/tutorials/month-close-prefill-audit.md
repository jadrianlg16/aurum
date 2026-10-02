# Month close: RESICO ISR + IVA and the prefill audit

**What it does.** For a persona física under RESICO, computes the month's ISR and IVA from your CFDIs
and bank lines, predicts what SAT's pre-filled declaration will show, and explains every difference
between the two — so you file with your eyes open. Impuestos → pick the period.

**How the numbers are made (all in code, all cited)**
- **Ingreso efectivamente cobrado** — SAT's own prefill rules: PUE invoices count in the month issued;
  payment complements (REP) count in the month of `FechaPago`; PPD invoices without an REP do not count.
  Rule `mx.resico.income_cash_basis`.
- **ISR** — LISR art. 113-E monthly table (1.00 % … 2.50 %), a *tiered flat* rate on the whole month's
  collected income, excluding IVA, **no deductions**. Rule `mx.resico.isr_monthly`. Retentions by
  personas morales (art. 113-J, 1.25 %) are shown separately and marked *(verify)*.
- **IVA** — trasladado minus acreditable; acreditable only for recibidos that pass LIVA art. 5 checks
  (bank-traceable forma de pago, valid uso CFDI, RFC match, actually paid). Rule `mx.iva.monthly`.

Every figure has **Ver el cálculo**: one line → worked steps → the citation with its effective date and
the rule version that produced it.

**The five kinds of difference** (the demo month 2026-08 shows all five)

| Badge | Meaning | What to do |
|---|---|---|
| PUE facturado pero no cobrado | SAT will tax it this month anyway | chase the payment; issue PPD next time |
| PPD sin complemento de pago | not declared until the REP exists | issue the REP when paid |
| Depósito sin CFDI | RESICO income must be invoiced | invoice it or document why not |
| Gasto pagado en efectivo | IVA not creditable (LIVA art. 5) | pay traceably next time |
| IVA de activo fijo | the prefill leaves this IVA out | review with your Contador |

**Draft** — *Descargar borrador PDF* gives a bilingual month-close sheet, watermarked DRAFT, with the
"file by the 17th" checklist. Aurum never transmits or signs; you file in the SAT portal.

**API equivalent**
```
GET /api/tax/mx/resico/demo-mx/2026-08
GET /api/tax/mx/resico/demo-mx/2026-08/draft.pdf
```

**Gotchas**
- Bank lines come from the ledger (`Assets:Bank:*`), so import statements first (quick-capture.md).
- Whether the RESICO monthly computation is cumulative and how monthly payments credit against the
  annual return are *(verify)* items: read arts. 113-E/F/J in the primary text before relying on them.
- All demo evidence is synthetic; the "match the real SAT prefill" gate needs a real RFC and month.
