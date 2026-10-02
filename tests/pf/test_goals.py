from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from aurum.core.money import Amount
from aurum.ledger.base import Posting, Transaction
from aurum.pf import credit, goals


def test_goal_monthly_required_and_progress(ledger):
    ledger.append(
        "ws",
        Transaction(
            date=date.today(),
            payee=None,
            narration="seed savings",
            postings=[
                Posting(account="Assets:Savings:Vacation", amount=Amount(amount="2000")),
                Posting(account="Assets:Bank:Checking"),
            ],
        ),
    )
    target_date = (date.today() + timedelta(days=90)).isoformat()
    g = goals.create_goal(
        "ws",
        goals.Goal(kind="savings", name="Vacation", target="10000", target_date=target_date,
                   account="Assets:Savings:Vacation"),
    )
    out = goals.goal_with_progress("ws", g)
    assert out["progress"]["amount"] == "2000.00"
    assert out["pct"] == 20.0 and out["account_id"] is None
    assert Decimal(out["monthly_required"]["amount"]) > 0
    assert "explain" in out


def test_debt_whatif_reduces_interest(ledger):
    loan = credit.create_loan(
        "ws",
        credit.Loan(account="Liabilities:Loan:Auto", name="Auto", principal="100000", annual_rate="0.12",
                    months=12, start=date.today().isoformat()),
    )
    g = goals.create_goal(
        "ws", goals.Goal(kind="debt", name="Pay off auto", target="0", account="Liabilities:Loan:Auto")
    )
    result = goals.debt_whatif("ws", g["id"], Decimal("1000"))
    assert Decimal(result["interest_saved"]["amount"]) > 0
    assert result["months_to_payoff"] <= loan["months"]


def test_goals_router_crud(client):
    r = client.post(
        "/api/pf/ws3/goals",
        json={"kind": "purchase", "name": "Laptop", "target": "20000", "account": "Assets:Savings:Laptop"},
    )
    assert r.status_code == 200
    goal_id = r.json()["id"]
    r = client.get("/api/pf/ws3/goals")
    assert any(g["id"] == goal_id for g in r.json())
    r = client.delete(f"/api/pf/ws3/goals/{goal_id}")
    assert r.status_code == 200
