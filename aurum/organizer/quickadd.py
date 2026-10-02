"""One-line quick add: ``"netflix 219 mensual día 15"`` → a Commitment preview.

Rule-based ES/EN, no model anywhere (math lives in code). The parser consumes
the line in a fixed order so that a number belonging to a *day* can never be mistaken for the amount:

    trial → "cada N días" → day-of-month → cadence keyword → currency → amount → name (what's left)

Everything the parser decided is reported in ``explain.steps``, so a wrong guess is visible before the
preview is saved. The amount is the **last** standalone number left once those tokens are stripped, so
``"Microsoft 365 1299 anual"`` is 1299 for *Microsoft 365*; a line with no number at all raises
:class:`QuickAddError` (the router answers 400) instead of saving a 0.00 commitment.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.money import Amount, q2
from . import cadence as cad
from . import normalize
from .models import CommitmentIn

CADENCE_WORDS: list[tuple[str, str]] = [
    # (regex, cadence) — longest / most specific first
    (r"\bsemi-?annual(?:ly)?\b|\bsemestral(?:mente)?\b|\bcada\s+seis\s+meses\b|\bevery\s+six\s+months\b", "semiannual"),
    (r"\bbi-?monthly\b|\bbimestral(?:mente)?\b|\bcada\s+dos\s+meses\b|\bevery\s+two\s+months\b", "bimonthly"),
    (r"\bquarterly\b|\btrimestral(?:mente)?\b|\bcada\s+tres\s+meses\b|\bevery\s+three\s+months\b", "quarterly"),
    (r"\bbi-?weekly\b|\bquincenal(?:mente)?\b|\bcada\s+quincena\b|\bfortnightly\b", "biweekly"),
    (r"\bannual(?:ly)?\b|\byearly\b|\banual(?:mente)?\b|\bal\s+a[nñ]o\b|\bper\s+year\b|\bcada\s+a[nñ]o\b", "annual"),
    (r"\bmonthly\b|\bmensual(?:mente)?\b|\bal\s+mes\b|\bper\s+month\b|\bcada\s+mes\b", "monthly"),
    (r"\bweekly\b|\bsemanal(?:mente)?\b|\bper\s+week\b|\bcada\s+semana\b", "weekly"),
]

_TRIAL = re.compile(r"\b(?:prueba|trial|free\s+trial)\s+(?:hasta|until|ends?)\s+(\d{4}-\d{2}-\d{2})\b")
_EVERY_N = re.compile(r"\bcada\s+(\d{1,3})\s*d[ií]as?\b|\bevery\s+(\d{1,3})\s*days?\b")
_DAY_ES = re.compile(r"\b(?:d[ií]a|el)\s+(\d{1,2})\b")
_DAY_EN = re.compile(r"\bon\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\b")
_CURRENCY = re.compile(r"\b(USD|MXN|EUR|CAD|GBP)\b", re.IGNORECASE)
_AMOUNT = re.compile(r"(?<![\w])\$?\s?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)(?![\w])")

class QuickAddError(ValueError):
    """The line cannot become a commitment (no amount). Message is user-facing Spanish/English."""


_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "por", "a", "the", "for", "of", "on", "at", "pago",
    "cargo", "suscripcion", "suscripción", "subscription", "payment", "bill", "recibo",
}


def parse(text: str, ws_id: str = "", today: date | None = None, lang: str = "es",
          currency: str = "MXN") -> tuple[CommitmentIn, Explain]:
    today = today or date.today()
    original = (text or "").strip()
    work = original
    explain = Explain(summary=i18n_t("organizer.quickadd", lang))
    explain.add_step("input", original)

    trial_ends: date | None = None
    m = _TRIAL.search(work)
    if m:
        trial_ends = date.fromisoformat(m.group(1))
        work = work[: m.start()] + " " + work[m.end():]
        explain.add_step("trial_ends", trial_ends.isoformat(), formula="prueba/trial hasta|until <ISO>")

    cadence = "monthly"
    interval_days: int | None = None
    m = _EVERY_N.search(work)
    if m:
        interval_days = int(m.group(1) or m.group(2))
        cadence = "custom"
        work = work[: m.start()] + " " + work[m.end():]
        explain.add_step("interval_days", interval_days, formula="cada N días / every N days")

    anchor_day: int | None = None
    for pattern in (_DAY_EN, _DAY_ES):
        m = pattern.search(work)
        if m and 1 <= int(m.group(1)) <= 31:
            anchor_day = int(m.group(1))
            work = work[: m.start()] + " " + work[m.end():]
            explain.add_step("anchor_day", anchor_day, formula="día N / el N / on the Nth")
            break

    if interval_days is None:
        for pattern, name in CADENCE_WORDS:
            m = re.search(pattern, work, re.IGNORECASE)
            if m:
                cadence = name
                work = work[: m.start()] + " " + work[m.end():]
                explain.add_step("cadence", cadence, formula=f"keyword {m.group(0).strip()!r}")
                break
        else:
            explain.add_step("cadence", cadence, formula="default when no keyword is present")
    else:
        explain.add_step("cadence", cadence)

    currency = (currency or "MXN").upper()
    m = _CURRENCY.search(work)
    if m:
        currency = m.group(1).upper()
        work = work[: m.start()] + " " + work[m.end():]
    explain.add_step("currency", currency)

    numbers = list(_AMOUNT.finditer(work))
    if not numbers:
        raise QuickAddError(i18n_t("organizer.quickadd.no_amount", lang))
    m = numbers[-1]
    try:
        amount = q2(Decimal(m.group(1).replace(",", "")))
    except InvalidOperation:  # pragma: no cover — regex already guarantees a number
        raise QuickAddError(i18n_t("organizer.quickadd.no_amount", lang)) from None
    work = work[: m.start()] + " " + work[m.end():]
    explain.add_step("amount", f"{amount} {currency}", formula="last standalone number")

    words = [w.strip(".,;:$") for w in work.split()]
    name_words = [w for w in words if w and w.lower() not in _STOPWORDS]
    name = " ".join(name_words).strip() or original
    explain.add_step("name", name, formula="remaining words after the parsed tokens")

    info = normalize.classify(name)
    merchant = str(info["merchant"])
    anchor = today.replace(day=min(anchor_day, 28)) if anchor_day else today
    next_due = cad.project_next(
        anchor, cadence, today=today, interval_days=interval_days,
        anchor_day=anchor_day, strictly_after=False,
    )
    explain.add_step("next_due", next_due.isoformat())
    explain.add_step("merchant", merchant, formula="normalize(name)")

    body = CommitmentIn(
        kind=str(info["kind"]) if info["kind"] != "other" else "subscription",
        name=name.title() if name.islower() else name,
        merchant_patterns=[merchant],
        amount=Amount(amount=amount, currency=currency),
        cadence=cadence,
        interval_days=interval_days,
        anchor_day=anchor_day,
        next_due=next_due,
        essential=str(info["essential"]),
        status="trial" if trial_ends else "active",
        trial_ends=trial_ends,
        started=today,
        source="manual",
        confidence=1.0,
        category_hint=info["category_hint"],
    )
    return body, explain
