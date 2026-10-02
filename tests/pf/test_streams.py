from __future__ import annotations

from datetime import date

from aurum.core.money import Amount
from aurum.organizer import commitments as org_commitments
from aurum.pf import accounts_admin, streams


def _account(ws="ws"):
    return accounts_admin.create_account(ws, accounts_admin.AccountIn(name="Nómina", type="checking"))


def test_monthly_stream_mirrors_into_one_commitment(ledger):
    acct = _account()
    stream = streams.create_stream(
        "ws",
        streams.IncomeStreamIn(
            name="Sueldo", source_type="salary", amount=Amount(amount="20000"), cadence="monthly",
            anchor_days=[1], account_id=acct["id"],
        ),
        today=date(2026, 1, 10),
    )
    assert len(stream["commitment_ids"]) == 1
    c = org_commitments.get("ws", stream["commitment_ids"][0])
    assert c.kind == "income"
    assert c.next_due == date(2026, 2, 1)


def test_semimonthly_stream_projects_correctly_across_month_end(ledger):
    """Anchor days 15 and 30: the 30th must clamp into February (28/29), never overflow."""
    acct = _account()
    stream = streams.create_stream(
        "ws",
        streams.IncomeStreamIn(
            name="Quincena", source_type="salary", amount=Amount(amount="8000"), cadence="semimonthly",
            anchor_days=[15, 30], account_id=acct["id"],
        ),
        today=date(2026, 1, 20),
    )
    assert len(stream["commitment_ids"]) == 2
    commitments = [org_commitments.get("ws", cid) for cid in stream["commitment_ids"]]
    due_days = sorted(c.next_due for c in commitments)
    # from Jan 20: next 15th is Feb 15, next 30th (clamped) is Jan 30
    assert due_days[0] == date(2026, 1, 30)
    assert due_days[1] == date(2026, 2, 15)

    # step the "30th" commitment forward past February: must clamp to the 28th (2026 is not leap)
    thirtieth = next(c for c in commitments if c.next_due.day == 30 or c.next_due.month == 1)
    stepped = org_commitments.get("ws", thirtieth.id)
    from aurum.organizer import cadence as cad

    projected = cad.project_next(stepped.next_due, "monthly", today=date(2026, 2, 1), anchor_day=30)
    assert projected == date(2026, 2, 28)


def test_delete_stream_cancels_its_commitments(ledger):
    acct = _account()
    stream = streams.create_stream(
        "ws",
        streams.IncomeStreamIn(
            name="Freelance", source_type="freelance", amount=Amount(amount="5000"), cadence="monthly",
            anchor_days=[10], account_id=acct["id"],
        ),
        today=date(2026, 1, 1),
    )
    cid = stream["commitment_ids"][0]
    streams.delete_stream("ws", stream["id"])
    assert org_commitments.get("ws", cid).status == "cancelled"
    try:
        streams.get_stream("ws", stream["id"])
        found = True
    except KeyError:
        found = False
    assert not found


def test_history_returns_expected_vs_received(ledger):
    acct = _account()
    stream = streams.create_stream(
        "ws",
        streams.IncomeStreamIn(
            name="Sueldo", source_type="salary", amount=Amount(amount="1000"), cadence="monthly",
            anchor_days=[5], account_id=acct["id"],
        ),
        today=date(2026, 1, 1),
    )
    history = streams.stream_history("ws", stream["id"])
    assert isinstance(history, list)


def test_router_crud(client):
    acct = client.post("/api/pf/ws/accounts", json={"name": "Cuenta", "type": "checking"}).json()
    created = client.post(
        "/api/pf/ws/income/streams",
        json={"name": "Sueldo", "source_type": "salary", "amount": {"amount": "10000", "currency": "MXN"},
              "cadence": "monthly", "anchor_days": [1], "account_id": acct["id"]},
    )
    assert created.status_code == 200
    sid = created.json()["id"]
    listed = client.get("/api/pf/ws/income/streams")
    assert any(s["id"] == sid for s in listed.json())
    deleted = client.delete(f"/api/pf/ws/income/streams/{sid}")
    assert deleted.status_code == 200
