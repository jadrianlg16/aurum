# Workflows: automating the recurring checks

**What it does.** A workflow is a short YAML list of API calls Aurum already exposes -- run the tax
month close, refresh insights, archive a report, send a digest -- executed in order, with every step's
request/response recorded. Run it by hand from the UI/API, or point a cron string at it and let the
(opt-in) scheduler run it for you.

**The four built-ins** (seeded into every workspace the first time you open Workflows):

| id | what it does |
|---|---|
| `month-close-mx` | RESICO month close → insights → archive the monthly-review report → digest |
| `weekly-review` | reconcile the review board → budget status → goals → insights digest |
| `us-quarterly` | US tax-year figures → archive the organizer report bundle (US workspaces) |
| `law-watch` | run the law/rule tracker → list changes since the last run |

**Running one**

```
GET  /api/workflows/demo-mx                          # lists (and seeds) the four built-ins
POST /api/workflows/demo-mx/month-close-mx/run
     {"period": "2026-08"}
GET  /api/workflows/demo-mx/month-close-mx/runs       # every past run, newest first
GET  /api/workflows/demo-mx/month-close-mx/runs/<id>  # one run's steps: status, duration, response excerpt
```

A run stops at the first failing step (an HTTP status ≥400, or a step whose path is on the deny-list)
unless that step -- or the workflow itself -- sets `continue_on_error: true`.

**Scheduling one.** Off by default. Setting a schedule always records it; whether it actually fires
depends on the `AURUM_WORKFLOWS_SCHEDULER=1` environment gate (`gated: true` in the response means it
was recorded but nothing is running yet -- the same pattern as the law-tracker's own scheduler).

```
POST   /api/workflows/demo-mx/weekly-review/schedule   {"cron": "0 8 * * 0"}   # 8am every Sunday
GET    /api/workflows/demo-mx/weekly-review/schedule
DELETE /api/workflows/demo-mx/weekly-review/schedule
```

**Writing your own.** `POST /api/workflows/{ws}` with `{"yaml": "..."}`. Steps template `{{ ws }}`,
`{{ period }}`, `{{ params.<key> }}`, and earlier steps' results (`{{ steps.<id>.body.<field> }}`); a
step can be gated with `when: "steps.tax_close.status == 200"`. See `docs/modules/workflows.md` for the
full grammar and `GET /api/workflows/catalog` for every endpoint you're allowed to call (the same list
the deny-list is checked against).

**Asking the assistant to draft one.** `POST /api/workflows/{ws}/propose {"description": "..."}` returns
`{yaml, valid, errors, warnings}` -- it is a draft only, never saved or run. Review it, fix anything
`errors` flags, then `POST` it yourself through the create endpoint above. Offline (no LLM reachable),
the description is keyword-matched to the closest built-in instead, and the response says so
(`"source": "offline-fallback"`).

**Gotchas**
- A workflow step can never touch the e.firma vault (`/satsync/{ws}/vault*`) or `DELETE /workspaces*` --
  both are rejected at save time and re-checked at run time. `GET /api/workflows/catalog` already
  excludes them, so a drafted workflow won't suggest them either.
- `params.year` (used by `us-quarterly`) has no default -- pass it explicitly:
  `POST .../us-quarterly/run {"year": 2026}` (the run body *is* `params`, not wrapped in a `params` key).
- Filing outputs stay watermarked DRAFT; a workflow archiving a report doesn't change that.
