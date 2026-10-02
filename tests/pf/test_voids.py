"""Void semantics: deleted/edited entries never count anywhere (budgets, review, goals, income, recurring)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from aurum.core.money import Amount
from aurum.pf import accounts, accounts_admin, budgets, entries, goals, income, labels, review

PERIOD = "2026-09"


def _setup(ws="ws"):
    acct = accounts_admin.create_account(ws, accounts_admin.AccountIn(name="Efectivo", type="cash"))
    food = next(x for x in labels.list_labels(ws) if x["name"] == "Comida fuera")
    budgets.create_budget(ws, budgets.Budget(label_id=food["id"], period=PERIOD, amount="2000"))
    return acct, food


def _spent(ws="ws") -> str:
    return budgets.budget_status(ws, PERIOD)["budgets"][0]["spent"]["amount"]


def test_delete_drops_spent_to_zero_everywhere(ledger, client):
    acct, food = _setup()
    e = entries.create_entry(
        "ws",
        entries.EntryIn(kind="expense", date=f"{PERIOD}-05", amount=Amount(amount="250"),
                        account_id=acct["id"], label_id=food["id"], payee="Tacos"),
    )
    assert _spent() == "250.00"
    rev = review.monthly_review("ws", PERIOD)
    assert rev["expense"]["amount"] == "250.00" and rev["top_labels"] == [{"label": "Comida fuera", "amount": "250.00"}]

    entries.delete_entry("ws", e["id"])
    assert _spent() == "0.00"
    rev = review.monthly_review("ws", PERIOD)
    assert rev["expense"]["amount"] == "0.00" and rev["top_labels"] == []
    # the ledger keeps both sides; only the live view hides them
    assert len(ledger.journal("ws")) == 2
    assert Decimal(accounts_admin.get_account("ws", acct["id"])["balance"]["amount"]) == 0

    r = client.delete(f"/api/pf/ws/entries/{e['id']}")
    assert r.status_code == 409


def test_edit_counts_only_the_new_amount(ledger):
    acct, food = _setup()
    e = entries.create_entry(
        "ws",
        entries.EntryIn(kind="expense", date=f"{PERIOD}-05", amount=Amount(amount="250"),
                        account_id=acct["id"], label_id=food["id"], payee="Tacos"),
    )
    entries.update_entry("ws", e["id"], entries.merge_patch(
        entries._fetch_row("ws", e["id"]), entries.EntryPatch(amount=Amount(amount="300"))))
    assert _spent() == "300.00"
    assert len(ledger.journal("ws")) == 3  # original + reversal + new
    assert Decimal(accounts_admin.get_account("ws", acct["id"])["balance"]["amount"]) == Decimal("-300")


def test_income_goals_and_recurring_ignore_voids(ledger):
    acct, _ = _setup()
    salary = next(x for x in labels.list_labels("ws") if x["name"] == "Sueldo/Nómina")
    inc = entries.create_entry(
        "ws",
        entries.EntryIn(kind="income", date=f"{PERIOD}-01", amount=Amount(amount="20000"),
                        account_id=acct["id"], label_id=salary["id"], payee="Nomina"),
    )
    assert income.get_income("ws", months=1, today=date(2026, 9, 15))["months"][0]["gross"]["amount"] == "20000.00"
    entries.delete_entry("ws", inc["id"])
    assert income.get_income("ws", months=1, today=date(2026, 9, 15))["months"][0]["gross"]["amount"] == "0.00"

    # recurring detection: three Netflix rows, one voided → no longer "same amount, monthly"
    ids = []
    for m in (6, 7, 8):
        ids.append(entries.create_entry(
            "ws", entries.EntryIn(kind="expense", date=f"2026-{m:02d}-05", amount=Amount(amount="199"),
                                  account_id=acct["id"], payee="Netflix"),
        )["id"])
    assert any(b["payee"] == "Netflix" for b in accounts.detect_recurring("ws", today=date(2026, 9, 1)))
    entries.delete_entry("ws", ids[1])
    assert not any(b["payee"] == "Netflix" for b in accounts.detect_recurring("ws", today=date(2026, 9, 1)))

    # emergency-fund months of spend: voided expenses do not inflate the average
    avg_before = goals._avg_monthly_spend("ws", months=3, today=date(2026, 9, 15))
    big = entries.create_entry(
        "ws", entries.EntryIn(kind="expense", date="2026-08-20", amount=Amount(amount="9000"), account_id=acct["id"]),
    )
    assert goals._avg_monthly_spend("ws", months=3, today=date(2026, 9, 15)) > avg_before
    entries.delete_entry("ws", big["id"])
    assert goals._avg_monthly_spend("ws", months=3, today=date(2026, 9, 15)) == avg_before
