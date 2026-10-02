"""pf schema migrations (see ``aurum/core/db.py``).

  1  labels_kind_archived   pf_labels.kind ('expense'|'income'|'transfer', backfilled from the account
                            root) + pf_labels.archived
  2  goals_account_id       pf_goals.account_id, backfilled from pf_accounts by (ws_id, account)
  3  entries_commitment_id  pf_entries.commitment_id + ix_pf_entries_ws_commitment
  4  liability_sign         legacy credit_card/loan rows whose ledger balance is positive get a
                            correction transaction (tag ``sign-migration``) and a WARNING; aborts on a
                            protected workspace unless AURUM_MIGRATE_PROTECTED=1

A migration receives ONLY the connection it is given (plus ledger calls); it must never call
``db.connect()``/``store.db()`` — ``connect()`` holds a non-reentrant lock while migrating. Migrations never
delete user data and tolerate a fresh database (``schema.sql`` already carries the final columns).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date
from decimal import Decimal

from ..core.db import Migration, ensure_column
from ..core.money import Amount

log = logging.getLogger(__name__)

LIABILITY_TYPES = {"credit_card", "loan"}
OPENING_EQUITY = "Equity:Opening"


def protected_workspaces() -> set[str]:
    raw = os.environ.get("AURUM_PROTECTED_WORKSPACES", "personal")
    return {x.strip() for x in raw.split(",") if x.strip()} | {"personal"}


def migrate_protected_allowed() -> bool:
    return os.environ.get("AURUM_MIGRATE_PROTECTED", "0") == "1"


def _v1_labels_kind_archived(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "pf_labels", "kind", "TEXT NOT NULL DEFAULT 'expense'")
    ensure_column(conn, "pf_labels", "archived", "INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE pf_labels SET kind='income' WHERE account LIKE 'Income:%'")
    conn.execute("UPDATE pf_labels SET kind='expense' WHERE account LIKE 'Expenses:%'")
    conn.execute(
        "UPDATE pf_labels SET kind='transfer' WHERE account NOT LIKE 'Income:%' AND account NOT LIKE 'Expenses:%'"
    )


def _v2_goals_account_id(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "pf_goals", "account_id", "TEXT")
    conn.execute(
        "UPDATE pf_goals SET account_id = (SELECT a.id FROM pf_accounts a WHERE a.ws_id = pf_goals.ws_id "
        "AND a.account = pf_goals.account) WHERE account_id IS NULL"
    )


def _v3_entries_commitment_id(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "pf_entries", "commitment_id", "TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_pf_entries_ws_commitment ON pf_entries(ws_id, commitment_id)"
    )


def _v4_liability_sign(conn: sqlite3.Connection) -> None:
    """Liabilities are stored negative (owed). Any credit_card/loan row that still carries a positive
    ledger balance (typed as "what I owe" by an older version) gets a correction txn of -2·balance."""
    from ..ledger.base import Posting, Transaction, get_ledger

    rows = conn.execute(
        "SELECT id, ws_id, type, account, currency FROM pf_accounts WHERE type IN ('credit_card', 'loan')"
    ).fetchall()
    if not rows:
        return
    ledger = get_ledger()
    protected = protected_workspaces()
    balances_by_ws: dict[str, dict[str, list[Amount]]] = {}
    for row in rows:
        ws_id = row["ws_id"]
        if ws_id not in balances_by_ws:
            balances_by_ws[ws_id] = ledger.balances(ws_id)
        amounts = balances_by_ws[ws_id].get(row["account"], [])
        bal = next((a.amount for a in amounts if a.currency == row["currency"]), Decimal("0"))
        if bal <= 0:
            continue
        if ws_id in protected and not migrate_protected_allowed():
            raise RuntimeError(
                f"pf migration v4 would correct a liability balance in protected workspace {ws_id!r}; "
                "set AURUM_MIGRATE_PROTECTED=1 after backing up data/ to allow it"
            )
        ledger.append(
            ws_id,
            Transaction(
                date=date.today(),
                payee=None,
                narration="Corrección de signo (migración pf v4)",
                postings=[
                    Posting(account=row["account"], amount=Amount(amount=-2 * bal, currency=row["currency"])),
                    Posting(account=OPENING_EQUITY),
                ],
                tags=["sign-migration"],
                meta={"pf_account_id": row["id"]},
            ),
        )
        log.warning(
            "pf migration v4: corrected liability sign for account %s in workspace %s (was +%s, now -%s)",
            row["id"], ws_id, bal, bal,
        )


MIGRATIONS: list[Migration] = [
    (1, "labels_kind_archived", _v1_labels_kind_archived),
    (2, "goals_account_id", _v2_goals_account_id),
    (3, "entries_commitment_id", _v3_entries_commitment_id),
    (4, "liability_sign", _v4_liability_sign),
]
