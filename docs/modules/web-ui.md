# web-ui — architecture as built

Next.js 15 App Router, TypeScript, **static export** (`output: 'export'`, `trailingSlash: true`),
plain CSS on design tokens (no UI kit), bilingual **es/en** with `es` as the default. It is a pure
client of the Aurum API: no Node runtime at run time, `next build` writes `out/`, and the nginx image
in `web-ui/Dockerfile` serves those files while proxying `/api` to the API container.

This file is the entry point for the UI. The design rules (vocabulary, tokens, primitives,
loading/error contract, keyboard, `localStorage` registry) live in [design-system.md](design-system.md)
— **read it before adding any copy**. The server-side prose localization is [i18n.md](i18n.md); the
project-wide principles (money as a decimal string, no PII in logs, never guess a rate) are in
[ARCHITECTURE.md](../ARCHITECTURE.md#principles).

## Commands

`web-ui/package.json` scripts:

```
cd web-ui
npm ci                 # Node 20; lockfile pins vitest, jsdom, puppeteer-core, axe-core — no browser download
npm run dev            # next dev (no /api rewrite — see docs/OPERATIONS.md "Dev loop against a real API")
npm run dev:mock       # dev server against the in-browser fake API (NEXT_PUBLIC_MOCK=1 set in Node)
npm run build          # static export to out/
npm run build:mock     # static export with the fake API baked in (demos only)
npm run start          # next start (unused in this repo's deployment; the image serves out/ with nginx)
npm run serve          # dependency-free static server for out/ (PORT, DIR) — does not proxy /api
npm run typecheck      # tsc --noEmit
npm run lint           # eslint . && npm run lint:ui
npm run lint:ui        # check-i18n.mjs && check-vocab.mjs && contrast.mjs
npm test               # vitest run (tests/** and src/**/*.test.{ts,tsx})
npm run test:watch     # vitest
npm run ui-check       # node scripts/ui-check.mjs  — BASE_URL × WS (required; `personal` refused) × routes × widths × themes
npm run a11y           # node scripts/ui-check.mjs --a11y   (dialog contract)
npm run ui-check:flows # node scripts/ui-check.mjs --flows  (day-one / Tuesday / month-end on a throwaway ui-check-<ts> workspace)
npm run screenshots    # node scripts/screenshots.mjs → web-ui/docs/screenshots/*.png (gitignored)
```

`ui-check` refuses to run without a workspace or against a protected one, before any request:

```
node scripts/ui-check.mjs             → "ui-check: WS is required (e.g. WS=demo-mx). Never `personal`."   exit 2
WS=personal node scripts/ui-check.mjs → "ui-check: refusing to run against the protected workspace 'personal'.
                                         No request was made."                                    exit 2
```

It needs a live stack (the compose stack, or a static export behind a proxy that serves `/api`). On
Git Bash pass `MSYS_NO_PATHCONV=1` when giving `--routes /`.

## Environment

Everything is read at **build** time (the browser is what calls the API), all with defaults, so nothing
machine-specific is baked in.

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `/api` | API base. Same origin in every deployment; nginx proxies it. |
| `NEXT_PUBLIC_MOCK` | `0` | `1` swaps in the in-browser fake API. **Never 1 in a deployed image.** |
| `NEXT_PUBLIC_API_TIMEOUT_MS` | `15000` | Request timeout (60 s for multipart). |
| `NEXT_PUBLIC_MCP_PORT` | `5042` | Shown on Tools (advanced). The browser never calls MCP. |
| `PORT` | `3000` | Dev server and `npm run serve`. |
| `BASE_URL`, `WS`, `CHROME_PATH` | — | `ui-check.mjs` / `screenshots.mjs`: target origin, workspace (never `personal`), browser binary. |

Docker (`run` stage): `WEB_PORT` (8080), `API_URL` (`http://api:5041`), `DNS_RESOLVER` (auto-detected by
`docker-resolver.envsh` from the container's own `/etc/resolv.conf`), and `AURUM_MAX_UPLOAD_MB`
(nginx `client_max_body_size`; compose passes it with default 25, the Dockerfile does not set it, so pass
it when running the image outside compose). Security posture of the stack (loopback
bind, no CORS by default, origin/host/path guards, optional bearer): [SECURITY.md](../SECURITY.md).

## Shell & navigation (`components/Shell.tsx`)

- **≥960 px**: brand + topbar, a left rail with icon + label for the everyday screens — `PRIMARY` in
  `Shell.tsx`, in everyday order: **Inicio `/` · Movimientos `/movimientos` · Pagos e ingresos
  fijos `/money` · Presupuesto `/presupuesto/` · Metas `/metas/` · Cuentas `/cuentas` · Categorías
  `/categorias/` · Ajustes `/settings`** — and, last for everyone, **Avanzado**, so the advanced screens
  stay reachable without being the first thing a person sees. With no advanced item visible (simple
  mode, no module on) it is a plain link to **`/avanzado/`** under the group's separator; otherwise it is the
  collapsed `<details>` (persisted in `aurum.advanced_open`) whose first link is **Todo lo avanzado** →
  `/avanzado/`, then the `ADVANCED` items — the list lives in `lib/advanced.ts` — each shown only when the
  workspace's `ui_mode === 'advanced'` or its `module` flag is on (`useAdvanced()` / `useModule()`); Negocio
  additionally requires `kind === 'business'`. The phone Más sheet ends the same way.
- **<960 px** (`max-width: 959px` in `globals.css`): no rail; a fixed bottom tab bar
  **Inicio · Movimientos · [+] · Cuentas · Más** — the FAB opens + Agregar, Más is a `Sheet` with the rest of
  the rail, language and theme.
- **Topbar**: the workspace name as text (a `<select>` labelled `Espacio` with demos grouped only when there
  is a real choice), **+ Agregar** (the only primary control in the chrome; hidden below 960 px, where the
  tab bar's + is the same action) and a ⋯ menu Sheet with Captura rápida (advanced only), Idioma, Tema.
- **Receipt photo**: `components/movimientos/ReceiptScanner.tsx` inside + Agregar on Gasto —
  `scanReceipt()` (`POST /ingest/{ws}/receipts`), fills only empty fields, shows reasons, the raw text and
  a duplicate warning; edit mode fetches the saved photo with `receiptObjectUrl()` (blob, auth header) and
  removing it sends `attachment: null`. Rows with a photo show a clip icon.
- **First run**: when no personal non-sample workspace exists (`resolved && wsOrNull === null`) the Shell
  drops the rail, tab bar and + Agregar and renders `components/Welcome.tsx` — name + currency,
  `POST /workspaces {id:'personal'}`, then `/empezar/`; a link opens `demo-personal` when it is on disk.
  Without it every screen would wait on its skeleton forever.
- **Keyboard**: `n` → `openAddEntry('expense')` from any screen (not while typing, not behind a dialog);
  `/` → Captura rápida only when advanced; Esc closes; ←/→ on `MonthPicker`. The `n` shortcut is
  registered by the Shell, not by `AddEntryProvider`.
- **Title**: the Shell renders the app's one `<title>` (`'<screen> · Aurum'`) — a page claims it with
  `usePageTitle` through `PageHeader`, else the active nav item.
- The skip link is the first focusable element; focus moves to `<main id="main">` after rail navigation.

## Client layer (`src/lib/**`)

Everything under `src/lib/{api,types*,workspace,useResource,health,period,query,validate}`,
`src/lib/mock/**` and `src/lib/i18n/data.ts`. Bootstrap is **`npm ci`** (Node 20; the lockfile pins
vitest, jsdom, puppeteer-core and axe-core — no browser is ever downloaded, the scripts drive the
Chrome/Edge already on the machine).

### Request layer (`lib/api.ts`)

- Every path segment goes through `seg()` (= `encodeURIComponent`), every request appends
  `?lang=<requestLang>` (`setRequestLang()` is called by the I18nProvider, and until it is the stored
  `aurum.lang` preference is used, default `es`). nginx forwards the raw `$request_uri` (no URI part on
  `proxy_pass`), so encoded segments reach the API intact and are validated there.
- Timeout: a manual `AbortController` + `setTimeout` (jsdom has no `AbortSignal.timeout`), 15 s for
  JSON and 60 s for multipart, `NEXT_PUBLIC_API_TIMEOUT_MS` overrides, merged with a caller `signal`
  (`useResource` passes one). Empty / 204 bodies resolve `undefined`.
- Token: `localStorage aurum.token` (one-time migration of `aurum.api_token`), sent as
  `Authorization: Bearer` (the server also accepts `X-Aurum-Token`).
- `ApiError { status, code?, field?, message, detail }`. Codes: pydantic array → `validation`
  (`field` = `loc` minus body/query/path, joined by `.`), `{detail:{code}}` → that code, middleware
  `{error}` → that string (`unauthorized, origin_not_allowed, host_not_allowed, bad_path,
  invalid_workspace_id, payload_too_large, rate_limited, demo_mode_read_only`), 5xx → `server`,
  fetch `TypeError` → `network`, abort → `timeout`; string details map through a regex table to
  `budget_exists, account_has_movements, entry_already_deleted, splits_sum, transfer_same_account,
  transfer_needs_target, account_archived, amount_not_positive, entry_not_editable`, then
  409 → `conflict`, 404 → `not_found`. `mapApiError()` is pure and unit-tested.
- `errorMessage(e, t?)`: with `t` → `t('err.<code>', vars)` (`{message, field, source}`), without
  `t` the Spanish table in `i18n/data.ts` is used, so one-arg legacy callers keep working.
  `errorKey(e)` gives the key alone (ErrorBox CTAs).
- `onUnauthorized(listener)` fires at most once per 2 s on a 401; `onRequestOk(listener)` fires on
  the first 2xx after one. `HealthProvider` subscribes to both → `useHealth().unauthorized`.
- Inventory: current names plus `@deprecated` aliases kept for older callers — `getBudgets → listBudgets`,
  `getBudgetsStatus → getBudgetStatus`, `getGoals → listGoals`, `getGoalWhatIf → goalWhatIf`,
  `updateCommitment → patchCommitment`, `listOrganizerAlerts → getAlerts`,
  `dismissOrganizerAlert → dismissAlert`, `listIncomeStreams/createIncomeStream/updateIncomeStream/
  deleteIncomeStream → listStreams/createStream/updateStream/deleteStream`, `createEntriesBulk →
  bulkCreateEntries`, `quickAdd → quickAddPreview/quickAddCommit`, `uploadBankCsv → importBankCsv`.
  `markOccurrence` has the body form and the positional overload. `listEntries` returns the envelope
  `EntriesPage{entries,next_cursor,totals}` (a bare-array server is wrapped with zero totals);
  `getStreamHistory` returns the real rows `{due,expected,received,status}` plus a derived `period`
  for older consumers.

### Workspace resolution (`lib/workspace.tsx`)

`ws` is null until resolved and **no request fires before that** (`useResource` waits on
`wsOrNull`; there is no fallback id). Order: `?ws=` (validated by the server id rule,
persisted, stripped with `replaceState`, read exactly once) → `localStorage aurum.ws` (migrating
`aurum.workspace`) → first `kind === 'personal' && !sample && !hidden` → first non-sample → null
with `error = 'ws.none'` (→ Welcome). A *sample* is `profile.demo` **or** `profile.synthetic`
(`isSampleWorkspace`; `demo-biz` ships only the latter). `refresh()` re-reads the list and keeps the
id; a dead API sets `error = 'ws.resolve_failed'` and never guesses. Exports: `useWorkspace() → {ws,
wsOrNull, resolved, setWs, workspaces, current, loading, error, refresh}`, `useAdvanced()`,
`useModule()`, `WorkspaceGate`, `useMaybeWorkspace()`, `pickWorkspace()` (pure). `ws` is typed
`string` (`''` while unresolved) because many consumers take it as a string; `wsOrNull` carries the
real state.

### Data hook (`lib/useResource.ts`)

`useResource(loader(signal), deps, {keepPrevious = true}) → {data, error, problem, loading,
refreshing, reload, set}`: `loading` only for the first load, later loads flip `refreshing` and keep
the rows on screen; every run has an `AbortController` (deps change / unmount abort it, a late result
never lands); `data` resets when the resolved workspace changes; `error` is `errorMessage(e, t)`.

### Periods, query state, validation

`period.ts`: `currentPeriod(now)` LOCAL, `shiftPeriod`, `monthBounds`, `periodLabel`,
`usePeriodParam()` (`?period=`, applied once after mount like `useQueryTab`); `closePeriod` keeps its
name but the personal pages never import it (`check-vocab` enforces zero imports). `query.ts`:
`readQuery/writeQuery/useQueryParam`. `validate.ts`: `isDecimalString`, `splitsMatch`, `sumDecimals` —
strings only, never `Number()` on money.

### localStorage registry

`aurum.ws`, `aurum.lang`, `aurum.theme`, `aurum.token`, `aurum.advanced_open`,
`aurum.lastAccount.<ws>`, `aurum.catUsage.<ws>`; every read is wrapped in try/catch; Ajustes ›
"Restablecer preferencias" clears them all. The registry is part of [design-system.md](design-system.md).

### Mock (`NEXT_PUBLIC_MOCK=1`)

Serves every personal-finance shape: entries envelope with a `date|id` keyset cursor (default 100,
`limit > 500` → pydantic 422 array), totals over the full filtered set, void semantics (`{id,
voided:true}`, second delete 409, voided rows out of lists/totals/balances), liability sign (seed card
opening `8420.00` owed → `balance` positive, `balance_signed` negative, signed `net_worth`), labels with
`kind/archived` + income seeds + derived accounts, `budgets/copy` idempotent + budget status computed
from the entries, goals `account_id`, stream partial PUT + real history rows, the onboarding step ids,
workspaces ordered personal-first with `protected/hidden/include_hidden`, `occurrences/mark` (link →
match → create an entry stamped `commitment_id`) + DELETE un-mark (voids the untouched auto-created
entry), `safe_to_spend.parts` with explain step ids exactly `[liquid_balance, until, committed_until,
budgeted_remaining, buffer, safe_to_spend]`, quickadd `preview/confidence/warnings/entry`, bank CSV
requiring `account_id`, health `auth/bind/schema`, ledger health, backup routes. Default workspace
`mock-personal` ("Mis finanzas", `profile.demo:false`, protected) ahead of `demo-mx/demo-biz/demo-us`
(`profile.demo:true`); the tax, cross-border, business and organizer fixtures serve the demo
workspaces. Dates are local (`todayLocalIso()`), never `toISOString`. Security simulations:
`setMockSimulation('unauthorized' | 'origin_not_allowed' | …)` or `?mock=unauthorized` on the page URL
answer middleware `{error}` bodies; bad workspace ids answer 400 `{error:'invalid_workspace_id'}`.

### Scripts (all `node scripts/<name>.mjs`, plain JS, Node 20)

| script | what | exit |
|---|---|---|
| `contrast.mjs` | parses `globals.css` (`:root`, the dark media block, `[data-theme='dark']`), asserts the pair table (text ≥ 4.5, boundary ≥ 3) per theme, `PASS/FAIL ratio` lines | 1 on any FAIL |
| `check-i18n.mjs` | tokenizes `i18n.tsx/3/4/5` + every `src/lib/i18n/*.ts` except `index.ts`; in-file and cross-file duplicates, ES/EN parity, `{placeholder}` parity, unused report (`--unused`, non-fatal); `scripts/i18n-baseline.json` is a ratchet for known cross-file duplicates (empty) | 1 |
| `check-vocab.mjs` | banned regexes + advanced prefixes from the fenced `banned-regex` / `advanced-prefixes` blocks of `design-system.md` (built-in defaults + WARN when a block is missing) over every non-advanced dictionary value; `closePeriod` grep over the personal pages; `scripts/vocab-baseline.json` ratchet of known legacy hits (`--write-baseline` regenerates — review the diff) | 1 |
| `ui-check.mjs` | `BASE_URL` (default `http://localhost:5024`) × `WS` (required, `personal` refused before any request) × routes `/, /movimientos/, /cuentas/, /presupuesto/, /metas/, /categorias/, /money/(+?tab=subs,calendar,flow,plan,income), /empezar/, /settings/, /avanzado/` × widths `320,390,768,1280` × themes light/dark: `scrollWidth ≤ viewport`, 0 console errors, 0 responses ≥ 400, axe `wcag2a/2aa/22aa` serious+critical = 0, tap targets ≥ 44 px below 960 px and ≥ 36 px with a fine pointer (inline text links allow-listed), banned vocabulary in the rendered text (simple mode; `/avanzado/` exempt), screenshots to the repo-root `docs/screenshots/ui/<route>-<w>-<theme>.png` + a JSON report (`--out`), both gitignored; `--a11y` = dialog contract (Enter on the opener, Esc closes, focus returns, form mode, `n` opens and not while typing); `--flows` = `ui-check-<ts>` workspace through the API, day-one / Tuesday / month-end asserted against the API's own totals, `PUT hidden:true` in `finally`; `--mock` skips flows; `--routes/--widths/--themes/--no-shots/--quiet` | 0 ok · 1 assertion · 2 refused · 3 no browser |
| `browser.mjs` | shared `launch()` over puppeteer-core with the `CHROME_PATH` probe list (throws `NoBrowserError` → callers exit 3) | — |
| `screenshots.mjs` | headless Chrome/Edge over a running mock build (`build:mock` + `serve`), one PNG per screen to `web-ui/docs/screenshots/` (gitignored) | 0 (also when no browser is found) |
| `serve.mjs`, `build-mock.mjs`, `dev-mock.mjs` | static server for `out/`; mock build; mock dev server | — |

`npm run lint` = `eslint . && npm run lint:ui` (check-i18n + check-vocab + contrast); `npm test` =
vitest (`tests/**/*.test.{ts,tsx}` and `src/**/*.test.{ts,tsx}`, jsdom, `tests/setup.ts` pins
`TZ=America/Mexico_City`; suites for format, period, validate, api, i18n, tokens, pickers, workspace,
useResource, the mock and the screen helpers next to their components).

## Per-screen (personal routes)

Every route is a directory under `web-ui/src/app/` with its own `index.html` after export
(`avanzado avisos books business categorias crossborder cuentas documents empezar inbox metas money
movimientos plan presupuesto reconcile reports research settings taxes tools watch workflows` +
`page.tsx` for `/`). All paths below are relative to `/api` and every request appends `?lang=`. "Reads"
are the requests the screen fires; "writes" go through the dialogs it opens; "empty" is the
`EmptyState` copy (keys in `lib/i18n/*.ts`); "skeleton/refresh" follows the design-system contract
(first load → `Skeleton`, later loads keep the content with `refreshing`, errors → `ErrorBox` +
Reintentar). Shared rule: lists reload after every write; toasts carry **Deshacer** for entry
create/delete, mark paid, account archive and commitment cancel; edits have no undo.

### `/` — Inicio (`app/page.tsx`, `components/home/**`)

- **Reads** — phase A: `GET /pf/{ws}/accounts` (`getAccountsOverview`). Zero accounts → one more,
  `GET /pf/{ws}/onboarding`, then **stop** (2 requests). Otherwise phase B, after `today` is read in an
  effect: `GET /organizer/{ws}/summary` (`safe_to_spend{amount, until, parts, explain}`, `setup.has_income`,
  `alerts_count`), `GET /organizer/{ws}/calendar?from=today&to=today+7`, `GET /pf/{ws}/review/{period}`,
  `GET /pf/{ws}/budgets/status?period=`, `GET /pf/{ws}/entries?from&to&limit=5` — **6 requests** on a seeded
  workspace. Never `/tax/`, the inbox, `/credit`; `closePeriod` is not imported. Inicio is "now": no month
  picker here (Movimientos and Presupuesto keep one), though a `?period=` deep link still works through
  `usePeriodParam()`; every resource also depends on `useAddEntry().version`.
- **Blocks** — hero `Stat` **"Disponible hasta el {date}"** (`inicio.disponible_hasta`) = `safe_to_spend.amount`
  with the four `parts` (Lo que tienes en cuentas +, Pagos fijos que faltan −, Presupuesto restante −,
  Colchón −) and the organizer's explain behind "¿Cómo se calcula?"; `has_income === false` → **"Lo que
  tienes hoy"** = `parts.balance` + CTA to `/empezar/?step=income` and no "Disponible" at all. Próximos
  pagos · 7 días (calendar items `due|upcoming|missed`, not `tax`, max 6; **Pagado** one-tap when
  `amount_variable === false`, **Registrar** otherwise → + Agregar prefilled with `commitment_id`); Este mes
  (Entró / Salió / Neto from `review`, "Presupuesto usado" bar from `budgets.totals`); Presupuesto top 3;
  Metas top 3 (`review.goals_progress`); Últimos movimientos (5, `ResponsiveTable`, nothing summed). Net
  worth is not a card here; Cuentas shows it per currency as Neto.
- **Writes** — Pagado: `POST /organizer/{ws}/occurrences/mark {commitment_id, date, status:'paid',
  log_entry:true}` (row flips at once — the one optimistic exception — toast "Pagado · {name} · {amount}"
  with Deshacer → `DELETE /organizer/{ws}/occurrences/mark?commitment_id&date`); Registrar: the shared
  dialog's `POST /pf/{ws}/entries` then `…/occurrences/mark {status:'paid', entry_id}`.
- **Empty** — `accounts.length === 0` → `EmptyState` **"Empieza aquí"** (`inicio.empieza`), body "Cuatro pasos a
  mano: cuentas, ingreso, pagos fijos y tus primeros gastos.", primary **"Empezar (5 minutos)"** →
  `/empezar/?step=<first not-done step>`, secondary **"Ver el demo (atajo)"** — a button that calls
  `setWs(demo-personal)` (a `?ws=` link would be a no-op, see Gotchas) — then the onboarding checklist.
  Per-block empties: "Nada por pagar esta semana", "Ponle límite a una categoría", "Ahorra para algo",
  "Todavía no hay movimientos este mes" / "Sin movimientos en {period}".
- **Skeleton/refresh** — one `Skeleton` per card; each block has its own `ErrorBox` + reload; a failed
  `accounts` call replaces the whole body. Title "Inicio · Aurum".

### `/empezar/` — Empezar (`app/empezar/page.tsx`, `components/onboarding/**`)

- **Steps** (`OnboardingStepKey`): `accounts` → `income` → `recurring` → `first_entries`, then a done
  screen. On mount `GET /pf/{ws}/onboarding`; the active view is `?step=<id|done>` when valid, else the
  first step with `done:false`, else `done`; every step change writes `?step=` with `replaceState`
  (`location.pathname` stays `/empezar/`). Rail of numbered pills, "Paso {n} de {total}", "Ya tienes {n}".
- **Step 1 Agrega tus cuentas** — `listPfAccounts` rows + `AccountForm{inline}` (`POST /pf/{ws}/accounts`,
  submit **"Guardar cuenta"** is the step's only primary). **Step 2 ¿De dónde viene tu dinero?** — template
  chips "Sueldo quincenal (15 y 30)" / "Sueldo mensual" / "Freelance o variable" + `StreamForm{inline,
  template}` (`POST /pf/{ws}/income/streams`, **"Guardar ingreso"**). **Step 3 Tus pagos fijos** — chips
  Renta / Luz / Internet / Streaming / Tarjeta (→ `initial {name, kind}`; Tarjeta = `loan_payment`, "Préstamo
  o tarjeta" in the form) + `CommitmentForm{inline}` (`POST /organizer/{ws}/commitments`, **"Guardar pago
  fijo"**); "o busca en mi estado de cuenta" → `/money/?tab=setup` only when advanced. **Step 4 Tus primeros
  gastos** — **"Agregar un gasto"** + chips Súper / Comida fuera / Transporte, each opening + Agregar with the
  payee prefilled, plus `listEntries(ws,{limit:5})`.
- **Footer** — "Siguiente" (secondary) and "Lo hago después" (ghost) both advance; "Atrás" from step 2.
- **Done** — "Listo. Así se ve tu dinero": `Stat` "Lo que tienes hoy" = `sumDecimals` of `balance_signed` over
  non-archived `cash|checking|savings` rows in the workspace currency (one of the few allowed client-side sums,
  `liquidBalance()` in `DoneScreen.tsx`, unit-tested); "Ir a Inicio", "Agregar mi primer gasto"; the
  "Importar un estado de cuenta" card → `/movimientos/?import=1` only when advanced.
- **Skeleton/refresh** — `Skeleton` until onboarding answers; a failed list is an inline `ErrorBox` with the
  form still rendered. Ticks come from the API, never from local state.

### `/movimientos/` — Movimientos (`app/movimientos/page.tsx`, `components/movimientos/**`, `components/AddEntry.tsx`)

- **URL state** — `?period=YYYY-MM` (`usePeriodParam`), `?label_id=` (seeded from Presupuesto's row links and
  written back), `?add=1` (opens + Agregar Gasto on mount), `?import=1` (→ `router.replace('/documents/')`
  only when advanced, else ignored).
- **Reads** — `GET /pf/{ws}/entries?from&to&account_id&label_id&kind&q&limit[&cursor]` →
  `{entries, next_cursor, totals{in,out,net,count}}`; `GET /pf/{ws}/accounts` (zero unarchived accounts
  → empty state); `GET /api/ledger/{ws}/health` (`error_count > 0` → the "{n} registros con error" banner).
  **Entró / Salió / Neto / count come from `totals` only** — `out` is Σ|amount| (positive, server convention).
  `limit` starts at 100; "Ver más" fetches `{cursor, limit:100}`; after a write the loader asks
  `min(500, max(100, rows shown))` so the person keeps what they had. Search debounced 250 ms.
- **Rows** — grouped by day (`formatDayHeading` → "Hoy · vie 12 sep"); a display-only per-day subtotal that
  is **`null` when the day mixes currencies**; payee + note, category (or "Sin categoría" / transfer),
  account (`account_name → to_account_name`), `<Money sign="always">`, origin `Badge` when `source !==
  'manual'` (A mano · Captura rápida · Importado · Factura · Nómina · Pago fijo); `editable === false` → "Se
  capturó desde {source} y no se puede cambiar aquí." (+ "Abrir en la vista avanzada" when advanced).
  Checkboxes appear only after "Seleccionar varios" (desktop); phones use the ⋯ menu.
- **Writes** — row click / ⋯ Editar → the same + Agregar dialog in edit mode → `PUT /pf/{ws}/entries/{id}`
  (full body; **the row itself is never editable in place**); ⋯ Duplicar (always; `commitment_id` not copied);
  ⋯ Eliminar → `ConfirmDialog` → `DELETE /pf/{ws}/entries/{id}` → toast "Movimiento borrado" + Deshacer
  (re-`POST`s the same fields, source manual); selected rows → sticky bar **"Poner categoría"** → one
  `PUT {label_id}` per row, transfers and locked rows skipped, toast "{done} de {total} actualizados · {n}
  sin cambios".
- **+ Agregar** (`useAddEntry().open(kindOrOpts, entry?)`, object form: `{kind?, accountId?,
  prefill?, mode?:'create'|'edit'|'duplicate', entryId?, onSaved?}`) — `ui/Dialog` in form mode; kind
  picker Gasto · Ingreso · Transferencia; **Monto first and focused**; "Frecuentes" chips (top 6 by
  `aurum.catUsage.<ws>`, topped up with common seeded categories) + `CategoryPicker{allowNew}`;
  `AccountPicker` (default `aurum.lastAccount.<ws>`); `DateField` with Hoy/Ayer; "Más detalles": comercio,
  nota, etiquetas, "Dividir en categorías" (parts must sum exactly). Enter saves; Ctrl/Cmd+Enter =
  "Guardar y agregar otro" (dialog stays open, in-dialog `role="status"` line); Esc cancels. Toast
  "Guardado · −$250.00 · Comida fuera" + Deshacer. Zero accounts → the body becomes "Primero agrega una
  cuenta…" + `AccountForm{inline}`.
- **Captura rápida** (`components/QuickAdd.tsx`, advanced only, `/` or the ⋯ menu; title "Captura rápida
  (atajo)") — text + `AccountPicker` → "Revisar" = `POST /ingest/{ws}/quickadd {text, account_id}` → preview
  Monto · Categoría · Cuenta · Comercio · Fecha (+ warnings; a low-confidence `Badge`, never a percentage)
  → "Guardar movimiento" = `…{commit:true}` → an ordinary **editable** entry with `source: 'quickadd'`; **no
  inbox row anywhere**. "Descartar" persists nothing.
- **Empty** — no accounts → "Para capturar movimientos primero necesitas una cuenta." → "Agregar mi primera
  cuenta" (`/empezar/?step=accounts`); active filters → "Nada coincide con tu búsqueda o filtros." + "Quitar
  filtros"; empty month → "Nada en {period}" / "Captura tu primer gasto o ingreso de este mes." → "Agregar
  movimiento", "Ver el mes anterior", and "o importa un estado de cuenta (atajo)" → `/documents/` in advanced.
- **Skeleton/refresh** — `Skeleton{list}` on first load; reloads keep rows mounted and show a thin progress
  bar (`aria-busy`), never "Cargando…". Title "Movimientos · Aurum".

### `/cuentas/` — Cuentas (`app/cuentas/page.tsx`, `components/cuentas/**`)

- **Reads** — `GET /pf/{ws}/accounts?include_archived=1` (deps `[ws, version]`). Fields used: `id name type
  institution currency balance balance_signed owed archived credit_limit cut_day due_day apr_percent
  loan_months opening_balance opening_date`.
- **Stats** — one card **per currency**: **Tienes** = Σ `balance_signed` of `owed=false` rows, **Debes** = Σ
  `balance` of `owed=true` rows, **Neto** = Tienes − Debes, through `sumDecimals` (integer centavos, the one
  client-side sum this screen makes); base currency first; **currencies are never added together**
  (with several, the label reads "Tienes · USD"). Groups: Efectivo y bancos (`checking|savings|cash`),
  Tarjetas de crédito, Préstamos, Inversiones, Otras; empty groups are not rendered; 1-up below 768 px.
- **Card** — type icon, name, `institution · type`, balance through `<Money>`; an owed row shows **"Debes
  {amount}"** from `balance` (positive owed); cards add "Corte día {n} · Pago día {n} · Límite {amount}" and
  a usage `progressbar`; loans "Tasa anual {rate} % · {n} meses"; **"Agregar movimiento aquí"** → + Agregar
  with the account preselected; ⋯ → `Sheet` Editar / Ajustar saldo / Archivar (Restaurar when archived).
  Ledger strings (`account`, `ledger_account`) are never rendered.
- **Writes** — `AccountForm` (a bare `<form>`, submit **"Guardar cuenta"**): tiles "¿Qué tipo de cuenta es?"
  (create only), Nombre, Banco o institución, Moneda (base / MXN / USD / EUR / "Otra…"), **"¿Cuánto tienes
  hoy?"** for assets or **"¿Cuánto debes hoy?"** for `credit_card|loan` — typed positive, sent verbatim as
  `opening_balance`, the server negates (liabilities are typed positive and stored signed); "Fecha del
  saldo"; card fields Día de corte / Día de pago / Límite de crédito / Tasa anual (%) sent as `apr_percent`,
  never divided; loan fields Tasa anual (%), Plazo en meses, Monto original del préstamo → `POST
  /pf/{ws}/accounts`; duplicate name → inline "Ya tienes una cuenta con ese nombre" (409). Optional fields
  sit behind "Más opciones". Edit → `PUT /pf/{ws}/accounts/{id}` with `{name, institution}` + card or loan
  terms only (type / currency / opening balance read-only: "El saldo inicial no se edita. Si el banco dice
  otra cosa, usa Ajustar saldo."). **Ajustar saldo** → `POST /pf/{ws}/accounts/{id}/adjust {balance, date,
  note}` ("Saldo real hoy" / "Lo que debes hoy"; "Se registra un ajuste; tus movimientos no cambian.").
  Archivar → `ConfirmDialog` "¿Archivar {name}?" → `PUT {archived:true}` → toast "Cuenta archivada" +
  Deshacer; "Ver archivadas" toggles the archived cards. After every write the page calls `reload()` only.
- **Empty** — "Todavía no tienes cuentas" / "Una cuenta es donde vive tu dinero…" → primary **"Agregar mi
  primera cuenta"**, secondary **"Empezar con el asistente"** → `/empezar/?step=accounts`.
- **Skeleton/refresh** — `Skeleton variant="card" rows={4}`; error with rows → `ErrorBox` above the content.
  Title "Cuentas · Aurum".

### `/money/` — Pagos e ingresos fijos, ex «Mi dinero» (`app/money/page.tsx`, `components/money/**`, `Money*.tsx`)

Tabs behind `?tab=` (`useQueryTab`), ids `summary | subs | income | calendar | flow | plan | setup`. Simple
mode shows **Pagos fijos · Ingresos · Calendario** (the three lists a person keeps by hand); advanced mode
shows **Resumen · Pagos fijos · Ingresos · Calendario · Flujo · Plan · Configurar**. A `?tab=` that the
mode does not offer falls back to Pagos fijos (simple) or Resumen (advanced). In simple mode the
organizer's avisos surface on Pagos fijos. A `Skeleton` renders until the workspace is resolved. Title
"Mi dinero · Aurum".

- **Resumen** (advanced) — reads `GET /organizer/{ws}/summary`, `GET /organizer/{ws}/commitments` (to join
  `account_id`, `label_id`, `amount_variable` onto `next_7_days` rows), `GET /organizer/{ws}/alerts`. Hero
  **"Disponible hasta el {date}"** (`money.available_until`) = `safe_to_spend.amount` with the four parts (Lo
  que tienes en cuentas, Pagos fijos pendientes, Presupuesto que falta, Colchón) and "¿Cómo se calcula?"
  (the API's explain, humanised client-side — its last step is labelled "Libre para gastar",
  `i18n/core.ts` `explain.id.safe_to_spend`); stats "Pagos fijos del mes" and "Próximo ingreso";
  **Próximos 7 días** table with the mark-paid machine (`useOccurrenceActions`, shared with the calendar):
  `amount_variable === false` → **"Pagado"** (`POST …/occurrences/mark {…, status:'paid',
  log_entry:true}`), variable or absent → **"Registrar"** (+ Agregar prefilled with `commitment_id`, then
  `mark {entry_id}`), income → **"Ya llegó"**, paid/skipped → Badge + ghost **"Deshacer"** (`DELETE
  …/occurrences/mark` — only after a `GET /commitments/{id}` pre-check: a mark that linked a movement *you*
  logged is kept and toasts "Sigue como pagado: el movimiento lo registraste tú y se queda…"). **Avisos**
  de-duplicated against the 7-day rows, "Entendido" → `POST /organizer/{ws}/alerts/{id}/dismiss`
  (`dismissAlert`, api.ts).
- **Pagos fijos** — reads `GET /organizer/{ws}/commitments?kind&status` (minus `kind === 'income'`), drawer
  `GET /organizer/{ws}/commitments/{id}`. **"+ Nuevo pago fijo"** → `CommitmentForm` (Nombre; "¿Qué es?"
  Suscripción / Servicio / Renta o hipoteca / Préstamo o tarjeta / Seguro / Otro; Monto; "¿Varía cada mes?";
  "Cuenta que paga"; Categoría; "Cada cuánto" + "Qué día" / "Último día del mes"; "Próximo pago"; "Se paga
  solo"; "Es indispensable"; Notas; submit **"Guardar pago fijo"**) → `POST /organizer/{ws}/commitments`
  (409 duplicate → "Ya tienes {name} — editar el existente · Guardar de todas formas"); edit → `PUT` with
  only the changed keys (PATCH-merge). Drawer: Editar / Pausar ‖ Reanudar / Cancelar (note →
  `POST …/cancel`) / **Quitar** (`DELETE …/commitments/{id}` = soft delete: "Queda como cancelado… no se
  borra"). Below the list, a closed `<details>` **"Atajo: escríbelo en una línea"** → `POST
  /organizer/{ws}/quickadd {text}` → preview "Así lo entendimos" → Guardar (`?save=1`).
- **Ingresos** — `IncomeStreamsPanel` (`components/IncomeStreams.tsx`): reads `GET /pf/{ws}/income/streams`,
  `GET /pf/{ws}/accounts` (account-name fallback), `GET /organizer/{ws}/commitments` only for rows with ≥ 2
  `commitment_ids`, `GET …/income/streams/{id}/history` behind **"Historial"**. Columns Nombre · Cada ·
  Próximo depósito · Cuenta · Monto; row actions **"Registrar ingreso"** (+ Agregar Ingreso prefilled with
  amount, label, payee and the matching `commitment_id`), Editar, Borrar (`ConfirmDialog` "¿Borrar
  {name}?"). `StreamForm` (submit **"Guardar ingreso"**): "¿Qué tipo de ingreso es?" (Sueldo / Honorarios /
  Renta / Pensión / Inversiones / Otro), Nombre, "¿A qué cuenta llega?", "Cuánto recibes", Categoría
  (defaults to "Sueldo/Nómina" for salary), "Cada cuánto" (Dos veces al mes = two pay days, "Último día" =
  31; Cada 14 días / Cada semana = weekday Monday-first; Una vez al año / Irregular = "Próximo pago"),
  "Sigue llegando" / "Ya no llega", "Más detalles" (Antes de impuestos, Notas) → `POST/PUT
  /pf/{ws}/income/streams[/{id}]`.
- **Calendario** — reads `GET /organizer/{ws}/calendar?from&to` over `monthBounds(period)` (`?period=` via
  `MonthPicker`) + `GET …/commitments` once. `buildMonthGrid(period, weekStart, days)` — **Monday-first for
  es, Sunday-first for en**, weekday indexes from `new Date(y, m-1, d).getDay()` in local time; `tax`
  items dropped client-side. ≥768 px: a 7-column grid, each in-month day a button opening the day `Sheet`;
  <768 px: an agenda `<ul>` grouped by day (no grid in the DOM). Strip "Sale {out} · Entra {in}" from
  `calendar.totals` when present, else `sumDecimals` over `days[].total_out/in`. `OccurrenceSheet`: **"Ya lo
  pagué"** ("Ya llegó" for income) → fixed → `mark {log_entry:true}`, variable → + Agregar prefilled →
  `mark {entry_id}`; **"Este mes no"** → `status:'skipped'`; paid/skipped → "Deshacer"; card cut/due and
  loan rows have no actions ("Este cargo lo calcula la app; no hay nada que marcar.").
- **Flujo** (advanced) — reads `GET /organizer/{ws}/forecast?days=30|60|90` + `GET …/commitments`. Stats
  "Disponible hasta el {date}" (`forecast.safe_to_spend`, same shape), "Punto más bajo", "Colchón" + ghost
  **"Ajustar"** → `PUT /organizer/{ws}/forecast/buffer {buffer}` ("Usar el 10 % automático" sends `null`).
  The chart is an inline SVG; `toChartNumber` is its only float.
- **Plan / Configurar** (advanced) — `GET/PUT /organizer/{ws}/plan`, `POST …/plan/auto`, `POST
  …/organize`, `GET/DELETE …/rules[/{id}]`; `GET …/setup/status`, `POST …/setup/run`, `POST
  …/detect/accept|dismiss`. Detection is a labelled shortcut, never the first path.
- **Empty** — organizer with neither commitments nor income → "Aquí van tus pagos fijos y tus ingresos" /
  "Con ellos calculamos cuánto te queda hasta tu próximo ingreso." → primary **"Agregar mi ingreso"**
  (`StreamForm` in a Dialog without form mode), secondary **"Agregar un pago fijo (atajo)"** — detection is
  never offered; 7-day list "Nada que pagar en los próximos 7 días."; avisos "Sin avisos. Todo en orden.";
  Pagos fijos "Todavía no tienes pagos fijos."; Calendario "Nada programado en {period}"; Flujo with no
  active commitment → a button that switches to Pagos fijos.
- **Skeleton/refresh** — `Skeleton variant=stat|table`, `ErrorBox` + retry, `aria-busy` while refreshing; the
  marked occurrence row flips at once and reverts on error.

### `/presupuesto/` — Presupuesto (`app/presupuesto/page.tsx`, `components/plan/Budget*.tsx`)

- **Reads** — `GET /pf/{ws}/budgets/status?period=` (the only request; `?period=` via `usePeriodParam`,
  `PageHeader{month}`). Three `Stat`s from `totals`: Presupuestado / Gastado / **"Presupuesto restante"**
  (the payload's `safe_to_spend` is compat and never rendered — there is one safe-to-spend figure, the
  organizer's). Rows sorted by the server's `pct`: "Va bien" / "Casi al límite" (≥80 %) / "Excedido"
  (≥100 %), "Gastado {spent} de {of} · queda {left}", "Incluye {amount} que sobró del mes pasado", "Te
  pasaste por {amount}"; row click → `/movimientos/?period=<p>&label_id=<id>`.
- **Writes** — `BudgetDialog` (Categoría via `CategoryPicker{kind:'expense', allowNew}`, "Monto del mes",
  Mes, "Pasar lo que sobre al mes siguiente") → `POST /pf/{ws}/budgets` / `PUT …/budgets/{id}` with exactly
  `{label_id, period, amount, currency, rollover}` (409 → inline "Ya hay un presupuesto…"); **"Copiar del
  mes anterior"** → `POST /pf/{ws}/budgets/copy {from, to}` (idempotent); ⋯ Borrar → `DELETE
  …/budgets/{id}` (confirm + toast, no undo). No client fan-out, no repeat flag.
- **Empty** — with `has_previous` → "Sin presupuesto para {period}" whose primary is **"Copiar del mes
  anterior"**; first month ever → "Elige 3 categorías para empezar".
- **Skeleton/refresh** — `Skeleton{list}`; reloads keep rows; `ErrorBox`. Title "Presupuesto · Aurum".

### `/metas/` — Metas (`app/metas/page.tsx`, `components/plan/Goal*.tsx`)

- **Reads** — `GET /pf/{ws}/goals` (reloaded on `useAddEntry().version`); per card, lazily behind **"Cómo
  va"**, `GET /pf/{ws}/goals/{id}/projection` ("A este ritmo llegas en {month}"); `POST …/goals/{id}/whatif
  {extra_monthly}` (**debt goals only** — "Simular" → "Terminarías {months} meses antes y ahorrarías {amount}
  en intereses"; the server has no savings what-if). The emergency template reads `GET /pf/{ws}/review/{p}`
  for the three previous months and sums `expense` with `sumDecimals`.
- **Card** — kind `Badge` (Ahorro / Fondo de emergencia / Pagar una deuda / Una compra), bar `min(pct,100)`,
  "Llevas {saved} de {target}" · "En {account}", "Necesitas ahorrar {amount} al mes para el {date}" /
  "Meta cumplida" / "Sin fecha límite"; **"Aportar"** → + Agregar **Transferencia** prefilled to the goal's
  account with `monthly_required` (the goal carries `account_id`, never a ledger string). `target` is read
  whether it arrives as an `Amount` object or a bare decimal string.
- **Writes** — `GoalDialog` (kind tiles, name, "Monto de la meta", "Para cuándo" (optional, `min` = today set
  in an effect), "Cuenta donde ahorras" / "Cuenta de la deuda" through `AccountPicker{filterTypes}`) →
  `POST /pf/{ws}/goals` / `PUT …/goals/{id}` with exactly `{kind, name, target, target_date?, account_id}`;
  Borrar → `DELETE …/goals/{id}` (confirm + toast). Contributions are ordinary transfers (no endpoint).
- **Empty** — "Todavía no tienes metas" + template buttons "Fondo de emergencia (3 meses de gastos)" / "Viaje";
  header "+ Nueva meta" is secondary (+ Agregar stays the only primary).
- **Skeleton/refresh** — grid 2-up from 768 px; `Skeleton`; `ErrorBox`. Title "Metas · Aurum".

### `/categorias/` — Categorías (`app/categorias/page.tsx`, `components/settings/CategoriesSection.tsx`)

- **Reads** — `GET /pf/{ws}/labels?include_archived=1` (`transfer` hidden); groups Gastos / Ingresos.
- **Writes** — **"Nueva categoría"** → `POST /pf/{ws}/labels {name, kind, icon}` (the server derives the
  ledger account); ⋯ Editar (`PUT {name, icon}`) / Esconder·Mostrar (`PUT {archived}`) / Borrar (`DELETE`;
  409 → toast "Esta categoría tiene movimientos. Escóndela en lugar de borrarla."). The only category
  management surface besides the pickers' inline "+ nueva categoría"; every write reloads the list.

### `/settings/` — Ajustes (`app/settings/page.tsx`, `components/settings/**`, `WorkspaceForm.tsx`, `AppMode.tsx`, `Security.tsx`)

One scrolling page; sections and anchors **Perfil `#perfil` · Apariencia `#apariencia` · Categorías
`#categorias` · Modo `#modo` · Copia de seguridad `#respaldo` · Espacios `#espacios`** (+ Avanzado
`#avanzado` only when advanced). The backup section's label is **"Copia de seguridad"** (`i18n/plan.ts`,
`settings.section.backup`).

- **Perfil** — `useWorkspace().current`; `PUT /api/workspaces/{ws} {name, base_currency}`, "Idioma de la app"
  (a `Select` → `setLang`), "Idioma de los avisos" (`{language}`).
- **Apariencia** — `<ThemeToggle>` Sistema / Claro / Oscuro (`aurum.theme`).
- **Categorías** — a short explanation and a link to `/categorias/`.
- **Modo** — `role=radiogroup` **Simple** ("Solo lo personal: Inicio, Mi dinero, Movimientos, Cuentas,
  Presupuesto, Metas y Ajustes.") / **Avanzado** → `PUT /api/workspaces/{ws} {ui_mode}`; "Encender solo
  algunos módulos" (`{modules}`) in a collapsed `<details>`, enabled only in simple mode.
- **Copia de seguridad** — **"Descargar copia de seguridad"** = `GET /api/workspaces/{ws}/backup.zip`
  (ledger files + docs + `metadata.json` + `movimientos.csv`) and **"Exportar movimientos (CSV)"** = `GET
  /api/workspaces/{ws}/movimientos.csv?from&to` (two `MonthPicker`s), both fetched with the stored bearer
  when one exists → Blob → download; a failure renders `ErrorBox` (401 → the Ajustes link). The full
  data-dir backup (`POST /api/backup`) and `scripts/restore.py` are operator recipes in
  [OPERATIONS.md](../OPERATIONS.md), not buttons.
- **Espacios** — reads `GET /api/workspaces?include_hidden=1`; personal spaces first, demos under a collapsed
  "Demos"; badges Actual / Protegido / Escondido; **Usar** (`setWs`), Esconder·Mostrar (`PUT {hidden}`,
  disabled for `protected` and the current space); **"Nuevo espacio"** → `POST /api/workspaces` (simple
  mode: id, name, currency, language). **No delete, no reset** (protected workspaces).
- **Unlabelled last card** (after Espacios): **"Empezar de nuevo"** → `/empezar/`; **"Restablecer
  preferencias"** → `ConfirmDialog` → removes every `localStorage` key starting with `aurum.` → `/`.
- **Avanzado** (advanced only) — API token (`aurum.token`, `Authorization: Bearer`), auth `Badge` from
  `GET /api/health` (`auth.required`), MCP snippet, Modelos from `health.llm`, raw profile, full
  `WorkspaceDialog`.
- Simple-mode `<main>` text carries none of Token, MCP, `AURUM_`, Bearer, `localStorage`, CFDI, ISR, IVA,
  `Expenses:`, `/api/` or "Espacio de trabajo". Title "Ajustes · Aurum".

### `/avanzado/` — Avanzado (`app/avanzado/page.tsx`, `lib/advanced.ts`)

The last menu item, for every workspace. Every advanced screen as a card — its name plus one plain line
(`adv.hub.desc.*`) — in four groups: **Entender y planear** (Avisos, Plan, Reportes) · **Documentos y bancos**
(Bandeja, Documentos, Conciliación) · **Impuestos y leyes** (Impuestos, Transfronterizo, Investigación,
Vigilancia) · **Para expertos** (Libros, Automatizaciones, Herramientas, + Negocio in a business workspace).
Each card is a link to the unchanged route. In simple mode a closing card "¿Las usas seguido?" → Ajustes ›
Modo. **Zero** requests. Title "Avanzado · Aurum". The page is the Avanzado home, so its copy may name CFDI /
RESICO / Libros / Bandeja (always after a plain explanation); `ui-check` runs every check on it except the
banned-vocabulary scan (`VOCAB_EXEMPT`).

### `/plan/` — Plan (advanced; `app/plan/page.tsx`, `components/plan/CreditDialogs.tsx`)

On mount `?tab=budgets` → `router.replace('/presupuesto/' + rest)` and `?tab=goals` → `/metas/` (every other
param kept). Tabs render only when allowed: Inversiones ⇐ `useModule('holdings')`, Escenarios ⇐
`useAdvanced()`, Crédito ⇐ either; a simple workspace sees one `EmptyState` **"Inversiones y crédito están
apagados"** and fires **zero** requests (no `/credit`, `/holdings`, `/scenarios`); its button **"Encender
inversiones y crédito"** → `PUT /api/workspaces/{ws} {modules: {…, holdings: true}}` (`useModeSave`), after
which Inversiones · Crédito render (Escenarios stays advanced-only). Crédito reads
`GET /pf/{ws}/credit/cards|loans|scores`, `GET /pf/{ws}/accounts?include_archived=1` (+ `/amortization` when
a loan is picked); Nueva tarjeta / Nuevo préstamo create **pf accounts** (`POST /pf/{ws}/accounts
{type:'credit_card'|'loan', …, apr_percent}` — the UI does not call `POST /credit/cards|loans`); "Editar
términos" → `PUT /pf/{ws}/accounts/{id}` with only the changed terms (an untouched save sends nothing);
MSI → `POST /pf/{ws}/credit/cards/{id}/msi`; puntaje → `POST /pf/{ws}/credit/scores`.

## Advanced routes (one click away from `/avanzado/`)

Route + endpoints only. Every route works at its URL; simple mode links to them only from the
`/avanzado/` page (the last menu item); the rail's Avanzado group lists them in advanced mode or per
module (`lib/advanced.ts`). **Vigilancia** reads `GET /watch/changes` as the bare list of verified rows
`{id, source_id, detected_at, summary, domains, diff_excerpt, corpus_source_id, effective_from}`;
**Transfronterizo** treats the API's 404 for a workspace with no profile yet as "Aún no tienes un perfil
transfronterizo" plus **Editar perfil**, so the profile can be created from the UI.

| Route | Screen | Endpoints consumed |
|---|---|---|
| `/avisos` | Avisos: insights by severity, 90-day deadline calendar, Telegram digest | `insights/{ws}`, `insights/{ws}/{id}/dismiss`, `insights/{ws}/calendar`, `insights/{ws}/digest?format=json` |
| `/inbox` | Bandeja: keyboard review queue (Telegram quick-add lands here) | `ingest/{ws}/inbox`, `.../accept`, `.../reject`, `pf/{ws}/labels` |
| `/documents` | CFDI table + upload zones (XML/ZIP, bank CSV with `account_id`, photo) | `ingest/{ws}/cfdi` (GET/POST), `ingest/{ws}/bank/csv`; the photo zone calls `ingest/{ws}/photo`, which the API does not serve (receipt photos go through `ingest/{ws}/receipts` in + Agregar); the zone carries a note that photo capture needs `AURUM_OCR_URL` |
| `/books` | Libros: journal (new / edit / void), accounts tree, BQL | `ledger/{ws}/journal`, `/balances`, `/accounts`, `/query`, `/transactions` (POST), `/transactions/{id}` (PUT, DELETE) |
| `/reconcile` | Conciliación board | `ingest/{ws}/reconcile`, `.../match`, `.../unmatch` |
| `/taxes` | Impuestos MX (RESICO month close vs prefill, DRAFT PDF) · US (Schedule C, SE, estimates, TX franchise) | `tax/mx/resico/{ws}/{period}` (+ `/draft.pdf`), `tax/us/{ws}/{year}` (+ `/tx-franchise`, `/organizer.pdf`) |
| `/crossborder` | Profile wizard + residency / treaty / FBAR / FEIE-FTC assessment | `crossborder/{ws}/assessment`, `crossborder/{ws}/profile` (PUT) |
| `/research` | Investigación: cited answers with `as_of`, cross-references | `research/ask`, `research/refs` |
| `/watch` | Vigilancia: change feed, sources, rule proposals | `watch/changes`, `watch/sources`, `watch/sources/{id}/history`, `watch/proposals` |
| `/plan` | Inversiones · Escenarios · Crédito (see above) | `holdings/{ws}` (+ `/trades`, `/prices`), `fx/rate`, `plan/{ws}/scenarios` (+ `/run`, `/sensitivity`, `/montecarlo`), `plan/{ws}/saved`, `creditreport/{ws}` (+ `/import`, `/explain`), `pf/{ws}/credit/*`, `pf/{ws}/accounts` |
| `/reports` | Report packs, monthly review, P&L / balance / cash-flow, net-worth series | `reports/{ws}`, `reports/{ws}/{pack}/preview`, `reports/{ws}/{pack}?format=html\|pdf`, `.../archive`, `ledger/{ws}/statements/{period}?type=`, `pf/{ws}/review/{period}`, `/accounts`, `/income` |
| `/business` | Negocio (business workspaces): KPIs · Facturación · Nómina · Constantes | `business/{ws}/kpis`, `business/{ws}/invoices` (+ `/remind`), `business/{ws}/payroll` (+ `/employees`, `/run`, `/{id}/draft.pdf`), `business/constants/mx-nl` |
| `/workflows` | Automatizaciones: YAML workflows, runs, schedules, AI proposal (draft only) | `workflows/{ws}` (GET/POST), `workflows/{ws}/{id}` (GET/PUT/DELETE), `.../run`, `.../runs` (+ `/{run_id}`), `.../schedule`, `workflows/{ws}/propose`, `workflows/catalog` |
| `/tools` | Herramientas: MCP status, vault, health, sync jobs | `health`, `satsync/{ws}/vault`, `satsync/{ws}/jobs` |

### Legacy components

The advanced screens still import the older `Bits` / `Ui3` / `Form` components (25 files under `src/`
import one of them); those are thin shims over `@/components/ui` and stay until the last caller
migrates. New personal screens import primitives only from `@/components/ui`.
`components/Personal.tsx` exports only `accountTypeKey` (used by `onboarding/StepAccounts.tsx`);
`components/Money.tsx` keeps `KindBadge`, `StatusBadge`, `OccDot`, `CadenceText` and
`MoneySummaryPanel` (a wrapper over `components/money/Summary.tsx`). `lib/api.ts` keeps the
`@deprecated` aliases listed in the client-layer section; `createCard` / `createLoan` have no importer
under `src/` any more.

## i18n

`i18n.tsx` (core dictionary), `i18n-business.ts` (business, insights, reports, workflows, security settings),
`i18n-organizer.ts` (Mi dinero) and `i18n-personal.ts` (personal, manual-first) hold the original strings; the per-area
files `lib/i18n/{core,data,home,movimientos,cuentas,money,plan,novice}.ts` hold the newer ones and are
merged by `lib/i18n/index.ts` (`AREA_ES` / `AREA_EN`, order core → data → home → movimientos → cuentas →
money → plan → novice) and spread **last** into `DICTS` in `i18n.tsx`. A new key goes in exactly one file
(`es` is the key set; `en: Record<keyof typeof es, string>` must cover it). `useI18n() → {lang, setLang,
t, tn}`: `t(key, vars)` with `{name}` tokens, `tn(key, n)` plurals via `.one/.other`
(`tn('common.days', n)`), `useMoney().fmt`; `translate()/translatePlural()` outside React.
`scripts/check-i18n.mjs` fails on cross-file duplicates, ES/EN key mismatch and placeholder mismatch;
`scripts/check-vocab.mjs` applies the fenced banned-regex block of `design-system.md` to every
non-advanced ES value (ratchet in `scripts/vocab-baseline.json`) and greps `closePeriod` under the
personal pages (0). Exact screen labels for docs and tutorials come from these files — never invent copy.

## Verification status

- `npm test` covers the client layer, the screen helpers and the primary forms against the
  in-browser mock; `ui-check.mjs` covers the personal routes and `/avanzado/` against a live stack
  (routes × widths × themes, the dialog contract and the day-one / Tuesday / month-end flows). The
  advanced screens are not part of `ui-check`.
- Response shapes in `lib/types*.ts` are typed from real responses captured in
  `web-ui/docs/api-samples.json` or read off the router that produces them. The ones still marked
  `not yet checked against a real API response` in code: research `ask` (`ResearchAnswer`), the `POST /watch/run`
  envelope (`ChangesResponse`) and rule proposals (`RuleProposal`), the e.firma vault's
  `stored_at`/`cer_fingerprint` (no sample has `present: true`), the photo upload, and
  `POST /organizer/{ws}/setup/run` (its payday shape is a best guess). `GET /watch/changes` rows
  (`LawChange`) are checked against the live API.

## Gotchas

- **Static export needs CSP `script-src 'unsafe-inline'`.** `app/layout.tsx` inlines a small
  pre-hydration theme script, and `nginx.conf.template` sends `script-src 'self' 'unsafe-inline'` (plus
  `style-src 'unsafe-inline'` for React's inline style attributes). Tightening the CSP means hashing that
  script first.
- **No `Date` at prerender.** Nothing that prerenders calls `new Date()`, `currentPeriod()` or computes
  "today" during render; the clock is read in an effect (or on click) so the first render matches the
  server's. `formatPeriod` is a twelve-string **table**, not `Intl` (Node and Chrome disagree on `sept`
  vs `sep` → hydration error #418); `todayLocalIso()` / `daysUntil()` use local calendar parts, never
  `toISOString()`.
- **Breakpoints.** Rail ⇄ tab bar at 960 px (`max-width: 959px`); every `Dialog` becomes a bottom sheet at
  **≤640 px**; `ResponsiveTable` is a `<table>` from 768 px and a `CardList` below; controls are 36 px with a
  mouse at ≥960 px and 44 px under `(pointer: coarse), (max-width: 959px)` (`ui-check.mjs` audits 36 px at
  ≥960 px through `tapMinFor()`).
- **Never add MXN + USD.** Money stays a decimal string; the UI never computes totals — they come from the
  API (`entries.totals`, `budgets.totals`, `net_worth`). The few allowed client-side sums all go through
  `sumDecimals` (integer centavos, `lib/validate.ts`) and never cross a currency: the per-currency stats on
  `/cuentas/`, the Movimientos per-day subtotal (`null` when a day mixes currencies), the Empezar done
  screen's liquid balance, the Calendario month strip when the API sends no `totals`, and the Metas
  emergency template (three months of `review.expense`). Foreign amounts render `US$…` / `MX$…`; the base
  currency renders `$`.
- **Static export routing**: no dynamic route segments; the workspace id lives in the provider (`?ws=` read
  **once** at provider mount, then `localStorage aurum.ws`, then the first personal non-demo workspace — an
  in-app `<Link href="/?ws=…">` is a no-op; switch with `setWs()`); `trailingSlash: true` (link to
  `/movimientos/`, never `index.html`); `?tab=` / `?period=` / `?step=` are read after mount.
- **nginx `proxy_pass` uses a variable** so the upstream is resolved per request (a literal host makes
  web-ui crash-loop while `api` restarts) — hence `DNS_RESOLVER`. nginx forwards `Host` with its port
  (`$http_host`): the API's origin guard compares it with the browser's `Origin`, and dropping the port
  turns every same-origin write into `403 origin_not_allowed`.
- **Dev loop against a real API**: `next dev` has no `/api` rewrite, and the API refuses browser writes whose
  `Sec-Fetch-Site` is `cross-site` (Chrome treats `localhost` and `127.0.0.1` as different sites). Follow
  [OPERATIONS.md](../OPERATIONS.md) "Dev loop against a real API" (both sides on `localhost`,
  `AURUM_ALLOWED_ORIGINS`, a scratch `AURUM_DATA_DIR`, never `./data`); `ui-check.mjs` reads
  `${BASE_URL}/api` on the same origin, so it runs against the compose stack or a static export behind a
  proxy, not against `next dev`.
- **`ui/Dialog` + React StrictMode (`next dev` only)**: a `<dialog>` mounted with `open` already true is
  closed by the simulated unmount/remount; screens work around it with `useOpenAfterMount` and by mounting
  `ConfirmDialog` once and driving it with `open`. Production builds are unaffected.
- **`localStorage` registry**: `aurum.ws`, `aurum.lang`, `aurum.theme`, `aurum.token`,
  `aurum.advanced_open`, `aurum.lastAccount.<ws>`, `aurum.catUsage.<ws>`; every read/write in `try/catch`;
  Ajustes › "Restablecer preferencias" clears them. Nothing else goes in `localStorage` without a row in
  `design-system.md` §9.
- **`(verify)` chips**: a rule's `unverified_constants` are opaque machine keys
  (`se.net_earnings_factor`, …); `components/VerifyChips.tsx` renders each key as is next to a
  translated "(verify)" badge. Do not invent translated labels for the keys (see [i18n.md](i18n.md)).
- **Seeded demo names trip the vocabulary scan**: `demo-mx` is called "Demo México (RESICO)" and the Shell's
  `Espacio` select renders every visible workspace name, so `ui-check` can report "RESICO" on every route of
  a data dir that has it (hide `demo-mx` in the scratch data or exclude the switcher from the scan).
- **`personal` is protected**: `ui-check.mjs` and `scripts/verify_demo.py` exit 2 before any request when
  `WS=personal`; the flows create `ui-check-<ts>` workspaces and `PUT {hidden:true}` in `finally`.
- **Screenshots are local output**: `ui-check.mjs` writes to the repo-root `docs/screenshots/ui/` and
  `screenshots.mjs` to `web-ui/docs/screenshots/`; both directories are gitignored.
