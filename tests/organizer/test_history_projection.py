"""History from the earliest evidence and void-aware matching."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from aurum.core.money import Amount
from aurum.ledger.base import Posting, Transaction, get_ledger
from aurum.organizer import calendar_view, detect, occurrences
from aurum.organizer import commitments as cmt
from aurum.organizer.models import CommitmentIn

from .conftest import TODAY, WS


def _accept(merchant: str):
    for candidate in detect.detect(WS, today=TODAY):
        if candidate.merchant == merchant:
            return detect.accept(WS, candidate.id, today=TODAY)
    raise AssertionError(f"{merchant} was not detected")


def test_netflix_history_is_projected_from_the_first_charge(demo) -> None:
    netflix = _accept("NETFLIX")
    # demo_org posts the three most recent 15ths at or before TODAY (2026-09-15): 07-15, 08-15, 09-15
    assert netflix.started == date(2026, 7, 15) and netflix.last_seen == date(2026, 9, 15)
    assert netflix.next_due == date(2026, 10, 15)  # stored: projected strictly after the last charge

    built = occurrences.build(WS, netflix, date(2026, 5, 1), date(2026, 10, 31), today=TODAY)
    assert [(o.due.isoformat(), o.status) for o in built] == [
        ("2026-07-15", "paid"), ("2026-08-15", "paid"), ("2026-09-15", "paid"), ("2026-10-15", "upcoming"),
    ]
    assert all(o.txn_id and o.txn_id.startswith("org-demo-netflix-") for o in built[:3])
    # the drawer's "recent" list shows the paid history, newest last
    recent = occurrences.recent(WS, netflix, 12, today=TODAY)
    assert [o.due.month for o in recent] == [7, 8, 9]


def test_past_months_populate_the_calendar_for_every_accepted_merchant(demo) -> None:
    accepted = [detect.accept(WS, c.id, today=TODAY) for c in detect.detect(WS, today=TODAY) if c.evidence]
    start, end = date(2026, 6, 1), date(2026, 8, 31)
    payload = calendar_view.calendar(WS, start, end, today=TODAY)
    items = [i for d in payload["days"] for i in d["items"] if i["kind"] in ("commitment", "income")]
    paid = [i for i in items if i["status"] == "paid"]
    assert len(items) >= 25, len(items)
    assert len(paid) >= 20, len(paid)
    # every monthly merchant seeded by demo_org shows exactly its evidence dates in the window as paid
    by_name: dict[str, list[str]] = {}
    for c in accepted:
        if c.cadence != "monthly" or c.source != "detected" or c.linked_loan_id:
            continue  # the pf-loan merge keeps the loan's anchor (15th) and matches the bank's 18th ±3d
        by_name[c.name] = sorted(
            p["observed"] for p in cmt.price_history(WS, c.id)
            if p["source"] == "detected" and start <= date.fromisoformat(p["observed"]) <= end
        )
    for name, observed in by_name.items():
        got = sorted(i["date"] for i in items if i["name"] == name and i["status"] == "paid")
        missed = [i["date"] for i in items if i["name"] == name and i["status"] == "missed"]
        assert got == observed, (name, got, observed)
        assert not missed, (name, missed)
    # the trial (Max, nothing billed yet) never projects a "missed" month before its trial ends
    assert not [i for i in items if i["name"] == "Max"]


def test_voiding_the_matching_txn_flips_the_occurrence_back(demo) -> None:
    netflix = _accept("NETFLIX")
    due = date(2026, 9, 15)
    txn_id = occurrences.find_matching_txn(WS, netflix, due)
    assert txn_id == "org-demo-netflix-2026-09-15"
    # the pf void convention: a reversal tagged entry-reversal whose meta names the original
    get_ledger().append(
        WS,
        Transaction(
            date=due, payee="NETFLIX.COM 866-579-7172 CIUDAD DE MEX", narration="Reversa",
            postings=[
                Posting(account="Expenses:Personal:Entertainment", amount=Amount(amount=Decimal("-219"))),
                Posting(account="Assets:Bank:BBVA", amount=Amount(amount=Decimal("219"))),
            ],
            tags=["entry-reversal"], meta={"reverses": txn_id},
        ),
    )
    assert occurrences.find_matching_txn(WS, netflix, due) is None
    built = occurrences.build(WS, netflix, due, due, today=TODAY)
    assert [(o.due, o.status) for o in built] == [(due, "due")]
    assert occurrences.build(WS, netflix, due, due, today=TODAY + timedelta(days=10))[0].status == "missed"


def test_whole_word_payee_matching(demo) -> None:
    """A pattern matches as whole words inside the normalized payee, never as a substring."""
    for payee, amount in (("COLEGIO ALFA", "5500"), ("COLEGIOS UNIDOS SA", "5500")):
        get_ledger().append(
            WS,
            Transaction(
                date=date(2026, 9, 2), payee=payee, narration="colegiatura",
                postings=[Posting(account="Expenses:Education:School", amount=Amount(amount=Decimal(amount))),
                          Posting(account="Assets:Bank:BBVA", amount=Amount(amount=-Decimal(amount)))],
                links=[payee.split()[0].lower()],
            ),
        )
    c = cmt.create(
        WS,
        CommitmentIn(name="Colegiatura", merchant_patterns=["Colegio"], kind="bill",
                     amount=Amount(amount=Decimal("5500")), cadence="monthly", anchor_day=1,
                     next_due=date(2026, 10, 1), started=date(2026, 8, 1)),
        today=TODAY,
    )
    assert c.merchant_patterns == ["COLEGIO"]  # normalized on write
    assert occurrences.find_matching_txn(WS, c, date(2026, 9, 1)) == "colegio"
    other = cmt.create(
        WS,
        CommitmentIn(name="Cuota escolar", merchant_patterns=["Colegios Unidos"], kind="bill",
                     amount=Amount(amount=Decimal("5500")), cadence="monthly", anchor_day=1,
                     next_due=date(2026, 10, 1), started=date(2026, 8, 1)),
        today=TODAY,
    )
    assert occurrences.find_matching_txn(WS, other, date(2026, 9, 1)) == "colegios"


def test_normalize_is_idempotent_over_the_alias_table() -> None:
    from aurum.organizer import normalize

    for alias in normalize.ALIASES:
        assert normalize.normalize(alias.merchant) == alias.merchant, alias.merchant


def test_one_ledger_read_per_build(demo, monkeypatch) -> None:
    from aurum.organizer import pf_bridge

    netflix = _accept("NETFLIX")
    calls = []
    original = pf_bridge.live_txns

    def counting(ws_id, start=None, end=None):
        calls.append((start, end))
        return original(ws_id, start, end)

    monkeypatch.setattr(pf_bridge, "live_txns", counting)
    occurrences.build(WS, netflix, date(2026, 5, 1), date(2026, 12, 31), today=TODAY)
    assert len(calls) == 1
    # and none at all when the caller shares its read
    shared = original(WS)
    occurrences.build(WS, netflix, date(2026, 5, 1), date(2026, 12, 31), today=TODAY, txns=shared)
    assert len(calls) == 1
