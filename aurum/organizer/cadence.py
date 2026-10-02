"""Cadence inference and next-due projection — pure date math, no I/O.

Cadence is inferred from the *median* interval between consecutive occurrences, so one late payment
cannot move a monthly bill into "bimonthly". The bands::

    weekly 7±2 · biweekly 14±3 · monthly 28-33 · bimonthly 58-64 · quarterly 88-95 ·
    semiannual 178-190 · annual 355-375        (anything else → custom, interval_days = median)

Projection rules:

* month-anchored cadences (monthly … annual) keep the *anchor day*, clamped to the length of the
  target month, so ``anchor_day=31`` lands on 28/29/30/31 as the month allows;
* weekly/biweekly keep the *weekday* of the anchor date;
* ``custom`` steps by ``interval_days``.
"""

from __future__ import annotations

import calendar
import statistics
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

# cadence -> (low, high) inclusive day band, and the month/day step used to project it.
BANDS: list[tuple[str, int, int]] = [
    ("weekly", 5, 9),
    ("biweekly", 11, 17),
    ("monthly", 28, 33),
    ("bimonthly", 58, 64),
    ("quarterly", 88, 95),
    ("semiannual", 178, 190),
    ("annual", 355, 375),
]

MONTH_STEP: dict[str, int] = {
    "monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "annual": 12,
}
DAY_STEP: dict[str, int] = {"weekly": 7, "biweekly": 14}

NOMINAL_DAYS: dict[str, int] = {
    "weekly": 7, "biweekly": 14, "monthly": 30, "bimonthly": 61, "quarterly": 91,
    "semiannual": 182, "annual": 365,
}

# How many times a cadence occurs in one year — used for monthly-committed and annual-cost math.
PER_YEAR: dict[str, float] = {
    "weekly": 52.0, "biweekly": 26.0, "monthly": 12.0, "bimonthly": 6.0,
    "quarterly": 4.0, "semiannual": 2.0, "annual": 1.0,
}


def min_occurrences(cadence: str) -> int:
    """≥2 occurrences to call something recurring, ≥3 for weekly (noise floor)."""
    return 3 if cadence == "weekly" else 2


def infer_cadence(dates: list[date]) -> tuple[str, int | None, list[int], int | None]:
    """→ (cadence, interval_days|None, intervals, median|None). ``custom`` keeps the median gap."""
    ordered = sorted(dates)
    intervals = [(b - a).days for a, b in zip(ordered, ordered[1:], strict=False)]
    if not intervals:
        return "custom", None, [], None
    median = int(round(statistics.median(intervals)))
    for name, low, high in BANDS:
        if low <= median <= high:
            return name, None, intervals, median
    return "custom", max(median, 1), intervals, median


def periods_per_year(cadence: str, interval_days: int | None = None) -> float:
    if cadence == "custom" and interval_days:
        return 365.0 / interval_days
    return PER_YEAR.get(cadence, 12.0)


def nominal_days(cadence: str, interval_days: int | None = None) -> int:
    if cadence == "custom" and interval_days:
        return interval_days
    return NOMINAL_DAYS.get(cadence, 30)


def clamp_day(year: int, month: int, day: int) -> date:
    """anchor_day 31 in a 30-day month → the 30th; in February → 28/29."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def step(d: date, cadence: str, interval_days: int | None = None, anchor_day: int | None = None) -> date:
    """One cadence step forward from ``d`` (keeping the anchor day for month cadences)."""
    if cadence in MONTH_STEP:
        nxt = d + relativedelta(months=MONTH_STEP[cadence])
        return clamp_day(nxt.year, nxt.month, anchor_day or d.day)
    if cadence in DAY_STEP:
        return d + timedelta(days=DAY_STEP[cadence])
    return d + timedelta(days=max(interval_days or 30, 1))


def project_next(
    anchor: date,
    cadence: str,
    *,
    today: date | None = None,
    interval_days: int | None = None,
    anchor_day: int | None = None,
    weekday: int | None = None,
    strictly_after: bool = True,
) -> date:
    """First occurrence at/after ``today`` (strictly after by default), stepping from ``anchor``."""
    today = today or date.today()
    if cadence in MONTH_STEP:
        day = anchor_day or anchor.day
        cur = clamp_day(anchor.year, anchor.month, day)
    elif cadence in DAY_STEP and weekday is not None:
        # snap the anchor to the requested weekday (backwards, so we never skip an occurrence)
        cur = anchor - timedelta(days=(anchor.weekday() - weekday) % 7)
    else:
        cur = anchor
    guard = 0
    while cur < today and guard < 5000:
        cur = step(cur, cadence, interval_days, anchor_day)
        guard += 1
    if strictly_after and cur == today:
        cur = step(cur, cadence, interval_days, anchor_day)
    return cur


def occurrences_between(
    anchor: date,
    cadence: str,
    start: date,
    end: date,
    *,
    interval_days: int | None = None,
    anchor_day: int | None = None,
    weekday: int | None = None,
) -> list[date]:
    """Every projected due date in ``[start, end]`` (inclusive), stepping forward from ``anchor``."""
    if end < start:
        return []
    cur = project_next(
        anchor, cadence, today=start, interval_days=interval_days,
        anchor_day=anchor_day, weekday=weekday, strictly_after=False,
    )
    out: list[date] = []
    guard = 0
    while cur <= end and guard < 2000:
        out.append(cur)
        cur = step(cur, cadence, interval_days, anchor_day)
        guard += 1
    return out


def anchors_from(dates: list[date], cadence: str) -> tuple[int | None, int | None]:
    """(anchor_day, weekday) for the cadence — the modal day-of-month / weekday of the evidence."""
    if not dates:
        return None, None
    if cadence in DAY_STEP:
        weekdays = [d.weekday() for d in dates]
        return None, max(set(weekdays), key=weekdays.count)
    days = [d.day for d in dates]
    # A bill hitting the 31st in one month and the 30th in the next is anchored at the later day.
    return max(days, key=lambda d: (days.count(d), d)), None
