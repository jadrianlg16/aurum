# tax — month close and the prefill audit

`aurum/tax/` produces the RESICO month close and the prefill audit, Aurum's core MX feature:
reconcile what the SAT prefill will show against bank reality and explain every difference (see
[SPEC.md](../SPEC.md)). Every figure comes from the rule registry ([rules.md](rules.md)).

## Model

```
sources.py      where CFDIs and bank lines come from (the only place that knows their shapes)
prefill.py      audit(ws, period) -> PrefillAudit (prefill_income/isr/iva_acreditable + diffs)
month_close.py  month_close(ws, period) -> the month-close JSON payload (below)
draft_pdf.py    render(payload) -> bilingual DRAFT-watermarked PDF bytes
router.py       GET /mx/resico/{ws}/{period} and .../draft.pdf
```

**`sources.load_cfdis`** tries, in order: documents passed in → the `ingest_cfdi` table (tolerant
column names; a missing table is not an error) → `{ws}/docs/cfdi/index.json` (the demo fixtures). It
returns `(documents, source)` so callers can say where a figure came from, and it means the ingest
module can reshape its table without touching rules or prefill. **`sources.bank_lines`** always reads
the ledger (`Assets:Bank:` postings) — the ledger is the truth.

**Month-close payload** (`month_close.py`): `period`, `workspace`, `currency`, `income`
(`collected`, `by_rule[]`, `explain`), `isr` (`value`, `explain`), `iva` (`trasladado`, `acreditable`,
`payable`, `explain`), `retentions` (`isr`, `iva`), `prefill_expected` (`income`, `isr`,
`iva_acreditable`, `explain`), `diffs[]`, `deadline`, `status` (always `"draft"`) and `warnings[]`.
Money is always a string with an explicit currency.

## Localization

`month_close()` and `prefill.audit()` take an optional `lang` parameter; the router resolves it via
`aurum.core.i18n.ws_lang(ws, lang_query_param)` (`Workspace.language`, `?lang=` wins when given,
default `es`) and passes it through `_payload` → `month_close` → `audit`. Every prose string built in
this module — the prefill `Explain.summary` and its steps, the two boilerplate `warnings` (prefill
mismatch, "this is a draft"), and each `Diff.explain.summary` (`pue_not_collected`, `ppd_missing_rep`,
`deposit_without_cfdi`, `cash_paid_expense`, `fixed_asset_iva`) — goes through
`aurum.core.i18n.t(key, lang, **kwargs)`. Numbers, citations, rule ids/versions and the payload shape
are unaffected by `lang` — only prose changes. `Explain` objects that come from `aurum.rules`
(income/ISR/IVA computation) are localized by the rules themselves, not here.

**Differences produced** (`diffs[].kind`):

| kind | meaning |
|---|---|
| `pue_not_collected` | a PUE invoice SAT counts as income, with no matching bank deposit |
| `ppd_missing_rep` | a PPD invoice with no payment complement — invisible to the prefill |
| `deposit_without_cfdi` | a deposit with nothing invoiced behind it (RESICO income must be invoiced) |
| `cash_paid_expense` | expense paid in efectivo → IVA not creditable |
| `fixed_asset_iva` | IVA on an investment, which the prefill leaves out |

Deposits are matched to income items first by the transaction's `cfdi_uuid` meta, then by amount
within `MATCH_TOLERANCE` (0.50 MXN). Deposits booked against `Equity:` (opening balances) are never
candidates.

## Endpoints (`/api/tax`)

| method | path | notes |
|---|---|---|
| GET | `/mx/resico/{ws}/{period}` | month-close payload; `?documents=<json array>` overrides the source; writes an audit record |
| GET | `/mx/resico/{ws}/{period}/draft.pdf` | reportlab, `BORRADOR · DRAFT` watermark, bilingual ES/EN, "never transmitted" footer |

`period` must be `YYYY-MM` (400 otherwise). RFC and currency come from the workspace profile; an
unknown workspace still computes from documents passed in.

## Env

`AURUM_DATA_DIR` only.

## Gotchas

* `prefill_expected` is what **SAT** will show (every PUE assumed collected); `diffs` are the deltas
  against reality. They are deliberately different numbers.
* Retentions are attributed to the invoice a REP pays; **partial payments are not pro-rated** —
  `(verify)` together with art. 113-J.
* `status` is always `"draft"`, and a warning saying Aurum never transmits or signs is always present.

## Tests

`tests/tax/test_tax.py` (sources, the prefill audit on the demo workspace, month close, the draft PDF) and
`tests/tax/test_i18n.py` (ES/EN prose).

## `(verify)`

Everything flagged in [rules.md](rules.md), plus the retention attribution above. Nothing here has
been checked against a real SAT prefill: "verified" in the strong sense (one real RFC, one real month,
reviewed by a contador) has **not** been done for this module.
