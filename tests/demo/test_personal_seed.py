"""The ``demo-personal`` seed."""

from __future__ import annotations

from datetime import date

import pytest

from aurum.core.workspaces import get_workspace
from aurum.demo.personal import WS_ID, seed_demo_personal, stamp_demos
from aurum.ledger.beancount_store import BeancountLedger
from aurum.pf import entries as pf_entries
from aurum.pf import onboarding

TODAY = date(2026, 9, 15)


@pytest.fixture
def seeded() -> dict:
    return seed_demo_personal(today=TODAY)


def test_workspace_and_accounts(seeded):
    ws = get_workspace(WS_ID)
    assert ws.kind == "personal"
    assert ws.profile["demo"] is True
    assert ws.profile["demo_seed"]["version"] == 1
    from aurum.pf import accounts_admin

    accounts = accounts_admin.list_accounts(WS_ID)
    assert len(accounts) == 4
    names = {a["name"] for a in accounts}
    assert names == {"BBVA Nómina", "Efectivo", "Ahorro viaje", "Nu"}
    card = next(a for a in accounts if a["name"] == "Nu")
    assert card["type"] == "credit_card"


def test_stream_and_commitments(seeded):
    from aurum.pf import streams as pf_streams

    streams = pf_streams.list_streams(WS_ID)
    assert len(streams) == 1
    assert streams[0]["name"] == "Sueldo"

    from aurum.organizer import commitments as org_commitments

    commitments = org_commitments.list_commitments(WS_ID)
    non_income = [c for c in commitments if c.kind != "income"]
    assert len(non_income) >= 4
    names = {c.name for c in non_income}
    assert {"Renta", "Netflix", "Telcel", "Gym"} <= names


def test_budgets_and_goal(seeded):
    from aurum.pf import budgets as pf_budgets
    from aurum.pf import goals as pf_goals

    budgets = pf_budgets.list_budgets(WS_ID)
    assert len(budgets) == 6  # 3 labels x 2 periods

    goals = pf_goals.list_goals(WS_ID)
    assert len(goals) == 1
    assert goals[0]["name"] == "Viaje a Japón"


def test_entries_are_all_editable_and_at_least_forty(seeded):
    rows = pf_entries.list_entries(WS_ID, limit=500)
    rows = rows.get("entries", rows) if isinstance(rows, dict) else rows
    assert len(rows) >= 40
    assert all(r["editable"] for r in rows)


def test_onboarding_reports_done(seeded):
    status = onboarding.get_onboarding(WS_ID) if hasattr(onboarding, "get_onboarding") else None
    if status is None:
        pytest.skip("onboarding module shape not available yet")
    assert status.get("done") is True


def test_ledger_loads_without_errors():
    ledger = BeancountLedger()
    _, errors = ledger.load(WS_ID)
    assert errors == []


def test_second_run_is_idempotent(seeded):
    before = pf_entries.list_entries(WS_ID, limit=500)
    before = before.get("entries", before) if isinstance(before, dict) else before
    result = seed_demo_personal(today=TODAY)
    assert result["status"] == "already-seeded"
    after = pf_entries.list_entries(WS_ID, limit=500)
    after = after.get("entries", after) if isinstance(after, dict) else after
    assert len(before) == len(after)

    from aurum.pf import accounts_admin

    assert len(accounts_admin.list_accounts(WS_ID)) == 4


def test_stamp_demos_sets_profile_demo_and_skips_demo_biz():
    from aurum.core.workspaces import Workspace, save_workspace

    save_workspace(Workspace(id="demo-foo", name="Demo Foo", profile={}))
    save_workspace(Workspace(id="demo-biz", name="Demo Biz", profile={"synthetic": True}))
    stamped = stamp_demos()
    assert "demo-foo" in stamped
    assert "demo-biz" not in stamped
    assert get_workspace("demo-foo").profile["demo"] is True
    assert "demo" not in get_workspace("demo-biz").profile

def test_reanchor_demo_trials_moves_only_expired_trials_of_a_demo_workspace():
    """A demo trial seeded weeks ago has expired; --refresh moves it to today + 5 so the alert showcase
    survives. Real (non-demo) workspaces and unexpired trials are untouched."""
    from datetime import date, timedelta

    from aurum.core.money import Amount
    from aurum.core.workspaces import Workspace, save_workspace
    from aurum.demo.personal import reanchor_demo_trials
    from aurum.organizer import commitments as org_commitments
    from aurum.organizer.models import CommitmentIn, CommitmentPatch

    today = date(2026, 9, 19)
    save_workspace(Workspace(id="demo-trial", name="Demo", profile={"demo": True}))
    save_workspace(Workspace(id="real-trial", name="Mine", profile={}))

    def trial(ws: str, name: str, ends: date):
        return org_commitments.create(ws, CommitmentIn(
            kind="subscription", name=name, amount=Amount(amount="249.00", currency="MXN"), cadence="monthly",
            anchor_day=1, next_due=today + timedelta(days=10), status="trial", trial_ends=ends,
            started=today - timedelta(days=25), force=True), today=today)

    expired = trial("demo-trial", "Max", today - timedelta(days=7))
    live = trial("demo-trial", "Spotify", today + timedelta(days=3))
    real = trial("real-trial", "Max", today - timedelta(days=7))

    # the organizer rolls an expired trial forward to active but keeps trial_ends — that shape must move too
    rolled = trial("demo-trial", "HBO", today - timedelta(days=20))
    org_commitments.update_partial("demo-trial", rolled.id, CommitmentPatch(status="active"), today=today)

    moved = reanchor_demo_trials("demo-trial", today=today)
    assert sorted(moved) == sorted([expired.id, rolled.id])
    assert org_commitments.get("demo-trial", rolled.id).status == "trial"
    assert org_commitments.get("demo-trial", rolled.id).trial_ends == today + timedelta(days=5)
    assert org_commitments.get("demo-trial", expired.id).trial_ends == today + timedelta(days=5)
    assert org_commitments.get("demo-trial", live.id).trial_ends == today + timedelta(days=3)
    assert org_commitments.get("real-trial", real.id).trial_ends == today - timedelta(days=7)
    assert reanchor_demo_trials("real-trial", today=today) == []

