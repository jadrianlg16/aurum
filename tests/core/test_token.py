"""aurum.core.token: settings defaults, token resolution, CLI."""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import sys
from dataclasses import fields

import pytest

from aurum.core import token as token_mod
from aurum.core.config import InvalidWorkspaceId, settings


def test_settings_defaults(monkeypatch, capsys):
    for name in (
        "AURUM_BIND", "AURUM_REQUIRE_TOKEN", "AURUM_ALLOWED_HOSTS", "AURUM_ALLOWED_ORIGINS",
        "AURUM_FORWARDED_ALLOW_IPS", "AURUM_MCP_HOST", "AURUM_API_HOST", "AURUM_LEDGER_CACHE",
        "AURUM_FETCH_MAX_MB", "AURUM_ALLOW_PRIVATE_FETCH", "AURUM_ZIP_MAX_MEMBERS",
        "AURUM_ZIP_MAX_MEMBER_MB", "AURUM_ZIP_MAX_TOTAL_MB", "AURUM_PROTECTED_WORKSPACES",
        "AURUM_BACKUP_KEEP", "AURUM_MIGRATE_PROTECTED", "AURUM_TEST_CLOCK", "AURUM_MCP_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    s = settings()
    for f in fields(s):
        print(f"{f.name}={getattr(s, f.name)!r}")
    assert s.bind == "127.0.0.1"
    assert s.bind_is_loopback is True
    assert s.require_token is False
    assert s.allowed_hosts == ()
    assert s.allowed_origins == ()
    assert s.forwarded_allow_ips == "127.0.0.1"
    assert s.mcp_host == "127.0.0.1"
    assert s.api_host == "127.0.0.1"
    assert s.mcp_token == ""
    assert s.ledger_cache is True
    assert s.fetch_max_mb == 10
    assert s.allow_private_fetch is False
    assert (s.zip_max_members, s.zip_max_member_mb, s.zip_max_total_mb) == (500, 10, 100)
    assert s.protected_workspaces == ("personal",)
    assert s.backup_keep == 10
    assert s.migrate_protected is False
    assert s.test_clock is False
    assert "bind=" in capsys.readouterr().out


def test_settings_lists_and_bind_parsing(monkeypatch):
    monkeypatch.setenv("AURUM_ALLOWED_HOSTS", " a.example, b.example ,,")
    monkeypatch.setenv("AURUM_ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("AURUM_BIND", "0.0.0.0")
    s = settings()
    assert s.allowed_hosts == ("a.example", "b.example")
    assert s.allowed_origins == ("http://localhost:3000",)
    assert s.bind_is_loopback is False
    monkeypatch.setenv("AURUM_BIND", "LOCALHOST")
    assert settings().bind_is_loopback is True


def test_workspace_dir_rejects_bad_ids():
    s = settings()
    assert s.workspace_dir("demo-mx").name == "demo-mx"
    for bad in ("../x", "A_B", "a b", "", "x", "-abc"):
        with pytest.raises(InvalidWorkspaceId):
            s.workspace_dir(bad)


# ------------------------------------------------------------------- token resolution cases (a)–(d)


def test_a_loopback_no_env_token_resolves_empty_and_creates_nothing():
    assert token_mod.resolve_api_token() == ""
    assert token_mod.auth_required() is False
    assert token_mod.auth_source() == "none"
    assert not settings().secrets_dir.exists()


def test_b_exposed_bind_generates_a_file_token_once(monkeypatch, caplog):
    monkeypatch.setenv("AURUM_BIND", "0.0.0.0")
    with caplog.at_level(logging.INFO, logger="aurum.token"):
        first = token_mod.resolve_api_token()
    assert len(first) >= 32
    path = token_mod.token_path()
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip() == first
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert token_mod.resolve_api_token() == first  # second call: same value, no rotation
    assert token_mod.auth_source() == "file"
    assert token_mod.auth_required() is True
    generated = [r for r in caplog.records if "generated" in r.getMessage()]
    assert len(generated) == 1
    assert str(path) in generated[0].getMessage()
    assert first not in caplog.text


def test_b2_require_token_alone_generates(monkeypatch):
    monkeypatch.setenv("AURUM_REQUIRE_TOKEN", "1")
    assert token_mod.resolve_api_token()
    assert token_mod.token_path().exists()


def test_c_env_token_wins_over_file(monkeypatch):
    path = token_mod.token_path()
    path.parent.mkdir(parents=True)
    path.write_text("filetoken\n", encoding="utf-8")
    assert token_mod.resolve_api_token() == "filetoken"
    assert token_mod.auth_source() == "file"
    monkeypatch.setenv("AURUM_API_TOKEN", "abc")
    assert token_mod.resolve_api_token() == "abc"
    assert token_mod.auth_source() == "env"


def _run_cli(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, "-m", "aurum.core.token", *args], capture_output=True, text=True, env=full_env, check=False
    )


def test_d_cli_show_rotate_status(tmp_path):
    data_dir = str(tmp_path / "data")
    env = {"AURUM_DATA_DIR": data_dir, "AURUM_BIND": "127.0.0.1"}
    env.pop("AURUM_API_TOKEN", None)
    base = {k: v for k, v in os.environ.items() if k != "AURUM_API_TOKEN"}

    def run(*args, extra=None):
        full = {**base, **env, **(extra or {})}
        return subprocess.run(
            [sys.executable, "-m", "aurum.core.token", *args], capture_output=True, text=True, env=full, check=False
        )

    status = run("status")
    assert status.returncode == 0
    assert status.stdout.strip() == "required=False source=none"
    assert not (tmp_path / "data" / "secrets").exists()

    path = tmp_path / "data" / "secrets" / "api_token"
    path.parent.mkdir(parents=True)
    path.write_text("filetoken123\n", encoding="utf-8")
    show = run("show")
    assert show.returncode == 0
    assert show.stdout.strip() == "filetoken123"
    assert run("status").stdout.strip() == "required=True source=file"

    rotated = run("rotate")
    assert rotated.returncode == 0
    new_value = path.read_text(encoding="utf-8").strip()
    assert new_value != "filetoken123"
    assert run("show").stdout.strip() == new_value

    with_env = run("rotate", extra={"AURUM_API_TOKEN": "envtoken"})
    assert with_env.returncode == 2
    assert path.read_text(encoding="utf-8").strip() == new_value  # untouched
