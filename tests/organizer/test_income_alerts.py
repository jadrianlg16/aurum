"""Income vocabulary + pre-formatted alert prose."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from aurum.core.money import Amount
from aurum.core.workspaces import ensure_workspace
from aurum.organizer import alerts as alerts_mod
from aurum.organizer import commitments as cmt
from aurum.organizer.models import CommitmentIn

WS = "inc-ws"
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


@pytest.fixture()
def stream():
    ensure_workspace(WS, name="Ingresos", base_currency="MXN", language="es")
    return cmt.create(
        WS,
        CommitmentIn(name="Nómina Acme", kind="income", amount=Amount(amount=Decimal("22500")), cadence="monthly",
                     anchor_day=15, next_due=date(2026, 9, 15), started=date(2026, 9, 1),
                     merchant_patterns=["NOMINA ACME"], essential="needs"),
        today=date(2026, 9, 1),
    )


def _bodies_are_human(alerts) -> None:
    for a in alerts:
        assert not ISO.search(a.body), a.body
        assert not ISO.search(a.title), a.title
        assert " MXN" not in a.body and " MXN" not in a.title, a.body


def test_income_expected_before_payday(stream) -> None:
    alerts = [a for a in alerts_mod.compute_alerts(WS, date(2026, 9, 12)) if a.commitment_id == stream.id]
    kinds = [a.kind for a in alerts]
    assert kinds == ["income_expected"], kinds
    a = alerts[0]
    assert a.severity == "info" and a.due == date(2026, 9, 15)
    assert a.title == "Ingreso esperado: Nómina Acme"
    assert "15 sep 2026" in a.body and "$22,500.00" in a.body
    _bodies_are_human(alerts)


def test_income_late_after_the_grace_days(stream) -> None:
    alerts = [a for a in alerts_mod.compute_alerts(WS, date(2026, 9, 20)) if a.commitment_id == stream.id]
    kinds = {a.kind for a in alerts}
    assert "income_late" in kinds and "missed_payment" not in kinds and "upcoming" not in kinds
    late = next(a for a in alerts if a.kind == "income_late")
    assert late.severity == "warn" and late.due == date(2026, 9, 15)
    assert "15 sep 2026" in late.body
    _bodies_are_human(alerts)


def test_income_changed_never_says_price_increase(stream) -> None:
    cmt.record_price(WS, stream.id, date(2026, 9, 16), Amount(amount=Decimal("24000")))
    alerts = [a for a in alerts_mod.compute_alerts(WS, date(2026, 9, 12)) if a.commitment_id == stream.id]
    kinds = {a.kind for a in alerts}
    assert "income_changed" in kinds and "price_increase" not in kinds
    changed = next(a for a in alerts if a.kind == "income_changed")
    assert changed.severity == "info"
    assert "$22,500.00" in changed.body and "$24,000.00" in changed.body
    _bodies_are_human(alerts)


def test_english_bodies_and_foreign_currency(stream) -> None:
    usd = cmt.create(
        WS,
        CommitmentIn(name="Consulting", kind="income", amount=Amount(amount=Decimal("1500"), currency="USD"),
                     cadence="monthly", anchor_day=15, next_due=date(2026, 9, 15), started=date(2026, 9, 1)),
        today=date(2026, 9, 1),
    )
    alerts = [a for a in alerts_mod.compute_alerts(WS, date(2026, 9, 12), lang="en") if a.commitment_id == usd.id]
    assert alerts[0].title == "Income expected: Consulting"
    assert "Sep 15, 2026" in alerts[0].body and "US$1,500.00" in alerts[0].body
    _bodies_are_human(alerts)


def test_expense_alert_bodies_are_formatted_too(stream) -> None:
    bill = cmt.create(
        WS,
        CommitmentIn(name="Renta", kind="rent", amount=Amount(amount=Decimal("12000")), cadence="monthly",
                     anchor_day=1, next_due=date(2026, 10, 1), started=date(2026, 9, 1)),
        today=date(2026, 9, 1),
    )
    alerts = [a for a in alerts_mod.compute_alerts(WS, date(2026, 9, 28)) if a.commitment_id == bill.id]
    kinds = {a.kind for a in alerts}
    assert "upcoming" in kinds and "income_expected" not in kinds
    upcoming = next(a for a in alerts if a.kind == "upcoming")
    assert upcoming.body == "Renta se cobra el 1 oct 2026 por $12,000.00."
    _bodies_are_human(alerts)
