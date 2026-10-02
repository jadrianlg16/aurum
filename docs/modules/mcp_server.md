# mcp_server

A FastMCP server exposing Aurum's API as MCP tools, so any MCP client (for example Claude
Desktop) can research law, compute taxes, and touch the ledger/pf endpoints without ever
importing Aurum's Python. Console script: `aurum-mcp` (declared in `pyproject.toml`).

## Purpose

Every tool below is a plain `httpx` call to `settings().api_url` at the documented API path
— this module has **zero** imports of `aurum.ledger`, `aurum.tax`, `aurum.pf`, etc. It only
knows the HTTP contract, same as any other MCP client would.

## Files

| File | Responsibility |
|---|---|
| `server.py` | The `FastMCP("aurum")` instance, ten `@mcp.tool` functions, `main()` (stdio / `--http`); `_client_factory()` forwards the resolved API token. |
| `http.py` | `build_http_app()` — the streamable-HTTP app at `/mcp` wrapped by `HostOriginGuard` + `MCPBearerMiddleware`. |

## Tools

| Tool | Calls | Notes |
|---|---|---|
| `search_law(query, jurisdiction="MX")` | `POST /api/research/ask` | `lang` is derived from `jurisdiction` (`en` for `US`, else `es`). |
| `get_law_changes(since=None, domain=None)` | `GET /api/watch/changes` | `domain` filters client-side on the returned `domains` list. |
| `calc_tax(workspace, period)` | `GET /api/tax/mx/resico/{ws}/{period}` | |
| `prefill_diff(workspace, period)` | same as `calc_tax`, returns `.diffs` | |
| `quick_add(workspace, text, account_id=None, commit=False)` | `POST /api/ingest/{ws}/quickadd` | A preview by default; `commit=True` writes an ordinary, editable pf entry (no Inbox row). |
| `post_entry(workspace, txn)` | `POST /api/ledger/{ws}/transactions` | `txn` is an `aurum.ledger.base.Transaction` dict. |
| `balances(workspace)` | `GET /api/ledger/{ws}/balances` | |
| `financial_statement(workspace, period, type="pnl")` | `GET /api/ledger/{ws}/journal` (pnl) or `/balances` (balance_sheet) | See below. |
| `goal_status(workspace)` | `GET /api/pf/{ws}/goals` | |
| `budget_status(workspace, period)` | `GET /api/pf/{ws}/budgets/status?period=` | Returns the endpoint's own shape (`{"period", "budgets", "safe_to_spend"}`), not a bare list. |

### `financial_statement`

`type="balance_sheet"` reads `/api/ledger/{ws}/balances?as_of=<period end>` and keeps only
`Assets:`/`Liabilities:`/`Equity:` accounts — a point-in-time balance is exactly what a balance
sheet needs.

`type="pnl"` (default) instead reads `/api/ledger/{ws}/journal?start=<period start>&end=<period
end>` and sums each posting's `Income:`/`Expenses:` amount by account and currency itself —
`balances()` alone cannot answer "how much *in* this period", only "as of this date", so P&L
derivation walks the journal.

## Transports

`main()` (no flags): stdio — the transport a local MCP client (such as Claude Desktop) uses when
it launches `aurum-mcp` as a subprocess; it has no network surface. `main() --http`:
`uvicorn.run(build_http_app(), host=settings().mcp_host, port=settings().mcp_port, proxy_headers=True,
forwarded_allow_ips=…)` — fastmcp's streamable-HTTP transport at `/mcp`, bound to `AURUM_MCP_HOST`
(default `127.0.0.1`; compose sets `0.0.0.0` inside the container and publishes it on
`${AURUM_BIND:-127.0.0.1}:5042`). The log line prints the real host. `mcp.http_app(path=,
middleware=)` has the same signature on fastmcp 2.14.x and 3.x.

Both entry points call `resolve_api_token()` eagerly at boot, so an exposed bind generates the file
token before the first request, and install the PII log filter.

### Auth and guard on `/mcp`

`aurum/mcp_server/http.py` wraps the MCP app in two pure-ASGI layers, outermost first:

- **`HostOriginGuard`** (`aurum/core/guards.py`, `api_prefixes=("/mcp",)`, no public paths): a decoded
  path with `.`/`..`, backslash, NUL or C0 → `400 {"error":"bad_path"}`; in token-less mode the `Host`
  must be a loopback name/address, `api`, `host.docker.internal` or in `AURUM_ALLOWED_HOSTS`, else
  `403 {"error":"host_not_allowed"}`; a POST carrying an `Origin` that does not match the `Host` (or
  `AURUM_ALLOWED_ORIGINS`), `Origin: null`, or `Sec-Fetch-Site: cross-site` → `403
  {"error":"origin_not_allowed"}`. Desktop MCP clients and `fastmcp.Client` send no `Origin`, so
  they pass.
- **`MCPBearerMiddleware`**: whenever the MCP secret is non-empty every request needs
  `Authorization: Bearer <secret>` (constant-time compare) → else `401 {"error":"unauthorized"}` +
  `WWW-Authenticate: Bearer`. The secret is `AURUM_MCP_TOKEN` when set, otherwise the API token from
  `aurum.core.token.resolve_api_token()` (env `AURUM_API_TOKEN` → `data/secrets/api_token` → generated
  when `AURUM_BIND` is not loopback or `AURUM_REQUIRE_TOKEN=1` → `''`). With no token and a loopback
  bind the endpoint stays open to local clients.

The tools themselves call the API with the same resolved token (`_client_factory()`), so a stack
that requires a bearer works end-to-end without any extra configuration.

### Connecting an MCP client

- **stdio** (recommended for a local client such as Claude Desktop): point the MCP client config at
  the `aurum-mcp` console script with no arguments, working directory anywhere `AURUM_API_URL` (and
  the other `AURUM_*` env vars) resolve correctly — no server process to manage.
- **HTTP**: run `aurum-mcp --http` once (e.g. under the same Docker Compose as `aurum-api`),
  then point the MCP client at `http://<host>:<AURUM_MCP_PORT>/mcp` using the streamable-HTTP
  transport. When the stack requires a token, read it with `python -m aurum.core.token show`
  (`docker compose exec api python -m aurum.core.token show` under compose) and configure the client
  to send it as `Authorization: Bearer <token>`. `python -m aurum.core.token status` prints
  `required=<bool> source=env|file|none`.

## Env

| Var | Default | Notes |
|---|---|---|
| `AURUM_API_URL` | `http://localhost:5041` | where the tools call the API (compose: `http://127.0.0.1:5041`, same container) |
| `AURUM_MCP_HOST` | `127.0.0.1` | `--http` bind address (compose: `0.0.0.0` in-container, published on `AURUM_BIND`) |
| `AURUM_MCP_PORT` | `5042` | `--http` port |
| `AURUM_MCP_TOKEN` | `` | separate bearer for `/mcp`; empty = the API token |
| `AURUM_API_TOKEN` / token file | `` | shared secret (see `docs/modules/security.md`) |
| `AURUM_ALLOWED_HOSTS` / `AURUM_ALLOWED_ORIGINS` | `` | extra Host values / origins admitted by the guard |
| `AURUM_FORWARDED_ALLOW_IPS` | `127.0.0.1` | uvicorn proxy trust for `--http` (compose: `*`) |
| `FASTMCP_CHECK_FOR_UPDATES` | fastmcp default | compose sets `off` (fastmcp accepts `stable`/`prerelease`/`off`; `"0"` fails validation at import) so the container never calls pypi.org |

## Testing

`tests/mcp_server/` never starts a real server: `server._client_factory` (the one seam every
tool goes through) is monkeypatched to build an `httpx.AsyncClient` over
`httpx.ASGITransport(app=aurum.api.app.create_app())`, so tools exercise the real FastAPI app
in-process. Tools are called through `fastmcp.Client(server.mcp)` (FastMCP's in-memory client
transport). Covers: the tool list, a `balances`/`post_entry` round trip against the in-memory
ledger, `search_law` abstaining against an empty corpus, the seeded `get_law_changes` fixture,
a `financial_statement` P&L sum, and reachability of `goal_status`/`budget_status`.
`tests/mcp_server/test_http_auth.py` drives `build_http_app()` through Starlette's `TestClient`
(`with TestClient(...) as c` so fastmcp's lifespan runs): `initialize` → 200 with no token; 401 with
a token and no/wrong bearer, 200 with the right one; `Host: attacker.example` → 403; a cross-site
`Origin` on POST → 403; a `..` path → 400.

Two FastMCP quirks worth knowing when adding a test: a tool returning a bare `list` gets wrapped
as `{"result": [...]}` by FastMCP's output-schema handling (read `result.structured_content
["result"]`, not `result.data[0]`), and an empty `dict` result can come back with `result.data
is None` even though `result.structured_content == {}` — assert on `structured_content` for
those.
