"""Detection over the demo workspace."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from aurum.organizer import commitments as cmt
from aurum.organizer import detect

from .conftest import TODAY, WS

# The seeded recurring items detection must find, with the cadence each one must be given.
EXPECTED: dict[str, str] = {
    "NETFLIX": "monthly",
    "SPOTIFY": "monthly",
    "TELCEL": "monthly",
    "CFE": "bimonthly",
    "RENTA": "monthly",
    "SMART FIT": "monthly",
    "ICLOUD": "monthly",
    "AMAZON PRIME": "annual",
    "CREDITO AUTOMOTRIZ": "monthly",
    "NOMINA ACME": "monthly",
    "CLIENTE DELTA": "monthly",
}


def test_detect_finds_the_seeded_recurring_items(demo) -> None:
    found = {c.merchant: c.preview for c in detect.detect(WS, today=TODAY)}
    hits = {m: c for m, c in EXPECTED.items() if m in found}
    assert len(hits) >= 8, f"only found {sorted(hits)}"
    assert set(EXPECTED) <= set(found), f"missing {sorted(set(EXPECTED) - set(found))}"
    for merchant, cadence in EXPECTED.items():
        assert found[merchant].cadence == cadence, merchant


def test_amounts_and_direction(demo) -> None:
    found = {c.merchant: c.preview for c in detect.detect(WS, today=TODAY)}
    assert found["NETFLIX"].amount.amount == Decimal("219.00")   # the latest price, not the average
    assert found["SPOTIFY"].amount.amount == Decimal("129.00")
    assert found["AMAZON PRIME"].amount.amount == Decimal("899.00")
    assert found["NOMINA ACME"].kind == "income"
    assert found["CLIENTE DELTA"].kind == "income"
    assert found["NETFLIX"].kind == "subscription"
    assert found["CFE"].kind == "utility"
    assert found["RENTA"].kind == "rent"


def test_utility_is_marked_variable_and_survives_a_wide_amount_spread(demo) -> None:
    found = {c.merchant: c for c in detect.detect(WS, today=TODAY)}
    cfe = found["CFE"]
    # 890 and 1,120 are 23% apart: only the utility band (±35%) keeps them as one commitment.
    assert cfe.preview.amount_variable is True
    assert {str(e.amount.amount) for e in cfe.evidence} == {"890.00", "1120.00"}


def test_every_candidate_carries_evidence_and_cadence_math(demo) -> None:
    for candidate in detect.detect(WS, today=TODAY):
        if not candidate.evidence:
            continue  # pf loan/card candidates have no bank evidence by construction
        explain = candidate.preview.explain
        assert explain is not None
        labels = {s.label for s in explain.steps}
        assert {"intervals_days", "median_interval", "cadence", "amount_tolerance",
                "confidence", "regularity"} <= labels
        assert 0.0 <= candidate.confidence <= 1.0
        assert len(candidate.evidence) >= 2


def test_bank_and_ledger_copies_of_one_charge_count_once(demo) -> None:
    netflix = next(c for c in detect.detect(WS, today=TODAY) if c.merchant == "NETFLIX")
    # demo_org writes each charge to ingest_bank_lines AND the ledger; three months = three events.
    assert len(netflix.evidence) == 3
    assert sorted({e.date for e in netflix.evidence}) == sorted({e.date for e in netflix.evidence})


def test_loan_candidate_links_the_pf_loan(demo) -> None:
    from aurum.pf import credit

    loan = credit.list_loans(WS)[0]
    found = [c for c in detect.detect(WS, today=TODAY) if c.preview.linked_loan_id == loan["id"]]
    assert found, "the pf loan produced no loan_payment candidate"
    preview = found[0].preview
    assert preview.kind == "loan_payment"
    assert preview.essential == "debt"
    assert preview.amount.amount == Decimal(credit.loan_amortization(WS, loan["id"])["payment"])


def test_detect_is_idempotent_and_resumable(demo) -> None:
    first = detect.detect(WS, today=TODAY)
    second = detect.detect(WS, today=TODAY)
    assert len(first) == len(second)
    assert {c.id for c in first} == {c.id for c in second}
    assert {c.id for c in detect.list_candidates(WS, "open")} == {c.id for c in first}


def test_accept_creates_a_commitment_with_its_price_history(demo) -> None:
    netflix = next(c for c in detect.detect(WS, today=TODAY) if c.merchant == "NETFLIX")
    created = detect.accept(WS, netflix.id, today=TODAY)
    assert created.source == "detected"
    assert created.merchant_patterns == ["NETFLIX"]
    prices = [p["amount"]["amount"] for p in cmt.price_history(WS, created.id)]
    assert "199.00" in prices and "219.00" in prices
    assert detect.get_candidate(WS, netflix.id).status == "accepted"


def test_accepted_merchants_are_not_proposed_again(demo) -> None:
    netflix = next(c for c in detect.detect(WS, today=TODAY) if c.merchant == "NETFLIX")
    created = detect.accept(WS, netflix.id, today=TODAY)
    assert "NETFLIX" not in {c.merchant for c in detect.detect(WS, today=TODAY)}
    # paused still claims the merchant (only active|trial|paused do)
    cmt.set_status(WS, created.id, "paused")
    assert "NETFLIX" not in {c.merchant for c in detect.detect(WS, today=TODAY)}


def test_cancelled_but_charging_resurfaces(demo) -> None:
    from aurum.organizer import alerts as alerts_mod

    netflix = next(c for c in detect.detect(WS, today=TODAY) if c.merchant == "NETFLIX")
    created = detect.accept(WS, netflix.id, today=TODAY)
    # cancelled on 07-01, yet the bank keeps charging on 07-15, 08-15 and 09-15
    cmt.set_status(WS, created.id, "cancelled", ended=date(2026, 7, 1))
    found = {c.merchant: c for c in detect.detect(WS, today=TODAY)}
    assert "NETFLIX" in found
    cand = found["NETFLIX"]
    assert cand.flags == ["cancelled_still_charging"]
    assert cand.existing_commitment_id == created.id
    assert cand.status == "open"
    assert all(e.date > date(2026, 7, 1) for e in cand.evidence) and len(cand.evidence) == 3
    assert detect.get_candidate(WS, cand.id).flags == ["cancelled_still_charging"]

    alerts = [a for a in alerts_mod.compute_alerts(WS, TODAY) if a.kind == "cancelled_still_charging"]
    assert len(alerts) == 1
    assert alerts[0].severity == "warn" and alerts[0].commitment_id == created.id
    assert "Netflix" in alerts[0].title and "15 sep 2026" in alerts[0].body

    # a cancelled merchant that really stopped charging stays quiet
    spotify = next(c for c in detect.detect(WS, today=TODAY) if c.merchant == "SPOTIFY")
    quiet = detect.accept(WS, spotify.id, today=TODAY)
    cmt.set_status(WS, quiet.id, "cancelled", ended=TODAY)
    assert "SPOTIFY" not in {c.merchant for c in detect.detect(WS, today=TODAY)}


def test_dismiss_removes_it_from_the_open_list(demo) -> None:
    spotify = next(c for c in detect.detect(WS, today=TODAY) if c.merchant == "SPOTIFY")
    detect.set_candidate_status(WS, spotify.id, "dismissed")
    assert "SPOTIFY" not in {c.merchant for c in detect.list_candidates(WS, "open")}


def test_next_due_is_in_the_future(demo) -> None:
    for candidate in detect.detect(WS, today=TODAY):
        assert candidate.preview.next_due > TODAY


def test_detect_on_an_empty_workspace_returns_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURUM_DATA_DIR", str(tmp_path / "data"))
    from aurum.core import db

    db.reset_for_tests()
    assert detect.detect("empty-ws", today=date.today() + timedelta(days=0)) == []
