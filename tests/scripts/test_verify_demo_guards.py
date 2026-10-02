"""scripts/verify_demo.py: the protected-workspace guard runs before any HTTP request."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "verify_demo", Path(__file__).resolve().parents[2] / "scripts" / "verify_demo.py"
)
verify_demo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["verify_demo"] = verify_demo
SPEC.loader.exec_module(verify_demo)


class _ExplodingClientFactory:
    """A stand-in for httpx.Client construction: raises if the guard ever lets main() reach it."""

    def __call__(self, api_url, headers):
        raise AssertionError("client_factory was called — the guard did not run before any HTTP request")


def test_ws_personal_exits_2_before_any_request():
    with pytest.raises(SystemExit) as exc:
        verify_demo.main(["--ws", "personal"], client_factory=_ExplodingClientFactory())
    assert exc.value.code == 2


def test_env_protected_list_extends_beyond_personal(monkeypatch):
    monkeypatch.setenv("AURUM_PROTECTED_WORKSPACES", "personal,vault")
    with pytest.raises(SystemExit) as exc:
        verify_demo.main(["--ws", "vault"], client_factory=_ExplodingClientFactory())
    assert exc.value.code == 2


def test_guard_protected_is_a_no_op_for_a_throwaway_id():
    verify_demo.guard_protected("verify-20260101000000-ab12")  # must not raise


def test_default_protected_set_is_just_personal(monkeypatch):
    monkeypatch.delenv("AURUM_PROTECTED_WORKSPACES", raising=False)
    assert verify_demo.protected_workspaces() == {"personal"}


def test_parse_args_defaults():
    a = verify_demo.parse_args([])
    assert a.ws == "demo-mx"
    assert a.level == 1
    assert a.json is None
    assert a.e2e is False


def test_parse_args_level7_and_json():
    a = verify_demo.parse_args(["--level", "7", "--json", "out.json", "--ws", "demo-mx"])
    assert a.level == 7
    assert a.json == "out.json"


def test_parse_args_help_lists_level(capsys):
    with pytest.raises(SystemExit):
        verify_demo.parse_args(["--help"])
    out = capsys.readouterr().out
    assert "--level" in out


def test_main_resets_fails_and_results_across_calls(monkeypatch):
    """A guard SystemExit for one call must not leak FAILS/RESULTS state into the next call."""
    with pytest.raises(SystemExit):
        verify_demo.main(["--ws", "personal"], client_factory=_ExplodingClientFactory())
    assert verify_demo.FAILS == []
    assert verify_demo.RESULTS == []
