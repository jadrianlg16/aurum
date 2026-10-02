# taxus — US annual figures and the preparer organizer

Mounted at `/api/tax/us`. Rules and constants: [rules-us.md](rules-us.md).

**This is an organizer, not a return.** Aurum never files, signs or transmits anything to the IRS or
the Texas Comptroller. Every number is an estimate off your own ledger, carries its explain, and the
PDF is watermarked DRAFT with "for your preparer" on the first line.

## Files

```
aurum/taxus/
  inputs.py         ledger → Schedule C lines (which postings count, COGS split, currency guard)
  service.py        composes the annual payload and the tx-franchise payload from the us.* rules
  organizer_pdf.py  DRAFT bilingual organizer (reportlab)
  demo_us.py        build_demo_us(data_dir) — the synthetic `demo-us` workspace
  router.py         the endpoints
```

## Which postings count

| Workspace | Counted |
|---|---|
| `jurisdictions == ["US"]` | every `Income:*` / `Expenses:*` posting in the year |
| mixed `["MX", "US"]` | only US-marked: a `US` account segment (`Income:US:Consulting`), the `us` tag, or `meta {"jurisdiction": "US"}` |
| no `US` at all | nothing — the endpoint answers **200** with `applicable: false` and a reason |

Income postings are negative in Beancount, so gross receipts are the negated sum; a *positive* income
posting is treated as a return/allowance (Schedule C line 2). An expense account with a `COGS` or
`CostOfGoodsSold` segment lands on line 4, everything else on line 28. Postings in a currency other
than USD are skipped with a warning — convert them first (`/api/fx`), Aurum will not guess a rate.

## Workspace profile fields

Read from `workspace.profile` (top level or nested under `profile["us"]`):
`filing_status` (`single|mfj|mfs|hoh`, default `single`), `entity_type` (default `sole_proprietorship`),
`business_type` (`other|retail|wholesale`), `state`, `wages`, `other_income`, `itemized_deductions`,
`prior_year_tax`, `prior_year_agi`, `withholding`.

Without `prior_year_tax` the estimate uses only the 90%-of-this-year leg and says so in a warning.

## Endpoints

`GET /api/tax/us/constants` — every 2026 constant with its citation, `verified` flag and source URL.

`GET /api/tax/us/{ws}/{year}`

```json
{"workspace":"demo-us","year":2026,"applicable":true,"currency":"USD",
 "profile":{"filing_status":"single","entity_type":"sole_proprietorship","business_type":"other","state":"TX"},
 "schedule_c":{"gross_receipts":{"amount":"141000.00","currency":"USD"},
               "returns_and_allowances":{},"cost_of_goods_sold":{},"expenses":{},
               "expenses_by_account":{},"income_by_account":{},"transactions":27,
               "net":{"amount":"117690.00","currency":"USD"},"explain":{}},
 "se_tax":{"value":{"amount":"16629.06","currency":"USD"},"deductible_half":{},"explain":{}},
 "income_tax":{"value":{"amount":"15232.60","currency":"USD"},"explain":{}},
 "total_tax":{"amount":"31861.66","currency":"USD"},
 "quarterly":{"due_dates":["2026-04-15","2026-06-15","2026-09-15","2027-01-15"],
              "amount_each":{"amount":"6000.00","currency":"USD"},"explain":{}},
 "organizer_url":"…/organizer.pdf","tx_franchise_url":"…/tx-franchise",
 "unverified_constants":["…"],"warnings":[],"disclaimer":"…","status":"draft"}
```

`GET /api/tax/us/{ws}/{year}/organizer.pdf` — DRAFT organizer: the figures table, the expense and
income breakdowns, the four installment dates, each section's explain summary with its citations, the
constants still marked `(verify)`, the warnings, and the disclaimer. Renders even when
`applicable: false` (a one-page "not applicable" sheet).

`GET /api/tax/us/{ws}/{year}/tx-franchise` — no-tax-due check on the year's gross receipts, with the
margin computation and the reports that are still due. Warns when the workspace state is not TX.

Both compute endpoints write an `aurum.core.audit` row with the rule versions used.

An unknown or non-US workspace is a 200 with `applicable: false` (never a 404 — the caller asked a
reasonable question). A year outside 2000–2100 is a 400.

## Demo

`aurum.taxus.demo_us.build_demo_us(data_dir)` creates the `demo-us` workspace: personal, US-only, TX,
sole proprietor, USD, 27 synthetic 2026 transactions — 12 monthly consulting retainers (132,000), two
training workshops (9,000), one refund (1,500 on line 2), two subcontractor invoices coded to COGS
(12,000) and five expense categories (9,810), plus a cross-border profile. Net profit 117,690.
Idempotent; writes `docs/demo-us-manifest.json` inside the workspace. `aurum.demo.extras` calls it
when the demo workspaces are built (see [demo.md](demo.md)).

## Tests

`tests/taxus/test_taxus_api.py` — the demo payload against the manifest, explains on every section,
`applicable: false` for MX-only and unknown workspaces, the PDF, the franchise check, the constants
endpoint, US-marking in a mixed workspace, the COGS split, the non-USD guard, and idempotency.

## Not modelled (on purpose)

Credits, QBI § 199A, NIIT, AMT, capital gains, depreciation/§ 179, home-office and vehicle methods,
state income tax (Texas has none), payroll for employees, entity elections. The explain steps say so
where a user would otherwise assume the number is complete.
