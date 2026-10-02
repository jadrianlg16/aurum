"""``POST /quickadd`` — rule-based ES/EN parsing, no model."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from aurum.organizer import quickadd

TODAY = date(2026, 9, 15)

# (text, amount, currency, cadence, anchor_day, interval_days, trial_ends, name fragment)
CASES = [
    ("netflix 219 mensual día 15", "219.00", "MXN", "monthly", 15, None, None, "Netflix"),
    ("spotify 129 al mes el 8", "129.00", "MXN", "monthly", 8, None, None, "Spotify"),
    ("amazon prime 899 anual", "899.00", "MXN", "annual", None, None, None, "Amazon Prime"),
    ("gym 649 mensualmente", "649.00", "MXN", "monthly", None, None, None, "Gym"),
    ("agua 380 bimestral el 20", "380.00", "MXN", "bimonthly", 20, None, None, "Agua"),
    ("predial 2400 trimestral", "2400.00", "MXN", "quarterly", None, None, None, "Predial"),
    ("seguro auto 7800 semestral", "7800.00", "MXN", "semiannual", None, None, None, "Seguro Auto"),
    ("limpieza 500 semanal", "500.00", "MXN", "weekly", None, None, None, "Limpieza"),
    ("nomina 15000 quincenal", "15000.00", "MXN", "biweekly", None, None, None, "Nomina"),
    ("suplementos 320 cada 45 días", "320.00", "MXN", "custom", None, 45, None, "Suplementos"),
    ("icloud 2.99 USD monthly on the 20th", "2.99", "USD", "monthly", 20, None, None, "Icloud"),
    ("adobe 599 yearly", "599.00", "MXN", "annual", None, None, None, "Adobe"),
    ("max 249 mensual prueba hasta 2026-10-01", "249.00", "MXN", "monthly", None, None,
     date(2026, 10, 1), "Max"),
    ("hbo 199 monthly trial until 2026-11-30", "199.00", "MXN", "monthly", None, None,
     date(2026, 11, 30), "Hbo"),
    ("renta 12,500 monthly on the 1st", "12500.00", "MXN", "monthly", 1, None, None, "Renta"),
    ("cleaning 800 every 10 days", "800.00", "MXN", "custom", None, 10, None, "Cleaning"),
    # the amount is the LAST standalone number, so a brand with digits keeps its name
    ("Microsoft 365 1299 anual", "1299.00", "MXN", "annual", None, None, None, "Microsoft 365"),
    ("Office 365 día 3 149 mensual", "149.00", "MXN", "monthly", 3, None, None, "Office 365"),
]


@pytest.mark.parametrize(
    ("text", "amount", "currency", "cadence", "anchor_day", "interval_days", "trial", "name"), CASES
)
def test_quickadd_cases(text, amount, currency, cadence, anchor_day, interval_days, trial, name):
    body, explain = quickadd.parse(text, "demo-mx", today=TODAY)
    assert body.amount.amount == Decimal(amount)
    assert body.amount.currency == currency
    assert body.cadence == cadence
    assert body.anchor_day == anchor_day
    assert body.interval_days == interval_days
    assert body.trial_ends == trial
    assert name.lower() in body.name.lower()
    assert explain.summary
    assert {s.label for s in explain.steps} >= {"amount", "cadence", "name", "next_due"}


def test_at_least_twelve_parser_cases() -> None:
    assert len(CASES) >= 12


def test_day_number_is_never_mistaken_for_the_amount() -> None:
    body, _ = quickadd.parse("netflix 219 mensual día 15", "demo-mx", today=TODAY)
    assert body.amount.amount == Decimal("219.00")
    assert body.anchor_day == 15


def test_trial_sets_the_trial_status() -> None:
    body, _ = quickadd.parse("max 249 mensual prueba hasta 2026-10-01", "demo-mx", today=TODAY)
    assert body.status == "trial"
    assert body.trial_ends == date(2026, 10, 1)


def test_known_merchant_gets_its_category_and_group() -> None:
    body, _ = quickadd.parse("telcel 399 mensual día 12", "demo-mx", today=TODAY)
    assert body.merchant_patterns == ["TELCEL"]
    assert body.category_hint == "telecom"
    assert body.kind == "bill"
    assert body.essential == "needs"


def test_next_due_respects_the_anchor_day() -> None:
    body, _ = quickadd.parse("netflix 219 mensual día 20", "demo-mx", today=TODAY)
    assert body.next_due == date(2026, 9, 20)
    body, _ = quickadd.parse("netflix 219 mensual día 1", "demo-mx", today=TODAY)
    assert body.next_due == date(2026, 10, 1)


def test_microsoft_365_keeps_its_name_and_takes_the_last_number() -> None:
    body, explain = quickadd.parse("Microsoft 365 1299 anual", "demo-mx", today=TODAY)
    assert body.amount.amount == Decimal("1299.00")
    assert body.name == "Microsoft 365"
    assert body.merchant_patterns == ["MICROSOFT 365"]
    step = next(s for s in explain.steps if s.label == "amount")
    assert step.formula == "last standalone number"


def test_no_amount_raises_and_the_router_answers_400(client) -> None:
    with pytest.raises(quickadd.QuickAddError):
        quickadd.parse("netflix mensual", "demo-mx", today=TODAY)
    r = client.post("/api/organizer/demo-mx/quickadd", json={"text": "spotify"})
    assert r.status_code == 400 and "monto" in r.json()["detail"]


def test_currency_defaults_to_the_workspace_base(client) -> None:
    body, _ = quickadd.parse("hulu 8.99 monthly", "demo-us", today=TODAY, currency="USD")
    assert body.amount.currency == "USD"


def test_no_cadence_keyword_defaults_to_monthly_and_says_so() -> None:
    body, explain = quickadd.parse("cafe 90", "demo-mx", today=TODAY)
    assert body.cadence == "monthly"
    step = next(s for s in explain.steps if s.label == "cadence")
    assert "default" in (step.formula or "")


def test_router_preview_does_not_persist(client) -> None:
    before = client.get("/api/organizer/demo-mx/commitments").json()
    r = client.post("/api/organizer/demo-mx/quickadd", json={"text": "netflix 219 mensual día 15"})
    assert r.status_code == 200
    assert r.json()["saved"] is False
    after = client.get("/api/organizer/demo-mx/commitments").json()
    assert len(after) == len(before)


def test_router_save_persists(client) -> None:
    r = client.post(
        "/api/organizer/demo-mx/quickadd?save=1", json={"text": "dropbox 199 mensual día 3"}
    )
    assert r.status_code == 200
    assert r.json()["saved"] is True
    names = [c["name"] for c in client.get("/api/organizer/demo-mx/commitments").json()]
    assert "Dropbox" in names
