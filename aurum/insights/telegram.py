"""Telegram integration: :mod:`scripts.telegram_nudges` (run from cron or any scheduler) sends nudges;
this module is the webhook side -- a Telegram update turns into a quick-add Inbox item.

Chat -> workspace mapping is a flat env var, never a database write: ``AURUM_TELEGRAM_WS_MAP``,
e.g. ``"123456:demo-mx,789:acme-biz"``. A chat not in the map gets a bilingual "not linked" reply and
nothing is written. An optional shared secret (``AURUM_TELEGRAM_SECRET``) is checked against the
``X-Telegram-Bot-Api-Secret-Token`` header when set, per Telegram's own webhook security recommendation.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..core.config import env
from ..core.i18n import ws_lang
from ..core.workspaces import WorkspaceNotFound, get_workspace
from ..ingest.inbox import create_inbox_item
from ..ingest.quickadd import parse_quickadd
from .i18n import t

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def chat_ws_map() -> dict[str, str]:
    raw = env("AURUM_TELEGRAM_WS_MAP")
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        chat_id, ws_id = pair.split(":", 1)
        out[chat_id.strip()] = ws_id.strip()
    return out


def resolve_workspace(chat_id: str) -> str | None:
    return chat_ws_map().get(str(chat_id))


def lang_for(ws_id: str | None) -> str:
    if not ws_id:
        return "es"
    try:
        return ws_lang(ws_id)
    except WorkspaceNotFound:
        return "es"


def handle_update(update: dict[str, Any]) -> dict[str, Any]:
    """Process one Telegram Update JSON. Returns ``{"reply": str, "chat_id": str|None, ...}``.

    Text messages become a quick-add Inbox item for the mapped workspace. Photos are acknowledged --
    OCR is not wired here (receipt OCR lives in ``aurum.ingest.receipts``). Never raises: any parsing
    failure becomes a bilingual reply, not a 500.
    """
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id")) if chat.get("id") is not None else None
    ws_id = resolve_workspace(chat_id) if chat_id else None
    lang = lang_for(ws_id)

    if ws_id is None:
        return {"chat_id": chat_id, "reply": t("insights.telegram.unknown_chat", lang), "ws_id": None, "created": False}

    if message.get("photo"):
        return {"chat_id": chat_id, "reply": t("insights.telegram.photo_ack", lang), "ws_id": ws_id, "created": False}

    text = (message.get("text") or message.get("caption") or "").strip()
    if not text:
        return {"chat_id": chat_id, "reply": t("insights.telegram.unknown_chat", lang), "ws_id": ws_id, "created": False}

    try:
        ws = get_workspace(ws_id)
        result = parse_quickadd(text, ws_id, base_currency=ws.base_currency)
        item = create_inbox_item(ws_id, "quickadd", result.transaction, confidence=result.confidence, source_ref=f"telegram:{chat_id}")
        return {
            "chat_id": chat_id,
            "reply": t("insights.telegram.quickadd_ok", lang, text=text),
            "ws_id": ws_id,
            "created": True,
            "inbox_id": item.id,
        }
    except Exception as e:  # noqa: BLE001 -- any parse failure becomes a friendly reply, never a 500
        return {
            "chat_id": chat_id,
            "reply": t("insights.telegram.quickadd_error", lang, error=str(e)),
            "ws_id": ws_id,
            "created": False,
        }


def check_secret(header_value: str | None) -> bool:
    """True when the webhook call is allowed: no secret configured, or the header matches it."""
    secret = env("AURUM_TELEGRAM_SECRET")
    if not secret:
        return True
    return header_value == secret


def send_message(chat_id: str, text: str, token: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
    """POST to the Telegram Bot API. Raises on transport/HTTP errors -- callers decide how to report."""
    token = token or env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")
    url = TELEGRAM_API.format(token=token)
    resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
