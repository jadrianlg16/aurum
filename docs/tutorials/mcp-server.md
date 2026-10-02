# MCP server: Aurum as tools for your local agents

**What it does.** Exposes Aurum's capabilities as MCP tools so an MCP client such as Claude Desktop, or
any local agent that speaks MCP, can search the law, compute a month, log an expense or read balances
without copy-paste. Every tool is an HTTP call to the Aurum API, and every call lands in the audit log.

**Tools**: `search_law`, `get_law_changes`, `calc_tax`, `prefill_diff`, `quick_add`, `post_entry`,
`balances`, `financial_statement`, `goal_status`, `budget_status`.

**Transports**
- **stdio** (local tools): `uv run aurum-mcp` with `AURUM_API_URL=http://localhost:5024/api` (through
  nginx) or `http://localhost:5041` when running the API directly.
- **HTTP** (networked agents): the compose stack serves it on `AURUM_MCP_HOST_PORT` (default
  5042) inside the `api` container (`aurum-mcp --http`).

**A stdio client** (for example Claude Desktop's MCP server config) — add an entry like this, with the
path pointing at your checkout:
```json
{ "mcpServers": { "aurum": { "command": "uv", "args": ["run", "--project", "/path/to/aurum", "aurum-mcp"],
  "env": { "AURUM_API_URL": "http://localhost:5024/api" } } } }
```
Then: *"Use aurum.prefill_diff for demo-mx 2026-08 and explain the differences."*

**An HTTP client** — point it at `http://localhost:5042/mcp` (streamable HTTP). A chat bot or automation
can call `quick_add(workspace, text, account_id=None, commit=False)` with a message body: it returns a
preview by default and writes the movement only with `commit=True`.

**Gotchas**
- The MCP process never imports Aurum's modules directly; if the API is down, tools fail loudly.
- The HTTP endpoint requires `Authorization: Bearer <token>` whenever a token is configured
  (`AURUM_MCP_TOKEN`, else the API token). With no token and the default loopback bind it is open to
  local clients, so do not expose 5042 beyond the machine without one.
