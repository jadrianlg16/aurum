# Security posture

Aurum is a self-hosted, single-operator app that holds its operator's real financial data. Its
security posture is safe **as shipped** (nothing to switch on) and gets stricter automatically when the
box is exposed. This page is the operator's reference: what protects what, where the trust boundaries
are, what is left, and how to check it on a running stack. The module-level map (files, middleware
order, env defaults) is [modules/security.md](modules/security.md); the design principles behind it are
in [ARCHITECTURE.md](ARCHITECTURE.md#principles).

## Default posture (nothing configured)

| Surface | As shipped | Why |
|---|---|---|
| Published ports | `127.0.0.1:5024` (UI + `/api`) and `127.0.0.1:5042` (MCP) — `AURUM_BIND` | nothing on the LAN can reach the containers |
| Bearer token | **none** (`auth.required=false`, `source=none`) | the localhost UI must keep working with zero setup |
| CORS | **no** CORS headers at all (`AURUM_ALLOWED_ORIGINS` empty) | the UI is same-origin behind nginx; `*` was pure attack surface |
| Host guard | `Host` must be a loopback name/address, `api` or `host.docker.internal` (or `AURUM_ALLOWED_HOSTS`) on every `/api/*`, `/docs`, `/openapi.json`, `/redoc` and `/mcp` request | DNS-rebinding defence for the token-less mode |
| Origin guard | non-GET requests with an `Origin` must match the `Host` (port significant) or be in `AURUM_ALLOWED_ORIGINS`; `Origin: null` and `Sec-Fetch-Site: cross-site` are refused | drive-by CSRF from any web page the operator visits |
| Path guard | decoded path segments `.`/`..`, backslash, NUL or C0 characters → `400 bad_path` | before any router sees the path |
| Body cap | `AURUM_MAX_UPLOAD_MB` (25) enforced by nginx AND the API, counted while streaming (chunked uploads too) | one upload cannot exhaust the container |
| Zip caps | CFDI zips: 500 members / 10 MB per member / 100 MB total, checked while inflating | decompression bombs |
| Rate limit | 600/min per client IP, real IP behind nginx (`proxy_headers`), bucket table bounded at 1,000 | runaway clients |
| Ledger writes | strict validators (accounts, tags, currency, control chars) + render-then-parse guard; every rewrite under the workspace lock | Beancount directive injection |
| Research ingest | collection id regex, type check before write, server-side `uuid` filenames under `corpus_sources/`, SSRF guard on URL fetches | arbitrary file write / internal probing |
| Workflows | deny-list on the normalized path (`/api` prefix, `//`, `.`, `..`, case), templating walks dicts/lists only | vault/workspace deletion via a proposed workflow |
| Cloud LLMs | every call to a cloud provider refused unless `AURUM_CLOUD_OPT_IN=1` | financial data never leaves the box by accident |
| Container | uid 10001 (`aurum`), `CapEff` 0, `no-new-privileges`, `cap_drop ALL` (+ the six caps the drop itself needs — CHOWN, SETUID, SETGID, SETPCAP, FOWNER, DAC_OVERRIDE — cleared by `setpriv`), `/tmp` tmpfs, json-file logs 10 MB × 3 | a compromise stays unprivileged |
| Logs | PII `LogRecordFactory` masks RFC/CURP/SSN/account numbers and bearer tokens on every record from every logger, plus the same filter on uvicorn's handlers | secrets never land in `docker compose logs` |

## Exposed posture (`AURUM_BIND=0.0.0.0` or `AURUM_REQUIRE_TOKEN=1`)

The API auto-generates `data/secrets/api_token` (`secrets.token_urlsafe(32)`, `O_CREAT|O_EXCL`,
mode `0600`, directory `0700`) the first time it needs the token and logs the **path** once — never
the value. From then on every route except `/api/health` and `/` needs `Authorization: Bearer <t>`
or `X-Aurum-Token: <t>` (constant-time compare); `/docs`, `/openapi.json`, `/redoc` included. The MCP
endpoint requires the same bearer (or `AURUM_MCP_TOKEN`). The Host allow-list is relaxed when a token
is required (unless `AURUM_ALLOWED_HOSTS` is set explicitly), the Origin guard never is — a valid
bearer does not bypass it.

```
python -m aurum.core.token show      # print the token (env or file)
python -m aurum.core.token rotate    # new file token (exit 2 when AURUM_API_TOKEN is set in env)
python -m aurum.core.token status    # required=<bool> source=env|file|none
```

Posture matrix (`tests/core/test_posture_matrix.py`, 30 cases):

| request | no token (loopback) | token (env or file, or exposed bind) |
|---|---|---|
| same-origin POST (UI) | route status | route status (bearer sent by the UI) |
| cross-origin POST | 403 `origin_not_allowed` | 403 `origin_not_allowed` even with a bearer |
| GET with `Host: attacker.example` | 403 `host_not_allowed` | 401 |
| curl GET, no headers | 200 | 401 |
| LAN GET with the bearer | 403 `host_not_allowed` | 200 |

## Trust boundaries

- **Browser → nginx (5024)**: same origin; nginx forwards `Host`, `Origin`, `X-Forwarded-*`; the API
  guard and bearer run on every proxied request. Static export is served with the CSP in
  `web-ui/nginx.conf.template` (`unsafe-inline` remains for the theme script; hashes deferred).
- **nginx → api (5041)**: not published; `AURUM_FORWARDED_ALLOW_IPS=*` in compose because only nginx
  can reach the socket. Outside compose the default is `127.0.0.1`.
- **MCP client → api**: `aurum-mcp` calls the API at `AURUM_API_URL` with the resolved token; its own
  HTTP endpoint is guarded the same way (`aurum/mcp_server/http.py`). stdio transport has no network
  surface.
- **Workflows runner → api**: in-process `TestClient` with `Host: localhost` and the bearer; the
  deny-list is evaluated on the normalized path before dispatch.
- **Server → internet**: only research URL ingest, through `aurum/core/netguard.py`.
- **Container → host**: bind-mounted `AURUM_DATA_DIR_HOST` owned by uid 10001 after the first boot:
  `/data`, its direct children and every `workspaces/<ws>` tree (recursively — a tree created by an
  older image that ran as root would otherwise be unwritable for the ledger); `AURUM_CHOWN_DATA=1` extends
  the recursive pass to the whole tree (corpus etc.). Secrets and the e.firma vault are `0700` where
  the filesystem honours it.

## Validation choke points

| Input | Where | Result |
|---|---|---|
| workspace id | `Settings.workspace_dir()` and `BeancountLedger.workspace_dir()` (`^[a-z0-9][a-z0-9-]{1,40}$`) | `400 invalid_workspace_id` |
| amounts | `aurum.core.money.Amount` — Decimal/int/str only, finite; currency `^[A-Z]{3}$` upper-cased | 422 (400 when built inside a handler) |
| accounts, tags, links, payee/narration/meta | `aurum.ledger.base` validators + `validate_account` | 422 / 400 |
| rendered transaction | `BeancountLedger._render_checked` parses the text back: one `Transaction`, zero errors | `400 LedgerRenderError`, nothing written |
| collection id, file type, filename | `aurum/research/router.py` before the first write | 400 |
| URL | `aurum/core/netguard.check_url` — scheme, hostname, every resolved address, every redirect hop | `400 url_not_allowed` / `fetch_too_large` |
| zip members | `aurum/ingest/cfdi.parse_upload` streaming caps | `413 zip too large after decompression` |
| workflow step path | `aurum/workflows/deny.normalize_api_path` | `denied path` (400 on save, failed step on run) |
| template path | `aurum/workflows/templating.resolve_path` — dict keys, list indexes, no `_`-prefixed parts, depth ≤ 16 | `KeyError` → step error |

## Residual risks

- **DNS-rebinding TOCTOU on the SSRF guard (not yet verified)**: `netguard.check_url` resolves the host,
  then httpx resolves it again to connect. A resolver that answers a public address first and a
  private one second would slip through. Pinning the checked address into the transport closes it;
  not done yet. Mitigation today: private fetch is only reachable through research ingest,
  which is hidden behind Avanzado.
- **Shared secret, no users**: one bearer for everything; anyone holding it has full access. There is
  no session, no per-workspace authorization beyond `personal` being protected from deletion.
- **No TLS**: the stack is plain HTTP. Exposing it beyond localhost means putting a TLS-terminating
  reverse proxy in front and setting `AURUM_ALLOWED_HOSTS`/`AURUM_ALLOWED_ORIGINS` to its name.
- **CSP `script-src 'unsafe-inline'`** is needed by the Next.js static export as served today (the
  pre-hydration theme script is inline); moving to script hashes is deferred.
- **Host filesystem**: anything with access to the data directory can read the ledger, `aurum.db`
  and the (encrypted, scrypt N=2^14) e.firma vault. A stronger KDF with in-place re-wrap is
  deferred.
- **Windows Docker Desktop bind mounts** ignore `chown`/`chmod`: the drop script reports the observed
  modes (`drop-privileges:` line in `docker compose logs api`) — it never claims them. On Linux the
  modes should be honoured (not yet verified on a Linux host).
- **Dependency advisories**: `fastmcp` is pinned `>=3.2,<4` (past PYSEC-2026-2475/2476) and web-ui
  overrides `postcss` to 8.5.28. Two dev-only advisories remain: the `extract-zip` chain (the fix needs
  puppeteer-core 25, which needs Node >= 22.12) and `@vitest/mocker` (the fix needs vitest 4, which
  needs Node >= 20.19).
- **Rate limit is per process and in memory**; it resets on restart and is not shared across
  replicas (there is one).

## Verification recipe (never touches workspace `personal`)

Run against a stack built with a fresh data dir (`AURUM_DATA_DIR_HOST=./data-fresh`) and, when your
main stack is already up on 5024/5042, a different project name and ports:

```
docker compose -p aurum-verify config | grep -E 'host_ip|max-size|max-file|cap_drop|no-new'
docker compose -p aurum-verify exec -T api sh -c 'grep -E "^Uid" /proc/1/status'   # 10001 (PID 1; `exec … id -u` prints 0 because exec itself enters as root)
docker compose -p aurum-verify exec -T api sh -c 'grep CapEff /proc/1/status'   # 0000000000000000
docker compose -p aurum-verify exec -T api ls -ld /data/secrets /data/vault    # observed modes
docker compose -p aurum-verify exec -T api python -m aurum.core.token status  # required=False source=none
curl -s http://localhost:5024/api/health | jq .auth                 # {"required": false, "source": "none"}
curl -si -H 'Origin: https://evil.example' http://localhost:5024/api/workspaces | grep -i access-control   # nothing
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:5024/api/pf/verify-x/labels \
     -H 'Origin: http://evil.example' -H 'Content-Type: application/json' -d '{}'     # 403
curl -s -H 'Host: attacker.example' http://localhost:5024/api/workspaces               # {"error":"host_not_allowed"}
curl -s http://localhost:5024/api/pf/A_B/accounts                                      # {"error":"invalid_workspace_id"}
curl -s 'http://localhost:5024/api/pf/..%2F..%2Fx/accounts' | head -c 60                 # HTML: nginx normalizes the encoded traversal before proxying, so it never reaches the API (the API itself answers {"error":"bad_path"} — tests/core/test_guards.py)
curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:5024/api/workspaces -H 'Origin: http://localhost:5024' -H 'Sec-Fetch-Site: same-origin' -H 'Content-Type: application/json' -d '{}'   # 4xx from validation, never 403: nginx forwards Host with its port ($http_host) so a same-origin browser write passes the origin guard
curl -s 'http://localhost:5024/api/workspaces/a%20b'                                   # JSON 400 from the API, not nginx
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5024/plan                  # 200 served directly (try_files $uri/index.html; never a :8080 redirect)
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5024/nope/                   # 404
curl -sI http://localhost:5024/manifest.webmanifest | grep -i content-type             # application/manifest+json
curl -s -X POST http://127.0.0.1:5042/mcp -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"c","version":"1"}}}'   # 200
docker compose -p aurum-verify logs api | grep -c pypi.org                             # 0
```

Ledger health for a throwaway workspace: `curl -s http://localhost:5024/api/ledger/verify-<ts>/health`
→ `{"txns":n,"errors":[],"error_count":0}`.

## Deployment recommendation

Keep `AURUM_BIND=127.0.0.1` on the machine you sit at. To reach Aurum from a phone on the same
network, set `AURUM_BIND=0.0.0.0`, read the generated token with `python -m aurum.core.token show`,
paste it into Ajustes › Avanzado (Token de la API) on the phone, and add the LAN name/IP you type in the browser to
`AURUM_ALLOWED_HOSTS` only if you also want the Host allow-list kept strict. Anything beyond the LAN
needs TLS in front.
