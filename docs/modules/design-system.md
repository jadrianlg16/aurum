# Design system (web-ui)

The rules every web-ui screen follows. What it describes lives in `web-ui/src/app/globals.css`
(tokens), `web-ui/src/components/ui/**` (primitives), `web-ui/src/lib/{format.ts,theme.tsx,a11y.ts,i18n.tsx}`,
`web-ui/src/lib/i18n/core.ts` and `web-ui/public/**`. Read this before writing a screen; import
primitives only from `@/components/ui`. The architecture of the UI as built is in [web-ui.md](web-ui.md).

## 1. Vocabulary (ES primary, EN parity)

| Use | Never | Notes |
|---|---|---|
| movimiento | transacción, asiento, posting, txn | `Movimientos` is the screen |
| categoría | etiqueta, label | |
| cuenta *by name* (BBVA, Efectivo) | `Assets:…`, cuenta contable, Beancount path | ledger strings only under Avanzado |
| espacio | espacio de trabajo, workspace | `header.workspace` = "Espacio" |
| pagos fijos y suscripciones | compromisos, commitments | |
| monto | importe | |
| comercio o quién | beneficiario, payee | |
| mes | periodo | in personal screens |
| **Libre para gastar** (safe_to_spend, once, "Disponible hasta el <fecha>") | disponible (as a second figure) | Home hero + Mi dinero, from the organizer only |
| **Presupuesto restante** | disponible para gastar | `budgets/status.safe_to_spend` is always labelled this |
| lo que tienes / lo que debes | activos / pasivos | |
| captura rápida (atajo) | bandeja, inbox | |
| avisos | alertas, insights | |
| borrar · archivar · a mano | eliminar · dar de baja · manual | |
| Avanzado | — | the only home of Bandeja, Libros, Asiento, CFDI, RESICO, DIOT, ISR, IVA (incl. the `/avanzado/` page: `adv.hub.*`, plain line first) |

Voice: tú, present tense, sentence case, no exclamation marks, no "por favor"; buttons are
verb + object ("Guardar gasto", "Borrar cuenta"); errors say what happened and what to do,
never the HTTP word; toasts are past participles ("Movimiento guardado"); hints ≤ 90 chars.
Empty state = one sentence of what belongs here + one of why + primary CTA (manual) +
optional secondary link labelled "(atajo)". Destructive confirms name the thing with the
formatted amount and date.

Banned in any non-advanced ES value (read by `scripts/check-vocab.mjs`, which also feeds the rendered-text
scan of `ui-check.mjs`; the advanced key prefixes are the built-in list in `check-vocab.mjs`):

```banned-regex
\b(Assets|Liabilities|Income|Expenses|Equity):
\bBandeja\b
\bAsiento\b
compromiso
\bEtiqueta\b
Espacio de trabajo
Importe
Beneficiario
Confianza \d+%
RESICO|DIOT|CFDI|\bISR\b|\bIVA\b|Beancount|Libros|localStorage|Bearer|AURUM_
[a-z]+_[a-z]+
```

## 2. Money and dates

- Money is a decimal **string** on the wire and stays one. Never `Number()` it except in
  `toChartNumber` (pixel geometry only). Render with `<Money>` or `useMoney().fmt`.
- The sign is **always explicit** and never colour-only: `−` (U+2212) before the affix,
  `+` with `sign: 'always'`; `<Money>` adds an sr-only "salida"/"entrada" whenever a sign shows.
- Base currency → `$1,234.56`; foreign → `US$…`, `MX$…`, else `EUR 1,234.56`. `−0.00` collapses.
  `formatAmount` never throws (a non-decimal input comes back verbatim).
- `todayLocalIso()` / `daysUntil()` use LOCAL calendar parts — never `toISOString()`.
- `formatDate(iso, lang, 'short'|'medium'|'long'|'weekday')` and `formatPeriod(period, lang,
  'short'|'long')` are table-driven (hydration-safe). `relativeDay` says hoy/mañana/ayer/en n
  días/hace n días inside ±7 days. Headings: `formatDayHeading` → "Hoy · vie 12 sep".
- **No Date at prerender**: nothing that prerenders calls `new Date()`, `currentPeriod()` or
  computes "today" during render. Read the clock in an effect (or on click) and keep the first
  render identical to the server's. `MonthPicker` formats its label after mount for this reason.
- Plurals: `tn('common.days', n)` → "3 días" via `common.days.one|.other`. No string concatenation.

## 3. Tokens (globals.css `:root`)

Spacing `--sp-1..7` (4 8 12 16 24 32 48) · type `--fs-xs..3xl` (12 13 14 16 20 26 34), `--lh-tight`
1.25, `--lh-body` 1.5 · radii `--r-1/2/3/pill` (6 10 14 999) · elevation `--el-1/2/3` · motion
`--dur-1` 120ms, `--dur-2` 200ms, `--ease` · `--tap` 44px · layout `--rail-w` 224, `--topbar-h` 56,
`--tabbar-h` 56, `--content-max` 1120, `--safe-b`.

Palette (AA-verified; `scripts/contrast.mjs` is the gate): `--paper --surface --surface-2 --line
--line-strong --ink --ink-2 --ink-3 --accent-text --accent --on-accent --accent-soft --pos/--pos-soft
--neg/--neg-soft --warn/--warn-soft --info/--info-soft --backdrop`. Gold as **text** is
`--accent-text`; gold as a **fill** (primary button, focus ring) is `--accent` with `--on-accent`
text. Old names stay as aliases (`--gold`, `--gold-soft`, `--gold-line`, `--radius`, `--radius-sm`,
`--shadow`, `--rail`, `--header`) — do not use them in new code. No hardcoded hex in screens.

Base rules: `:focus-visible` 2px `--accent` ring (inset in `.tabs`/`.rail`); `prefers-reduced-motion`
zeroes animations; `.money`/`.num` are the sans stack with tabular figures (mono only for `.kbd`,
`.formula`, `.rule-chip`); no text below 12px; controls are 36px with a mouse and `--tap` (44px)
under `(pointer: coarse)` or below 960px; `.sr-only` = `.visually-hidden`.

## 4. Theme

`lib/theme.tsx`: `ThemeProvider` (outermost in layout.tsx), `useTheme() → {theme, setTheme,
effective}`, `theme ∈ system|light|dark`, stored in `aurum.theme` (absent = system). It sets
`data-theme` on `<html>` (removed for system) and rewrites `<meta name="theme-color">` to the
effective `--paper`. The palette is declared three times in globals.css: light on `:root`, dark
under `@media (prefers-color-scheme: dark) { :root:not([data-theme='light']) }`, dark again under
`:root[data-theme='dark']`. A 124-byte inline script in `app/layout.tsx` applies the stored value
before first paint; it depends on the CSP's existing `'unsafe-inline'` for scripts — if the CSP is
tightened, hash it. `<ThemeToggle>` is the Sistema/Claro/Oscuro control (keys `theme.*`).

## 5. Primitives (`@/components/ui`)

| Primitive | Props | Notes |
|---|---|---|
| `Button` | `variant primary\|secondary\|ghost\|danger, size sm\|md\|lg, loading, icon, href, type` | `href` → `<a class="btn">`; `loading` keeps the label |
| `IconButton` | `ariaLabel` (required), `icon`, `bordered` | 36px, 44px on coarse pointers |
| `Field` | `label, hint, error, required, asGroup, children` | ids via `useId`; `aria-describedby` hint+error; `aria-invalid` only with an error; `*` + sr "obligatorio" |
| `Input` / `Textarea` / `Select` | native props | bind to the surrounding `Field` through `useFieldIds` |
| `MoneyInput` | `value:string, onChange(string), currency, allowNegative=false, autoFocus, focusKey` | `inputMode=decimal`, digits/one dot/leading minus, groups on blur, unformats on focus, currency chip; focus by ref |
| `DateField` | `value, onChange, todayYesterdayChips, min, max` | native date + Hoy/Ayer chips (local dates, computed on click) |
| `MonthPicker` | `value 'YYYY-MM', onChange, min?, max?` | ‹ › Hoy, ←/→ while focused, `aria-live` label after mount; pair with `usePeriodParam()` |
| `Tabs` / `TabPanel` | `items [{id,label,count?}], value, onChange, queryKey?, label` | tablist, roving tabindex, ←/→/Home/End, scrollable pills, `?tab=` via `replaceQueryParam` |
| `Dialog` | `open, onClose, title, description?, size sm\|md\|lg, form? {onSubmit,busy,submitLabel}, footer?, destructive?, initialFocus?, error?, hideClose?` | native `showModal`, Esc/backdrop close, return focus, Enter submits in form mode, sticky footer, internal scroll, bottom sheet ≤640px, body scroll lock |
| `Sheet` | same minus `size` | bottom-anchored at every width (menus, row actions) |
| `ConfirmDialog` | `title, body, confirmLabel, destructive, busy, onConfirm, onCancel` | `body` is formatted content (`<Money>`), never a raw string; destructive → alertdialog, focus on Cancelar |
| `ToastProvider` / `useToast()` | `success(msg,{action?}), error(msg), info(msg), dismiss(id)` | one polite + one assertive region always present; max 3; 5 s / 8 s (error); pause on hover/focus; Cerrar; Esc dismisses newest; deferred while a dialog is open |
| `Skeleton` | `variant text\|stat\|table\|card\|list, rows, what` | `role=status aria-busy`, sr "Cargando {what}"; shimmer off under reduced motion |
| `EmptyState` | `icon, title, body, primary {label,onClick\|href}, secondary {label,onClick\|href}, compact` | labelled `<section>`; secondary is a text link suffixed "(atajo)" |
| `ErrorBox` | `error: unknown\|string, onRetry` | `role=alert`, message from `ApiError.message`/string; 401 adds the Ajustes link |
| `Badge` | `tone neutral\|accent\|pos\|neg\|warn\|info, dot` | |
| `Stat` | `label, value, sub?, delta? {amount, vs}, tone?, explain?, size md\|lg` | explain behind "¿Cómo se calcula?" |
| `Sparkline` | `points [{label,value}], title?, height?, columns?` | `<title>`, `currentColor`, theme-aware |
| `ResponsiveTable` | `columns [{key,header,align,mobile title\|subtitle\|value\|meta\|hidden,render,numeric}], rows, rowKey, onRowClick?, actions?, label` | `<table>` ≥768px in a focusable scroll region; `ul.cardlist` below; row actions → ⋯ → Sheet |
| `CardList` / `DataTable` | see Table.tsx | `DataTable{caption,columns,rows}`: sr-only caption, `th scope`, scroll region |
| `AccountPicker` | `ws, value, onChange(id, account), filterTypes?, allowNew?, onCreateNew?, version?` | groups Efectivo y bancos / Tarjetas / Préstamos / Inversiones / Otras; option text `name · institution · balance`; never a ledger string; `ws` may be null |
| `CategoryPicker` | `ws, kind expense\|income\|undefined, value, onChange(id, label), allowNew?, version?` | filters by `label.kind ?? account prefix`, hides archived, first option "Sin categoría"; `allowNew` → inline name + Crear → `createLabel(ws,{name,kind})` |
| `PageHeader` | `title, subtitle?, actions?, month? (MonthPicker props)` | the page's only `<h1>`; claims the document title |
| `MoreOptions` | `children, defaultOpen?, label?` | a form shows only what must be answered; fields with a sensible default go in this "Más opciones" `<details>` (open when editing) |
| `Money` | `amount, currency?, sign auto\|always, compactCents, tone auto\|pos\|neg\|neutral\|none` | via `useMoney()` |
| `Icon` | `name, size, label?` | home wallet list bank target flag settings plus search more sun moon chevron-left/right check x alert info undo calendar grid |
| `ThemeToggle` | — | Sistema / Claro / Oscuro |

`lib/a11y.ts`: `useReturnFocus(active)`, `useShortcut(key, handler, {when, allowInDialog})`,
`usePageTitle(title)`, `focusMain()`, `isTypingTarget()`, `dialogIsOpen()`.
`lib/i18n`: `t(key, vars?)` (`{name}` tokens; a missing var leaves the token and warns in dev),
`tn(key, n, vars?)`, `useI18n()`, `useMoney()`, `translate()/translatePlural()` outside React.
Legacy shims for the older (advanced) screens: `Form.Dialog`, `Ui3.useToast` (`node` is `null`),
`Bits.{Loading,Empty,ErrorBox,Money,Sparkline}`. New screens do not use them.

## 6. Layout recipes

- Page: `<PageHeader title … month={…} actions={…} />` then sections in `.card`s or a
  `.grid.cols-2/3/4` (`minmax(min(N, 100%), 1fr)` — never overflows at 320px). `main` has
  `min-width: 0`; wide content goes in `.table-scroll` or `ResponsiveTable`.
- Shell: rail ≥960px with `Icon` + label; bottom tab bar Inicio · Movimientos · [+] ·
  Cuentas · Más below; topbar wraps; **+ Agregar is the only `.primary` in the chrome** (a page may
  have one primary of its own); Captura rápida lives in the ⋯ menu and only in advanced mode.
  `<main id="main" tabIndex={-1}>` receives focus after rail navigation and from the skip link.
- Forms: one `Dialog` in form mode (or an inline `<form>` on wizard screens); `Field` around
  every control; `MoneyInput` for amounts; `AccountPicker`/`CategoryPicker`; submit → toast →
  reload the list. No `window.confirm`, no hand-rolled modals, no `style={{}}` for
  spacing/colour, no hardcoded hex.
- Advanced gating: `useAdvanced()` / `useModule(name)`; simple mode never calls `/tax`, the
  ingest inbox, `/credit`, `/holdings`, `/scenarios`.

## 7. Loading / error contract

First load → `Skeleton` in place of the content. Reloads keep the content on screen and set
`refreshing` (stale-while-refresh) — never swap back to a skeleton or "Cargando…". Errors →
`ErrorBox` inline with Reintentar (401 links to Ajustes; the Shell also shows the auth banner from
`useHealth().authRequired || unauthorized`). Writes → toast (`success` with `Deshacer`
for entry create/delete, mark paid, account archive, commitment cancel; edits have no undo),
then reload. Lists never update optimistically except the marked occurrence row.

## 8. Keyboard

| Key | Where | Action |
|---|---|---|
| `n` | any screen, not while typing, no dialog open | open + Agregar (Gasto) |
| `/` | advanced mode only | Captura rápida |
| `Esc` | dialog / sheet / toast | close (dialog `cancel` event); dismiss newest toast |
| `Enter` | Dialog form mode | submit (`busy` blocks) |
| `Tab` (first) | every page | "Ir al contenido" skip link → `#main` |
| `←` `→` `Home` `End` | Tabs, MonthPicker | move |
| `Enter` / `Space` | clickable table rows | open |

No `a` shortcut and no chords. Shortcuts use `useShortcut`, never raw listeners.

## 9. localStorage registry

`aurum.ws`, `aurum.lang`, `aurum.theme`, `aurum.token`, `aurum.advanced_open`,
`aurum.lastAccount.<ws>`, `aurum.catUsage.<ws>`. Every read/write is wrapped in try/catch; Ajustes ›
"Restablecer preferencias" clears them all. Nothing else goes in localStorage without a row here.

## 10. Icons and static assets

`public/favicon.svg`, `favicon.ico`, `apple-touch-icon.png` (180), `manifest.webmanifest`
(name Aurum, `start_url '/'`, standalone, theme/background = `--paper` light), `icons/icon.svg` +
`icon-192.png`, `icon-512.png`, `icon-maskable-512.png` (artwork inset to 80 % on `--accent`).
Regenerate the PNGs from `icon.svg` with headless Chrome (no node canvas), from `web-ui/`:

```
chrome --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 \
  --window-size=512,512 --screenshot=public/icons/icon-512.png file:///<abs>/icon.html
```

where `icon.html` is a page whose body is the SVG at the target size (192, 512, 180; the maskable
one on a `#b8860b` background with the SVG at 80 %). Then `favicon.ico` = the 32px PNG wrapped
with Pillow (`Image.save(..., format='ICO', sizes=[(16,16),(32,32)])`). nginx serves
`.webmanifest` as `application/manifest+json` and `/404.html` for unknown paths
(`web-ui/nginx.conf.template`).

## 11. Checks for a new screen

`npm run typecheck && npm run lint && npm run build:mock`; `npm run ui-check` (or a manual pass) at
320/390/768/1280 with no horizontal overflow (`document.documentElement.scrollWidth <= innerWidth`); `document.
querySelectorAll('[aria-live]').length === 2`; dialogs: focus inside on open, Esc closes, focus
returns to the opener; every amount through `<Money>`; `check-i18n`/`check-vocab` green.
