# Watch: the law tracker

**What it does.** Polls official sources (DOF, SAT RMF and CFDI catalogs, Nuevo León Periódico Oficial,
IRS Internal Revenue Bulletin, Federal Register, eCFR Title 26), detects changes by content hash, indexes
the new text into the corpus as a **new version** (old versions stay queryable, "as of" matters), tags
the affected domains (RESICO, IVA, ISN, platform withholding, …) and, when a change mentions a rate or a
threshold, files a **rule-update proposal**. Proposals are never applied automatically: a human approves,
the rule version bumps, and every figure computed afterwards carries the new version.

**Using it.** Vigilancia shows the feed and the proposals. `POST /api/watch/run` runs all sources (or one
with `{"source_id": "..."}`); `GET /api/watch/changes?since=2026-06-01`; `GET /api/watch/proposals`.
The first fixture entry is the 2026 reform (CFF art. 30-B real-time SAT access for digital platforms,
in force 2026-04-01) tagged `platform_withholding` — it only affects users with platform income, which is
the point: triage should target the right workspaces.

**Gotchas**
- There is no clean "tax-law API": several sources are polite scrapes. Respect their cadence; the
  `sources.yml` comments say which is feed, API, bulk or scrape.
- A detected change is not a rule change. Only an approved proposal changes a number.
- Tests use `AURUM_WATCH_FAKE_DIR` (one `<source_id>.txt` per source) — never the network.
