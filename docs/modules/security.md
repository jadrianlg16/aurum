# security

Security posture: safe as shipped on localhost, and a bearer token appears automatically the moment
the box is exposed. The operator's view (tables, trust boundaries, residual risks, verification
recipe) is [SECURITY.md](../SECURITY.md); this page is the module map.

## Files

| File | Responsibility |
|---|---|
| `aurum/core/config.py` | `Settings` posture fields (`bind`, `require_token`, `allowed_hosts`, `allowed_origins`, `forwarded_allow_ips`, `mcp_host`, `mcp_token`, `ledger_cache`, `fetch_max_mb`, `allow_private_fetch`, `zip_max_*`) + read-only settings used by other modules (`protected_workspaces`, `backup_keep`, `migrate_protected`, `test_clock`); `WS_ID_RE`, `InvalidWorkspaceId`, `Settings.workspace_dir()` raises; `api_host` default `127.0.0.1`. |
| `aurum/core/token.py` | `resolve_api_token()` (env → `data/secrets/api_token` → auto-generated when exposed/required → `''`), `auth_required()`, `auth_source()`; CLI `python -m aurum.core.token show\|rotate\|status`. No process cache. |
| `aurum/core/security.py` | `BearerTokenMiddleware` (pure ASGI, `Authorization: Bearer` or `X-Aurum-Token`, constant-time, 401 body + `WWW-Authenticate`), `MaxBodySizeMiddleware` (pure ASGI, Content-Length precheck + streamed count → 413), `RateLimitMiddleware` (bounded bucket table), `DemoModeMiddleware`, `SecurityHeadersMiddleware`, `install_pii_log_filter()` (LogRecordFactory), `PiiLogFilter` + `uvicorn_log_config()`, `install_middleware()`. |
| `aurum/core/guards.py` | `HostOriginGuard` (pure ASGI, fn-valued settings): bad-path 400, Host allow-list in token-less mode, Origin/`Sec-Fetch-Site` check on unsafe methods. Shared by the API and the MCP HTTP app. |
| `aurum/core/netguard.py` | `fetch_public_url()` / `check_url()` SSRF guard (scheme, hostname, every resolved address incl. IPv4-mapped, manual redirects, streamed size cap), `FetchBlocked`, `FetchTooLarge`. |
| `aurum/api/app.py` | CORS only when `AURUM_ALLOWED_ORIGINS` is set (outermost); exception handlers `InvalidWorkspaceId`→400, pydantic `ValidationError`→400, `LedgerRenderError`→400, `ZipTooLarge`→413; `main()` runs uvicorn with `proxy_headers`, `forwarded_allow_ips`, the PII log config and resolves the token eagerly. |
| `aurum/mcp_server/http.py` | `build_http_app()` = `mcp.http_app(path="/mcp")` wrapped by `HostOriginGuard` + `MCPBearerMiddleware` (`AURUM_MCP_TOKEN` or the API token). |
| `aurum/ledger/*` | validators + render-then-parse guard + locked rewrites (see `docs/modules/ledger.md`). |
| `aurum/research/router.py` | collection regex, type check before write, resolved destination, uuid filenames, `fetch_public_url` for URLs. |
| `aurum/ingest/cfdi.py` | streamed zip caps → `ZipTooLarge`. |
| `aurum/workflows/{deny,runner,templating}.py` | `normalize_api_path()`, dict/index-only templating, runner bearer + `Host: localhost`. |
| `aurum/llm/structured.py` | cloud gate on every call (`AURUM_CLOUD_OPT_IN`). |
| `Dockerfile.api`, `docker/drop-privileges.sh`, `docker-compose.yml`, `web-ui/nginx.conf.template`, `.env.example` | non-root container, loopback publishing, caps, log rotation, nginx hardening. |
| `tests/conftest.py` | autouse `AURUM_ALLOWED_HOSTS=testserver`, clears the auth/bind/origin/cache env, resets the ledger cache. |

## Middleware order (`install_middleware`)

Add order `RateLimit, MaxBody, Demo, BearerToken, HostOriginGuard, SecurityHeaders`; Starlette runs the
last-added outermost, so a request flows **SecurityHeaders → HostOriginGuard → BearerToken → Demo →
MaxBody → RateLimit → routes**. The guard sits outside the bearer on purpose: a valid token never
bypasses the Host/Origin checks. CORS (when configured) wraps everything.

## Env (defaults)

| Var | Default | Notes |
|---|---|---|
| `AURUM_BIND` | `127.0.0.1` | compose host_ip for 5024/5042; not loopback ⇒ token required |
| `AURUM_API_TOKEN` | `` | explicit bearer (wins over the file) |
| `AURUM_REQUIRE_TOKEN` | `0` | require (and generate) a token on loopback too |
| `AURUM_MCP_TOKEN` | `` | separate MCP bearer; empty = API token |
| `AURUM_ALLOWED_HOSTS` | `` | extra `Host` values; loopback names, `api`, `host.docker.internal` always allowed |
| `AURUM_ALLOWED_ORIGINS` | `` | CORS + Origin allow-list; empty = no CORS middleware at all |
| `AURUM_FORWARDED_ALLOW_IPS` | `127.0.0.1` | uvicorn proxy trust (compose: `*`) |
| `AURUM_API_HOST` | `127.0.0.1` | uvicorn bind inside the process (container: `0.0.0.0`) |
| `AURUM_MCP_HOST` | `127.0.0.1` | MCP HTTP bind (container: `0.0.0.0`) |
| `AURUM_MAX_UPLOAD_MB` | `25` | nginx + API body cap |
| `AURUM_RATE_LIMIT_PER_MIN` | `600` | 0 disables; table bounded at 1,000 buckets |
| `AURUM_FETCH_MAX_MB` | `10` | research URL body cap |
| `AURUM_ALLOW_PRIVATE_FETCH` | `0` | let URL ingest reach private addresses |
| `AURUM_ZIP_MAX_MEMBERS` / `_MEMBER_MB` / `_TOTAL_MB` | `500` / `10` / `100` | CFDI zip caps |
| `AURUM_LEDGER_CACHE` | `1` | parse cache |
| `AURUM_CLOUD_OPT_IN` | `0` | every cloud LLM call refused otherwise |
| `AURUM_DEMO_MODE` | `0` | read-only public demo |
| `AURUM_CHOWN_DATA` | `0` | recursive chown of `/data` on boot |
| `FASTMCP_CHECK_FOR_UPDATES` | `off` (compose) | fastmcp accepts `stable\|prerelease\|off` — `"0"` crashes the MCP process at import |

## Bodies

401 `{"error":"unauthorized","hint":"…"}` + `WWW-Authenticate: Bearer`; 403 `{"error":"origin_not_allowed"|"host_not_allowed"}`;
400 `{"error":"bad_path"|"invalid_workspace_id"|"validation","detail"?}`; 413 `{"error":"payload_too_large"}` /
`{"detail":"zip too large after decompression"}`; `LedgerRenderError` → 400 `{"detail":…}`; 429 `{"error":"rate_limited"}`;
demo mode 403 `{"error":"demo_mode_read_only","message":…}`.

## Other protections

- **Token check is constant-time** (`hmac.compare_digest`) and the token is never echoed in a 401 body;
  the PII factory also masks `Bearer …`/`X-Aurum-Token: …` in any log line.
- **Demo mode** (`AURUM_DEMO_MODE=1`): non-GET requests under `/api/` are refused except the fixed
  `DEMO_ALLOW` regex list in `security.py` (quick-add, inbox accept/reject, research ask, scenario
  run/montecarlo/sensitivity, workflow propose) — not user-configurable.
- **Private corpus collections** (`ws:{id}`): plain `collection_id` strings, no ACL table. The filter
  lives in `aurum/research/router.py`: `/ask` only searches `ws:{workspace}` when the request names
  that workspace; `/ingest` refuses another workspace's `ws:{id}` (403); `/collections` hides `ws:*`
  rows unless `X-Aurum-Workspace` names the owning workspace. `:` is invalid in a Windows path component, so the
  on-disk `corpus_sources/` directory replaces it with `_`; the DB keeps the real id.
- **License audit**: `scripts/license_audit.py` → `docs/LICENSES.md` flags GPL/AGPL dependencies
  (Beancount) against the project's posture note.
- **Security headers** land on every API response (headers middleware is outermost of ours) and are
  set again by nginx for the static export (`proxy_hide_header` on `/api/` keeps one copy per header).

## Tests

`tests/core/test_token.py`, `test_security.py`, `test_guards.py`, `test_posture_matrix.py` (30 cases),
`test_money_validation.py`, `test_money_props.py`; `tests/ledger/test_render_validation.py`, `test_cache.py`,
`test_roundtrip_props.py`; `tests/research/test_ingest_hardening.py`; `tests/ingest/test_zip_caps.py`;
`tests/workflows/test_deny_hardening.py`; `tests/mcp_server/test_http_auth.py`; `tests/llm/test_llm.py` (gate).

## Not protected

See `docs/SECURITY.md` → Residual risks (single shared secret, no TLS, DNS-rebinding TOCTOU on the
resolver as not yet verified, CSP `unsafe-inline`, host filesystem access, open dependency advisories).
