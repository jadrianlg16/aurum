"""scripts/restore.py: restores a POST /api/backup zip into a NEW directory only."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location(
    "restore", Path(__file__).resolve().parents[2] / "scripts" / "restore.py"
)
restore = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["restore"] = restore
SPEC.loader.exec_module(restore)


def _make_backup_zip(path: Path, *, corrupt: bool = False) -> Path:
    db_path = path.parent / "src.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO t (name) VALUES ('a'), ('b')")
    conn.commit()
    conn.close()

    ws_dir = path.parent / "ws_src" / "workspaces" / "demo1"
    ws_dir.mkdir(parents=True)
    (ws_dir / "workspace.json").write_text(json.dumps({"id": "demo1", "name": "Demo"}), encoding="utf-8")
    (ws_dir / "main.beancount").write_text("", encoding="utf-8")

    files = {"aurum.db": db_path, "workspaces/demo1/workspace.json": ws_dir / "workspace.json",
             "workspaces/demo1/main.beancount": ws_dir / "main.beancount"}
    manifest = {
        "version": "0.1.0", "created_at": "2026-09-12T00:00:00+00:00",
        "schema": {"pf": 1},
        "files": {name: restore._sha256_bytes(p.read_bytes()) for name, p in files.items()},
    }
    with zipfile.ZipFile(path, "w") as zf:
        for name, p in files.items():
            zf.writestr(name, p.read_bytes())
        if corrupt:
            manifest["files"]["aurum.db"] = "0" * 64
        zf.writestr("manifest.json", json.dumps(manifest))
    return path


@pytest.fixture(autouse=True)
def _api_down(monkeypatch):
    """Default: the API is not running (a real ConnectError), matching a stopped server."""

    def raise_connect_error(url, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(restore.httpx, "get", raise_connect_error)


def test_exit_2_when_into_dir_exists_and_is_nonempty(tmp_path):
    zpath = _make_backup_zip(tmp_path / "b.zip")
    into = tmp_path / "into"
    into.mkdir()
    (into / "already-here.txt").write_text("x", encoding="utf-8")
    assert restore.main([str(zpath), "--into", str(into)]) == 2


def test_exit_3_when_api_answers(tmp_path, monkeypatch):
    def fake_get(url, timeout=None):
        class R:
            status_code = 200

        return R()

    monkeypatch.setattr(restore.httpx, "get", fake_get)
    zpath = _make_backup_zip(tmp_path / "b.zip")
    into = tmp_path / "into"
    assert restore.main([str(zpath), "--into", str(into), "--api", "http://localhost:9999"]) == 3
    assert not into.exists()


def test_exit_4_on_sha256_mismatch(tmp_path):
    zpath = _make_backup_zip(tmp_path / "b.zip", corrupt=True)
    into = tmp_path / "into"
    assert restore.main([str(zpath), "--into", str(into)]) == 4
    assert not into.exists()


def test_success_extracts_and_prints_counts_and_workspaces(tmp_path, capsys):
    zpath = _make_backup_zip(tmp_path / "b.zip")
    into = tmp_path / "into"
    rc = restore.main([str(zpath), "--into", str(into)])
    assert rc == 0
    assert (into / "aurum.db").exists()
    assert (into / "workspaces" / "demo1" / "workspace.json").exists()
    out = capsys.readouterr().out
    assert "t: 2" in out
    assert "demo1" in out


def test_never_touches_an_existing_empty_into_dir_before_success(tmp_path):
    """An existing but empty --into directory is fine (not 'non-empty')."""
    zpath = _make_backup_zip(tmp_path / "b.zip")
    into = tmp_path / "into"
    into.mkdir()
    rc = restore.main([str(zpath), "--into", str(into)])
    assert rc == 0
    assert (into / "aurum.db").exists()
