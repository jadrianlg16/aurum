"""SQLite for metadata (labels, budgets, goals, inbox, audit, rule versions). Balances live in the ledger.

Each module may ship ``aurum/<module>/schema.sql`` (idempotent ``CREATE TABLE IF NOT EXISTS`` with
module-prefixed table names). ``connect()`` applies every schema it finds on first open of a database
file, so modules never need to register anything.

Schema changes to an existing install go through **migrations**: a module may also ship
``aurum/<module>/migrations.py`` exposing
``MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Connection], None]]]`` — ``(version, name, fn)`` with
versions strictly increasing per module. After the schemas are applied, ``connect()`` runs every migration
whose version is above the module's recorded one, in order, each in its own transaction, and records it in
``core_schema_migrations``. Migrations must tolerate a fresh database (``CREATE TABLE IF NOT EXISTS`` may
already have produced the final shape — use ``ensure_column``) and must never delete user data.

**Rules for a migration function (enforced or documented here):**

1. A migration ``fn(conn)`` must use *only* the ``conn`` it is given, plus ledger file calls
   (``aurum.ledger.beancount_store``). It must **never** call :func:`connect` or ``aurum.pf.store.db()``
   (or any other wrapper around this module's ``connect()``): ``connect()`` holds a plain, non-reentrant
   ``threading.Lock`` for the whole schema+migration pass, so a nested call on the same thread would
   deadlock forever. ``connect()`` instead detects the same-thread re-entry and raises ``RuntimeError``
   immediately (see the module-level ``_migrating`` guard below).
2. A migration must never delete user data. Corrective/backfill migrations append rather than rewrite.
3. A *data* migration (one that can change money already on a workspace's ledger, e.g. a sign
   correction) must abort when the workspace it would touch is protected
   (``aurum.core.workspaces.protected_workspace_ids()``) unless ``AURUM_MIGRATE_PROTECTED=1`` is set —
   the user's real workspace is never silently rewritten by an upgrade.
4. On startup, a database that records a ``(module, version)`` pair above what this install's
   ``aurum.<module>.migrations`` actually knows (including a module with no ``migrations.py`` at all)
   refuses to start: a newer install wrote data this code cannot safely interpret.
"""

from __future__ import annotations

import importlib
import logging
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .config import settings

log = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_lock = threading.Lock()
_initialized: set[Path] = set()
_migrating = threading.local()
_last_applied: list[tuple[str, int, str]] = []


# Modules that own their own database file (not the shared metadata DB) are skipped here.
_OWN_DB_MODULES = {"corpus"}


def schema_files() -> list[Path]:
    return sorted(p for p in _PACKAGE_ROOT.glob("*/schema.sql") if p.parent.name not in _OWN_DB_MODULES)


def _apply_schemas(conn: sqlite3.Connection) -> None:
    for path in schema_files():
        conn.executescript(path.read_text(encoding="utf-8"))
    conn.commit()


# --- migrations -------------------------------------------------------------------------------------

Migration = tuple[int, str, Callable[[sqlite3.Connection], None]]

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS core_schema_migrations (
    module     TEXT NOT NULL,
    version    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    PRIMARY KEY (module, version)
);
"""


def migration_modules() -> list[str]:
    """Module names (``aurum/<module>``) that ship a ``migrations.py``."""
    return sorted(
        p.parent.name for p in _PACKAGE_ROOT.glob("*/migrations.py") if p.parent.name not in _OWN_DB_MODULES
    )


def load_migrations(module: str) -> list[Migration]:
    mod = importlib.import_module(f"aurum.{module}.migrations")
    migrations: list[Migration] = list(getattr(mod, "MIGRATIONS", []))
    versions = [m[0] for m in migrations]
    if versions != sorted(versions) or len(set(versions)) != len(versions):
        raise RuntimeError(f"aurum.{module}.migrations: versions must be strictly increasing: {versions}")
    return migrations


def applied_versions(conn: sqlite3.Connection) -> dict[str, int]:
    conn.executescript(_MIGRATIONS_TABLE)
    rows = conn.execute(
        "SELECT module, MAX(version) AS v FROM core_schema_migrations GROUP BY module"
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def _apply_migrations(conn: sqlite3.Connection) -> list[tuple[str, int, str]]:
    """Run every pending migration. Returns the (module, version, name) triples applied."""
    done = applied_versions(conn)
    known_modules = set(migration_modules())
    for module, recorded_version in done.items():
        if module not in known_modules:
            raise RuntimeError(
                f"core_schema_migrations records module {module!r} at version {recorded_version}, but "
                f"this install has no aurum.{module}.migrations — refusing to start"
            )
        known_max = max((v for v, _, _ in load_migrations(module)), default=0)
        if recorded_version > known_max:
            raise RuntimeError(
                f"core_schema_migrations records module {module!r} at version {recorded_version}, but "
                f"this install only knows versions up to {known_max} — refusing to start (a newer "
                f"install wrote data this code cannot read)"
            )
    applied: list[tuple[str, int, str]] = []
    for module in migration_modules():
        current = done.get(module, 0)
        for version, name, fn in load_migrations(module):
            if version <= current:
                continue
            try:
                conn.execute("BEGIN")
                fn(conn)
                conn.execute(
                    "INSERT INTO core_schema_migrations (module, version, name, applied_at) VALUES (?, ?, ?, ?)",
                    (module, version, name, datetime.now(UTC).isoformat()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                log.exception("migration failed: %s v%s (%s)", module, version, name)
                raise
            log.info("migration applied: %s v%s (%s)", module, version, name)
            applied.append((module, version, name))
    return applied


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    """``ALTER TABLE ... ADD COLUMN`` only if the column is missing. ``ddl`` is the column definition
    (e.g. ``"TEXT NOT NULL DEFAULT 'expense'"``). Returns True when the column was added."""
    if not table.replace("_", "").isalnum() or not column.replace("_", "").isalnum():
        raise ValueError("table and column must be identifiers")
    if has_column(conn, table, column):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    return True


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not table.replace("_", "").isalnum():
        raise ValueError("table must be an identifier")
    return column in {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (and initialise on first use) the metadata database."""
    if getattr(_migrating, "active", False):
        raise RuntimeError(
            "db.connect() inside a migration is not allowed: a migration function may use only the "
            "`conn` it receives (plus ledger file calls) — connect() holds a non-reentrant lock while "
            "migrations run, so calling it again from the same thread here would deadlock. See the rules "
            "in this module's docstring."
        )
    db_path = path or settings().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    with _lock:
        if db_path not in _initialized:
            _apply_schemas(conn)
            _migrating.active = True
            try:
                applied = _apply_migrations(conn)
            finally:
                _migrating.active = False
            _last_applied[:] = applied
            _initialized.add(db_path)
    return conn


def migrate(path: Path | None = None) -> dict[str, int]:
    """Bring the metadata database at ``path`` (default: the configured one) up to date and return the
    resulting ``{module: version}`` map. Used by ``python -m aurum.core.db`` and by the Docker
    entrypoint, which must fail the boot when a migration raises."""
    conn = connect(path)
    try:
        return applied_versions(conn)
    finally:
        conn.close()


def reset_for_tests() -> None:
    """Forget which databases were initialised (tests point AURUM_DATA_DIR at tmp dirs)."""
    with _lock:
        _initialized.clear()
        _last_applied.clear()


def main() -> int:
    import json

    schema = migrate()
    print(json.dumps({"schema": schema, "applied": [list(x) for x in _last_applied]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
