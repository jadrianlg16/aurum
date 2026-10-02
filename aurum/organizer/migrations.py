"""organizer schema migrations (see ``aurum/core/db.py``).

Versions:
  1  commitments_account_id        organizer_commitments.account_id + backfill from pf_accounts
  2  mark_links_and_candidate_flags organizer_occurrences.entry_id / auto_created,
                                    organizer_candidates.flags / existing_commitment_id

``schema.sql`` already carries the final shape, so a fresh database needs no ALTER — ``ensure_column``
is a no-op there and only the backfill runs. Both migrations are additive and never delete rows.

A migration receives ONLY the connection it is given (plus ledger calls); it must never call
``db.connect()``/``store.db()`` — ``connect()`` holds a non-reentrant lock while migrating.
"""

from __future__ import annotations

import sqlite3

from ..core.db import Migration, ensure_column


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _v1_commitments_account_id(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "organizer_commitments", "account_id", "TEXT")
    if not _table_exists(conn, "pf_accounts"):
        return
    conn.execute(
        "UPDATE organizer_commitments SET account_id=("
        "  SELECT p.id FROM pf_accounts p"
        "  WHERE p.ws_id=organizer_commitments.ws_id"
        "    AND p.account=organizer_commitments.account AND p.archived=0"
        "  LIMIT 1"
        ") WHERE account_id IS NULL"
    )


def _v2_mark_links_and_candidate_flags(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "organizer_occurrences", "entry_id", "TEXT")
    ensure_column(conn, "organizer_occurrences", "auto_created", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "organizer_candidates", "flags", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(conn, "organizer_candidates", "existing_commitment_id", "TEXT")


MIGRATIONS: list[Migration] = [
    (1, "commitments_account_id", _v1_commitments_account_id),
    (2, "mark_links_and_candidate_flags", _v2_mark_links_and_candidate_flags),
]
