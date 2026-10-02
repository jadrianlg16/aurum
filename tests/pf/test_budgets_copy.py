"""POST /budgets/copy is idempotent; status follows the stable shape with ok/warn/over states."""

from __future__ import annotations

from aurum.core.money import Amount
from aurum.pf import accounts_admin, budgets, entries, labels

PREV, CUR = "2026-08", "2026-09"


def _labels(ws="ws"):
    rows = labels.list_labels(ws)
    return {r["name"]: r for r in rows}


def test_copy_is_idempotent_and_skips_archived(ledger, client):
    by = _labels()
    for name in ("Comida fuera", "Súper", "Ropa"):
        budgets.create_budget("ws", budgets.Budget(label_id=by[name]["id"], period=PREV, amount="1000"))
    r = client.post("/api/pf/ws/budgets/copy", json={"from": PREV, "to": CUR})
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 3, "skipped": 0, "period": CUR}
    r = client.post("/api/pf/ws/budgets/copy", json={"from": PREV, "to": CUR})
    assert r.json() == {"created": 0, "skipped": 3, "period": CUR}
    assert len(budgets.list_budgets("ws", CUR)) == 3

    labels.update_label("ws", by["Ropa"]["id"], labels.LabelPatch(archived=True))
    r = client.post("/api/pf/ws/budgets/copy", json={"from": PREV, "to": "2026-10"})
    assert r.json() == {"created": 2, "skipped": 1, "period": "2026-10"}
    assert client.post("/api/pf/ws/budgets/copy", json={"from": "2026-8", "to": CUR}).status_code == 422


def test_status_shape_states_and_totals(ledger, client):
    by = _labels()
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Efectivo", type="cash"))
    budgets.create_budget("ws", budgets.Budget(label_id=by["Comida fuera"]["id"], period=PREV, amount="1000"))
    budgets.create_budget("ws", budgets.Budget(label_id=by["Comida fuera"]["id"], period=CUR, amount="1000"))
    budgets.create_budget("ws", budgets.Budget(label_id=by["Súper"]["id"], period=CUR, amount="2000"))

    def log(label, amount, day=5):
        entries.create_entry("ws", entries.EntryIn(kind="expense", date=f"{CUR}-{day:02d}", amount=Amount(amount=amount),
                                                   account_id=acct["id"], label_id=by[label]["id"]))

    log("Comida fuera", "850")
    log("Súper", "2100")
    r = client.get(f"/api/pf/ws/budgets/status?period={CUR}")
    assert r.status_code == 200, r.text
    status = r.json()
    assert status["period"] == CUR and status["currency"] == "MXN"
    assert status["has_previous"] is True and status["previous_period"] == PREV
    rows = {b["label_name"]: b for b in status["budgets"]}
    food = rows["Comida fuera"]
    assert set(food) >= {"budget_id", "label_id", "label_name", "icon", "budget", "carried", "effective", "spent",
                         "remaining", "pct", "state", "rollover", "alert", "explain"}
    assert food["spent"]["amount"] == "850.00" and food["pct"] == 85.0 and food["state"] == "warn" and food["alert"] == "80"
    assert food["carried"]["amount"] == "0.00" and food["effective"]["amount"] == "1000.00"
    assert rows["Súper"]["state"] == "over" and rows["Súper"]["remaining"]["amount"] == "-100.00"
    assert status["totals"] == {
        "budget": {"amount": "3000.00", "currency": "MXN"},
        "spent": {"amount": "2950.00", "currency": "MXN"},
        "remaining": {"amount": "50.00", "currency": "MXN"},
    }
    assert status["safe_to_spend"]["amount"] == "150.00"
    assert "explain" in status

    prev = client.get(f"/api/pf/ws/budgets/status?period={PREV}").json()
    assert prev["has_previous"] is False and prev["previous_period"] is None
    assert prev["budgets"][0]["state"] == "ok" and prev["budgets"][0]["pct"] == 0.0


def test_duplicate_budget_is_409_and_unknown_label_404(ledger, client):
    by = _labels()
    body = {"label_id": by["Ropa"]["id"], "period": CUR, "amount": "100"}
    assert client.post("/api/pf/ws/budgets", json=body).status_code == 200
    assert client.post("/api/pf/ws/budgets", json=body).status_code == 409
    assert client.post("/api/pf/ws/budgets", json={**body, "label_id": "nope"}).status_code == 404
    assert client.post("/api/pf/ws/budgets", json={**body, "amount": "-1"}).status_code == 400
    assert client.post("/api/pf/ws/budgets", json={**body, "period": "2026/09"}).status_code == 422


def test_rollover_carries_the_unspent_prior_amount(ledger):
    by = _labels()
    acct = accounts_admin.create_account("ws", accounts_admin.AccountIn(name="Efectivo", type="cash"))
    budgets.create_budget("ws", budgets.Budget(label_id=by["Ropa"]["id"], period=PREV, amount="500", rollover=True))
    budgets.create_budget("ws", budgets.Budget(label_id=by["Ropa"]["id"], period=CUR, amount="500", rollover=True))
    entries.create_entry("ws", entries.EntryIn(kind="expense", date=f"{PREV}-10", amount=Amount(amount="200"),
                                               account_id=acct["id"], label_id=by["Ropa"]["id"]))
    row = budgets.budget_status("ws", CUR)["budgets"][0]
    assert row["carried"]["amount"] == "300.00" and row["effective"]["amount"] == "800.00" and row["rollover"] is True
