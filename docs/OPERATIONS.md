# Operations

How to run, migrate, back up, restore and verify a real Aurum instance, plus the dev loop against a
real API.

**Never `rm -rf data`.** `AURUM_DATA_DIR` (`./data` by default, `/data` in the container) holds every
workspace's ledger files and the `aurum.db`/`corpus.db` metadata. There is no undo. Back it up
(`POST /api/backup`) before anything that touches it — an upgrade, a migration, a restore drill.

## Running

```
docker compose up --build          # the whole stack: UI + API on 5024 (nginx proxies /api), MCP on 5042
uv run aurum-api                   # API only, for local dev (AURUM_API_PORT, default 5041)
uv run python -m aurum.demo        # seed demo-mx into AURUM_DATA_DIR (idempotent)
```

Both published ports bind to `AURUM_BIND` (default `127.0.0.1`); change them with `AURUM_PORT` and
`AURUM_MCP_HOST_PORT`.

### Dev loop against a real API (not the mock)

The API refuses browser writes whose `Sec-Fetch-Site` is `cross-site` (docs/SECURITY.md), and Chrome
treats `localhost` and `127.0.0.1` as different sites. Keep both sides on `localhost`, name the UI
origin in the allow-list, and never point either at `./data`:

```
AURUM_DATA_DIR=<scratch> AURUM_API_PORT=5041 AURUM_ALLOWED_ORIGINS=http://localhost:3000 uv run aurum-api
cd web-ui && PORT=3000 NEXT_PUBLIC_API_URL=http://localhost:5041/api npm run dev
```

`next dev` has no `/api` rewrite (the app is a static export; nginx proxies `/api` in the container), so
`web-ui/scripts/ui-check.mjs`, which reads `${BASE_URL}/api`, runs against the compose stack or a static
export served behind a proxy, not against `next dev`.

## Migrations

Every module that ships `aurum/<module>/migrations.py` is migrated automatically the first time
anything calls `aurum.core.db.connect()` in a process — this happens on API boot, so there is normally
nothing to run by hand. To check or force it explicitly (e.g. before starting the API after a code
upgrade, so a bad migration fails the deploy instead of the first request):

```
uv run python -m aurum.core.db
# {"schema": {"pf": 3, "organizer": 1, ...}, "applied": [["pf", 3, "commitment_id"], ...]}
```

`docker/entrypoint.sh` runs this before the API starts and **fails the container boot** if a migration
raises, rather than starting against a half-migrated database.

Rules a migration must follow (enforced or documented in `aurum/core/db.py`):

- Uses only the `conn` it is handed, plus ledger file calls — never `aurum.core.db.connect()` again
  (it holds a non-reentrant lock while migrating; a nested call raises `RuntimeError` immediately
  instead of deadlocking).
- Never deletes user data.
- A migration that could rewrite money already on a workspace's ledger (a sign-correction, for
  example) must check `aurum.core.workspaces.protected_workspace_ids()` and abort on a protected
  workspace unless `AURUM_MIGRATE_PROTECTED=1` is set.
- A database that has already been migrated by a *newer* install than the one currently running
  refuses to start (`RuntimeError` naming the module and both version numbers) rather than silently
  skipping the migration it doesn't recognise.

## Protected and hidden workspaces

- **Protected** (`"protected": true` in `GET /api/workspaces/{id}`): `personal` is protected by
  default and this cannot be turned off — `PUT /api/workspaces/personal {"protected": false}` returns
  `400`. Extend the protected set with `AURUM_PROTECTED_WORKSPACES` (comma-separated ids) or by writing
  `"protected": true` directly into a workspace's `workspace.json`. The verification scripts
  (`scripts/verify_demo.py`, `web-ui/scripts/ui-check.mjs`) refuse a protected workspace outright: asked
  to run against one, they exit with code 2 before sending a single HTTP request. `guard_protected()` in
  `scripts/verify_demo.py` is the reference implementation; any new script that writes to a workspace
  should do the same.
- **Hidden** (`"hidden": true`): omitted from `GET /api/workspaces` unless `?include_hidden=1`. This is
  how throwaway verification workspaces are put away without a delete endpoint — there is no
  `DELETE /workspaces`, no trash, no reset (nothing is deleted; see
  [ARCHITECTURE.md](ARCHITECTURE.md#principles)). `scripts/verify_demo.py` creates
  `verify-<timestamp>-<hex4>`, runs its checks against it, and `PUT`s `{"hidden": true}` in a
  `finally` block so a crash mid-run still tidies up.

## Backup

```
curl -X POST http://localhost:5024/api/backup
# {"path": "backups/aurum-20260912-143000.zip", "name": "...", "size": N, "sha256": "..."}
curl http://localhost:5024/api/backups                       # [{name, size, created_at}], newest first
curl -O http://localhost:5024/api/backups/aurum-<ts>.zip      # download one
```

A full backup copies `aurum.db` (and `corpus.db` when present) through `sqlite3.Connection.backup()` —
never the live file directly, so a concurrent write can't leave a half-written page in the archive —
plus every file under `workspaces/**` except `*.lock`, and a `manifest.json` with a sha256 per file.
Keeps the newest `AURUM_BACKUP_KEEP` (default 10) matching backups in `data/backups/`; touches nothing
else there.

Per-workspace exports, for a user who wants just their own data:

```
curl http://localhost:5024/api/workspaces/<ws>/backup.zip        # ledger files + docs + metadata.json + movimientos.csv
curl http://localhost:5024/api/workspaces/<ws>/movimientos.csv   # ?from=YYYY-MM-DD&to=YYYY-MM-DD
```

Every one of these routes is recorded in the audit log (`core.backup.workspace|csv|full|download`).

## Restore

**Always into a new, empty directory. Never in place, never onto the live data dir.**

```
uv run python scripts/restore.py backups/aurum-<ts>.zip --into /path/to/new-empty-dir [--api http://localhost:5024]
```

Exit codes: `2` the `--into` directory already exists and is non-empty; `3` the API at `--api`
answered (any HTTP status counts as "up" — stop the container first); `4` a file's sha256 didn't match
`manifest.json` (the archive is suspect — don't use it); `0` success, with per-table row counts and the
restored workspace list printed for a human to sanity-check before doing anything with the result. To
actually cut over, stop the API, point `AURUM_DATA_DIR` at the restored directory, and start it again —
this script never does that for you.

## Verify

```
docker compose up --build -d
uv run python scripts/verify_demo.py --level 7 --json verify-results.json
```

Drives the real API end-to-end and prints `[PASS]`/`[FAIL]`/`[SKIP]` per check plus a final `RESULT:`
line; the exit code is non-zero when any check fails. `--level N` runs every level up to `N`:

| Level | Adds |
|---|---|
| 1 (default) | The core tax flow on `--ws` (default `demo-mx`): month close and prefill audit, quick add (voided again afterwards), personal-finance reads, research cite-or-abstain, law tracker |
| 2 | Statements, reconcile, US tax and cross-border on `demo-us`, holdings, FX, credit reports, planning |
| 3 | Business (`demo-biz`, including an idempotent payroll run), insights, reports |
| 4 | Workflows and hardening (health `demo_mode`, security headers) |
| 5 | The Mi dinero money organizer |
| 6 | The manual personal flow on a fresh throwaway workspace |
| 7 | The full numbered acceptance list (items #1–#26) on its own throwaway workspace |

`--level 7` creates a `verify-<timestamp>-<hex4>` workspace, runs the numbered acceptance items against
it and hides it when done; every check name ends with its item number `(#N)`, and the script's module
docstring says what each item covers. A few items depend on the environment:

- **#22** (MCP `initialize`) needs `--mcp http://127.0.0.1:5042/mcp` (or `AURUM_MCP_URL`), or the
  running compose stack, whose published MCP port the script reads from `docker compose port`.
- **#23** (docker posture) runs only when `docker compose ps` reports the `api` and `web-ui` services
  running; otherwise it prints a `SKIP` line with the reason.
- **#26** runs the headless UI flows (`web-ui/scripts/ui-check.mjs --flows`) only with `--e2e`, and needs
  Node.

At level 7 the script also prints a `SIDE EFFECTS:` line comparing demo-mx's balances and entry count
before and after the run. A protected workspace (`personal` by default) is refused as `--ws` (exit 2,
before any request) and is never written; see `guard_protected()` in the script.

## Checks (run before a merge or a release)

```
uv run ruff check aurum tests scripts
uv run pytest tests -p no:warnings -o addopts=""
cd web-ui && npm run typecheck && npm run lint && npm test    # when web-ui was touched
```

## Environment variables this document's features read

| Variable | Default | Meaning |
|---|---|---|
| `AURUM_PROTECTED_WORKSPACES` | `personal` | Comma-separated ids no script/migration may ever touch. |
| `AURUM_BACKUP_KEEP` | `10` | How many `aurum-<ts>.zip` files `POST /api/backup` keeps. |
| `AURUM_MIGRATE_PROTECTED` | unset (off) | Set to `1` to let a data migration run against a protected workspace anyway — only for a deliberate, backed-up upgrade. |
| `AURUM_SEED_DEMO` | `1` | Set to `0` to skip all demo seeding in `docker/entrypoint.sh`. |
| `AURUM_BIND` | `127.0.0.1` | Address `docker-compose.yml` publishes the UI and MCP ports on, and what `GET /api/health` reports as `bind`. A non-loopback value makes the API require a token (see `aurum/core/token.py` and docs/SECURITY.md). |
| `AURUM_PORT` | `5024` | Host port of the web front door (UI + `/api`). |
| `AURUM_MCP_HOST_PORT` | `5042` | Host port of the MCP endpoint. |
| `AURUM_MCP_URL` | unset | Default for `verify_demo.py --mcp`. |
