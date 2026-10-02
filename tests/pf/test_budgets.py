from __future__ import annotations

from datetime import date

from aurum.pf import budgets, labels
from tests.pf.helpers import post


def test_budget_status_computes_spent_remaining_alert(ledger):
    lbls = labels.list_labels("ws")
    food = next(x for x in lbls if x["name"] == "Comida fuera")
    budgets.create_budget("ws", budgets.Budget(label_id=food["id"], period="2026-08", amount="1000"))
    post(ledger, "ws", date(2026, 8, 5), "Tacos", food["account"], "850")

    status = budgets.budget_status("ws", "2026-08")
    row = status["budgets"][0]
    assert row["spent"]["amount"] == "850.00"
    assert row["remaining"]["amount"] == "150.00"
    assert row["alert"] == "80" and row["state"] == "warn" and row["pct"] == 85.0
    assert "explain" in row
    assert status["totals"]["spent"]["amount"] == "850.00" and status["currency"] == "MXN"


def test_budget_status_100_alert_and_safe_to_spend(ledger):
    lbls = labels.list_labels("ws")
    food = next(x for x in lbls if x["name"] == "Súper")
    budgets.create_budget("ws", budgets.Budget(label_id=food["id"], period="2026-09", amount="500"))
    post(ledger, "ws", date(2026, 9, 5), "Super", food["account"], "600")
    status = budgets.budget_status("ws", "2026-09")
    row = status["budgets"][0]
    assert row["alert"] == "100" and row["state"] == "over"
    assert status["safe_to_spend"]["amount"] == "0.00"


def test_budget_router_crud(client):
    lbls = client.get("/api/pf/ws2/labels").json()
    label_id = lbls[0]["id"]
    r = client.post("/api/pf/ws2/budgets", json={"label_id": label_id, "period": "2026-08", "amount": "100"})
    assert r.status_code == 200
    budget_id = r.json()["id"]
    r = client.get("/api/pf/ws2/budgets?period=2026-08")
    assert len(r.json()) == 1
    assert r.json()[0]["amount"] == {"amount": "100.00", "currency": "MXN"} and r.json()[0]["label_name"]
    r = client.delete(f"/api/pf/ws2/budgets/{budget_id}")
    assert r.status_code == 200
