"""Migration runner: discovers ``aurum/<module>/migrations.py``, applies pending versions once, records them."""

from __future__ import annotations

import sqlite3

import pytest

from aurum.core import db


@pytest.fixture
def fake_module(monkeypatch):
    """Register a synthetic migrations module without touching the package tree."""
    calls: list[str] = []

    def m1(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE IF NOT EXISTS zz_demo (id INTEGER PRIMARY KEY, name TEXT)")
        calls.append("m1")

    def m2(conn: sqlite3.Connection) -> None:
        db.ensure_column(conn, "zz_demo", "kind", "TEXT NOT NULL DEFAULT 'expense'")
        calls.append("m2")

    migrations: list[db.Migration] = [(1, "create", m1), (2, "add kind", m2)]
    monkeypatch.setattr(db, "migration_modules", lambda: ["zzfake"])
    monkeypatch.setattr(db, "load_migrations", lambda module: list(migrations))
    return calls, migrations


def test_migrations_apply_once_and_are_recorded(fake_module, tmp_path):
    calls, _ = fake_module
    path = tmp_path / "m.db"
    conn = db.connect(path)
    assert calls == ["m1", "m2"]
    assert db.applied_versions(conn) == {"zzfake": 2}
    assert db.has_column(conn, "zz_demo", "kind")
    conn.close()

    # A second open of the same file (new process) must not re-run anything.
    db.reset_for_tests()
    conn = db.connect(path)
    assert calls == ["m1", "m2"]
    rows = conn.execute(
        "SELECT module, version, name FROM core_schema_migrations ORDER BY version"
    ).fetchall()
    assert [(r[0], r[1], r[2]) for r in rows] == [("zzfake", 1, "create"), ("zzfake", 2, "add kind")]
    conn.close()


def test_new_version_runs_on_existing_db(fake_module, tmp_path):
    calls, migrations = fake_module
    path = tmp_path / "m.db"
    db.connect(path).close()
    assert calls == ["m1", "m2"]

    migrations.append((3, "third", lambda conn: calls.append("m3")))
    db.reset_for_tests()
    conn = db.connect(path)
    assert calls == ["m1", "m2", "m3"]
    assert db.applied_versions(conn) == {"zzfake": 3}
    conn.close()


def test_failed_migration_rolls_back_and_is_not_recorded(fake_module, tmp_path):
    calls, migrations = fake_module

    def bad(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE zz_partial (id INTEGER)")
        raise RuntimeError("boom")

    migrations.append((3, "bad", bad))
    path = tmp_path / "m.db"
    with pytest.raises(RuntimeError):
        db.connect(path)
    db.reset_for_tests()
    migrations.pop()
    conn = db.connect(path)
    assert db.applied_versions(conn) == {"zzfake": 2}
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "zz_partial" not in tables
    conn.close()


def test_versions_must_increase(monkeypatch, tmp_path):
    class Mod:
        MIGRATIONS = [(2, "b", lambda c: None), (1, "a", lambda c: None)]

    monkeypatch.setattr(db, "migration_modules", lambda: ["zzbad"])
    monkeypatch.setattr(db.importlib, "import_module", lambda name: Mod)
    with pytest.raises(RuntimeError):
        db.connect(tmp_path / "v.db")


def test_ensure_column_is_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "e.db")
    conn.execute("CREATE TABLE t (id INTEGER)")
    assert db.ensure_column(conn, "t", "c", "TEXT") is True
    assert db.ensure_column(conn, "t", "c", "TEXT") is False
    with pytest.raises(ValueError):
        db.ensure_column(conn, "t; DROP TABLE t", "c", "TEXT")
    conn.close()


def test_real_package_has_no_broken_migration_modules(tmp_path):
    """Every shipped migrations.py loads and applies cleanly on a fresh database."""
    conn = db.connect(tmp_path / "fresh.db")
    for module in db.migration_modules():
        db.load_migrations(module)
    conn.close()


# --- newer-schema refusal + re-entrancy guard + migrate() ------------------------------------------


def test_recorded_version_above_known_refuses_to_start(fake_module, tmp_path):
    """A database that has already been migrated by a newer install than this one must not silently
    skip the "future" migration — it must refuse to start."""
    calls, migrations = fake_module
    path = tmp_path / "m.db"
    db.connect(path).close()
    db.reset_for_tests()

    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO core_schema_migrations (module, version, name, applied_at) VALUES ('zzfake', 999, 'future', 'x')"
    )
    conn.commit()
    conn.close()

    db.reset_for_tests()
    with pytest.raises(RuntimeError, match="zzfake"):
        db.connect(path)


def test_recorded_module_with_no_migrations_py_refuses_to_start(tmp_path):
    path = tmp_path / "m.db"
    db.connect(path).close()
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS core_schema_migrations (module TEXT, version INTEGER, name TEXT, "
        "applied_at TEXT, PRIMARY KEY (module, version))"
    )
    conn.execute(
        "INSERT INTO core_schema_migrations (module, version, name, applied_at) VALUES ('pf', 999, 'x', 'x')"
    )
    conn.commit()
    conn.close()
    db.reset_for_tests()
    with pytest.raises(RuntimeError, match="pf"):
        db.connect(path)


def test_migration_calling_connect_raises_instead_of_deadlocking(monkeypatch, tmp_path):
    """The whole test must finish quickly — a deadlock would hang until the suite's own timeout."""
    import time

    def reentrant(conn: sqlite3.Connection) -> None:
        db.connect(tmp_path / "other.db")

    monkeypatch.setattr(db, "migration_modules", lambda: ["zzreentrant"])
    monkeypatch.setattr(db, "load_migrations", lambda module: [(1, "reentrant", reentrant)])

    start = time.monotonic()
    with pytest.raises(RuntimeError, match="db.connect\\(\\) inside a migration"):
        db.connect(tmp_path / "m.db")
    assert time.monotonic() - start < 5


def test_migrate_returns_schema_versions(fake_module, tmp_path):
    calls, _ = fake_module
    path = tmp_path / "m.db"
    assert db.migrate(path) == {"zzfake": 2}


def test_main_prints_schema_and_applied(fake_module, tmp_path, capsys, monkeypatch):
    import json

    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path))
    rc = db.main()
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == {"zzfake": 2}
    assert out["applied"] == [["zzfake", 1, "create"], ["zzfake", 2, "add kind"]]
