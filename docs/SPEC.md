# Aurum product spec

What Aurum is meant to do, how far it goes, and where it deliberately stops. The architecture is in
[`ARCHITECTURE.md`](ARCHITECTURE.md); each module's reference doc is in [`modules/`](modules/).

## Contents

1. [What this is and is not](#1-what-this-is-and-is-not)
2. [Who it is for](#2-who-it-is-for)
3. [Scope](#3-scope)
4. [Product shape: personal first, manual first](#4-product-shape-personal-first-manual-first)
5. [Accounting and the tax rule registry](#5-accounting-and-the-tax-rule-registry)
6. [The RESICO slice and the prefill audit](#6-the-resico-slice-and-the-prefill-audit)
7. [Personal finance features and their status](#7-personal-finance-features-and-their-status)
8. [Documents and data in](#8-documents-and-data-in)
9. [Knowledge base and research](#9-knowledge-base-and-research)
10. [Law tracker](#10-law-tracker)
11. [AI assistance](#11-ai-assistance)
12. [Local MCP server](#12-local-mcp-server)
13. [Compliance, privacy and disclaimers](#13-compliance-privacy-and-disclaimers)
14. [Data sources](#14-data-sources)
15. [Not built yet](#15-not-built-yet)
16. [Research sources](#16-research-sources)

## 1. What this is and is not

Aurum assists with understanding money, bookkeeping and tax. It is decision support, not a licensed
professional. Every substantive output is grounded in cited primary sources, labelled with a
confidence level, and framed as "verify with a licensed CPA / Contador / attorney before acting" when
it touches filing, legal or investment questions.

- In the US, tax-return preparation and representation before the IRS is regulated (Circular 230,
  PTIN, EA/CPA/attorney).
- In Mexico, filings to SAT require a valid e.firma and, in practice, a Contador Público.
- Investment advice is regulated (SEC/FINRA in the US, CNBV/CONDUSEF in Mexico).

The system is therefore human-in-the-loop by design: it drafts, explains, cites and reconciles; a
person reviews and files. The e.firma, if a user opts in at all, is used only to read their own CFDIs
from SAT, never to sign or transmit anything. Filing artifacts are watermarked DRAFT.

## 2. Who it is for

| Who | What they need | What Aurum gives them |
|---|---|---|
| Household / personal | Accounts, what they owe, pay days, budgets, goals | A manual-first daily app with one honest "available until <date>" figure |
| Freelancer under RESICO (MX) | Know what tax they owe and why, catch prefill errors | Cash-basis books, cited ISR/IVA, an audit of SAT's prefilled declaration |
| Cross-border earner (US/MX) | Residency, treaty, FBAR, FEIE vs FTC | A cited cross-border profile instead of forum answers |
| Small business owner | Books, payroll, invoices, KPIs | Business workspaces on the same engine |

A workspace switcher (personal, business, advisory) sits over one engine. Each workspace has its own
ledger, jurisdictions and base currency.

**Positioning.** Automation alone is not a differentiator: SAT itself prefills RESICO declarations,
and several commercial products in Mexico and the US already automate bookkeeping. What Aurum combines
is different: it is private and self-hosted (CFDIs, statements and the e.firma never leave the
machine), every figure is cited and explained, it handles the US/MX cross-border case, it exposes its
tools over MCP, and it tracks law changes against the rules it computes with.

## 3. Scope

Two axes: jurisdiction, and personal versus business.

- **Mexico, federal:** CFF, LISR, LIVA, RMF (including the 2026 reform), CFDI 4.0, SAT obligations,
  IMSS/INFONAVIT payroll basics.
- **Nuevo León:** state payroll tax (ISN) and the state's official gazette.
- **United States, federal:** Internal Revenue Code (Title 26), Treasury Regulations, IRS guidance.
- **Texas:** no state income tax; franchise (margin) tax and sales and use tax.

Deep cross-border edge cases (transfer pricing, FATCA entity classification) are flagged and cited,
not resolved. The individual cross-border profile (days in each country, homes, income sources,
accounts abroad, leading to residency, the treaty tie-breaker, FBAR and FEIE vs FTC) is covered.

## 4. Product shape: personal first, manual first

The everyday surface is the product: **Inicio, Movimientos, Pagos e ingresos fijos, Cuentas,
Presupuesto, Metas, Categorías and Ajustes**. Manual entry is the primary path everywhere, from one
**+ Agregar** dialog; every automation (recurring-payment detection, quick add, CSV import, receipt
OCR) is a labelled shortcut that produces an ordinary, editable movement.

Everything else (tax, business, research, the law tracker, workflows, reports, cross-border,
investments, credit reports) keeps its code and routes behind **Avanzado**, one click away.

Product rules that shape the personal screens:

- **Void semantics.** Editing or deleting a movement never rewrites history: a reversing transaction
  is appended, and every read that matters (budgets, review, goals, income, accounts, organizer
  matching) goes through one filter that excludes reversed and voided transactions.
- **Liabilities typed positive, stored signed.** For a credit card or loan the person types what they
  owe as a positive number; the server negates it on write, and net worth is the signed sum.
- **One "available" figure.** The only safe-to-spend number is the organizer's
  `safe_to_spend = balance − fixed payments pending − budgets remaining − buffer`, shown as
  "Disponible hasta el <fecha>" with its explanation. The budgets figure is always labelled
  "Presupuesto restante".
- **Nothing is deleted, backups first.** No workspace DELETE, trash or reset endpoint. Per-workspace
  backup zip and movements CSV, a full data backup with a sha256 manifest, and restore only into a new
  directory.

## 5. Accounting and the tax rule registry

- **Ledger:** Beancount v3, used unmodified as an engine behind Aurum's own API and UI. Importers and
  queries go through Beancount v3's APIs; commodities and lots give investment tracking.
- **Rule registry:** every tax rule is a small tested module with computation code, a citation (law,
  article, effective range), YAML test vectors and a verification flag. Every computed figure carries
  the rule versions it used. A constant that was not confirmed in a primary source renders `(verify)`
  and lowers the result's confidence.
- **Rules shipped (2026.1):**

| Rule | Citation |
|---|---|
| `mx.resico.income_cash_basis` | RMF 2026 prefill rules for RESICO |
| `mx.resico.isr_monthly` | LISR art. 113-E |
| `mx.resico.retention_pm` | LISR art. 113-J (rate flagged `(verify)`) |
| `mx.iva.monthly` | LIVA art. 5 |
| `mx.general.isr_provisional` | LISR art. 106 (monthly tariff verified against Anexo 8 RMF 2026) |
| `mx.imss.employer_quotas` | LSS arts. 25, 71, 106, 107, 147, 168, 211 |
| `mx.infonavit.employer` | LINFONAVIT art. 29 fr. II |
| `mx.nl.isn` | Ley de Hacienda del Estado de Nuevo León art. 157 |
| `us.fed.schedule_c_net`, `us.fed.se_tax`, `us.fed.income_tax`, `us.fed.quarterly_estimate` | IRC §§ 61/162, 1401/1402, 1(j)(2)/63(c), 6654 |
| `us.tx.franchise_no_tax_due`, `us.tx.sales_use_basics` | Texas Tax Code chs. 171 and 151 |
| `xb.residency`, `xb.treaty_tiebreaker`, `xb.fbar`, `xb.feie_vs_ftc` | IRC 7701(b)(3) and CFF art. 9; US–MX treaty art. 4; 31 CFR 1010.350; IRC 911 |

  Each module doc ([`rules.md`](modules/rules.md), [`rules-mx-general.md`](modules/rules-mx-general.md),
  [`rules-mx-nl.md`](modules/rules-mx-nl.md), [`rules-us.md`](modules/rules-us.md)) lists which
  constants were verified, against which primary source, and on what date.
- **Law tracker link:** when a tracked change touches a rate or threshold, the tracker files a
  proposed constant update with the diff and citation. Nothing changes a computed figure until a person
  approves it; an approved change becomes a new rule version with its own effective date.
- **US scope:** estimates, explanations and an "organize for your preparer" pack. No US filing
  artifacts.

## 6. The RESICO slice and the prefill audit

The first end-to-end slice is a Mexican persona física under RESICO, because CFDI data is structured
XML (no OCR ambiguity), RESICO is a high-volume regime, and the slice exercises every subsystem.

1. **Ingest:** CFDI 4.0 XML by drop or SAT bulk download (issued and received, plus payment
   complements); bank statement CSV.
2. **Classify on a cash basis:** issued PUE counts in the issue month; PPD waits for a REP; a REP
   counts in the month of its `FechaPago`; received CFDIs are IVA-creditable candidates, each checked
   (bank-traceable payment form, allowed use code, RFC match, actually paid).
3. **Reconcile:** bank lines against PUE/REP and expenses. Flag PUE issued but never collected,
   deposits with no CFDI, and cash-paid expenses.
4. **Books:** post double-entry transactions to the ledger with a RESICO chart of accounts.
5. **Calculate (cited):** monthly ISR under RESICO is a tiered flat rate on the month's collected
   income with no deductions (LISR art. 113-E, 2026: 1.00% up to 25,000; 1.10% up to 50,000; 1.50% up
   to 83,333.33; 2.00% up to 208,333.33; 2.50% up to 3,500,000 MXN), due the 17th of the following
   month. IVA is trasladado minus acreditable (LIVA art. 5).
6. **Prefill audit:** SAT has prefilled RESICO declarations from CFDIs since 2023. Aurum computes the
   same figures independently, predicts what the prefill will show, and explains every difference
   against reality: PUE invoices SAT counts but the bank never received, PPD invoices missing a REP,
   IVA the prefill excludes (cash-paid expenses, fixed assets), deposits with no CFDI behind them.
7. **Draft:** a bilingual monthly ISR + IVA month-close PDF, watermarked DRAFT, never transmitted,
   plus the "file by the 17th" checklist.
8. **Explain:** every figure expands into one line, the worked math and the statute excerpt.

Open points on the statute side, kept visible in the product as `(verify)`: the 1.25% retention when
invoicing a persona moral (art. 113-J), how monthly payments credit against the annual declaration
(art. 113-F), and one secondary source that describes the monthly computation as cumulative. The rule
implements the per-month reading of art. 113-E.

## 7. Personal finance features and their status

| Feature | Status |
|---|---|
| Accounts of every kind (bank, cash, cards, loans, investments) and signed net worth | Built |
| Receivable / payable account types | Not built |
| Multi-currency | Partial: per-currency balances and totals, never converted |
| Fixed payments and income with a calendar and alerts | Built, typed by hand; detection from bank lines is a shortcut |
| Monthly review | Partial: feeds Inicio's "Este mes" block; no separate review screen |
| Income streams, expected vs received, history | Built |
| Payroll CFDI to gross / ISR withheld / IMSS on the personal side | Not built (payroll exists in business workspaces) |
| Categories by kind (expense, income) mapped to ledger accounts | Built; tax flags stay out of the simple screens |
| One-line quick add (`250 tacos comida`) | Built as a shortcut that creates an editable movement |
| Receipt photo to prefilled movement | Built as a shortcut: EXIF stripped, Tesseract OCR (or an external OCR service), a keyword reader fills only empty fields; no LLM |
| Telegram text to inbox | Built (optional) |
| CSV statement import onto a chosen account with dedupe | Built; PDF statements not built |
| CFDI received becomes an expense | Built (Avanzado) |
| Auto-labelling that learns from corrections | Not built: alias matching only |
| Bulk relabel, split transactions, tags, payee | Built |
| Monthly category budgets with rollover, 80% / 100% alerts, copy forward | Built |
| Envelope-style plan (needs / wants / savings / debt) | Partial: Avanzado only |
| Savings goals with target date, required monthly amount, linked account | Built |
| Debt goals with a what-if (months and interest saved) | Partial: avalanche/snowball ordering lives in the scenario engine |
| Investments: holdings, lots, prices, allocation, tax lens | Built (Avanzado) |
| Credit cards: cut day, due day, limit, APR, utilisation | Built |
| Statement cycle, minimum vs no-interest payment, MSI schedules on the personal screens | Partial: Avanzado only |
| Loans: amortisation tables and extra-payment what-ifs | Built (Avanzado) |
| Credit report import (Buró de Crédito) | Built (Avanzado) |
| Backup and export | Built |
| Mark a fixed payment paid, as a real undoable movement | Built |

## 8. Documents and data in

Three ways to get CFDIs in, most private first:

1. **XML/ZIP drop:** the default; works with any provider's export.
2. **SAT bulk download (opt-in):** the official Descarga Masiva web service (RMF rule 2.7.2.4), signed
   with the user's e.firma (CFF art. 17-D). The e.firma lives in a local encrypted vault; the
   passphrase is held in memory only; it is never exported and never used to sign. The client and a
   fake SAT for tests are built; the installed `satcfdi` release lacks the service, so the real call
   answers 501 (see the limitations in the README).
3. **Paid aggregators:** not built; a possible optional connector.

CFDI 4.0 XML is parsed natively: UUID, issuer and receiver RFC, concepts, transferred and withheld
taxes, use code, payment method (PUE/PPD), payment form, and payment complements with `FechaPago`.

Bank and card statements are the cash-basis truth layer. In Mexico the realistic path for a
self-hosted tool is CSV import: the Fintech Law's open-banking article still has no secondary rules
for transactional data as of 2026, and aggregators work through bilateral bank agreements.

## 9. Knowledge base and research

Ask a question in Spanish or English and get a plain-language answer with citations to primary law,
or an abstention.

- **Pipeline:** ingest, chunk by article, embed, store in SQLite FTS5 plus vectors, hybrid retrieval
  with reciprocal-rank fusion, then cite or abstain.
- **Citations** carry the law, article, URL, effective dates, trust tier, jurisdiction and the best
  supporting excerpt, plus retrieval diagnostics (score, support) so a caller can judge them.
- **Cross-references** between articles ("see art. 113-F") are extracted at ingest, so a citation can
  list related provisions.
- **Trust tiers**, shown on every citation: primary law › official guidance › professional secondary
  (link and short excerpt only) › blogs (never cited as authority).
- **Versioning:** a re-ingested source becomes a new version; old versions stay queryable for "as of"
  answers.
- **Embeddings:** `nomic-embed-text` through Ollama by default, with an offline hash backend for
  tests. Retrieval quality on the synthetic fixtures is recorded in [`research-eval.md`](research-eval.md).

## 10. Law tracker

- **Sources:** a catalog of monitored sources with a fetch method (feed, API, bulk, page), a cadence,
  a jurisdiction and a trust tier.
- **Change detection:** content hash plus structural diff against the last snapshot; native feeds
  where they exist.
- **Versioned re-index:** a change is parsed, chunked, embedded and stored as a new version, never
  overwriting the previous one.
- **Impact triage:** each change is summarised and tagged with the domains it affects; workspaces that
  care about a domain get an alert. The first fixture is the 2026 reform's real-time SAT access for
  digital platforms (CFF art. 30-B, in force 2026-04-01) and the new platform withholdings.

There is no single "tax law API": the Federal Register and eCFR have real APIs, govinfo has bulk data,
and Mexico's DOF and SAT publish without a structured update feed. The tracker is a polite feed reader
and crawler that respects robots.txt and caches.

## 11. AI assistance

Models are used where they add leverage and never to compute a figure:

- **Research answers** over the law corpus, with citations and an extractive fallback when the model
  declines or is unavailable.
- **Insights:** anomalies, deadlines and "you may owe about X this quarter", computed by code and
  optionally rewritten into one paragraph by a model.
- **Explanations:** any number turned into a plain-language, sourced explanation.
- **Impact triage** of law changes, and **drafting** of workflow definitions for review.

Local models are the default (Ollama, LM Studio); Claude and OpenAI are an opt-in tier, refused
entirely unless `AURUM_CLOUD_OPT_IN=1`. Outputs that feed the app are schema-validated.

## 12. Local MCP server

The same capabilities are exposed as an MCP server so a user's own local AI tools can use them:
`search_law`, `get_law_changes`, `calc_tax`, `prefill_diff`, `quick_add`, `post_entry`, `balances`,
`financial_statement`, `goal_status` and `budget_status`. Transports are stdio for a local client and
streamable HTTP for a client on the network, with the same bearer token as the API whenever auth is
required.

## 13. Compliance, privacy and disclaimers

- **Not advice, by design.** The UI and every report carry a disclaimer; actionable items require a
  person.
- **Drafts, never filings.** Aurum drafts filing artifacts but never transmits to the IRS or SAT and
  never signs on the user's behalf.
- **e.firma: read, never sign.** Opt-in local encrypted vault, read-only use, every use audited.
- **Data sovereignty.** Local models and local storage by default; cloud LLM calls are opt-in.
- **PII.** RFC, CURP, SSN, account numbers and tokens are masked in logs; workspaces are isolated.
- **Source terms.** The crawler is rate-limited, caches, and prefers official feeds and bulk data.
- **Auditability.** Inputs, sources, rule versions and outputs are recorded for every figure.
- **Licensing hygiene.** Every dependency's license is tracked in [`LICENSES.md`](LICENSES.md);
  copyleft components are used unmodified.

## 14. Data sources

**United States:** IRS (Internal Revenue Bulletin, forms, publications), Federal Register API, eCFR
API (Title 26), govinfo bulk data.
**Texas:** Comptroller (franchise, sales and use tax), Texas statutes and administrative code.
**Mexico:** DOF (daily publications), SAT (RMF, CFDI 4.0 schemas and catalogs), Cámara de Diputados
(CFF, LISR, LIVA texts).
**Nuevo León:** Periódico Oficial del Estado, state treasury (ISN).
**Secondary, lower trust:** professional tax newsletters, cited as interpretation only.
**Prices and FX:** Banxico SIE (MXN rates, CETES), US Treasury / Fed, `bean-price` sources.

## 15. Not built yet

- Verification of the RESICO slice against a real SAT prefill for a real taxpayer and month (all
  evidence so far is on synthetic data).
- A real SAT bulk download (the installed `satcfdi` lacks the service).
- Real fetches for every law-tracker source; bulk and page sources hash an index page only.
- Receivable/payable account types, FX-converted net worth, PDF statement import, auto-labelling that
  learns, a dedicated monthly review screen.
- An advisory-client workspace, US filing artifacts, and a server database (Postgres) for multi-user
  setups.

## 16. Research sources

The regulatory facts above were gathered from these pages on 2026-09-05 and 2026-09-06; the rule
modules record which constants were then confirmed in the primary text.

- RESICO (LISR art. 113-E) and its 2026 table: <https://mley.mx/LISR/articulo/113-e/>,
  <https://sdv.com.mx/compendio/ley-isr/articulo-113-e/>
- RESICO prefill, PUE/PPD/REP rules and IVA acreditable:
  <https://resicocalc.com/blog/errores-prellenado-sat-resico>,
  <https://idconline.mx/fiscal-contable/2022/02/15/metodo-de-pago-en-declaraciones-del-resico>,
  <https://idconline.mx/fiscal-contable/2022/04/04/iva-acreditable-de-personas-fisicas-en-el-resico>
- SAT Descarga Masiva web service:
  <https://developers.sw.com.mx/knowledge-base/consumo-webservice-descarga-masiva-sat/>
- Monthly provisional-payment tariff, Anexo 8 RMF 2026:
  <https://www.sat.gob.mx/minisitio/NormatividadRMFyRGCE/documentos2026/rmf/anexos/Anexo-8-RMF-2026_DOF-28122025.pdf>
- Open banking in Mexico: <https://belvo.com/es/blog/estado-regulacion-open-banking-mexico/>
- 2026 reform: <https://www.hklaw.com/en/insights/publications/2025/11/reforma-fiscal-para-2026-en-mexico>,
  <https://basham.com.mx/en/principales-modificaciones-a-la-rmf-para-2026/>
- Beancount v3: <https://github.com/beancount/beancount>; CFDI library:
  <https://github.com/SAT-CFDI/python-satcfdi>
- US–Mexico treaty overview: <https://www.taxesforexpats.com/country-guides/mexico/us-mexico-tax-treaty.html>
