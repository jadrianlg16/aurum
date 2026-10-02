"""Endpoint shapes, CRUD and the setup wizard."""

from __future__ import annotations

from decimal import Decimal

from .conftest import WS


def test_organizer_is_mounted() -> None:
    from aurum.api.app import create_app

    assert "/api/organizer" in create_app().state.mounted


def test_summary_shape(client) -> None:
    r = client.get(f"/api/organizer/{WS}/summary")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "monthly_committed", "annual_subscriptions", "next_7_days", "alerts_count",
        "safe_to_spend", "uncategorized_count", "setup", "explain",
    }
    assert set(body["monthly_committed"]) == {"total", "by_kind"}
    # safe_to_spend carries currency + parts.
    assert set(body["safe_to_spend"]) == {"amount", "until", "currency", "parts", "explain"}
    assert set(body["safe_to_spend"]["parts"]) == {"balance", "fixed_pending", "budgets_remaining", "buffer"}
    assert set(body["setup"]) >= {"has_bank_lines", "has_commitments", "has_income", "has_plan"}
    assert body["explain"]["summary"]
    for item in body["next_7_days"]:
        assert set(item) == {"commitment_id", "name", "kind", "due", "amount", "status", "txn_id", "entry_id", "amount_variable"}


def test_summary_totals_match_the_commitment_list(client) -> None:
    client.post(f"/api/organizer/{WS}/setup/run", json={"months": 3})
    for candidate in client.post(f"/api/organizer/{WS}/detect").json()["candidates"]:
        client.post(f"/api/organizer/{WS}/detect/accept", json={"candidate_id": candidate["id"]})
    summary = client.get(f"/api/organizer/{WS}/summary").json()
    commitments = client.get(f"/api/organizer/{WS}/commitments").json()
    expected = sum(
        (Decimal(c["monthly_equivalent"]["amount"]) for c in commitments
         if c["status"] in ("active", "trial") and c["kind"] != "income"),
        Decimal("0"),
    )
    assert Decimal(summary["monthly_committed"]["total"]["amount"]) == expected
    by_kind = sum(
        (Decimal(v["amount"]) for v in summary["monthly_committed"]["by_kind"].values()), Decimal("0")
    )
    assert by_kind == expected


def test_commitment_crud_and_lifecycle(client) -> None:
    created = client.post(
        f"/api/organizer/{WS}/commitments",
        json={
            "kind": "subscription", "name": "Crunchyroll",
            "amount": {"amount": "149.00", "currency": "MXN"},
            "cadence": "monthly", "anchor_day": 3, "next_due": "2026-10-03",
            "essential": "wants", "merchant_patterns": ["CRUNCHYROLL"],
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    assert created.json()["monthly_equivalent"]["amount"] == "149.00"
    assert created.json()["explain"]["summary"]

    fetched = client.get(f"/api/organizer/{WS}/commitments/{cid}").json()
    assert set(fetched) >= {"price_history", "occurrences", "loan"}
    assert fetched["price_history"]

    # PUT is a PATCH-merge — send only what changes.
    updated = client.put(
        f"/api/organizer/{WS}/commitments/{cid}",
        json={"amount": {"amount": "179.00", "currency": "MXN"}},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"]["amount"] == "179.00"
    assert updated.json()["name"] == "Crunchyroll"
    assert updated.json()["anchor_day"] == 3

    assert client.post(f"/api/organizer/{WS}/commitments/{cid}/pause").json()["status"] == "paused"
    assert client.post(f"/api/organizer/{WS}/commitments/{cid}/resume").json()["status"] == "active"
    cancelled = client.post(
        f"/api/organizer/{WS}/commitments/{cid}/cancel", json={"cancel_notes": "cancelado en la app"}
    ).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_notes"] == "cancelado en la app"

    deleted = client.delete(f"/api/organizer/{WS}/commitments/{cid}").json()
    assert deleted["status"] == "cancelled" and deleted["ended"] is not None
    assert client.get(f"/api/organizer/{WS}/commitments/{cid}").status_code == 200  # soft delete


def test_commitment_filters(client) -> None:
    for candidate in client.post(f"/api/organizer/{WS}/detect").json()["candidates"]:
        client.post(f"/api/organizer/{WS}/detect/accept", json={"candidate_id": candidate["id"]})
    incomes = client.get(f"/api/organizer/{WS}/commitments?kind=income").json()
    assert incomes and all(c["kind"] == "income" for c in incomes)
    trials = client.get(f"/api/organizer/{WS}/commitments?status=trial").json()
    assert all(c["status"] == "trial" for c in trials)


def test_unknown_ids_are_404(client) -> None:
    assert client.get(f"/api/organizer/{WS}/commitments/nope").status_code == 404
    assert client.delete(f"/api/organizer/{WS}/commitments/nope").status_code == 404
    assert client.post(f"/api/organizer/{WS}/commitments/nope/pause").status_code == 404
    assert client.post(f"/api/organizer/{WS}/detect/accept",
                       json={"candidate_id": "nope"}).status_code == 404
    assert client.post(f"/api/organizer/{WS}/detect/dismiss",
                       json={"candidate_id": "nope"}).status_code == 404


def test_bad_lifecycle_action_is_400(client) -> None:
    listed = client.get(f"/api/organizer/{WS}/commitments").json()
    cid = listed[0]["id"]
    assert client.post(f"/api/organizer/{WS}/commitments/{cid}/explode").status_code == 400


def test_linked_loan_drawer_carries_the_amortization(client) -> None:
    candidates = client.post(f"/api/organizer/{WS}/detect").json()["candidates"]
    linked = next(c for c in candidates if c["preview"]["linked_loan_id"])
    cid = client.post(
        f"/api/organizer/{WS}/detect/accept", json={"candidate_id": linked["id"]}
    ).json()["id"]
    drawer = client.get(f"/api/organizer/{WS}/commitments/{cid}").json()
    assert drawer["loan"] is not None
    assert set(drawer["loan"]) >= {"loan_id", "payment", "total_interest", "months", "explain"}


def test_setup_status_and_run(client) -> None:
    status = client.get(f"/api/organizer/{WS}/setup/status").json()
    assert status["has_bank_lines"] is True
    assert set(status) >= {"has_bank_lines", "has_commitments", "has_income", "has_plan",
                           "counts", "progress", "explain"}

    run = client.post(f"/api/organizer/{WS}/setup/run", json={"months": 3}).json()
    assert run["candidates_total"] > 0
    assert run["income_candidates"]
    assert run["plan"]["written"]
    assert run["status"]["has_plan"] is True


def test_detect_dismiss_endpoint(client) -> None:
    candidate = client.post(f"/api/organizer/{WS}/detect").json()["candidates"][0]
    assert client.post(
        f"/api/organizer/{WS}/detect/dismiss", json={"candidate_id": candidate["id"]}
    ).json()["status"] == "dismissed"
    open_ids = {c["id"] for c in client.get(f"/api/organizer/{WS}/detect").json()["candidates"]}
    assert candidate["id"] not in open_ids


def test_language_override(client) -> None:
    es = client.get(f"/api/organizer/{WS}/summary?lang=es").json()["explain"]["summary"]
    en = client.get(f"/api/organizer/{WS}/summary?lang=en").json()["explain"]["summary"]
    assert es != en
    assert "month" in en.lower()


def test_every_money_field_is_a_string(client) -> None:
    def walk(node) -> None:
        if isinstance(node, dict):
            if set(node) == {"amount", "currency"}:
                assert isinstance(node["amount"], str), node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path in ("summary", "commitments", "alerts", "plan", "forecast?days=10", "calendar"):
        walk(client.get(f"/api/organizer/{WS}/{path}").json())


def test_endpoints_work_on_a_bare_workspace(client) -> None:
    from aurum.core.workspaces import ensure_workspace

    ensure_workspace("bare-ws", name="Bare")
    for path in ("summary", "commitments", "alerts", "plan", "forecast", "calendar",
                 "setup/status", "rules"):
        assert client.get(f"/api/organizer/bare-ws/{path}").status_code == 200, path
