"""Bank CSV import: lines become pf entries on a required account, deduped by line hash."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aurum.core.db import connect
from aurum.ingest import bank_csv
from aurum.pf import accounts_admin, entries

CSV_TEXT = """Fecha,Concepto,Monto,Saldo
2026-08-01,OXXO COMPRA,-150.00,5000.00
2026-08-02,DEPOSITO NOMINA,20000.00,25000.00
2026-08-01,OXXO COMPRA,-150.00,5000.00
"""


def _account(ws, name="BBVA Débito"):
    return accounts_admin.create_account(ws, accounts_admin.AccountIn(name=name, type="checking"))


def test_detect_mapping_and_import_writes_entries():
    acct = _account("demo")
    result = bank_csv.import_csv("demo", "BBVA", CSV_TEXT.encode("utf-8"), account_id=acct["id"], base_currency="MXN")
    assert result["imported"] == 2 and len(result["created"]) == 2  # third row is a dupe of the first
    assert result["skipped_duplicates"] == 1 and result["errors"] == []
    assert "inbox_items" not in result

    conn = connect()
    rows = conn.execute("SELECT * FROM ingest_bank_lines WHERE ws_id='demo'").fetchall()
    conn.close()
    assert len(rows) == 2
    amounts = sorted(Decimal(r["amount"]) for r in rows)
    assert amounts == [Decimal("-150.00"), Decimal("20000.00")]

    page = entries.list_entries("demo")
    by_payee = {r["payee"]: r for r in page["entries"]}
    assert by_payee["OXXO COMPRA"]["amount"]["amount"] == "-150.00"
    assert by_payee["OXXO COMPRA"]["kind"] == "expense" and by_payee["OXXO COMPRA"]["editable"] is True
    assert by_payee["DEPOSITO NOMINA"]["kind"] == "income" and by_payee["DEPOSITO NOMINA"]["label_name"] == "Sueldo/Nómina"
    assert set(by_payee["OXXO COMPRA"]["tags"]) == {"import", "csv-bbva"}
    assert all(r["source"] == "import" for r in page["entries"])
    assert Decimal(accounts_admin.get_account("demo", acct["id"])["balance"]["amount"]) == Decimal("19850.00")


def test_reimport_is_a_no_op():
    acct = _account("demo")
    bank_csv.import_csv("demo", "BBVA", CSV_TEXT.encode("utf-8"), account_id=acct["id"])
    again = bank_csv.import_csv("demo", "BBVA", CSV_TEXT.encode("utf-8"), account_id=acct["id"])
    assert again["imported"] == 0 and again["skipped_duplicates"] == 3
    assert entries.list_entries("demo")["totals"]["count"] == 2


def test_mapping_is_remembered():
    acct = _account("demo")
    bank_csv.import_csv("demo", "BBVA", CSV_TEXT.encode("utf-8"), account_id=acct["id"])
    mapping = bank_csv.load_mapping("demo", "BBVA")
    assert mapping is not None
    assert mapping.date and mapping.description


def test_debit_credit_columns():
    acct = _account("demo2", "Santander")
    csv_text = "Date,Description,Debit,Credit\n2026-08-05,Rent,1000.00,\n2026-08-06,Salary,,3000.00\n"
    result = bank_csv.import_csv("demo2", "Santander", csv_text.encode("utf-8"), account_id=acct["id"])
    assert result["imported"] == 2
    conn = connect()
    rows = {r["description"]: Decimal(r["amount"]) for r in conn.execute(
        "SELECT * FROM ingest_bank_lines WHERE ws_id='demo2'"
    ).fetchall()}
    conn.close()
    assert rows["Rent"] == Decimal("-1000.00")
    assert rows["Salary"] == Decimal("3000.00")


def test_bad_lines_are_reported_not_swallowed_and_stay_reimportable():
    acct = _account("demo3")
    csv_text = "Fecha,Concepto,Monto\n2026-08-01,OXXO,-50.00\nno-date,Basura,-10\n2026-08-03,Cero,0\n2026-08-04,Raro,abc\n"
    result = bank_csv.import_csv("demo3", "BBVA", csv_text.encode("utf-8"), account_id=acct["id"])
    assert result["imported"] == 1
    assert [e["line"] for e in result["errors"]] == [3, 4, 5]
    assert "date" in result["errors"][0]["detail"]
    conn = connect()
    (n,) = conn.execute("SELECT COUNT(*) FROM ingest_bank_lines WHERE ws_id='demo3'").fetchone()
    conn.close()
    assert n == 1


def test_unknown_account_is_a_key_error_with_nothing_written():
    with pytest.raises(KeyError):
        bank_csv.import_csv("demo4", "BBVA", CSV_TEXT.encode("utf-8"), account_id="nope")
    conn = connect()
    (n,) = conn.execute("SELECT COUNT(*) FROM ingest_bank_lines WHERE ws_id='demo4'").fetchone()
    conn.close()
    assert n == 0
