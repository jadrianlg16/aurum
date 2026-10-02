"""A minimal, dependency-free cron parser: ``minute hour dom month dow``.

Each field is ``*``, a single integer, or a comma-separated list of integers.
No steps (``*/5``) or ranges (``1-5``) — this is intentionally small, matching what
the built-in workflows need (daily/weekly/monthly ticks). ``dow`` follows standard cron
(0 and 7 both mean Sunday, 1..6 mean Monday..Saturday) and is converted internally to
match Python's ``date.weekday()`` (Monday=0..Sunday=6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class CronError(ValueError):
    pass


def _parse_field(text: str, lo: int, hi: int) -> set[int] | None:
    text = text.strip()
    if text == "*":
        return None
    values = set()
    for part in text.split(","):
        part = part.strip()
        if not part.lstrip("-").isdigit():
            raise CronError(f"invalid cron field value: {part!r}")
        v = int(part)
        if not (lo <= v <= hi):
            raise CronError(f"cron field value {v} out of range [{lo},{hi}]")
        values.add(v)
    return values


@dataclass(frozen=True)
class CronSchedule:
    minute: set[int] | None
    hour: set[int] | None
    dom: set[int] | None
    month: set[int] | None
    dow: set[int] | None
    raw: str

    def matches(self, when: datetime) -> bool:
        if self.minute is not None and when.minute not in self.minute:
            return False
        if self.hour is not None and when.hour not in self.hour:
            return False
        if self.dom is not None and when.day not in self.dom:
            return False
        if self.month is not None and when.month not in self.month:
            return False
        if self.dow is not None and when.weekday() not in self.dow:
            return False
        return True


def parse(expr: str) -> CronSchedule:
    fields = expr.strip().split()
    if len(fields) != 5:
        raise CronError(f"cron expression must have 5 fields, got {len(fields)}: {expr!r}")
    minute, hour, dom, month, dow = fields
    cron_dow = _parse_field(dow, 0, 7)
    py_dow = {(v - 1) % 7 for v in cron_dow} if cron_dow is not None else None
    return CronSchedule(
        minute=_parse_field(minute, 0, 59),
        hour=_parse_field(hour, 0, 23),
        dom=_parse_field(dom, 1, 31),
        month=_parse_field(month, 1, 12),
        dow=py_dow,
        raw=expr.strip(),
    )
