"""Cadence inference and next-due projection, including month ends."""

from __future__ import annotations

from datetime import date

import pytest

from aurum.organizer import cadence as cad


@pytest.mark.parametrize(
    ("dates", "expected"),
    [
        ([date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 19), date(2026, 1, 26)], "weekly"),
        ([date(2026, 1, 5), date(2026, 1, 19), date(2026, 2, 2)], "biweekly"),
        ([date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)], "monthly"),
        ([date(2026, 1, 10), date(2026, 3, 10), date(2026, 5, 10)], "bimonthly"),
        ([date(2026, 1, 10), date(2026, 4, 10), date(2026, 7, 10)], "quarterly"),
        ([date(2025, 1, 10), date(2025, 7, 10), date(2026, 1, 10)], "semiannual"),
        ([date(2025, 3, 1), date(2026, 3, 1)], "annual"),
        ([date(2026, 1, 1), date(2026, 1, 21), date(2026, 2, 10)], "custom"),
    ],
)
def test_infer_cadence_bands(dates: list[date], expected: str) -> None:
    assert cad.infer_cadence(dates)[0] == expected


def test_custom_keeps_the_median_interval() -> None:
    cadence, interval, intervals, median = cad.infer_cadence(
        [date(2026, 1, 1), date(2026, 1, 21), date(2026, 2, 10)]
    )
    assert (cadence, interval, intervals, median) == ("custom", 20, [20, 20], 20)


def test_one_late_payment_does_not_change_the_cadence() -> None:
    # 31, 45, 30 days: the median (31) is still monthly even though one gap is 45 days.
    dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 18), date(2026, 4, 17)]
    assert cad.infer_cadence(dates)[0] == "monthly"


def test_weekly_needs_three_occurrences() -> None:
    assert cad.min_occurrences("weekly") == 3
    assert cad.min_occurrences("monthly") == 2


@pytest.mark.parametrize(
    ("anchor_day", "start", "expected"),
    [
        (31, date(2026, 1, 31), date(2026, 2, 28)),   # February clamps to the 28th
        (31, date(2026, 3, 31), date(2026, 4, 30)),   # April clamps to the 30th
        (31, date(2026, 4, 30), date(2026, 5, 31)),   # …and springs back to the 31st in May
        (30, date(2028, 1, 30), date(2028, 2, 29)),   # leap February
        (15, date(2026, 12, 15), date(2027, 1, 15)),  # year rollover
    ],
)
def test_month_end_projection(anchor_day: int, start: date, expected: str) -> None:
    assert cad.step(start, "monthly", anchor_day=anchor_day) == expected


def test_project_next_is_strictly_after_today_by_default() -> None:
    nxt = cad.project_next(date(2026, 6, 15), "monthly", today=date(2026, 9, 15), anchor_day=15)
    assert nxt == date(2026, 10, 15)


def test_project_next_can_include_today() -> None:
    nxt = cad.project_next(
        date(2026, 6, 15), "monthly", today=date(2026, 9, 15), anchor_day=15, strictly_after=False
    )
    assert nxt == date(2026, 9, 15)


def test_weekly_projection_keeps_the_weekday() -> None:
    # 2026-09-15 is a Tuesday (weekday 1); a Friday-anchored weekly bill must land on Fridays.
    dues = cad.occurrences_between(
        date(2026, 9, 4), "weekly", date(2026, 9, 15), date(2026, 10, 5), weekday=4
    )
    assert dues == [date(2026, 9, 18), date(2026, 9, 25), date(2026, 10, 2)]
    assert all(d.weekday() == 4 for d in dues)


def test_biweekly_projection_steps_fourteen_days() -> None:
    dues = cad.occurrences_between(date(2026, 9, 1), "biweekly", date(2026, 9, 1), date(2026, 10, 15))
    assert dues == [date(2026, 9, 1), date(2026, 9, 15), date(2026, 9, 29), date(2026, 10, 13)]


def test_custom_interval_days_projection() -> None:
    dues = cad.occurrences_between(
        date(2026, 9, 1), "custom", date(2026, 9, 1), date(2026, 10, 1), interval_days=10
    )
    assert dues == [date(2026, 9, 1), date(2026, 9, 11), date(2026, 9, 21), date(2026, 10, 1)]


@pytest.mark.parametrize(
    ("cadence", "per_year"),
    [("weekly", 52.0), ("biweekly", 26.0), ("monthly", 12.0), ("bimonthly", 6.0),
     ("quarterly", 4.0), ("semiannual", 2.0), ("annual", 1.0)],
)
def test_periods_per_year(cadence: str, per_year: float) -> None:
    assert cad.periods_per_year(cadence) == per_year


def test_anchors_from_picks_the_modal_day() -> None:
    anchor_day, weekday = cad.anchors_from(
        [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 16)], "monthly"
    )
    assert (anchor_day, weekday) == (15, None)


def test_annual_and_semiannual_projection_from_a_month_end() -> None:
    assert cad.step(date(2026, 8, 31), "semiannual", anchor_day=31) == date(2027, 2, 28)
    assert cad.step(date(2026, 2, 28), "annual", anchor_day=31) == date(2027, 2, 28)
