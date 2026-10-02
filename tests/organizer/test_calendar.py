"""Bills calendar and occurrence marking."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from aurum.organizer import calendar_view, detect, occurrences

from .conftest import TODAY, WS


def _netflix():
    for candidate in detect.detect(WS, today=TODAY):
        if candidate.merchant == "NETFLIX":
            return detect.accept(WS, candidate.id, today=TODAY)
    raise AssertionError("Netflix was not detected")


def test_a_seeded_charge_marks_its_day_paid(demo) -> None:
    netflix = _netflix()
    # demo_org posts Netflix on the 15th; TODAY is the 15th, so this month's charge is in the ledger.
    days = calendar_view.calendar(WS, TODAY - timedelta(days=40), TODAY, today=TODAY)["days"]
    netflix_items = [
        item for day in days for item in day["items"] if item.get("id") == netflix.id
    ]
    assert netflix_items, "Netflix produced no calendar items"
    paid = [i for i in netflix_items if i["status"] == "paid"]
    assert paid, [i["status"] for i in netflix_items]
    assert paid[-1]["txn_id"] is not None
    assert paid[-1]["txn_id"].startswith("org-demo-netflix-")


def test_matching_needs_the_amount_and_the_date_window(demo) -> None:
    netflix = _netflix()
    due = date(2026, 9, 15)
    assert occurrences.find_matching_txn(WS, netflix, due) is not None
    # 10 days away is outside the ±3-day window
    assert occurrences.find_matching_txn(WS, netflix, due + timedelta(days=10)) is None
    # a wildly different expected amount fails the ±10% test
    wrong = netflix.model_copy(update={"amount": netflix.amount.model_copy(update={"amount": Decimal("999")})})
    assert occurrences.find_matching_txn(WS, wrong, due) is None


def test_unpaid_future_occurrence_is_upcoming(demo) -> None:
    netflix = _netflix()
    future = occurrences.build(WS, netflix, TODAY + timedelta(days=20), TODAY + timedelta(days=40),
                               today=TODAY)
    assert future and all(o.status == "upcoming" for o in future)


def test_manual_mark_overrides_the_derived_status(demo) -> None:
    netflix = _netflix()
    due = TODAY + timedelta(days=30)
    occurrences.mark(WS, netflix.id, due, "skipped")
    built = occurrences.build(WS, netflix, due, due, today=TODAY)
    assert [o.status for o in built] == ["skipped"]


def test_calendar_totals_and_explain(demo) -> None:
    _netflix()
    payload = calendar_view.calendar(WS, TODAY, TODAY + timedelta(days=45), today=TODAY)
    assert payload["days"]
    for day in payload["days"]:
        expected_out = sum(
            (Decimal(i["amount"]["amount"]) for i in day["items"]
             if i["kind"] in ("commitment", "loan", "card_due") and i["status"] != "skipped"),
            Decimal("0"),
        )
        assert Decimal(day["total_out"]["amount"]) == expected_out
    assert payload["explain"]["summary"]
    labels = {s["label"] for s in payload["explain"]["steps"]}
    assert {"range", "days_with_items", "paid_match_rule"} <= labels


def test_calendar_includes_card_and_income_rows(demo) -> None:
    for candidate in detect.detect(WS, today=TODAY):
        if candidate.merchant == "NOMINA ACME":
            detect.accept(WS, candidate.id, today=TODAY)
    payload = calendar_view.calendar(WS, TODAY, TODAY + timedelta(days=45), today=TODAY)
    kinds = {i["kind"] for day in payload["days"] for i in day["items"]}
    assert "income" in kinds
    assert {"card_cut", "card_due"} & kinds


def test_router_mark_paid(client) -> None:
    created = client.post(
        "/api/organizer/demo-mx/quickadd?save=1", json={"text": "notion 199 mensual día 9"}
    ).json()
    due = created["next_due"]
    r = client.post(
        f"/api/organizer/demo-mx/occurrences/{created['id']}/{due}/mark", json={"status": "paid"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


def test_router_rejects_a_bad_status_and_date(client) -> None:
    """The legacy alias only accepts paid|skipped and validates the date → 422."""
    listed = client.get("/api/organizer/demo-mx/commitments").json()
    cid = listed[0]["id"]
    assert client.post(
        f"/api/organizer/demo-mx/occurrences/{cid}/2026-09-15/mark", json={"status": "nope"}
    ).status_code == 422
    assert client.post(
        f"/api/organizer/demo-mx/occurrences/{cid}/2026-09-15/mark", json={"status": "upcoming"}
    ).status_code == 422
    assert client.post(
        f"/api/organizer/demo-mx/occurrences/{cid}/not-a-date/mark", json={"status": "paid"}
    ).status_code == 422


def test_router_calendar_range_validation(client) -> None:
    ok = client.get("/api/organizer/demo-mx/calendar?from=2026-09-01&to=2026-09-30")
    assert ok.status_code == 200
    bad = client.get("/api/organizer/demo-mx/calendar?from=2026-09-30&to=2026-09-01")
    assert bad.status_code == 400
    assert client.get("/api/organizer/demo-mx/calendar?from=2026-13-01").status_code == 422
    too_long = client.get("/api/organizer/demo-mx/calendar?from=2026-01-01&to=2028-02-01")
    assert too_long.status_code == 422
    assert too_long.json()["detail"] == "range must be 24 months or less"


def test_calendar_items_carry_account_and_no_tax_rows_in_simple_mode(client) -> None:
    """A simple-mode workspace with modules.tax off gets no tax rows. demo-mx seeds with tax on
    (it is the RESICO demo), so the flag is switched off here first — the gate is what is under test."""
    from aurum.core.workspaces import get_workspace, save_workspace

    ws = get_workspace("demo-mx")
    ws.modules.tax = False
    save_workspace(ws)
    payload = client.get("/api/organizer/demo-mx/calendar?from=2026-09-01&to=2026-09-30").json()
    kinds = {i["kind"] for day in payload["days"] for i in day["items"]}
    assert "tax" not in kinds
    commitment_items = [i for day in payload["days"] for i in day["items"] if i["kind"] in ("commitment", "income")]
    assert commitment_items
    for item in commitment_items:
        assert {"account_id", "account_name", "entry_id"} <= set(item)
