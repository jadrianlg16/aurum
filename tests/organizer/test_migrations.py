"""organizer migrations v1–v2 on a legacy database."""

from __future__ import annotations

import sqlite3

from aurum.core import db

# The organizer tables exactly as they were before migrations v1–v2 (no account_id / entry_id /
# auto_created / flags columns), plus the pf_accounts table the v1 backfill reads.
LEGACY_SCHEMA = """
CREATE TABLE organizer_commitments (
    id TEXT PRIMARY KEY, ws_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
    merchant_patterns TEXT NOT NULL DEFAULT '[]', amount TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'MXN',
    amount_variable INTEGER NOT NULL DEFAULT 0, cadence TEXT NOT NULL, interval_days INTEGER,
    anchor_day INTEGER, weekday INTEGER, next_due TEXT NOT NULL, account TEXT NOT NULL DEFAULT 'Assets:Bank',
    label_id TEXT, essential TEXT NOT NULL DEFAULT 'needs', status TEXT NOT NULL DEFAULT 'active',
    trial_ends TEXT, started TEXT, ended TEXT, auto_pay INTEGER NOT NULL DEFAULT 0, cancel_notes TEXT,
    linked_loan_id TEXT, linked_card_id TEXT, source TEXT NOT NULL DEFAULT 'manual',
    confidence REAL NOT NULL DEFAULT 1.0, last_seen TEXT, notes TEXT, category_hint TEXT, reviewed_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE organizer_occurrences (
    id TEXT PRIMARY KEY, ws_id TEXT NOT NULL, commitment_id TEXT NOT NULL, due TEXT NOT NULL,
    amount TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'MXN', status TEXT NOT NULL DEFAULT 'upcoming',
    txn_id TEXT, marked_at TEXT, UNIQUE(ws_id, commitment_id, due)
);
CREATE TABLE organizer_candidates (
    id TEXT PRIMARY KEY, ws_id TEXT NOT NULL, merchant TEXT NOT NULL, preview_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0.0, status TEXT NOT NULL DEFAULT 'open',
    detected_at TEXT NOT NULL, UNIQUE(ws_id, merchant)
);
CREATE TABLE pf_accounts (
    id TEXT PRIMARY KEY, ws_id TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL, institution TEXT,
    currency TEXT NOT NULL DEFAULT 'MXN', account TEXT NOT NULL, credit_limit TEXT, cut_day INTEGER,
    due_day INTEGER, apr TEXT, archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _seed(path) -> None:
    raw = sqlite3.connect(path)
    raw.executescript(LEGACY_SCHEMA)
    raw.execute(
        "INSERT INTO pf_accounts (id, ws_id, name, type, account, archived, created_at, updated_at) "
        "VALUES ('acc-1','ws','BBVA','checking','Assets:Bank:Bbva',0,'t','t'),"
        "       ('acc-old','ws','Vieja','checking','Assets:Bank:Vieja',1,'t','t'),"
        "       ('acc-other','other','BBVA','checking','Assets:Bank:Bbva',0,'t','t')"
    )
    raw.execute(
        "INSERT INTO organizer_commitments (id, ws_id, kind, name, amount, cadence, next_due, account, "
        "created_at, updated_at) VALUES "
        "('cmt-1','ws','subscription','Netflix','219','monthly','2026-10-15','Assets:Bank:Bbva','t','t'),"
        "('cmt-2','ws','rent','Renta','12000','monthly','2026-10-01','Assets:Bank:Vieja','t','t'),"
        "('cmt-3','ws','bill','Agua','380','monthly','2026-10-20','Assets:Bank','t','t')"
    )
    raw.execute(
        "INSERT INTO organizer_occurrences (id, ws_id, commitment_id, due, amount, status) "
        "VALUES ('occ-1','ws','cmt-1','2026-09-15','219','paid')"
    )
    raw.execute(
        "INSERT INTO organizer_candidates (id, ws_id, merchant, preview_json, evidence_json, detected_at) "
        "VALUES ('cand-1','ws','SPOTIFY','{}','[]','t')"
    )
    raw.commit()
    raw.close()


def test_legacy_db_gets_both_migrations(tmp_path) -> None:
    path = tmp_path / "old.db"
    _seed(path)
    db.reset_for_tests()
    conn = db.connect(path)

    assert db.has_column(conn, "organizer_commitments", "account_id")
    assert db.has_column(conn, "organizer_occurrences", "entry_id")
    assert db.has_column(conn, "organizer_occurrences", "auto_created")
    assert db.has_column(conn, "organizer_candidates", "flags")
    assert db.has_column(conn, "organizer_candidates", "existing_commitment_id")

    rows = conn.execute(
        "SELECT version, name FROM core_schema_migrations WHERE module='organizer' ORDER BY version"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        (1, "commitments_account_id"), (2, "mark_links_and_candidate_flags"),
    ]

    # nothing deleted
    assert conn.execute("SELECT COUNT(*) FROM organizer_commitments").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM organizer_occurrences").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM organizer_candidates").fetchone()[0] == 1

    # v1 backfill: same workspace + same ledger account + not archived; archived/other-ws rows stay NULL
    by_id = {r[0]: r[1] for r in conn.execute("SELECT id, account_id FROM organizer_commitments")}
    assert by_id == {"cmt-1": "acc-1", "cmt-2": None, "cmt-3": None}

    # v2 defaults on existing rows
    occ = conn.execute("SELECT entry_id, auto_created FROM organizer_occurrences").fetchone()
    assert (occ[0], occ[1]) == (None, 0)
    cand = conn.execute("SELECT flags FROM organizer_candidates").fetchone()
    assert cand[0] == "[]"
    conn.close()


def test_fresh_db_needs_no_alter_and_records_the_same_versions(tmp_path) -> None:
    """schema.sql already carries the final shape: migrations are recorded but add no column."""
    path = tmp_path / "fresh.db"
    db.reset_for_tests()
    conn = db.connect(path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(organizer_commitments)")}
    assert "account_id" in cols
    versions = db.applied_versions(conn)
    assert versions["organizer"] == 2
    conn.close()

    # re-open (new process): nothing re-runs, nothing breaks
    db.reset_for_tests()
    conn = db.connect(path)
    assert conn.execute(
        "SELECT COUNT(*) FROM core_schema_migrations WHERE module='organizer'"
    ).fetchone()[0] == 2
    conn.close()


def test_migrations_use_only_the_given_connection() -> None:
    import inspect

    from aurum.organizer import migrations

    for _version, _name, fn in migrations.MIGRATIONS:
        src = inspect.getsource(fn)
        assert "connect(" not in src and "store.db(" not in src
