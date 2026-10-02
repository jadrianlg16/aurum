"""Liabilities: the person types what they owe as a positive number; the ledger stores liabilities negative."""

from __future__ import annotations

from decimal import Decimal

from aurum.core.money import Amount
from aurum.pf import accounts, accounts_admin, credit, entries, goals


def _card(ws="ws", owed="5000"):
    return accounts_admin.create_account(
        ws, accounts_admin.AccountIn(name="Tarjeta", type="credit_card", opening_balance=Amount(amount=owed),
                                     credit_limit=Amount(amount="20000"), cut_day=20, due_day=10, apr_percent="42"),
    )


def test_opening_balance_is_negated_and_rows_carry_owed(ledger):
    checking = accounts_admin.create_account(
        "ws", accounts_admin.AccountIn(name="Cheques", type="checking", opening_balance=Amount(amount="20000")),
    )
    cash = accounts_admin.create_account(
        "ws", accounts_admin.AccountIn(name="Efectivo", type="cash", opening_balance=Amount(amount="1200")),
    )
    card = _card()
    assert card["owed"] is True
    assert card["balance"]["amount"] == "5000.00" and card["balance_signed"]["amount"] == "-5000.00"
    assert card["opening_balance"]["amount"] == "5000.00" and card["opening_date"]
    assert card["ledger_account"] == card["account"] == "Liabilities:CreditCard:Tarjeta"
    assert card["apr"] == "0.42" and card["apr_percent"] == "42"
    assert checking["owed"] is False and checking["balance"]["amount"] == "20000.00"
    assert cash["opening_balance"]["amount"] == "1200.00"

    bal = ledger.balances("ws")
    assert bal["Liabilities:CreditCard:Tarjeta"][0].amount == Decimal("-5000")

    overview = accounts.get_accounts("ws")
    assert overview["net_worth"]["amount"] == "16200.00"
    assert len(overview["net_worth_series"]) == 12

    # an expense on the card raises what is owed; a transfer to the card lowers it, net worth unchanged
    entries.create_entry(
        "ws", entries.EntryIn(kind="expense", date="2026-09-05", amount=Amount(amount="300"), account_id=card["id"]),
    )
    assert accounts_admin.get_account("ws", card["id"])["balance"]["amount"] == "5300.00"
    assert accounts.get_accounts("ws")["net_worth"]["amount"] == "15900.00"
    entries.create_entry(
        "ws", entries.EntryIn(kind="transfer", date="2026-09-06", amount=Amount(amount="1000"),
                              account_id=checking["id"], to_account_id=card["id"]),
    )
    assert accounts_admin.get_account("ws", card["id"])["balance"]["amount"] == "4300.00"
    assert accounts_admin.get_account("ws", checking["id"])["balance"]["amount"] == "19000.00"
    assert accounts.get_accounts("ws")["net_worth"]["amount"] == "15900.00"


def test_negative_owed_is_422_and_adjust_takes_owed(ledger, client):
    r = client.post("/api/pf/ws/accounts", json={
        "name": "Tarjeta", "type": "credit_card", "opening_balance": {"amount": "-5000", "currency": "MXN"},
    })
    assert r.status_code == 422, r.text
    card = _card()
    r = client.post(f"/api/pf/ws/accounts/{card['id']}/adjust", json={"balance": {"amount": "4000", "currency": "MXN"}})
    assert r.status_code == 200, r.text
    assert r.json()["balance"]["amount"] == "4000.00" and r.json()["balance_signed"]["amount"] == "-4000.00"
    assert ledger.balances("ws")[card["account"]][0].amount == Decimal("-4000")
    r = client.post(f"/api/pf/ws/accounts/{card['id']}/adjust", json={"balance": {"amount": "-1", "currency": "MXN"}})
    assert r.status_code == 422


def test_card_status_and_debt_goal_read_owed(ledger):
    card = _card(owed="5000")
    status = credit.card_status("ws", credit.list_cards("ws")[0])
    assert status["owed"]["amount"] == "5000.00" and status["balance"]["amount"] == "-5000.00"
    assert Decimal(status["utilization"]) == Decimal("0.2500")
    assert status["pago_no_intereses"]["amount"] == "5000.00"

    g = goals.create_goal("ws", goals.Goal(kind="debt", name="Pagar tarjeta", target="5000", account_id=card["id"]))
    row = goals.goal_with_progress("ws", g)
    assert row["progress"]["amount"] == "0.00" and row["pct"] == 0.0
    checking = accounts_admin.create_account(
        "ws", accounts_admin.AccountIn(name="Cheques", type="checking", opening_balance=Amount(amount="9000")),
    )
    entries.create_entry(
        "ws", entries.EntryIn(kind="transfer", date="2026-09-06", amount=Amount(amount="2000"),
                              account_id=checking["id"], to_account_id=card["id"]),
    )
    row = goals.goal_with_progress("ws", g)
    assert row["progress"]["amount"] == "2000.00" and row["pct"] == 40.0


def test_loan_fields_round_trip(ledger):
    loan = accounts_admin.create_account(
        "ws", accounts_admin.AccountIn(name="Auto", type="loan", opening_balance=Amount(amount="100000"),
                                       apr_percent="12", loan_months=36, loan_principal=Amount(amount="120000")),
    )
    assert loan["owed"] is True and loan["balance"]["amount"] == "100000.00"
    assert loan["loan_months"] == 36 and loan["apr"] == "0.12"
    rows = credit.list_loans("ws")
    assert rows[0]["months"] == 36 and rows[0]["principal"] == "120000.00" and rows[0]["annual_rate"] == "0.12"
