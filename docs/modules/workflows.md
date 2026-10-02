# workflows

YAML-defined sequences of Aurum API calls -- month close, weekly review, etc. -- run on demand or on a
schedule, with a per-step audit trail. Nothing here invents a number: every step is
an ordinary call to another module's endpoint; the workflow only sequences, templates, and records.

## Files

- `aurum/workflows/models.py` -- `WorkflowDef` / `Step` pydantic models.
- `aurum/workflows/templating.py` -- `{{ }}` placeholder substitution (`render_value`) and a restricted
  `when:` expression evaluator (`eval_when`) with its own hand-written tokenizer/parser. No `eval`/`exec`.
- `aurum/workflows/cron.py` -- a small `minute hour dom month dow` parser (no steps/ranges), standard
  cron `dow` (0/7=Sunday), converted internally to `date.weekday()`.
- `aurum/workflows/deny.py` -- the deny-list (below) and `is_denied(method, path)`.
- `aurum/workflows/store.py` -- CRUD over `workflows_defs` + a mirrored YAML file per workflow under
  `{DATA_DIR}/workspaces/{ws}/workflows/{id}.yaml`; `validate_yaml()` parses, checks the schema, and
  rejects denied steps.
- `aurum/workflows/runner.py` -- `run(ws, workflow_id, params)` executes steps in order in-process
  (`httpx` through Starlette's `TestClient`, itself an `httpx.Client` bridged synchronously to the ASGI
  app -- no socket needed) or against `AURUM_WORKFLOWS_API_URL` if set. Records every step in
  `workflows_runs` / `workflows_steps` and one `aurum.core.audit.record` per run.
- `aurum/workflows/scheduler.py` -- an in-process thread, same shape as `aurum.updater.scheduler`,
  gated by `AURUM_WORKFLOWS_SCHEDULER=1` (off by default); `tick()` runs every workflow whose stored
  cron schedule matches "now" (minute resolution, de-duplicated per minute).
- `aurum/workflows/catalog.py` -- `build_catalog()` reads `create_app().openapi()["paths"]` (so it can
  never drift from the real API surface) and drops denied paths.
- `aurum/workflows/propose.py` -- `propose(ws, description)`: an LLM drafts a YAML from the catalog;
  offline fallback keyword-matches the description to the closest built-in. **Never saved or run.**
- `aurum/workflows/seed.py` -- seeds the four built-ins into a workspace on first `GET`.
- `aurum/workflows/builtin/*.yaml` -- `month-close-mx`, `weekly-review`, `us-quarterly`, `law-watch`.
- `aurum/workflows/router.py` -- `/api/workflows` (mounted by `aurum/api/app.py`).
- `aurum/workflows/schema.sql` -- `workflows_defs`, `workflows_runs`, `workflows_steps`.

## Workflow definition shape

```yaml
id: month-close-mx
name: Month close (MX)
description: ...
schedule: null            # cron string, or null
continue_on_error: false  # workflow-level default; a step can override with continue_on_error: true
steps:
  - id: tax_close
    method: GET
    path: /tax/mx/resico/{{ ws }}/{{ period }}
  - id: archive_report
    method: POST
    path: /reports/{{ ws }}/monthly-review/archive?period={{ period }}
    when: "steps.tax_close.status == 200"   # tiny restricted grammar, see templating.py
```

Template context available to every step: `ws`, `period` (defaults to the current `YYYY-MM`), `params`
(whatever was passed to `run`), and `steps.<id>.{status,body}` for every step that already ran. `when`
supports `==`, `!=`, `<`, `<=`, `>`, `>=`, `and`, `or`, `not`, `len(...)`, and dotted-path lookups --
nothing else; it is a hand-written recursive-descent parser, never `eval`.

## Deny-list (`aurum/workflows/deny.py`)

A workflow step is rejected at validate-time (create/update) and re-checked at run-time on the rendered
path:

1. Any method on `/satsync/{ws}/vault*` -- the e.firma vault is opt-in and read-only; a workflow must
   never be a path to exfiltrating it.
2. `POST /satsync/{ws}/sync*` -- a workflow never triggers a Descarga Masiva job.
3. `DELETE /workspaces*` -- a workflow must never delete a workspace.

Matching runs on the normalized path (`normalize_api_path`): query/fragment stripped, `//`, `.` and
`..` collapsed, one leading `/api` removed case-insensitively, then lower-cased. Templating
(`templating.resolve_path`) only walks dict keys and list indexes, refuses `_`-prefixed parts and stops
at a depth of 16.

## Runner semantics

- Steps run in order. A step whose `when` evaluates false is recorded (status/duration null) but
  skipped, not treated as a failure.
- A step returning `>=400` stops the run (`status: "failed"`) unless that step or the workflow sets
  `continue_on_error: true`.
- Every step is one row in `workflows_steps` (method, path, status, duration_ms, a response excerpt
  capped at 2000 chars, and any error). Every run is one row in `workflows_runs` plus one
  `aurum.core.audit.record("workflows.<id>.run", ...)` call.

## Endpoints

`GET /{ws}` (list, seeds built-ins) · `POST /{ws}` (create from `{yaml}`) · `GET /{ws}/{id}` (definition
+ validation) · `PUT /{ws}/{id}` · `DELETE /{ws}/{id}` · `POST /{ws}/{id}/run {params?}` ·
`GET /{ws}/{id}/runs` · `GET /{ws}/{id}/runs/{run_id}` · `POST|GET|DELETE /{ws}/{id}/schedule` ·
`POST /{ws}/propose {description}` · `GET /catalog`.

## Design notes

- `save_as` is accepted in the schema but not yet consumed by the runner beyond the implicit
  `steps.<id>.body` context every step gets automatically -- an explicit named alias was not needed by
  any built-in workflow. Left in the schema for a future workflow that wants a shorter template path.
- `us-quarterly`'s second step (`organizer_archive`) targets the `us-organizer-bundle` report pack via
  `/reports/{ws}/us-organizer-bundle/archive`, since `aurum/taxus/router.py` itself has no archive
  endpoint -- this matches how `month-close-mx` archives through `aurum/reports`, not `aurum/tax`.

## Tests

`tests/workflows/test_workflows_api.py` (CRUD, built-ins, runner semantics, schedule, propose) and
`tests/workflows/test_deny_hardening.py` (deny-list normalization, templating lockdown, the runner's
bearer and `Host` headers).
