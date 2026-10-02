# rules-us — US federal, Texas and cross-border rules

Files: `aurum/rules/us/**`, `aurum/rules/crossborder/**`, vectors `aurum/rules/vectors/{us,xb}.*.yaml`.
The rule protocol and registry are described in [rules.md](rules.md).

**No model produces a number here.** Every figure comes from a rule with a citation, an effective range
and YAML test vectors, exactly like the MX rules. Every US/XB explain summary ends with a not-advice
line; anything built on an unverified constant carries `(verify)`.

## Rules shipped (all `2026.1`)

| id | inputs | value | citation |
|---|---|---|---|
| `us.fed.schedule_c_net` | `gross_receipts`, `returns_and_allowances`, `cost_of_goods_sold`, `expenses` (number, list or `{name: amount}`) | net profit/loss, USD | IRC § 61/162 (Schedule C) |
| `us.fed.se_tax` | `net_profit`, `filing_status`, `wages` | self-employment tax, USD | IRC §§ 1401/1402 |
| `us.fed.income_tax` | `filing_status`, `schedule_c_net`, `other_income`, `se_tax_deduction`, `adjustments`, `itemized_deductions`, or `taxable_income` | federal income tax, USD | IRC § 1(j)(2) / § 63(c) |
| `us.fed.quarterly_estimate` | `current_year_tax`, `filing_status`, `prior_year_tax`, `prior_year_agi`, `withholding` | one installment, USD | IRC § 6654 |
| `us.tx.franchise_no_tax_due` | `total_revenue`, `entity_type`, `business_type`, `cost_of_goods_sold`, `compensation`, `apportionment_factor` | franchise tax due, USD (0 = no tax due) | Tex. Tax Code ch. 171 |
| `us.tx.sales_use_basics` | `taxable_sales`, `out_of_state_purchases`, `local_rate` | sales + use tax, USD | Tex. Tax Code ch. 151 (+ chs. 321/322/323) |
| `xb.residency` | `days_us`, `days_us_prior_1`, `days_us_prior_2`, `days_mx`, `home_us`, `home_mx`, `citizenship`, `green_card`, `mx_source_income_share`, `main_professional_center` | weighted US days, unit `DAY` | IRC § 7701(b)(3) · CFF art. 9 |
| `xb.treaty_tiebreaker` | `dual_resident`, `permanent_home`, `center_of_vital_interests`, `habitual_abode`, `nationality` | step at which the ladder resolves (0 = unresolved), unit `STP` | US–MX treaty art. 4 |
| `xb.fbar` | `foreign_accounts[{country, institution, max_balance_usd}]`, `us_person` | aggregate peak balance, USD | 31 C.F.R. § 1010.350 |
| `xb.feie_vs_ftc` | `foreign_earned_income`, `foreign_tax_paid`, `days_abroad`, `bona_fide_resident` | exclusion available, USD | IRC § 911 · § 901 |

Non-money rules still return an `Amount` because `RuleResult.value` is one; the unit lives in the
currency slot (`DAY`, `STP`) and the real answer is in the explain steps.

## How the arithmetic works

**SE tax** — net earnings = `max(0, net profit) × 0.9235`; the 12.4% OASDI portion applies to
`min(net earnings, 184,500 − W-2 wages)`; 2.9% Medicare applies to all net earnings; the 0.9%
additional Medicare tax applies to the SE share of `wages + net earnings` above the filing-status
threshold. Half of (OASDI + Medicare) — not the additional Medicare tax — is the § 164(f) adjustment.

**Income tax** — AGI = Schedule C net + other income − the SE-tax half − other adjustments; the
deduction is the larger of the § 63(c) standard deduction and any itemized amount; the § 1(j)(2) table
is walked bracket by bracket and each slice is an explain step. Credits, QBI (§ 199A), NIIT, AMT and
capital-gain rates are **not modelled** and the explain says so.

**Quarterly estimate** — the required annual payment is the smaller of 90% of this year's tax and
100% of last year's (110% when prior-year AGI exceeds 150,000, or 75,000 MFS); withholding is
subtracted and the rest is split in four. Under the § 6654(e)(1) de-minimis the installment is zero.

**Texas franchise** — a sole proprietorship is not a taxable entity at all. Otherwise margin is the
lowest of 70% of revenue, revenue − COGS, revenue − compensation, revenue − 1,000,000; apportioned;
times 0.75% (0.375% retail/wholesale). Below the 2026 threshold the tax is zero but an information
report is still due. Combined groups, passive entities and sourcing rules are not modelled.

**Cross-border** — `xb.residency` never *decides*: it reports each country's test and whether both
point at you. `xb.treaty_tiebreaker` walks art. 4 in order and stops at the first decisive answer.
`xb.feie_vs_ftc` prices both options and explicitly refuses to choose.

## Constants (`aurum/rules/us/constants_2026.py`)

Each constant is a `Const` record: `{key, value, citation, source_url, verified, verified_on, note}`.
`GET /api/tax/us/constants` serves the whole table. Verification pass: **2026-09-06**, against the
primary text of IRS Rev. Proc. 2025-32, irs.gov topic/FAQ pages and comptroller.texas.gov.

| key | value | citation | verified | source |
|---|---|---|---|---|
| `se.net_earnings_factor` | 0.9235 | IRC § 1402(a)(12) | **(verify)** | uscode.house.gov (statute not read) |
| `se.oasdi_rate` | 0.124 | IRC § 1401(a) | 2026-09-06 | irs.gov self-employment-tax page |
| `se.medicare_rate` | 0.029 | IRC § 1401(b)(1) | 2026-09-06 | irs.gov self-employment-tax page |
| `se.social_security_wage_base` | 184,500 | IRS Topic no. 751 | 2026-09-06 | <https://www.irs.gov/taxtopics/tc751> |
| `se.additional_medicare_rate` | 0.009 | IRC § 1401(b)(2) | 2026-09-06 | irs.gov Additional Medicare Tax Q&A |
| `se.additional_medicare_thresholds` | single/HoH/QSS 200,000 · MFJ 250,000 · MFS 125,000 | IRC § 1401(b)(2)(A) | 2026-09-06 | irs.gov Additional Medicare Tax Q&A |
| `se.deductible_share` | 0.5 | IRC § 164(f) | 2026-09-06 | irs.gov self-employment-tax page |
| `fed.brackets` | 10/12/22/24/32/35/37% tables for single, MFJ, MFS, HoH | IRC § 1(j)(2) | 2026-09-06 | <https://www.irs.gov/pub/irs-drop/rp-25-32.pdf> § 4.01 |
| `fed.standard_deduction` | single 16,100 · MFJ 32,200 · MFS 16,100 · HoH 24,150 | IRC § 63(c)(2) | 2026-09-06 | rp-25-32.pdf § 4.14(1) |
| `fed.estimate.current_year_share` | 0.90 | IRC § 6654(d)(1)(B)(i) | 2026-09-06 | <https://www.irs.gov/faqs/estimated-tax> |
| `fed.estimate.prior_year_share` | 1.00 | IRC § 6654(d)(1)(B)(ii) | 2026-09-06 | irs.gov estimated-tax FAQ |
| `fed.estimate.high_income_prior_year_share` | 1.10 | IRC § 6654(d)(1)(C)(i) | 2026-09-06 | irs.gov estimated-tax FAQ |
| `fed.estimate.high_income_agi` | default 150,000 · MFS 75,000 | IRC § 6654(d)(1)(C)(i) | 2026-09-06 | irs.gov estimated-tax FAQ |
| `fed.estimate.de_minimis` | 1,000 | IRC § 6654(e)(1) | 2026-09-06 | <https://www.irs.gov/taxtopics/tc306> |
| `fed.estimate.due_dates` | 2026-04-15, 06-15, 09-15, 2027-01-15 | IRC § 6654(c)(2) | 2026-09-06 | irs.gov estimated-tax FAQ |
| `tx.franchise.no_tax_due_threshold` | 2,650,000 | Tex. Tax Code § 171.006 | 2026-09-06 | <https://comptroller.texas.gov/taxes/franchise/> |
| `tx.franchise.rate_retail_wholesale` | 0.00375 | § 171.002(b) | 2026-09-06 | comptroller franchise page |
| `tx.franchise.rate_other` | 0.0075 | § 171.002(a) | 2026-09-06 | comptroller franchise page |
| `tx.franchise.ez_rate` | 0.00331 | § 171.1016 | 2026-09-06 | comptroller franchise page |
| `tx.franchise.ez_threshold` | 20,000,000 | § 171.1016(a) | 2026-09-06 | comptroller franchise page |
| `tx.franchise.compensation_deduction_limit` | 480,000 | § 171.1013 | 2026-09-06 | comptroller franchise page |
| `tx.franchise.margin_revenue_share` | 0.70 | § 171.101(a)(1)(A) | **(verify)** | not on the page read; confirm in the statute |
| `tx.franchise.margin_flat_deduction` | 1,000,000 | § 171.101(a)(1)(B)(ii) | **(verify)** | not confirmed in primary text |
| `tx.franchise.sole_proprietor_not_taxable` | true | § 171.0002(b)(1) | **(verify)** | statutory text not read |
| `tx.sales.state_rate` | 0.0625 | ch. 151 (§ 151.051) | 2026-09-06 | <https://comptroller.texas.gov/taxes/sales/> |
| `tx.sales.local_max_rate` | 0.02 | chs. 321/322/323 | 2026-09-06 | comptroller sales page |
| `tx.sales.max_combined_rate` | 0.0825 | ch. 151 + local | 2026-09-06 | comptroller sales page |
| `xb.spt.current_year_min_days` | 31 | IRC § 7701(b)(3)(A)(i) | 2026-09-06 | irs.gov substantial-presence-test |
| `xb.spt.weighted_days` | 183 | IRC § 7701(b)(3)(A)(ii) | 2026-09-06 | irs.gov substantial-presence-test |
| `xb.spt.weights` | current 1 · prior 1/3 · second prior 1/6 | IRC § 7701(b)(3)(A)(ii) | 2026-09-06 | irs.gov substantial-presence-test |
| `xb.fbar.threshold_usd` | 10,000 | 31 C.F.R. § 1010.350 | 2026-09-06 | irs.gov FBAR page |
| `xb.fbar.due_date` | 2027-04-15, auto extension 2027-10-15 | 31 C.F.R. § 1010.306(c) | 2026-09-06 | irs.gov FBAR page |
| `xb.feie.amount` | 132,900 | IRC § 911(b)(2)(D)(i) | 2026-09-06 | rp-25-32.pdf § 4.39 |
| `xb.feie.physical_presence_days` | 330 | IRC § 911(d)(1)(B) | **(verify)** | statutory text not read |
| `xb.mx.residency_cff9` | casa habitación → centro de intereses vitales (>50% MX-source income) | CFF art. 9 | **(verify)** | CFF PDF not read |
| `xb.treaty.article_4` | permanent home → vital interests → habitual abode → nationality → competent authority | US–MX treaty art. 4 | **(verify)** | ordering follows the OECD model |
| `xb.ftc.concept` | credit for foreign income tax, § 904-limited | IRC § 901 | **(verify)** | concept only; § 904 not modelled |

**29 of 37 constants verified against a primary or official source on 2026-09-06.** The eight
`(verify)` rows are the ones a human still has to read in the statute; they are surfaced in every
affected explain summary, in `GET /api/tax/us/constants`, and in the organizer PDF.

## Test vectors

`aurum/rules/vectors/us.*.yaml` and `xb.*.yaml` — 10 files, 76 cases, run by the shared runner in
`tests/rules/test_vectors.py`. Cross-checks worth knowing: the bracket walker is
asserted against the tax amount Rev. Proc. 2025-32 itself states at the start of each 37% bracket
(e.g. MFS 103,291.75 at 384,350), so a typo in a threshold fails the suite.

Unit tests: `tests/rules_us/test_us_rules.py`.

## Adding a 2027 table

Copy `constants_2026.py` to `constants_2027.py`, add a new rule instance with `version="2027.1"` and
`effective_from=date(2027, 1, 1)`, register it, and add a vectors file. `registry.get(id, on=…)`
resolves the right one; nothing in 2026 changes.
