# reports — bilingual PDF/HTML packs

Mounted at `/api/reports`.

This module computes nothing. Every pack composes other modules' already-computed endpoints
in-process (`aurum.pf.*`, `aurum.ledger.statements`, `aurum.tax.month_close`, `aurum.taxus.service`,
`aurum.crossborder.*`, `aurum.holdings.trades`) and lays the numbers out as a report. If a data source
is missing (no US profile, no cross-border profile, no CFDIs for a given month) the affected section
says so and the report still renders — never a 500.

## Files

```
aurum/reports/
  builder.py   the DSL (KPI, Table, ExplainBlock, Section, Report) + render_pdf / render_html
  packs.py     one function per pack + the catalog() applicability rules
  archive.py   persists a rendered PDF/HTML under the workspace docs/reports/ + reports_archive row
  schema.sql   reports_archive table
  router.py    the endpoints
```

## Every report carries

- The fixed bilingual footer: `Aurum — decision support, not advice / no es asesoría`.
- Page numbers and a `Generated <timestamp> · rules: <rule_versions>` line.
- A DRAFT (`BORRADOR · DRAFT`) watermark on `mx-annual` and `us-organizer-bundle` (tax-related, always
  `draft=True`); `client-pack` instead carries `Prepared with Aurum — reviewed by <name>` when `?reviewer=`
  is given.
- Bilingual section labels (`Section title / Título`) — the underlying figures are the same regardless
  of `?lang=`; only prose is localized (`aurum.core.i18n`), per repo convention.

## Endpoints

- `GET /api/reports/{ws}` — catalog: which packs apply to this workspace, given `kind` and
  `jurisdictions` (unknown workspace → empty `packs` list, not a 404, so a UI can render "no reports yet").
- `GET /api/reports/{ws}/{pack}?period=&format=pdf|html` — the rendered report. `period` is `YYYY-MM`
  for `monthly-review`/`client-pack`, `YYYY` for `mx-annual`/`us-organizer-bundle`, omitted for
  `net-worth`. `client-pack` also takes `?reviewer=`.
- `GET /api/reports/{ws}/{pack}/preview` — the same content as JSON (the `Report` model dumped), for a
  UI preview pane before generating the PDF.
- `POST /api/reports/{ws}/{pack}/archive?period=&format=` — renders and stores the file under
  `{workspace}/docs/reports/`, records `{id, ws_id, pack, period, format, path, sha256, created_at}` in
  `reports_archive`, returns that row (including a `size` field).
- `GET /api/reports/{ws}/{pack}/archive` — lists archived runs for that workspace+pack, newest first.

## Packs

| Pack | Applies when | Content |
|---|---|---|
| `monthly-review` | always | income vs. spend, top labels, deltas vs. prior month, anomalies (>2x trailing 3-month average), budget status, goals progress, upcoming recurring bills, net worth |
| `mx-annual` | `"MX" in jurisdictions` | 12 month-closes (`aurum.tax.month_close`) summarized: income/ISR/IVA per month, ISR/IVA computed totals, ISR/IVA **withheld** (retentions), count of prefill diffs, personal-deduction candidates (labels with `tax.MX.personal_deduction=True`, summed from the ledger for the year), a plain-language "for your Contador" checklist. Always `draft=True`. |
| `us-organizer-bundle` | `"US" in jurisdictions` | Schedule C summary, SE tax + computed income tax + quarterly-estimate due dates, Texas franchise no-tax-due check, the cross-border assessment (if a profile was PUT) and its FBAR foreign-account list. Always `draft=True`, "for your preparer" note. |
| `client-pack` | `kind == "advisory"` | executive summary (from `monthly-review`), P&L statement, tax position (MX month-close or US annual depending on jurisdictions), open items (the monthly review's warnings). Watermark is `Prepared with Aurum — reviewed by <name>` from `?reviewer=` instead of DRAFT. |
| `net-worth` | always | account groups + balances, 12-month net-worth series, holdings positions (units/cost basis/market value/unrealized) when `aurum.holdings` has trades |

`demo-mx` (`jurisdictions=["MX"]`, `kind="personal"`) is applicable for `monthly-review`, `net-worth`,
and `mx-annual`; not for `us-organizer-bundle` or `client-pack` — confirmed by
`tests/reports/test_reports_api.py::test_catalog_lists_applicable_packs_for_demo_mx`.

## Known limitation: "paid vs. computed"

`mx-annual` would ideally show "ISR/IVA paid vs. computed". Nothing in Aurum tracks money actually
remitted to the SAT (or the IRS/EFTPS, for the US bundle) — only the ledger and the rule-computed
liability exist. The report shows the **computed** monthly figures only, with an explicit note that
Aurum has no record of what was actually paid and to reconcile against the SAT/preparer statement
before filing. This is called out here rather than fabricated as a "paid" number.

## Tests

`tests/reports/test_reports_api.py` runs against `aurum.demo.generate.build_demo` (`demo-mx`) via
`TestClient`: catalog applicability, PDF magic bytes (`%PDF`), the fixed footer text in HTML, the known
August 2026 ISR figure (`407.00`, from `tests/tax/test_tax.py`) inside the `mx-annual` HTML, the DRAFT
watermark on tax packs, graceful "not applicable" for `us-organizer-bundle` on an MX-only workspace,
and the archive round trip.
