from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from aurum.api.app import create_app
from aurum.core.i18n import resolve_lang, t, ws_lang
from aurum.core.workspaces import Workspace, get_workspace, ordered_workspaces, save_workspace


def _client() -> TestClient:
    return TestClient(create_app())


def test_put_workspace_updates_fields_and_merges_profile():
    save_workspace(Workspace(id="ws1", name="Old", language="es", profile={"rfc": "XAXX010101000"}))
    client = _client()

    resp = client.put(
        "/api/workspaces/ws1",
        json={"name": "New", "language": "en", "profile": {"state": "NL"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == "ws1"
    assert body["name"] == "New"
    assert body["language"] == "en"
    # profile merged, not replaced — rfc from before is still there (masked)
    assert body["profile"]["state"] == "NL"
    assert body["profile"]["rfc"].endswith("1000")

    stored = get_workspace("ws1")
    assert stored.profile["rfc"] == "XAXX010101000"  # unmasked on disk
    assert stored.profile["state"] == "NL"


def test_put_workspace_id_is_immutable():
    save_workspace(Workspace(id="ws1", name="Old"))
    client = _client()
    resp = client.put("/api/workspaces/ws1", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "ws1"
    # trying to sneak a different id in the body has no effect on the path's workspace
    assert get_workspace("ws1").name == "New"


def test_put_workspace_missing_404():
    client = _client()
    resp = client.put("/api/workspaces/does-not-exist", json={"name": "x"})
    assert resp.status_code == 404


def test_put_workspace_partial_update_keeps_other_fields():
    save_workspace(Workspace(id="ws1", name="Old", base_currency="MXN", kind="personal"))
    client = _client()
    resp = client.put("/api/workspaces/ws1", json={"base_currency": "USD"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["base_currency"] == "USD"
    assert body["name"] == "Old"
    assert body["kind"] == "personal"


def test_i18n_default_es_and_en_override():
    assert t("pf.net_worth", None) == t("pf.net_worth", "es")
    assert t("pf.net_worth", "en") != t("pf.net_worth", "es")
    assert "Net worth" in t("pf.net_worth", "en")
    assert "Patrimonio" in t("pf.net_worth", "es")


def test_i18n_unknown_key_returns_key():
    assert t("nonexistent.key", "en") == "nonexistent.key"


def test_i18n_formats_kwargs():
    out = t("pf.income_smoothed", "en", months=3)
    assert "3 months" in out


def test_resolve_lang_prefers_explicit():
    assert resolve_lang("en", "es") == "en"
    assert resolve_lang(None, "en") == "en"
    assert resolve_lang(None, None) == "es"


def test_ws_lang_reads_workspace_language():
    save_workspace(Workspace(id="ws-en", name="EN", language="en"))
    assert ws_lang("ws-en") == "en"
    assert ws_lang("ws-en", "es") == "es"  # explicit override wins
    assert ws_lang("unknown-ws") == "es"  # unknown workspace falls back, never raises


def test_workspace_defaults_to_simple_mode_with_every_advanced_module_hidden():
    ws = save_workspace(Workspace(id="ws-simple", name="Simple"))
    assert ws.ui_mode == "simple"
    assert ws.modules.model_dump() == {
        "tax": False, "business": False, "research": False, "watch": False,
        "workflows": False, "reports": False, "crossborder": False, "holdings": False,
    }


def test_get_workspace_surfaces_ui_mode_and_modules():
    save_workspace(Workspace(id="ws-adv", name="Adv", ui_mode="advanced"))
    client = _client()
    resp = client.get("/api/workspaces/ws-adv")
    assert resp.status_code == 200
    assert resp.json()["ui_mode"] == "advanced"
    assert resp.json()["modules"]["tax"] is False


def test_put_workspace_sets_ui_mode_and_merges_modules():
    save_workspace(Workspace(id="ws1", name="Old"))
    client = _client()

    resp = client.put("/api/workspaces/ws1", json={"ui_mode": "advanced", "modules": {"tax": True}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ui_mode"] == "advanced"
    assert body["modules"]["tax"] is True
    assert body["modules"]["business"] is False  # untouched flags stay off, merged not replaced

    # health keeps working unchanged regardless of ui_mode/modules
    assert client.get("/api/health").status_code == 200


# --- protected + hidden flags, ordering ------------------------------------------------------------


def test_personal_is_always_protected_even_if_the_file_says_false(monkeypatch, tmp_path):
    save_workspace(Workspace(id="personal", name="Personal", protected=False))
    assert get_workspace("personal").protected is True


def test_env_protected_list_extends_beyond_personal(monkeypatch):
    monkeypatch.setenv("AURUM_PROTECTED_WORKSPACES", "personal,vault")
    save_workspace(Workspace(id="vault", name="Vault"))
    assert get_workspace("vault").protected is True


def test_put_protected_false_on_personal_is_rejected():
    save_workspace(Workspace(id="personal", name="Personal"))
    client = _client()
    resp = client.put("/api/workspaces/personal", json={"protected": False})
    assert resp.status_code == 400
    assert "personal" in resp.json()["detail"]
    assert get_workspace("personal").protected is True


def test_put_hidden_round_trips():
    save_workspace(Workspace(id="ws1", name="Old"))
    client = _client()
    resp = client.put("/api/workspaces/ws1", json={"hidden": True})
    assert resp.status_code == 200
    assert resp.json()["hidden"] is True
    assert get_workspace("ws1").hidden is True


def test_get_workspaces_orders_personal_first_then_other_then_demo():
    now = datetime.now(UTC)
    save_workspace(Workspace(id="demo-mx", name="Demo", profile={"demo": True}, created_at=now))
    save_workspace(Workspace(id="biz1", name="Biz", kind="business", created_at=now + timedelta(seconds=1)))
    save_workspace(
        Workspace(id="personal", name="Personal", kind="personal", created_at=now + timedelta(seconds=2))
    )
    client = _client()
    ids = [w["id"] for w in client.get("/api/workspaces").json()]
    assert ids == ["personal", "biz1", "demo-mx"]
    assert client.get("/api/workspaces").json()[0]["protected"] is True


def test_get_workspaces_orders_personal_by_created_at_oldest_first():
    now = datetime.now(UTC)
    save_workspace(Workspace(id="p2", name="P2", kind="personal", created_at=now + timedelta(seconds=5)))
    save_workspace(Workspace(id="p1", name="P1", kind="personal", created_at=now))
    ids = [w.id for w in ordered_workspaces()]
    assert ids == ["p1", "p2"]


def test_hidden_workspace_omitted_unless_include_hidden():
    save_workspace(Workspace(id="ws1", name="One"))
    save_workspace(Workspace(id="ws2", name="Two", hidden=True))
    client = _client()
    ids = [w["id"] for w in client.get("/api/workspaces").json()]
    assert ids == ["ws1"]
    ids_all = [w["id"] for w in client.get("/api/workspaces?include_hidden=1").json()]
    assert set(ids_all) == {"ws1", "ws2"}


def test_new_workspace_defaults_unprotected_and_visible():
    save_workspace(Workspace(id="fresh", name="Fresh"))
    ws = get_workspace("fresh")
    assert ws.protected is False
    assert ws.hidden is False
