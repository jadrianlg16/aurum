"""Push the Aurum digest + urgent insights for one workspace to Telegram.

Meant to be run from cron or any other scheduler:

    uv run python scripts/telegram_nudges.py --ws demo-mx --send

Reads ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` from the environment; nothing is hard-coded.
Without ``--send`` it prints what *would* be sent and exits 0 (a dry run needs neither variable). With
``--send``, a missing variable or a failed delivery prints a clear error line to stderr and exits 1 --
it never fails silently or swallows the exception. Runs in-process (imports ``aurum`` directly), so the
scheduler does not need the API running.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ws", required=True, help="workspace id, e.g. demo-mx")
    parser.add_argument("--period", default=None, help="YYYY-MM; defaults to the current month")
    parser.add_argument("--lang", default=None, help="es|en; defaults to the workspace language")
    parser.add_argument("--send", action="store_true", help="actually POST to the Telegram Bot API")
    parser.add_argument("--urgent-only", action="store_true", help="send urgent insights as separate lines, skip the digest paragraph")
    parser.add_argument("--no-llm", action="store_true", help="skip the LLM paragraph rewrite; send the deterministic bullet list as-is")
    args = parser.parse_args(argv)

    from aurum.core.i18n import ws_lang
    from aurum.core.workspaces import WorkspaceNotFound, get_workspace
    from aurum.insights.digest import digest_text
    from aurum.insights.engine import build_insights
    from aurum.insights.telegram import send_message

    try:
        get_workspace(args.ws)
    except WorkspaceNotFound:
        print(f"error: workspace {args.ws!r} does not exist", file=sys.stderr)
        return 2

    period = args.period or date.today().strftime("%Y-%m")
    lang = args.lang or ws_lang(args.ws, args.lang)
    insights = build_insights(args.ws, period, lang)
    urgent = [i for i in insights if i.severity == "urgent"]

    if args.urgent_only:
        lines = [f"!! {i.title}: {i.body}" for i in urgent] or ["No urgent insights."]
        text = "\n".join(lines)
    else:
        text = digest_text(args.ws, period, insights, lang, use_llm=not args.no_llm)

    print("--- message ---")
    print(text)
    print("--- end ---")
    print(f"{len(insights)} insight(s), {len(urgent)} urgent, workspace={args.ws}, period={period}")

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not args.send:
        print("(dry run: pass --send to actually deliver this)")
        return 0
    if not token or not chat_id:
        print("error: --send given but TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID is not set", file=sys.stderr)
        return 1
    try:
        send_message(chat_id, text, token=token)
    except Exception as e:  # noqa: BLE001 -- report loudly, never swallow a delivery failure
        print(f"error: failed to send to Telegram: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print("sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
