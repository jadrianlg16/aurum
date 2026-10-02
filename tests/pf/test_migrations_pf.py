"""pf migrations v1–v4 on a legacy database (old CREATE TABLEs), run through ``core.db.connect()``."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from aurum.core import db
from aurum.core.config import settings
from aurum.core.money import Amount
from aurum.ledger.base import Posting, Transaction, get_ledger

OLD_DDL = """
CREATE TABLE pf_labels (
    id TEXT PRIMARY KEY, ws_id TEXT NOT NULL, name TEXT NOT NULL, aliases TEXT NOT NULL DEFAULT '[]',
    account TEXT NOT NULL, icon TEXT, tax TEXT NOT NULL DEFAULT '{}', sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE pf_goals (
    id TEXT PRIMARY KEY, ws_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, target TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'MXN', target_date TEXT, account TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE pf_accounts (
    id TEXT PRIMARY KEY, ws_id TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL, institution TEXT,
    currency TEXT NOT NULL DEFAULT 'MXN', account TEXT NOT NULL, credit_limit TEXT, cut_day INTEGER, due_day INTEGER,
    apr TEXT, archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE pf_entries (
    id TEXT PRIMARY KEY, ws_id TEXT NOT NULL, kind TEXT NOT NULL, date TEXT NOT NULL, amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'MXN', account_id TEXT NOT NULL, to_account_id TEXT, label_id TEXT, payee TEXT,
    note TEXT, tags TEXT NOT NULL DEFAULT '[]', splits TEXT NOT NULL DEFAULT '[]', source TEXT NOT NULL DEFAULT 'manual',
    txn_id TEXT NOT NULL, voided INTEGER NOT NULL DEFAULT 0, editable INTEGER NOT NULL DEFAULT 1,
    non_editable_reason TEXT, attachment TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""


def _old_db(ws: str = "old-ws", card_ws: str | None = None) -> sqlite3.Connection:
    path = settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(OLD_DDL)
    conn.executemany(
        "INSERT INTO pf_labels (id, ws_id, name, account) VALUES (?,?,?,?)",
        [("lbl-1", ws, "Comida", "Expenses:Food"), ("lbl-2", ws, "Freelance", "Income:Freelance"),
         ("lbl-3", ws, "Ahorro", "Assets:Investments:General")],
    )
    conn.execute(
        "INSERT INTO pf_accounts (id, ws_id, name, type, currency, account, created_at, updated_at) "
        "VALUES ('acct-1', ?, 'Nu', 'savings', 'MXN', 'Assets:Bank:Nu', 't', 't')", (ws,),
    )
    conn.execute(
        "INSERT INTO pf_goals (id, ws_id, kind, name, target, account, created_at) "
        "VALUES ('goal-1', ?, 'savings', 'Fondo', '1000', 'Assets:Bank:Nu', 't')", (ws,),
    )
    conn.execute(
        "INSERT INTO pf_entries (id, ws_id, kind, date, amount, account_id, txn_id, created_at, updated_at) "
        "VALUES ('ent-1', ?, 'expense', '2026-09-01', '10', 'acct-1', 'txn-1', 't', 't')", (ws,),
    )
    if card_ws:
        conn.execute(
            "INSERT INTO pf_accounts (id, ws_id, name, type, currency, account, created_at, updated_at) "
            "VALUES ('acct-card', ?, 'Tarjeta', 'credit_card', 'MXN', 'Liabilities:CreditCard:Tarjeta', 't', 't')",
            (card_ws,),
        )
    conn.commit()
    conn.close()
    return conn


def _positive_card_balance(ws: str) -> None:
    get_ledger().append(
        ws,
        Transaction(
            date=date(2026, 8, 1), payee=None, narration="Saldo inicial (viejo signo)",
            postings=[Posting(account="Liabilities:CreditCard:Tarjeta", amount=Amount(amount="5000")),
                      Posting(account="Equity:Opening")],
            tags=["opening-balance"], meta={"pf_account_id": "acct-card"},
        ),
    )


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_legacy_db_is_upgraded_and_second_run_is_a_no_op():
    _old_db()
    conn = db.connect()
    assert {"kind", "archived"} <= _columns(conn, "pf_labels")
    assert "account_id" in _columns(conn, "pf_goals")
    assert "commitment_id" in _columns(conn, "pf_entries")
    kinds = {r[0]: r[1] for r in conn.execute("SELECT id, kind FROM pf_labels").fetchall()}
    assert kinds == {"lbl-1": "expense", "lbl-2": "income", "lbl-3": "transfer"}
    assert conn.execute("SELECT account_id FROM pf_goals WHERE id='goal-1'").fetchone()[0] == "acct-1"
    assert conn.execute("SELECT commitment_id FROM pf_entries WHERE id='ent-1'").fetchone()[0] is None
    indexes = {r[1] for r in conn.execute("PRAGMA index_list(pf_entries)").fetchall()}
    assert "ix_pf_entries_ws_commitment" in indexes
    rows = conn.execute(
        "SELECT version, name FROM core_schema_migrations WHERE module='pf' ORDER BY version"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        (1, "labels_kind_archived"), (2, "goals_account_id"), (3, "entries_commitment_id"), (4, "liability_sign"),
    ]
    applied_at = [r[0] for r in conn.execute("SELECT applied_at FROM core_schema_migrations WHERE module='pf'")]
    conn.close()

    db.reset_for_tests()
    conn = db.connect()
    again = [r[0] for r in conn.execute("SELECT applied_at FROM core_schema_migrations WHERE module='pf'")]
    assert again == applied_at
    assert conn.execute("SELECT COUNT(*) FROM core_schema_migrations WHERE module='pf'").fetchone()[0] == 4
    # the data survived and the old rows read back through the pf API
    from aurum.pf import labels

    rows = labels.list_labels("old-ws", include_archived=True)
    assert {r["name"] for r in rows} >= {"Comida", "Freelance", "Ahorro", "Sueldo/Nómina"}
    conn.close()


def test_liability_sign_correction_on_an_ordinary_workspace():
    _old_db(card_ws="old-ws")
    _positive_card_balance("old-ws")
    db.connect()
    bal = get_ledger().balances("old-ws")["Liabilities:CreditCard:Tarjeta"][0].amount
    assert str(bal) == "-5000.00"
    fix = [t for t in get_ledger().journal("old-ws") if "sign-migration" in t.tags]
    assert len(fix) == 1 and fix[0].meta["pf_account_id"] == "acct-card"


def test_protected_workspace_aborts_unless_env_allows(monkeypatch):
    monkeypatch.delenv("AURUM_MIGRATE_PROTECTED", raising=False)
    _old_db(card_ws="personal")
    _positive_card_balance("personal")
    with pytest.raises(RuntimeError):
        db.connect()
    assert str(get_ledger().balances("personal")["Liabilities:CreditCard:Tarjeta"][0].amount) == "5000.00"
    db.reset_for_tests()
    conn = sqlite3.connect(settings().db_path)
    versions = [r[0] for r in conn.execute("SELECT version FROM core_schema_migrations WHERE module='pf'")]
    conn.close()
    assert versions == [1, 2, 3]  # v4 rolled back, earlier ones kept

    monkeypatch.setenv("AURUM_MIGRATE_PROTECTED", "1")
    db.connect()
    assert str(get_ledger().balances("personal")["Liabilities:CreditCard:Tarjeta"][0].amount) == "-5000.00"


def test_fresh_database_records_all_versions_without_touching_the_ledger():
    conn = db.connect()
    versions = [r[0] for r in conn.execute("SELECT version FROM core_schema_migrations WHERE module='pf'")]
    assert versions == [1, 2, 3, 4]
    assert {"kind", "archived"} <= _columns(conn, "pf_labels")
