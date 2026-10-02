from __future__ import annotations

from datetime import date
from decimal import Decimal

from aurum.pf import credit
from tests.pf.helpers import post


def test_card_status_balance_and_utilization(ledger):
    card = credit.create_card(
        "ws",
        credit.CreditCard(account="Liabilities:CreditCard:Visa", name="Visa", cut_day=15, due_day=5,
                           limit_amount="20000"),
    )
    post(ledger, "ws", date(2026, 8, 3), "Amazon", "Expenses:Personal:Clothing", "5000",
         asset_account="Liabilities:CreditCard:Visa")
    status = credit.card_status("ws", card, today=date(2026, 8, 10))
    assert status["balance"]["amount"] == "-5000.00"
    assert status["owed"]["amount"] == "5000.00"
    assert Decimal(status["utilization"]) == Decimal("0.2500")
    assert status["next_cut_date"] == "2026-08-15"


def test_loan_amortization_and_whatif(ledger):
    loan = credit.create_loan(
        "ws",
        credit.Loan(account="Liabilities:Loan:Personal", name="Personal", principal="50000", annual_rate="0.18",
                    months=24, start=date.today().isoformat()),
    )
    am = credit.loan_amortization("ws", loan["id"])
    assert len(am["rows"]) == 24
    assert Decimal(am["rows"][-1]["balance"]) == Decimal("0.00")

    whatif = credit.loan_whatif("ws", loan["id"], Decimal("500"))
    assert whatif["months_to_payoff"] < 24
    assert Decimal(whatif["interest_saved"]["amount"]) > 0


def test_msi_schedule():
    card = credit.create_card(
        "ws", credit.CreditCard(account="Liabilities:CreditCard:Amex", name="Amex", cut_day=1, due_day=20,
                                 limit_amount="30000")
    )
    credit.create_msi(
        "ws", credit.MSI(card_id=card["id"], purchase="TV", amount="6000", months=6, started="2026-06-01",
                          paid_months=2)
    )
    schedules = credit._msi_for_card("ws", card["id"])
    assert schedules[0]["monthly"] == "1000.00"
    assert schedules[0]["remaining_months"] == 4


def test_credit_score_crud(client):
    r = client.post("/api/pf/ws4/credit/scores", json={"bureau": "Buro", "score": 720, "date": "2026-08-01"})
    assert r.status_code == 200
    score_id = r.json()["id"]
    r = client.get("/api/pf/ws4/credit/scores")
    assert len(r.json()) == 1
    r = client.delete(f"/api/pf/ws4/credit/scores/{score_id}")
    assert r.status_code == 200
