# updater

The law/rule change tracker, mounted at `/api/watch`. Fetches a watched
source, hash-diffs it against the last snapshot, versions a real change into `aurum.corpus`
(never overwriting the previous text), and drafts — never applies — a proposal when a change
looks like it touched a rate or threshold.

## Purpose

- Give a human a feed of "this law/guidance page changed" events with enough context (domain
  tags, an excerpt, an `effective_from` when known) to decide whether `aurum/rules` needs a new
  version.
- Never auto-apply anything: `updater_proposals.status` is always `"proposed"` until a person
  changes it elsewhere. Nothing in this module writes to `aurum/rules`.

## Files

| File | Responsibility |
|---|---|
| `sources.yml` | The watched sources: DOF, SAT RMF, SAT CFDI catálogos, NL Periódico Oficial, IRS IRB, Federal Register (Title 26 search), eCFR Title 26. |
| `schema.sql` | `updater_snapshots`, `updater_changes`, `updater_proposals` (module-prefixed, applied automatically by `aurum.core.db.connect()` — this module does NOT own its own database, unlike `corpus`). |
| `tracker.py` | `Fetcher` protocol, `HttpFetcher`, `FakeFetcher`, `run()` / `run_one()`: fetch -> hash -> (if changed) reindex into the corpus as a new source + record the change. |
| `triage.py` | `detect_domains()` (regex/keyword tagging), `summarize()` (LLM with an offline fallback), `propose_from_change()` (drafts a proposal when a percentage/currency amount appears near a tagged domain). |
| `router.py` | `GET /changes`, `POST /run`, `GET /sources`, `GET /proposals`, `GET /sources/{id}/history`, `POST /schedule`, `GET /schedule`. Seeds one fixture change on first access. |
| `scheduler.py` | `Scheduler` — an in-process, env-gated (`AURUM_WATCH_SCHEDULER=1`) background thread that runs each source on its own `cadence`. |

## `sources.yml`

Each entry: `id`, `name`, `jurisdiction`, `doc_type`, `fetch_method` (`feed`\|`api`\|`bulk`\|
`scrape`), `cadence`, `trust_tier`, `url`. The comments in the file are honest about what each
`fetch_method` actually buys today:

- `feed`/`api` sources (IRS IRB, Federal Register, eCFR) have a real, documented, stable
  endpoint — `HttpFetcher` fetching that one URL is a reasonable diff signal.
- `bulk`/`scrape` sources (DOF, SAT RMF, SAT CFDI catálogos, NL Periódico Oficial) have no feed
  or API at all. `HttpFetcher` re-fetches the **index/landing page** and hashes it — this
  detects "the page changed", not "which specific document changed". A per-source scraper that
  enumerates today's entries is future work, not built here.

## `tracker.run(source_id, fetcher)`

For each matching source: fetch -> sha256 -> compare with the last row in `updater_snapshots`.
The **first-ever** fetch of a source only lays down the baseline snapshot (nothing to diff
against yet, so it is never reported as a change). A changed hash on a later run:

1. Ingests the fetched text into `aurum.corpus` as a **new source** (`ingest_text`, never
   `reindex_source` on the old one) in `mx-law`/`us-law` (statute) or `guidance` (everything
   else) — so the previous text stays retrievable at its own `effective_to`.
2. Tags domains with `triage.detect_domains()` and writes an `updater_changes` row (`summary`,
   `domains`, a 280-char `diff_excerpt`, the new corpus `source_id`).
3. Calls `triage.propose_from_change()`, which only writes a row when a percentage or currency
   amount appears in the text near a tagged domain — deliberately conservative; most changes
   produce zero proposals.

`FakeFetcher({source_id: text})` and `fake_fetcher_from_dir(path)` (reading
`<path>/<source_id>.txt`) make every step of this offline-testable; `AURUM_WATCH_FAKE_DIR` wires
the same fake into `POST /api/watch/run` without touching the network.

## `GET /changes` and `GET /proposals`

Both call `_ensure_seed()` first: if `updater_changes` is empty (a fresh database, before any
`run` has ever executed), one fixture change is inserted — the 2026 reform to CFF art. 30-B
(real-time SAT access to digital platforms, effective 2026-04-01, notice via forma 168/CFF by
2026-04-30, RMF 2026 regla 2.9.21) tagged `platform_withholding`, plus one seeded proposal — so
the Watch screen has real content even before the first scheduled run. The check-then-insert runs
under a process lock (`_SEED_LOCK`): the Watch screen reads both endpoints at once on first load, and
without the lock the two threadpool requests could both see an empty table and seed the fixture twice
(covered by `test_seed_runs_once_under_concurrent_first_reads`).

`GET /changes?since=` is a bare list, newest first, filtered by `detected_at >= since` when
given. Each item's shape: `{"id", "source_id", "detected_at", "summary", "domains": [str],
"diff_excerpt", "corpus_source_id", "effective_from"}`.

`POST /run` body `{"source_id": str|null}` runs every source (or just one) synchronously and
returns `{"ran": [source_id, ...], "changed": [change dict, ...]}`.

## Domains tagged by `triage.detect_domains`

`RESICO`, `IVA`, `ISN`, `platform_withholding`, `CFDI`, `standard_deduction`, `franchise_tax`,
`se_tax`, `sales_tax`, `fbar`, `feie` — see `DOMAIN_KEYWORDS` in `triage.py` for the exact
Spanish/English keyword lists. The last four (plus `standard_deduction`/`franchise_tax`) each
have a matching US/TX watched source in `sources.yml` (`irs-standard-deduction`, `irs-se-tax`,
`tx-comptroller-franchise`, `tx-comptroller-sales`, `fincen-fbar`, `irs-feie`), tagged with a
`domains: [...]` field for the UI to group by.

## `GET /sources/{source_id}/history`

`{"source_id", "snapshots": [{source_id, fetched_at, content_hash, bytes}, ...],
"changes": [same shape as GET /changes rows]}`, both newest first. Snapshots record
microsecond-precision `fetched_at` (the table's primary key is `(source_id, fetched_at)`, and
two fetches of the same source within one second must not collide and silently overwrite each
other's row).

## `POST /schedule` and the in-process scheduler

`{"enabled": bool, "sources": [id, ...] | null}` starts (or stops) `aurum.updater.scheduler`'s
process-wide `Scheduler`: a background thread that, once a minute-ish (`AURUM_WATCH_POLL_S`,
default 3600s), calls `Scheduler.tick()`, which runs every *due* source through
`tracker.run_one()`. "Due" is judged per source from its own `cadence` (`daily`/`weekly`/
`monthly`, `CADENCE_SECONDS` in `scheduler.py`) against the most recent `updater_snapshots` row
— a source with no snapshot yet is always due.

**Gated by `AURUM_WATCH_SCHEDULER=1`**: `enabled: true` with the gate unset is recorded in the
response (`{"gated": true, "reason": "..."}`) but starts nothing — this repo does not make
background network calls on a timer unless the operator opted in. `enabled: false` always stops
a running scheduler regardless of the gate. `GET /schedule` returns
`{"enabled", "sources", "running"}`.

The background thread's fetcher honors `AURUM_WATCH_FAKE_DIR` the same way `POST /run` does
(`tracker.default_fetcher()`), so a test that starts the real scheduler thread still never
touches the network. Tests otherwise drive `Scheduler.tick(fetcher=..., now=...)` directly
with a fake fetcher and a fake "now" rather than waiting on the thread's poll interval.

## Testing

`tests/updater/` (`AURUM_EMBED_MODEL=hash`, no network): loading `sources.yml`, the
baseline-then-diff sequence over `FakeFetcher`, that a real change reindexes into the corpus and
tags a domain, `fake_fetcher_from_dir`, an unknown source id raising, the seeded fixture change
and proposal via the router, `POST /run` with `AURUM_WATCH_FAKE_DIR`, the new US/TX domains and
sources, `GET /sources/{id}/history`, and the scheduler (gated-off by default, starts under the
env gate with a fake fetcher, `Scheduler.tick()` cadence logic with a fake clock).
