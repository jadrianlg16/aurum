"""Telegram webhook + quick-add mapping. Never calls the real Telegram API (tests stay offline)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.workspaces import Workspace, save_workspace
from aurum.insights import telegram as telegram_mod


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    save_workspace(Workspace(id="tg-ws", name="Telegram test", jurisdictions=["MX"], language="es"))
    return "tg-ws"


def test_chat_ws_map_parses_pairs(monkeypatch):
    monkeypatch.setenv("AURUM_TELEGRAM_WS_MAP", "111:demo-mx, 222:acme-biz")
    assert telegram_mod.chat_ws_map() == {"111": "demo-mx", "222": "acme-biz"}


def test_unknown_chat_gets_bilingual_reply(monkeypatch, ws):
    monkeypatch.delenv("AURUM_TELEGRAM_WS_MAP", raising=False)
    result = telegram_mod.handle_update({"message": {"chat": {"id": 999}, "text": "250 tacos comida"}})
    assert result["created"] is False
    assert result["ws_id"] is None
    assert result["reply"]


def test_text_message_creates_inbox_item(monkeypatch, ws):
    monkeypatch.setenv("AURUM_TELEGRAM_WS_MAP", f"555:{ws}")
    result = telegram_mod.handle_update({"message": {"chat": {"id": 555}, "text": "250 tacos comida"}})
    assert result["created"] is True
    assert result["ws_id"] == ws
    assert "inbox_id" in result

    from aurum.ingest.inbox import list_inbox

    items = list_inbox(ws, status="pending")
    assert any(i.id == result["inbox_id"] for i in items)


def test_photo_message_is_acknowledged_without_ocr(monkeypatch, ws):
    monkeypatch.setenv("AURUM_TELEGRAM_WS_MAP", f"555:{ws}")
    result = telegram_mod.handle_update({"message": {"chat": {"id": 555}, "photo": [{"file_id": "abc"}]}})
    assert result["created"] is False
    assert result["ws_id"] == ws
    assert result["reply"]


def test_garbage_text_never_raises(monkeypatch, ws):
    monkeypatch.setenv("AURUM_TELEGRAM_WS_MAP", f"555:{ws}")
    result = telegram_mod.handle_update({"message": {"chat": {"id": 555}, "text": "not a number at all"}})
    assert result["created"] is False
    assert result["reply"]


def test_check_secret_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AURUM_TELEGRAM_SECRET", raising=False)
    assert telegram_mod.check_secret(None) is True
    assert telegram_mod.check_secret("anything") is True


def test_check_secret_enforced_when_set(monkeypatch):
    monkeypatch.setenv("AURUM_TELEGRAM_SECRET", "s3cret")
    assert telegram_mod.check_secret("s3cret") is True
    assert telegram_mod.check_secret("wrong") is False
    assert telegram_mod.check_secret(None) is False


def test_webhook_route_rejects_bad_secret(monkeypatch, ws):
    monkeypatch.setenv("AURUM_TELEGRAM_SECRET", "s3cret")
    monkeypatch.setenv("AURUM_TELEGRAM_WS_MAP", f"555:{ws}")
    client = TestClient(create_app())
    r = client.post(
        "/api/insights/telegram/webhook",
        json={"message": {"chat": {"id": 555}, "text": "100 super"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert r.status_code == 401


def test_webhook_route_ok_without_send(monkeypatch, ws):
    """No TELEGRAM_BOT_TOKEN set -> send_message would fail, but the webhook must still ack Telegram."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("AURUM_TELEGRAM_SECRET", raising=False)
    monkeypatch.setenv("AURUM_TELEGRAM_WS_MAP", f"555:{ws}")
    client = TestClient(create_app())
    r = client.post(
        "/api/insights/telegram/webhook",
        json={"message": {"chat": {"id": 555}, "text": "100 super"}},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["created"] is True
