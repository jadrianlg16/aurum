"""scripts/verify_demo.py --level 7: helper behaviour and the fake-client behaviour of the numbered
acceptance items that do not need a live API (the items are listed in the script's module docstring)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_demo.py"
SPEC = importlib.util.spec_from_file_location("verify_demo_acceptance", SCRIPT)
vd = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["verify_demo_acceptance"] = vd
SPEC.loader.exec_module(vd)


class FakeResponse:
    def __init__(self, status_code: int = 200, body: object = None, headers: dict | None = None, content: bytes | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        if content is not None:
            self.content, self._body = content, body
        else:
            self._body = {} if body is None else body
            self.content = json.dumps(self._body).encode("utf-8")
        self.text = self.content.decode("utf-8", errors="replace")

    def json(self) -> object:
        return json.loads(self.content) if self._body is None else self._body


class FakeClient:
    """Routes ``METHOD path`` to a canned response; records every call. Unknown routes → 404."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[tuple[str, str, dict]] = []

    def _dispatch(self, method: str, path: str, **kw) -> FakeResponse:
        self.calls.append((method, path, kw))
        hit = self.routes.get(f"{method} {path}")
        if callable(hit):
            hit = hit(kw)
        if hit is None:
            return FakeResponse(404, {"detail": "not found"})
        return hit if isinstance(hit, FakeResponse) else FakeResponse(200, hit)

    def get(self, path, **kw):
        return self._dispatch("GET", path, **kw)

    def post(self, path, **kw):
        return self._dispatch("POST", path, **kw)

    def put(self, path, **kw):
        return self._dispatch("PUT", path, **kw)

    def delete(self, path, **kw):
        return self._dispatch("DELETE", path, **kw)


@pytest.fixture(autouse=True)
def _reset_results():
    vd.FAILS.clear()
    vd.RESULTS.clear()
    yield
    vd.FAILS.clear()
    vd.RESULTS.clear()


def _names() -> list[str]:
    return [str(r["name"]) for r in vd.RESULTS]


# --------------------------------------------------------------------------- naming convention


def test_every_acceptance_check_name_ends_with_its_item_number():
    src = SCRIPT.read_text(encoding="utf-8")
    names = re.findall(r'(?:check|skip)\(\s*"(acceptance:[^"]*)"', src)
    assert len(names) > 90, "the acceptance list should be large"
    bad = [n for n in names if not re.search(r"\(#\d+\)$", n)]
    assert bad == []
    covered = {int(m) for n in names for m in re.findall(r"\(#(\d+)\)$", n)}
    assert {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26} <= covered


# --------------------------------------------------------------------------- small helpers


def test_skip_is_neither_pass_nor_fail(capsys):
    vd.skip("acceptance: something (#23)", "no stack")
    assert vd.FAILS == []
    assert vd.RESULTS == [{"name": "acceptance: something (#23)", "ok": None, "detail": "no stack"}]
    assert "[SKIP] acceptance: something (#23) - no stack" in capsys.readouterr().out


def test_web_origin_strips_the_api_suffix_only():
    assert vd.web_origin("http://localhost:5024/api") == "http://localhost:5024"
    assert vd.web_origin("http://127.0.0.1:5156/api/") == "http://127.0.0.1:5156"
    assert vd.web_origin("http://host:9/other") == "http://host:9/other"


def test_amt_and_ledger_amount():
    assert vd._amt({"amount": "12.50", "currency": "MXN"}) == Decimal("12.50")
    assert vd._amt(None) == Decimal("0")
    assert vd._amt({"amount": "abc"}) == Decimal("0")
    balances = {"Assets:Cash": [{"amount": "1200.00", "currency": "MXN"}, {"amount": "5.00", "currency": "USD"}]}
    assert vd._ledger_amount(balances, "Assets:Cash") == Decimal("1200.00")
    assert vd._ledger_amount(balances, "Assets:Cash", "USD") == Decimal("5.00")
    assert vd._ledger_amount(balances, "Assets:Nope") == Decimal("0")


def test_balance_diff_names_what_moved_and_is_empty_only_when_identical():
    """Item #25 compares the raw balances maps; balance_diff only explains a difference (#25)."""
    before = {"Assets:Cash": [{"amount": "1200.00", "currency": "MXN"}], "Expenses:Personal:Entertainment": [{"amount": "4749.00", "currency": "MXN"}]}
    assert vd.balance_diff(before, dict(before)) == {}
    # an account the quickadd auto-opened and the void reversal left at 0.00 is still a difference — named as such
    opened = dict(before, **{"Expenses:Food:DiningOut": [{"amount": "0.00", "currency": "MXN"}]})
    assert vd.balance_diff(before, opened) == {"Expenses:Food:DiningOut": "opened at 0.00"}
    moved = dict(before, **{"Assets:Cash": [{"amount": "950.00", "currency": "MXN"}]})
    assert vd.balance_diff(before, moved) == {"Assets:Cash": "1200.00 MXN -> 950.00 MXN"}
    assert vd.balance_diff(before, {"Assets:Cash": before["Assets:Cash"]}) == {"Expenses:Personal:Entertainment": "removed"}
    # a new account with a real amount is a change, not an "opened at 0.00"
    assert vd.balance_diff(before, dict(before, X=[{"amount": "1.00", "currency": "MXN"}])) == {"X": "absent -> 1.00 MXN"}
    # unparseable amounts never read as zero
    assert vd.balance_diff(before, dict(before, X=[{"amount": "abc", "currency": "MXN"}])) == {"X": "absent -> abc MXN"}
    assert vd.balance_diff(None, {}) == {}
    assert vd.balance_diff({}, {"X": "not-a-list"}) == {"X": "absent -> not-a-list"}


def _core_quickadd_fake(expense_account: str, seeded: bool) -> FakeClient:
    """main()'s level-1 quickadd block against a demo-mx shaped API. ``seeded`` = the label's expense
    account already carries a balance (the seed posts to it), so the reversal restores the raw map;
    otherwise the quickadd auto-opens it and the void leaves a 0.00 row behind."""
    state = {"committed": False, "voided": False}
    base = {"Assets:Cash": [{"amount": "1200.00", "currency": "MXN"}]}
    if seeded:
        base[expense_account] = [{"amount": "4749.00", "currency": "MXN"}]

    def balances(_kw):
        if state["committed"] and not state["voided"]:
            return {"Assets:Cash": [{"amount": "950.00", "currency": "MXN"}], expense_account: [{"amount": "4999.00" if seeded else "250.00", "currency": "MXN"}]}
        if state["voided"]:
            return dict(base) if seeded else dict(base, **{expense_account: [{"amount": "0.00", "currency": "MXN"}]})
        return dict(base)

    def quickadd(kw):
        if kw.get("json", {}).get("commit"):
            state["committed"] = True
            return {"status": "committed", "id": "ent-1", "proposed": {"postings": [{"account": expense_account}, {"account": "Assets:Cash"}]}}
        return {"status": "preview", "id": None}

    def void(_kw):
        state["voided"] = True
        return {"id": "ent-1", "voided": True}

    return FakeClient({
        "GET /ledger/demo-mx/balances": balances,
        "GET /pf/demo-mx/accounts": [{"id": "acc-cash", "type": "cash"}],
        "GET /ingest/demo-mx/inbox": [],
        "POST /ingest/demo-mx/quickadd": quickadd,
        "DELETE /pf/demo-mx/entries/ent-1": void,
    })


def _run_core_quickadd_block(c: FakeClient, text: str) -> None:
    # the same statements main() runs for the level-1 quickadd, isolated from the rest of the script
    before = c.get("/ledger/demo-mx/balances").json()
    acct_id = [x["id"] for x in c.get("/pf/demo-mx/accounts").json()][0]
    r = c.post("/ingest/demo-mx/quickadd", json={"text": text, "account_id": acct_id, "commit": True})
    item = r.json()
    after = c.get("/ledger/demo-mx/balances").json()
    acct = item["proposed"]["postings"][0]["account"]
    assert vd._ledger_amount(after, acct) - vd._ledger_amount(before, acct) == Decimal("250")
    r = c.delete(f"/pf/demo-mx/entries/{item['id']}")
    diff = vd.balance_diff(before, c.get("/ledger/demo-mx/balances").json())
    vd.check("acceptance: level-1 quickadd on demo-mx voided (#25)", r.status_code == 200 and r.json().get("voided") is True and not diff, f"restored={not diff}" + (f" diff={diff}" if diff else ""))


def test_core_quickadd_void_restores_the_raw_map_on_a_seeded_account():
    """'250 cinepolis cine' → Expenses:Personal:Entertainment, which the demo-mx seed already posts to:
    +250 then the reversal returns the raw balances map byte-for-byte (#25 'identical')."""
    _run_core_quickadd_block(_core_quickadd_fake("Expenses:Personal:Entertainment", seeded=True), "250 cinepolis cine")
    assert vd.FAILS == []
    assert vd.RESULTS[-1]["ok"] is True


def test_core_quickadd_void_fails_honestly_when_the_account_stays_open_at_zero():
    """The old text ('250 tacos comida') auto-opens Expenses:Food:DiningOut on a fresh stack; the void
    leaves a 0.00 row, which is not 'identical' — the check FAILS and names the opened account."""
    _run_core_quickadd_block(_core_quickadd_fake("Expenses:Food:DiningOut", seeded=False), "250 tacos comida")
    assert vd.FAILS == ["acceptance: level-1 quickadd on demo-mx voided (#25)"]
    assert "diff={'Expenses:Food:DiningOut': 'opened at 0.00'}" in str(vd.RESULTS[-1]["detail"])


def test_main_core_quickadd_text_targets_a_seeded_expense_account():
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'quickadd_text = "250 cinepolis cine"' in src
    # the throwaway-workspace item #19 keeps its own text
    assert src.count('"250 tacos comida"') == 2


def test_parse_args_new_flags(monkeypatch):
    monkeypatch.delenv("AURUM_MCP_URL", raising=False)
    a = vd.parse_args(["--level", "7", "--web", "http://localhost:5024", "--mcp", "http://127.0.0.1:5042/mcp"])
    assert (a.web, a.mcp, a.e2e) == ("http://localhost:5024", "http://127.0.0.1:5042/mcp", False)
    monkeypatch.setenv("AURUM_MCP_URL", "http://x/mcp")
    assert vd.parse_args([]).mcp == "http://x/mcp"


# --------------------------------------------------------------------------- docker posture (#23)


def test_compose_services_up_reads_both_json_layouts():
    lines = '{"Service":"api","State":"running"}\n{"Service":"web-ui","State":"running"}\n{"Service":"x","State":"exited"}'
    assert vd.compose_services_up(lines) == {"api", "web-ui"}
    as_list = json.dumps([{"Service": "api", "State": "running"}, {"Service": "web-ui", "State": "restarting"}])
    assert vd.compose_services_up(as_list) == {"api"}
    assert vd.compose_services_up("") == set()
    assert vd.compose_services_up("not json at all") == set()


def test_cap_eff_is_empty():
    assert vd.cap_eff_is_empty("Name:\tpython\nCapEff:\t0000000000000000\n") is True
    assert vd.cap_eff_is_empty("CapEff:\t000001ffffffffff\n") is False
    assert vd.cap_eff_is_empty("no such line") is False


def test_docker_stack_up_false_without_docker(monkeypatch):
    monkeypatch.setattr(vd.shutil, "which", lambda _name: None)
    assert vd.docker_stack_up(Path(".")) is False


def test_docker_stack_up_uses_the_runner(monkeypatch):
    monkeypatch.setattr(vd.shutil, "which", lambda _name: "/usr/bin/docker")
    up = '{"Service":"api","State":"running"}\n{"Service":"web-ui","State":"running"}'
    assert vd.docker_stack_up(Path("."), run=lambda args, cwd=None: (0, up)) is True
    assert vd.docker_stack_up(Path("."), run=lambda args, cwd=None: (1, "")) is False
    assert vd.docker_stack_up(Path("."), run=lambda args, cwd=None: (0, '{"Service":"api","State":"running"}')) is False


def test_docker_posture_skips_when_the_stack_is_down():
    st = vd._AcceptanceState(ws="verify-x", today=date(2026, 9, 19), period="2026-09", prev_period="2026-08", past=date(2026, 4, 10))
    a = argparse.Namespace(api="http://127.0.0.1:5156/api", web=None)
    vd._item_docker_posture(a, st, Path("."), run=lambda *_a, **_k: (0, ""))
    assert vd.FAILS == []
    assert _names() == ["acceptance: docker posture (#23)"]
    assert vd.RESULTS[0]["ok"] is None


def test_proc_uid_reads_pid_1_not_exec():
    """Dockerfile.api has no USER line (the entrypoint drops privileges), so `exec id -u` says 0 while
    PID 1 runs as 10001: the uid check reads /proc/1/status (#23)."""
    assert vd.proc_uid("Name:\tpython\nUid:\t10001\t10001\t10001\t10001\nGid:\t10001\n") == 10001
    assert vd.proc_uid("Uid:\t0\t0\t0\t0\n") == 0
    assert vd.proc_uid("no such line") is None
    assert vd.proc_uid("Uid:\tabc\n") is None


def test_expected_published_ports_come_from_env_with_the_compose_defaults():
    assert vd.expected_published_ports({}) == ("127.0.0.1:5024", "127.0.0.1:5042")
    assert vd.expected_published_ports({"AURUM_PORT": "5156", "AURUM_MCP_HOST_PORT": "5142"}) == ("127.0.0.1:5156", "127.0.0.1:5142")
    # the host is the posture under test, never taken from AURUM_BIND
    assert vd.expected_published_ports({"AURUM_BIND": "0.0.0.0"}) == ("127.0.0.1:5024", "127.0.0.1:5042")


def test_compose_mcp_url_reads_the_published_port():
    assert vd.compose_mcp_url(Path("."), run=lambda args, cwd=None: (0, "127.0.0.1:5042\n")) == "http://127.0.0.1:5042/mcp"
    assert vd.compose_mcp_url(Path("."), run=lambda args, cwd=None: (0, "127.0.0.1:5142\n")) == "http://127.0.0.1:5142/mcp"
    assert vd.compose_mcp_url(Path("."), run=lambda args, cwd=None: (1, "")) == ""
    assert vd.compose_mcp_url(Path("."), run=lambda args, cwd=None: (0, "no port")) == ""


class _Http:
    """Canned httpx.get replacement for the front-door part of #23."""

    def __init__(self, plan: FakeResponse):
        self.plan = plan

    def __call__(self, url: str, **_kw) -> FakeResponse:
        if url.endswith("/plan"):
            return self.plan
        if url.endswith("/nope/"):
            return FakeResponse(404, {}, headers={"content-type": "text/html"})
        return FakeResponse(200, {}, headers={"content-type": "application/manifest+json"})


def _compose_stack(uid: str = "10001", web_port: str = "127.0.0.1:5024", mcp_port: str = "127.0.0.1:5042"):
    def run(args, cwd=None):
        if args[:4] == ["docker", "compose", "port", "web-ui"]:
            return 0, f"{web_port}\n"
        if args[:4] == ["docker", "compose", "port", "api"]:
            return 0, f"{mcp_port}\n"
        if args[-1] == "/proc/1/status":
            return 0, f"Name:\tpython\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\nCapEff:\t0000000000000000\n"
        if args[:3] == ["docker", "compose", "config"]:
            return 0, 'logging:\n  driver: json-file\n  options:\n    max-file: "3"\n    max-size: 10m\n'
        return 1, ""
    return run


@pytest.mark.parametrize("plan", [
    FakeResponse(200, {}, headers={"content-type": "text/html; charset=utf-8"}),
    FakeResponse(301, {}, headers={"location": "/plan/"}),
    FakeResponse(301, {}, headers={"location": "http://127.0.0.1:5024/plan/"}),
])
def test_docker_posture_accepts_the_live_stack_shape(monkeypatch, plan):
    """The compose stack serves /plan directly (try_files $uri/index.html) and PID 1 is uid 10001 while
    `exec id -u` would print 0; both shapes pass and a relative 301 is also fine (#23)."""
    monkeypatch.delenv("AURUM_PORT", raising=False)
    monkeypatch.delenv("AURUM_MCP_HOST_PORT", raising=False)
    monkeypatch.setattr(vd.httpx, "get", _Http(plan))
    st = vd._AcceptanceState(ws="verify-x", today=date(2026, 9, 19), period="2026-09", prev_period="2026-08", past=date(2026, 4, 10), docker_up=True)
    vd._item_docker_posture(argparse.Namespace(api="http://127.0.0.1:5024/api", web=None), st, Path("."), run=_compose_stack())
    assert vd.FAILS == []
    assert len(_names()) == 7 and all(n.endswith("(#23)") for n in _names())


def test_docker_posture_fails_on_root_pid1_container_port_redirect_and_foreign_ports(monkeypatch):
    monkeypatch.setenv("AURUM_PORT", "5156")
    monkeypatch.delenv("AURUM_MCP_HOST_PORT", raising=False)
    monkeypatch.setattr(vd.httpx, "get", _Http(FakeResponse(301, {}, headers={"location": "http://localhost:8080/plan/"})))
    st = vd._AcceptanceState(ws="verify-x", today=date(2026, 9, 19), period="2026-09", prev_period="2026-08", past=date(2026, 4, 10), docker_up=True)
    vd._item_docker_posture(argparse.Namespace(api="http://127.0.0.1:5156/api", web=None), st, Path("."), run=_compose_stack(uid="0", web_port="0.0.0.0:5024"))
    assert [n for n in vd.FAILS] == [
        "acceptance: docker port shows loopback web-ui and mcp bindings (AURUM_PORT/AURUM_MCP_HOST_PORT, default 127.0.0.1:5024 / :5042) (#23)",
        "acceptance: api container PID 1 runs as uid != 0 (/proc/1/status; exec id -u would say 0, no USER line) (#23)",
        "acceptance: slash-less /plan -> 200 served directly, or 301 to relative /plan/ (never :8080) (#23)",
    ]
    assert "want 127.0.0.1:5156" in str(vd.RESULTS[0]["detail"])


# --------------------------------------------------------------------------- items with a fake client


def _state() -> vd._AcceptanceState:
    return vd._AcceptanceState(ws="verify-x", today=date(2026, 9, 19), period="2026-09", prev_period="2026-08", past=date(2026, 4, 10),
                  checking="acct-c", checking_name="Cuenta", checking_ledger="Assets:Bank:Cuenta", cash="acct-e", cash_name="Efectivo",
                  card="acct-t", card_ledger="Liabilities:CreditCard:Tarjeta")


def test_health_item_21_passes_on_the_expected_shape():
    c = FakeClient({"GET /health": {"ok": True, "auth": {"required": False, "source": "none"}, "bind": "127.0.0.1", "schema": {"pf": 4, "organizer": 2}}})
    vd._item_health(c)
    assert vd.FAILS == []
    assert all(n.startswith("acceptance:") and n.endswith("(#21)") for n in _names())


def test_health_item_21_fails_on_data_dir_and_auth_drift():
    c = FakeClient({"GET /health": {"ok": True, "data_dir": "/data", "auth": {"required": True, "source": "env"}, "bind": "0.0.0.0", "schema": {"pf": 4}}})
    vd._item_health(c)
    assert vd.FAILS == ["acceptance: health has no data_dir (#21)", "acceptance: health auth {required false, source none}, bind 127.0.0.1 (#21)", "acceptance: health.schema includes pf and organizer versions (#21)"]


def test_security_smoke_item_22_reads_the_middleware_bodies_and_skips_mcp():
    def workspaces(kw):
        headers = kw.get("headers", {})
        if headers.get("Host") == "attacker.example":
            return FakeResponse(403, {"error": "host_not_allowed"})
        return FakeResponse(200, [{"id": "demo-mx"}])

    def labels(kw):
        if kw.get("headers", {}).get("Origin"):
            return FakeResponse(403, {"error": "origin_not_allowed"})
        return FakeResponse(200, {"id": "lbl-1"})

    c = FakeClient({
        "GET /workspaces": workspaces,
        "POST /pf/verify-x/labels": labels,
        "GET /pf/A_B/accounts": FakeResponse(400, {"error": "invalid_workspace_id"}),
        "GET /pf/..%2F..%2Fx/accounts": FakeResponse(400, {"error": "bad_path"}),
        "GET /health": {"ok": True},
    })
    a = argparse.Namespace(mcp="")
    st = _state()
    vd._item_security_smoke(c, a, st)
    assert vd.FAILS == []
    assert _names()[-1] == "acceptance: MCP initialize -> 200 (#22)"
    assert vd.RESULTS[-1]["ok"] is None
    assert all(n.startswith("acceptance:") and n.endswith("(#22)") for n in _names())
    assert ("POST", "/pf/verify-x/labels", {"headers": {"Origin": "https://evil.example"}, "json": {"name": "x", "kind": "expense"}}) in c.calls


def test_security_smoke_item_22_fails_when_cors_leaks():
    c = FakeClient({
        "GET /workspaces": FakeResponse(200, [], headers={"access-control-allow-origin": "*"}),
        "POST /pf/verify-x/labels": FakeResponse(200, {"id": "lbl-1"}),
        "GET /pf/A_B/accounts": FakeResponse(200, {}),
        "GET /pf/..%2F..%2Fx/accounts": FakeResponse(200, {}),
        "GET /health": {"ok": True},
    })
    vd._item_security_smoke(c, argparse.Namespace(mcp=""), _state())
    assert "acceptance: GET with Origin evil prints no access-control-allow-origin (#22)" in vd.FAILS
    assert "acceptance: POST with Origin evil -> 403 origin_not_allowed (#22)" in vd.FAILS
    assert "acceptance: Host attacker.example -> 403 host_not_allowed (#22)" in vd.FAILS
    assert "acceptance: /pf/A_B/accounts -> 400 invalid_workspace_id (#22)" in vd.FAILS
    assert "acceptance: /pf/..%2F..%2Fx/accounts -> 400 bad_path (api) or a non-API 404 (front door) (#22)" in vd.FAILS


def test_security_smoke_item_22_accepts_the_front_door_404_for_the_traversal_and_not_a_json_404():
    """Through nginx (5024) `/api/pf/..%2F..%2Fx/accounts` is normalized to /x/accounts before it is
    proxied, so the API never sees it and nginx answers its own text/html 404; a JSON 404 would mean
    the path reached the API unrefused and still fails (#22)."""
    routes = {
        "GET /workspaces": FakeResponse(200, []),
        "POST /pf/verify-x/labels": FakeResponse(403, {"error": "origin_not_allowed"}),
        "GET /pf/A_B/accounts": FakeResponse(400, {"error": "invalid_workspace_id"}),
        "GET /health": {"ok": True},
    }
    name = "acceptance: /pf/..%2F..%2Fx/accounts -> 400 bad_path (api) or a non-API 404 (front door) (#22)"
    c = FakeClient(dict(routes, **{"GET /pf/..%2F..%2Fx/accounts": FakeResponse(404, None, headers={"content-type": "text/html"}, content=b"<!DOCTYPE html>")}))
    vd._item_security_smoke(c, argparse.Namespace(mcp=""), _state())
    assert name not in vd.FAILS
    assert "front door" in str(next(r["detail"] for r in vd.RESULTS if r["name"] == name))
    vd.FAILS.clear()
    vd.RESULTS.clear()
    c = FakeClient(dict(routes, **{"GET /pf/..%2F..%2Fx/accounts": FakeResponse(404, {"detail": "Not Found"}, headers={"content-type": "application/json"})}))
    vd._item_security_smoke(c, argparse.Namespace(mcp=""), _state())
    assert name in vd.FAILS


def test_security_smoke_item_22_uses_the_stack_mcp_url(monkeypatch):
    seen = {}

    def post(url, **kw):
        seen["url"] = url
        return FakeResponse(200, {"result": {"serverInfo": {"name": "aurum"}}})

    monkeypatch.setattr(vd.httpx, "post", post)
    c = FakeClient({"GET /workspaces": FakeResponse(200, []), "POST /pf/verify-x/labels": FakeResponse(403, {"error": "origin_not_allowed"}),
                    "GET /pf/A_B/accounts": FakeResponse(400, {"error": "invalid_workspace_id"}), "GET /pf/..%2F..%2Fx/accounts": FakeResponse(400, {"error": "bad_path"}), "GET /health": {"ok": True}})
    st = _state()
    st.mcp_url = "http://127.0.0.1:5142/mcp"
    vd._item_security_smoke(c, argparse.Namespace(mcp=""), st)
    assert seen["url"] == "http://127.0.0.1:5142/mcp"
    assert vd.RESULTS[-1] == {"name": "acceptance: MCP initialize -> 200 (#22)", "ok": True, "detail": vd.RESULTS[-1]["detail"]}


def test_tax_gating_item_17_toggles_modules_and_reverts():
    state = {"tax": False}

    def calendar(_kw):
        items = [{"kind": "tax", "name": "Declaración", "status": "upcoming"}] if state["tax"] else []
        return {"days": [{"date": "2026-10-17", "items": items}]}

    def insights(_kw):
        return [{"kind": "deposit_without_cfdi"}] if state["tax"] else [{"kind": "organizer_upcoming"}]

    def put_ws(kw):
        state["tax"] = bool(kw["json"]["modules"]["tax"])
        return {"id": "verify-x"}

    c = FakeClient({
        "GET /organizer/verify-x/calendar": calendar,
        "GET /insights/verify-x": insights,
        "PUT /workspaces/verify-x": put_ws,
        "GET /insights/demo-mx": [{"kind": "organizer_upcoming", "title": "Próximo cargo: Max"}, {"kind": "organizer_upcoming", "title": "Próximo cargo: Icloud"}, {"kind": "organizer_price_increase", "title": "Subió el precio: Netflix"}],
    })
    vd._item_tax_gating(c, _state())
    assert vd.FAILS == []
    assert state["tax"] is False  # reverted
    assert [n for n in _names()] == [
        "acceptance: simple workspace -> zero tax calendar items and zero cfdi/resico/diot insights (#17)",
        "acceptance: modules.tax true -> tax rows appear; revert -> gone (#17)",
        "acceptance: insights/demo-mx has exactly one nudge per commitment name (#17)",
    ]


def test_tax_gating_item_17_catches_a_duplicate_nudge():
    c = FakeClient({
        "GET /organizer/verify-x/calendar": {"days": []},
        "GET /insights/verify-x": [],
        "PUT /workspaces/verify-x": {"id": "verify-x"},
        "GET /insights/demo-mx": [{"kind": "organizer_upcoming", "title": "Próximo cargo: Max"}, {"kind": "organizer_upcoming", "title": "Próximo cargo: Max"}],
    })
    vd._item_tax_gating(c, _state())
    assert "acceptance: insights/demo-mx has exactly one nudge per commitment name (#17)" in vd.FAILS


def test_onboarding_item_18_fresh_and_done():
    steps = [{"id": s, "done": False, "count": 0} for s in ("accounts", "income", "recurring", "first_entries")]
    c = FakeClient({"GET /pf/verify-x/onboarding": {"steps": steps, "done": False}})
    vd._item_onboarding(c, "verify-x", expect_done=False)
    assert vd.FAILS == []
    done = [{"id": s, "done": s in ("accounts", "first_entries"), "count": 1} for s in ("accounts", "income", "recurring", "first_entries")]
    c = FakeClient({"GET /pf/verify-x/onboarding": {"steps": done, "done": True}})
    vd._item_onboarding(c, "verify-x", expect_done=True)
    assert vd.FAILS == []
    c = FakeClient({"GET /pf/verify-x/onboarding": {"steps": [{"id": "accounts", "done": False}, {"id": "import", "done": False}], "done": False}})
    vd._item_onboarding(c, "verify-x", expect_done=False)
    assert vd.FAILS == ["acceptance: onboarding has the four step ids (#18)"]


def test_e2e_item_26_skips_without_node(monkeypatch, tmp_path):
    monkeypatch.setattr(vd.shutil, "which", lambda _name: None)
    a = argparse.Namespace(e2e=True, api="http://127.0.0.1:5156/api", web=None)
    vd._item_e2e(a, "verify-x", tmp_path)
    assert vd.FAILS == []
    assert _names() == ["acceptance: --e2e ui-check flows (#26)"]
    vd.RESULTS.clear()
    vd._item_e2e(argparse.Namespace(e2e=False, api="", web=None), "verify-x", tmp_path)
    assert _names() == []


def test_acceptance_suite_never_targets_a_protected_workspace(monkeypatch):
    """The throwaway id is generated, so the guard can only trip when someone protects the verify- prefix
    — and then it must trip before any request."""
    class Exploding:
        def __getattr__(self, name):
            raise AssertionError("HTTP call before the guard")

    class FakeNow:
        @staticmethod
        def now():
            return vd.date(2026, 1, 1)

    monkeypatch.setattr(vd.uuid, "uuid4", lambda: type("U", (), {"hex": "abcd1234"})())
    monkeypatch.setattr(vd, "datetime", FakeNow)
    fixed = "verify-20260101000000-abcd"
    monkeypatch.setenv("AURUM_PROTECTED_WORKSPACES", f"personal,{fixed}")
    with pytest.raises(SystemExit) as exc:
        vd.acceptance_suite(Exploding(), argparse.Namespace(api="http://x/api", web=None, mcp="", e2e=False))
    assert exc.value.code == 2
