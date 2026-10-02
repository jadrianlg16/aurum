"""Calendar helpers shared by pf and organizer. Pure functions, local dates only."""

from __future__ import annotations

import calendar
from datetime import date


def last_day(d: date) -> date:
    """Last calendar day of ``d``'s month."""
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def clamp_day(year: int, month: int, day: int) -> date:
    """``day`` clamped to the month's length: 31 → Feb 28/29, 30 → Feb 28/29, etc. ``day`` must be ≥ 1."""
    if day < 1:
        raise ValueError("day must be >= 1")
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def month_bounds(period: str) -> tuple[date, date]:
    """``'YYYY-MM'`` → (first day, last day)."""
    year, month = (int(x) for x in period.split("-", 1))
    first = date(year, month, 1)
    return first, last_day(first)


def add_months_keep_anchor(d: date, n: int, anchor_day: int | None = None) -> date:
    """Move ``n`` months from ``d`` keeping the intended day-of-month (``anchor_day`` or ``d.day``), so a
    commitment anchored on the 31st never drifts to the 28th permanently."""
    anchor = anchor_day or d.day
    total = d.year * 12 + (d.month - 1) + n
    year, month = divmod(total, 12)
    return clamp_day(year, month + 1, anchor)


def period_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def shift_period(period: str, n: int) -> str:
    first, _ = month_bounds(period)
    return period_of(add_months_keep_anchor(first, n, 1))
