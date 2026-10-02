"""The whole personal flow over HTTP on a fresh workspace, against the real Beancount store.

After every write: the ledger loads with zero errors (``beancount.loader.load_file``), and
``/api/ledger/{ws}/balances`` agrees with ``/api/pf/{ws}/accounts`` rows.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from beancount import loader
from fastapi.testclient import TestClient

from aurum.core.config import settings

pytestmark = pytest.mark.usefixtures("_tmp_data_dir")


@pytest.fixture
def client():
    from aurum.api.app import create_app

    return TestClient(create_app())


@pytest.fixture
def ws(client) -> str:
    r = client.post("/api/workspaces", json={"id": "t-flow", "name": "Flujo", "kind": "personal"})
    assert r.status_code == 200, r.text
    return "t-flow"


def _main(ws: str):
    return settings().workspace_dir(ws) / "main.beancount"


def _assert_clean(client: TestClient, ws: str) -> None:
    entries, errors, _ = loader.load_file(str(_main(ws)))
    assert errors == [], [str(e) for e in errors]
    balances = client.get(f"/api/ledger/{ws}/balances").json()
    rows = client.get(f"/api/pf/{ws}/accounts?include_archived=1").json()["accounts"]
    for row in rows:
        ledger_amount = next(
            (Decimal(a["amount"]) for a in balances.get(row["ledger_account"], []) if a["currency"] == row["currency"]),
            Decimal("0"),
        )
        assert Decimal(row["balance_signed"]["amount"]) == ledger_amount, row["name"]
        expected = -ledger_amount if row["owed"] else ledger_amount
        assert Decimal(row["balance"]["amount"]) == expected, row["name"]


def _post(client, path, body, status=200):
    r = client.post(path, json=body)
    assert r.status_code == status, (path, r.text)
    return r.json()


def test_personal_flow_end_to_end(client, ws):
    period = date.today().strftime("%Y-%m")
    today = date.today().isoformat()

    # accounts + liabilities (typed positive, stored signed)
    checking = _post(client, f"/api/pf/{ws}/accounts", {"name": "Cheques BBVA", "type": "checking", "institution": "BBVA",
                                                        "opening_balance": {"amount": "20000", "currency": "MXN"}})
    cash = _post(client, f"/api/pf/{ws}/accounts", {"name": "Efectivo", "type": "cash",
                                                    "opening_balance": {"amount": "1200", "currency": "MXN"}})
    card = _post(client, f"/api/pf/{ws}/accounts", {"name": "Tarjeta", "type": "credit_card", "cut_day": 20, "due_day": 10,
                                                    "apr_percent": "42", "credit_limit": {"amount": "30000", "currency": "MXN"},
                                                    "opening_balance": {"amount": "5000", "currency": "MXN"}})
    _assert_clean(client, ws)
    overview = client.get(f"/api/pf/{ws}/accounts").json()
    assert overview["net_worth"]["amount"] == "16200.00"
    assert card["owed"] is True and card["balance"]["amount"] == "5000.00" and card["balance_signed"]["amount"] == "-5000.00"
    assert client.get(f"/api/ledger/{ws}/balances").json()[card["ledger_account"]][0]["amount"] == "-5000.00"
    _post(client, f"/api/pf/{ws}/accounts", {"name": "Otra", "type": "credit_card",
                                             "opening_balance": {"amount": "-5000", "currency": "MXN"}}, status=422)

    # labels (kind, server-side accounts)
    labels = client.get(f"/api/pf/{ws}/labels?kind=income").json()
    assert any(lbl["name"] == "Sueldo/Nómina" for lbl in labels)
    gym = _post(client, f"/api/pf/{ws}/labels", {"name": "Gimnasio", "kind": "expense"})
    assert gym["account"] == "Expenses:Gimnasio"
    food = next(lbl for lbl in client.get(f"/api/pf/{ws}/labels?kind=expense").json() if lbl["name"] == "Comida fuera")
    salary = next(lbl for lbl in labels if lbl["name"] == "Sueldo/Nómina")

    # income stream (mirrors into organizer commitments)
    stream = _post(client, f"/api/pf/{ws}/income/streams", {
        "name": "Nómina Acme", "source_type": "salary", "amount": {"amount": "22500", "currency": "MXN"},
        "cadence": "semimonthly", "anchor_days": [15, 30], "account_id": checking["id"], "label_id": salary["id"]})
    assert stream["account_name"] == "Cheques BBVA" and len(stream["commitment_ids"]) == 2

    # budget + expense + void
    _post(client, f"/api/pf/{ws}/budgets", {"label_id": food["id"], "period": period, "amount": "2000"})
    e = _post(client, f"/api/pf/{ws}/entries", {"kind": "expense", "date": today, "amount": {"amount": "500", "currency": "MXN"},
                                                "account_id": cash["id"], "label_id": food["id"], "payee": "Tacos El Primo",
                                                "tags": ["tacos"]})
    _assert_clean(client, ws)
    assert e["amount"]["amount"] == "-500.00" and e["editable"] is True and e["non_editable_reason"] is None
    status = client.get(f"/api/pf/{ws}/budgets/status?period={period}").json()
    assert status["budgets"][0]["spent"]["amount"] == "500.00" and status["budgets"][0]["state"] == "ok"
    block = _main(ws).read_text(encoding="utf-8")
    expected = (
        f'{today} * "Tacos El Primo" "Tacos El Primo" #tacos ^{e["txn_id"]}\n'
        f'  pf_entry_id: "{e["id"]}"\n'
        f"  Expenses:Food:DiningOut                  500.00 MXN\n"
        f"  Assets:Cash                              -500.00 MXN\n"
    )
    assert expected in block, block[-600:]

    # edit: validate-then-write; one reversal + one new txn
    journal_len = len(client.get(f"/api/ledger/{ws}/journal").json())
    r = client.put(f"/api/pf/{ws}/entries/{e['id']}", json={"account_id": "nope"})
    assert r.status_code == 404 and len(client.get(f"/api/ledger/{ws}/journal").json()) == journal_len
    r = client.put(f"/api/pf/{ws}/entries/{e['id']}", json={"amount": {"amount": "300", "currency": "MXN"}})
    assert r.status_code == 200 and len(client.get(f"/api/ledger/{ws}/journal").json()) == journal_len + 2
    _assert_clean(client, ws)
    assert client.get(f"/api/pf/{ws}/budgets/status?period={period}").json()["budgets"][0]["spent"]["amount"] == "300.00"

    # delete → spent 0.00, second delete 409
    assert client.delete(f"/api/pf/{ws}/entries/{e['id']}").status_code == 200
    _assert_clean(client, ws)
    assert client.get(f"/api/pf/{ws}/budgets/status?period={period}").json()["budgets"][0]["spent"]["amount"] == "0.00"
    review = client.get(f"/api/pf/{ws}/review/{period}").json()
    assert review["top_labels"] == [] and review["expense"]["amount"] == "0.00"
    assert client.delete(f"/api/pf/{ws}/entries/{e['id']}").status_code == 409

    # card expense + transfer to the card; net worth unchanged by the transfer
    _post(client, f"/api/pf/{ws}/entries", {"kind": "expense", "date": today, "amount": {"amount": "300", "currency": "MXN"},
                                            "account_id": card["id"], "label_id": gym["id"], "payee": "Gym"})
    assert client.get(f"/api/pf/{ws}/accounts/{card['id']}").json()["balance"]["amount"] == "5300.00"
    _post(client, f"/api/pf/{ws}/entries", {"kind": "transfer", "date": today, "amount": {"amount": "1000", "currency": "MXN"},
                                            "account_id": checking["id"], "to_account_id": card["id"]})
    _assert_clean(client, ws)
    assert client.get(f"/api/pf/{ws}/accounts/{card['id']}").json()["balance"]["amount"] == "4300.00"
    assert client.get(f"/api/pf/{ws}/accounts").json()["net_worth"]["amount"] == "15900.00"
    adj = _post(client, f"/api/pf/{ws}/accounts/{card['id']}/adjust", {"balance": {"amount": "4000", "currency": "MXN"}})
    assert adj["balance"]["amount"] == "4000.00"
    _assert_clean(client, ws)

    # entries envelope + input hygiene
    page = client.get(f"/api/pf/{ws}/entries?limit=1").json()
    assert set(page) == {"entries", "next_cursor", "totals"} and page["totals"]["count"] == 2
    assert client.get(f"/api/pf/{ws}/entries?limit=501").status_code == 422
    before = _main(ws).read_bytes()
    _post(client, f"/api/pf/{ws}/entries", {"kind": "expense", "date": today, "amount": {"amount": "1", "currency": "MXN"},
                                            "account_id": cash["id"], "tags": ["a b"]}, status=400)
    _post(client, f"/api/pf/{ws}/entries", {"kind": "expense", "date": today, "amount": {"amount": 12.5, "currency": "MXN"},
                                            "account_id": cash["id"]}, status=422)
    _post(client, f"/api/pf/{ws}/entries", {"kind": "income", "date": today, "amount": {"amount": "1", "currency": "MXN"},
                                            "account_id": cash["id"], "label_id": food["id"]}, status=400)
    assert _main(ws).read_bytes() == before
    ok = _post(client, f"/api/pf/{ws}/entries", {"kind": "expense", "date": today, "amount": {"amount": "1", "currency": "mxn"},
                                                 "account_id": cash["id"]})
    assert ok["amount"]["currency"] == "MXN"
    _assert_clean(client, ws)

    # goals (by account id)
    savings = _post(client, f"/api/pf/{ws}/accounts", {"name": "Ahorro", "type": "savings",
                                                       "opening_balance": {"amount": "12000", "currency": "MXN"}})
    goal = _post(client, f"/api/pf/{ws}/goals", {"kind": "savings", "name": "Viaje", "target": "30000",
                                                 "target_date": f"{date.today().year + 1}-06-30", "account_id": savings["id"]})
    assert goal["account"].startswith("Assets:") and goal["account_name"] == "Ahorro"
    assert goal["progress"]["amount"] == "12000.00" and goal["pct"] == 40.0
    _post(client, f"/api/pf/{ws}/entries", {"kind": "transfer", "date": today, "amount": {"amount": "2000", "currency": "MXN"},
                                            "account_id": checking["id"], "to_account_id": savings["id"]})
    assert client.get(f"/api/pf/{ws}/goals").json()[0]["progress"]["amount"] == "14000.00"
    _assert_clean(client, ws)

    # quickadd + CSV write real entries
    qa = _post(client, f"/api/ingest/{ws}/quickadd", {"text": "250 tacos comida", "account_id": cash["id"], "commit": True})
    assert qa["status"] == "committed" and qa["entry"]["source"] == "quickadd" and qa["entry"]["editable"] is True
    csv_bytes = "\n".join(["Fecha,Concepto,Monto"] + [f"2026-09-{i:02d},COMPRA {i},-{10 * i}.00" for i in range(1, 11)]).encode()
    r = client.post(f"/api/ingest/{ws}/bank/csv", data={"bank": "BBVA", "account_id": checking["id"]},
                    files={"file": ("mov.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200 and r.json()["imported"] == 10 and r.json()["errors"] == []
    _assert_clean(client, ws)
    balances_before = client.get(f"/api/ledger/{ws}/balances").json()
    r = client.post(f"/api/ingest/{ws}/bank/csv", data={"bank": "BBVA", "account_id": checking["id"]},
                    files={"file": ("mov.csv", csv_bytes, "text/csv")})
    assert r.json()["skipped_duplicates"] == 10 and client.get(f"/api/ledger/{ws}/balances").json() == balances_before

    # onboarding
    ob = client.get(f"/api/pf/{ws}/onboarding").json()
    assert [s["id"] for s in ob["steps"]] == ["accounts", "income", "recurring", "first_entries"]
    assert ob["done"] is True
    # 4 live manual rows (card expense, 2 transfers, the "mxn" one) + 1 quickadd; the voided row and the 10
    # imported ones do not count
    assert {s["id"]: s["count"] for s in ob["steps"]}["first_entries"] == 5

    # health at the end of the whole flow
    _assert_clean(client, ws)
    health = client.get(f"/api/ledger/{ws}/health")
    if health.status_code == 200:  # the health route is optional here; do not depend on it
        assert health.json().get("error_count", 0) == 0
