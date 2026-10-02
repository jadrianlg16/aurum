# Telegram nudges: a daily digest from cron or any scheduler

Telegram is an optional channel. You bring your own bot; Aurum's side is a single script,
`scripts/telegram_nudges.py`, which you run from cron, a systemd timer, Task Scheduler or any other
scheduler. It imports `aurum` directly (no running API required), so the job only needs this repo
checked out (or on `PYTHONPATH`) and the environment variables below.

## 1. Create a Telegram bot and get your chat id

1. Talk to [@BotFather](https://t.me/BotFather), `/newbot`, copy the token it gives you.
2. Send any message to your new bot, then call
   `https://api.telegram.org/bot<token>/getUpdates` and read `message.chat.id` from the response — that
   is your `TELEGRAM_CHAT_ID`.

Keep both values out of the repo: they belong in the scheduler's environment or a local `.env` file.

## 2. Set the environment

```
export TELEGRAM_BOT_TOKEN="<your-bot-token>"
export TELEGRAM_CHAT_ID="<your-chat-id>"
# only if you also want the chat to quick-add via Telegram (step 4):
export AURUM_TELEGRAM_WS_MAP="<your-chat-id>:demo-mx"
```

These are read directly from the environment (`os.environ`), not from `aurum.core.config.Settings` —
they only matter to the Telegram integration, not to the rest of the app.

## 3. Schedule the script

A dry run (no env vars needed) always prints what it *would* send and exits 0:

```
uv run python scripts/telegram_nudges.py --ws demo-mx
```

Add `--send` for the real delivery; that is the command to schedule:

```
uv run python scripts/telegram_nudges.py --ws demo-mx --send
```

Useful flags:
- `--period YYYY-MM` — defaults to the current month.
- `--lang es|en` — defaults to the workspace's own language.
- `--urgent-only` — send just the urgent insights as short lines, skipping the digest paragraph (good
  for a more frequent check, e.g. every few hours, versus a once-daily full digest).
- `--no-llm` — skip the optional LLM paragraph rewrite and send the deterministic bullet list.

A typical schedule: the full digest once a day, `--urgent-only` every few hours in between so a card due
tomorrow or a filing due in 2 days doesn't wait for the next daily digest. For example, with cron
(replace the path with your checkout):

```
0 8 * * *     cd /path/to/aurum && uv run python scripts/telegram_nudges.py --ws demo-mx --send
0 */4 * * *   cd /path/to/aurum && uv run python scripts/telegram_nudges.py --ws demo-mx --send --urgent-only
```

The script never fails silently: missing `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` with `--send` given
prints a clear error to stderr and exits 1; a delivery failure (bad token, network) does the same. A
plain dry run (no `--send`) always exits 0 once it has printed the message, so you can use it to
preview a digest without risking a delivery.

## 4. (Optional) Quick-add via the same chat

Telegram quick-add lands in the workspace's **Inbox** (the review queue under Avanzado), not directly
in Movimientos: each message becomes a proposed entry you accept or reject there. This is different from
the in-app *Captura rápida*, which writes an editable movement on a chosen account with no Inbox step
(see [quick-capture.md](quick-capture.md)).

If you also want to text `250 tacos comida` at the bot and have it land in the workspace's Inbox, point
Telegram's webhook at Aurum's API (this needs the API reachable from the internet, e.g. behind the same
reverse proxy that serves the rest of Aurum):

```
curl -X POST "https://api.telegram.org/bot<token>/setWebhook" \
     -d "url=https://your-aurum-host/api/insights/telegram/webhook" \
     -d "secret_token=<a random string, matches AURUM_TELEGRAM_SECRET>"
```

Set `AURUM_TELEGRAM_SECRET` to the same random string on the Aurum side so the webhook rejects calls
that don't carry Telegram's `X-Telegram-Bot-Api-Secret-Token` header. Every `chat_id` that should be
allowed to quick-add needs an entry in `AURUM_TELEGRAM_WS_MAP`; an unmapped chat gets a bilingual
"not linked" reply and nothing is written. Photos are acknowledged but not OCR'd here — use
**+ Agregar › Gasto › "Leer foto del recibo (atajo)"** in the app instead.
