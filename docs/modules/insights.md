# insights

Deterministic, code-only nudges assembled from what the other modules already compute. Nothing here
invents a number: every `Insight.amount` comes straight out of a tax/pf/ledger result
that already carries its own `Explain`; this module only decides *whether* a nudge fires and writes a
short localized sentence around it. An optional one-paragraph LLM digest may rephrase the deterministic
text (never its figures), with an offline fallback — same pattern as `aurum.updater.triage.summarize`.

## Files

- `aurum/insights/engine.py` — `Insight` / `Action` models and `build_insights(ws_id, period, lang)`.
- `aurum/insights/i18n.py` — a thin re-export of `aurum.core.i18n.t` (the `insights.*` keys live in
  `aurum/core/i18n.py`).
- `aurum/insights/digest.py` — `deterministic_text()` (bullet list) and `digest_text()` (optional LLM
  paragraph rewrite, same figures, offline-safe).
- `aurum/insights/telegram.py` — chat↔workspace mapping, webhook handling, `send_message()`.
- `aurum/insights/router.py` — `/api/insights` (mounted by `aurum/api/app.py`).
- `aurum/insights/schema.sql` — `insights_dismissed(ws_id, insight_id, dismissed_at)`.
- `scripts/telegram_nudges.py` — command-line entry point that pushes the digest to Telegram; run it
  from cron or any scheduler.

## Kinds produced

| kind | source | severity |
|---|---|---|
| `pue_not_collected`, `deposit_without_cfdi`, `cash_paid_expense`, `fixed_asset_iva`, `ppd_missing_rep` | `aurum.tax.month_close` diffs | warn / info |
| `you_may_owe` | ISR + IVA payable from `month_close`, due the 17th | urgent ≤7d, warn ≤15d, else info |
| `us_quarterly_estimate` | `aurum.taxus.service.annual` (only when `'US' in workspace.jurisdictions`) | urgent ≤7d, else warn, only surfaced within 30d |
| `budget_alert` | `aurum.pf.budgets.budget_status` rows with `alert != "none"` | urgent (100%) / warn (80%) |
| `goal_off_track` | `aurum.pf.goals.goal_with_progress`: `monthly_required` vs. 3-month average net inflow into the goal's account | warn |
| `card_cut_due`, `card_payment_due` | `aurum.pf.credit.card_status`, next 7 days | urgent ≤2d, else warn |
| `spending_anomaly` | `aurum.pf.review.monthly_review` anomalies (>2x trailing 3-month average) | warn |
| `regime_exit_risk` | RESICO annual cap pace: `(YTD income / months elapsed) * 12` vs `ANNUAL_CAP` (3,500,000 MXN, `aurum.rules.mx.resico`), only 'MX' + `profile.regime == "RESICO_PF"` | urgent ≥100% pace, warn ≥80% |
| `missing_statement` | no `Assets:Bank:*` ledger postings in the period, but there were postings in an earlier period (so an empty workspace never false-positives) | info |
| `organizer_<kind>` | `aurum.organizer.alerts.compute_alerts` re-wrapped; the insight **id is the alert id** (`org-<kind>-<hash>`), the action label is `insights.action.view_organizer` | as the alert |

### Tax gating and dedupe

- **Tax nudges only with the tax module on.** `build_insights` runs `_month_close_insights`,
  `_regime_exit_insight` and `_us_quarterly_insight` only when `core.workspaces.module_on(ws, "tax")`
  (`ui_mode == "advanced"` or `modules.tax`); `_missing_statement_insight`, budgets, goals, cards,
  anomalies and organizer alerts are unchanged. The Telegram digest inherits the gate because it calls
  `build_insights`. The demo workspaces are created in simple mode with `modules.tax=false`, so the
  tests that assert tax kinds switch the flag on first.
- **Calendar.** `_mx_calendar` requires `module_on(ws, "tax")` and `"MX" in jurisdictions`;
  `_us_calendar` requires `module_on(ws, "tax")` and `"US"`. The organizer calendar's tax rows come from
  this endpoint and are gated the same way.
- **One nudge per bill.** The insights engine has no bill-due producer of its own (it does not read
  `pf.accounts.detect_recurring`); the organizer's `upcoming` / `income_expected` alerts are the single
  source. Because
  organizer insights keep the alert id, `POST /{ws}/{id}/dismiss` with an `org-…` id writes
  `organizer_dismissed_alerts` (via `organizer.alerts.dismiss`) instead of `insights_dismissed`, so the
  nudge disappears from Avisos and from Mi dinero at once.
- `spending_anomaly` amounts use the workspace base currency (no `MXN` literal).

Every producer function is defensive: a missing optional module, an unreadable workspace, or a data
shape it doesn't recognize makes that one kind skip silently (`except Exception` around each helper)
rather than failing the whole list. Modules stay independently testable, and at runtime one failing
source never hides the others.

## Endpoints (`/api/insights`)

- `GET /{ws}?period=&lang=&include_dismissed=` — the list above, sorted urgent → warn → info, minus
  dismissed ids unless `include_dismissed=true`. `period` defaults to the current month.
- `GET /{ws}/digest?period=&lang=&format=text|json&llm=false` — `deterministic_text()` by default;
  `llm=true` asks `aurum.llm.structured.generate_text` to rewrite it as one paragraph (falls back to the
  deterministic text on any provider error, including no local model running). Kept `llm=false` by
  default so the endpoint stays deterministic/offline out of the box.
- `POST /{ws}/{insight_id}/dismiss` — persists to `insights_dismissed` (or to
  `organizer_dismissed_alerts` when the id starts with `org-`); the id is a stable hash of
  `(ws_id, kind, ...disambiguators)` so the same underlying fact dismissed today re-appears once its
  disambiguators change (a new period, a new due date, …) rather than being silenced forever.
- `GET /{ws}/calendar?from=&to=` — deadlines in range: MX monthly declaration (17th of the month after
  each period; DIOT is assumed folded into the same filing — **(verify)**), the MX annual declaration
  for personas físicas (**(verify)** exact date against LISR art. 150; assumed April 30), US quarterly
  estimates (when applicable), credit-card cut/due dates, and goal target dates.
- `POST /telegram/webhook` — see below.

## Telegram

`aurum/insights/telegram.py`:
- `chat_ws_map()` parses `AURUM_TELEGRAM_WS_MAP` (`"chat_id:ws_id,chat_id:ws_id"`).
- `handle_update(update)` never raises: a text message becomes a quick-add Inbox item
  (`aurum.ingest.quickadd.parse_quickadd` → `aurum.ingest.inbox.create_inbox_item`) for the mapped
  workspace; an unmapped chat gets a bilingual "not linked" reply; a photo gets a bilingual
  acknowledgement (OCR is not wired here); a parse failure becomes a friendly reply, not a 500.
- `check_secret(header_value)` — when `AURUM_TELEGRAM_SECRET` is set, the router requires
  `X-Telegram-Bot-Api-Secret-Token` to match it (401 otherwise); unset, every call is allowed.
- `send_message(chat_id, text, token=None)` — the only place that talks to `api.telegram.org`. Tests
  never call it for real; they monkeypatch env vars and inspect `handle_update`'s return value, or hit
  the webhook route without `TELEGRAM_BOT_TOKEN` set (the webhook still ACKs Telegram even if the reply
  send fails — see `scripts/telegram_nudges.py`'s docstring for the scheduled push side).

See `docs/tutorials/telegram-nudges.md` for setting up the bot and scheduling the nudges.

## Limitations and unverified points

- DIOT and the MX annual declaration exact dates are marked `(verify)` in the calendar payload: LISR
  art. 150 and the DIOT rule primary text have not been re-read for this calendar; the April date rests
  on the project's spec notes ("the April annual declaration (art. 113-F)").
- The `budget_alert` sentence shows `budget_status`'s `pct` as is: it is already a percent number.
- `regime_exit_risk` reuses `aurum.rules.mx.resico.ANNUAL_CAP` (already a repo constant); the pace
  formula itself (`(ytd/months_elapsed)*12`) is this module's own heuristic, not a cited rule.
- The LLM digest paragraph is off by default on the HTTP endpoint (`llm=false`) precisely because a
  real local Ollama can be running during development, which would make `GET /digest`
  non-deterministic for tests and callers who just want the plain text; `scripts/telegram_nudges.py` defaults it on (`--no-llm` to
  disable) since a nicer paragraph is the point of a Telegram nudge.
