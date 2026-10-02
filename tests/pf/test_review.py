from __future__ import annotations

from datetime import date

from aurum.pf import review
from tests.pf.helpers import income as post_income
from tests.pf.helpers import post


def test_monthly_review_income_expense_and_anomaly(ledger):
    for m in (5, 6, 7):
        post(ledger, "ws", date(2026, m, 5), "Super", "Expenses:Food:Groceries", "1000")
    post(ledger, "ws", date(2026, 8, 5), "Super", "Expenses:Food:Groceries", "5000")
    post_income(ledger, "ws", date(2026, 8, 1), "Nomina", "Income:Salary", "20000")

    out = review.monthly_review("ws", "2026-08")
    assert out["income"]["amount"] == "20000.00"
    assert out["expense"]["amount"] == "5000.00"
    assert out["upcoming_bills"] == []
    assert any(a["label"] == "Súper" for a in out["anomalies"])
    assert "explain" in out


def test_review_router(client):
    r = client.get("/api/pf/ws5/review/2026-08")
    assert r.status_code == 200
    assert r.json()["period"] == "2026-08"
    assert client.get("/api/pf/ws5/review/2026-13").status_code == 422
