"""Alerts: computed from stored facts on every call, never persisted.

Thresholds (all of them constants in this module, all of them repeated in each alert's ``explain``):

=========================  ============================================================
price_increase              latest price vs the previous distinct price, > 2 % **or** > 20 (base currency)
price_decrease              same test, downwards
trial_ending                ``status == trial`` and ``trial_ends`` within 7 days
missed_payment              a due date ≥ 3 days in the past with no matching ledger transaction
upcoming                    effective next due within 7 days
duplicate                   ≥ 2 active subscriptions sharing a ``category_hint``
annual_renewal              annual/semiannual commitment renewing within 30 days
forgotten                   annual/semiannual not reviewed in 11 months
income_expected/late/changed the same three tests for ``kind == income`` (info / warn / info)
cancelled_still_charging    a cancelled commitment's merchant keeps charging (open flagged candidate)
=========================  ============================================================

Titles and bodies carry pre-formatted money (``fmt_money``: base currency as ``$``) and dates
(``fmt_date``: ``12 sep 2026``) — never ISO dates or ``249.00 MXN``. ``POST /alerts/{id}/dismiss``
writes to ``organizer_dismissed_alerts``; because ids are a stable hash of (workspace, kind, commitment,
due/amount), a dismissed alert stays dismissed until the underlying fact changes.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal

from ..core.explain import Explain
from ..core.i18n import fmt_date, fmt_money, ws_lang
from ..core.i18n import t as i18n_t
from ..core.money import Amount, q2
from . import commitments as cmt
from . import occurrences as occ
from . import pf_bridge, store
from .models import Alert, Commitment

PRICE_PCT = Decimal("0.02")
PRICE_ABS = Decimal("20")
TRIAL_DAYS = 7
UPCOMING_DAYS = 7
RENEWAL_DAYS = 30
MISSED_AFTER_DAYS = 3
MISSED_LOOKBACK_DAYS = 60
FORGOTTEN_MONTHS = 11
DUPLICATE_HINTS = {"streaming", "music", "cloud", "gym"}


def _aid(ws_id: str, kind: str, *parts: str) -> str:
    raw = "|".join((ws_id, kind, *[str(p) for p in parts]))
    return f"org-{kind}-{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def dismissed_ids(ws_id: str) -> set[str]:
    conn = store.db()
    rows = conn.execute("SELECT alert_id FROM organizer_dismissed_alerts WHERE ws_id=?", (ws_id,)).fetchall()
    return {r["alert_id"] for r in rows}


def dismiss(ws_id: str, alert_id: str) -> None:
    conn = store.db()
    conn.execute(
        "INSERT OR REPLACE INTO organizer_dismissed_alerts (ws_id, alert_id, dismissed_at) VALUES (?,?,?)",
        (ws_id, alert_id, store.now()),
    )
    conn.commit()


class _Fmt:
    """Per-call formatting context (language + workspace base currency)."""

    def __init__(self, ws_id: str, lang: str) -> None:
        self.lang = lang
        self.base = pf_bridge.base_currency(ws_id)

    def money(self, amount: Decimal, currency: str) -> str:
        return fmt_money(amount, currency, self.lang, self.base)

    def date(self, d: date) -> str:
        return fmt_date(d, self.lang)


# --------------------------------------------------------------------------- individual rules


def _price_alerts(ws_id: str, c: Commitment, f: _Fmt) -> list[Alert]:
    if c.amount_variable:
        return []
    lang = f.lang
    history = cmt.price_history(ws_id, c.id)
    prices: list[tuple[str, Decimal]] = []
    for row in history:
        amount = Decimal(row["amount"]["amount"])
        if not prices or prices[-1][1] != amount:
            prices.append((row["observed"], amount))
    if len(prices) < 2:
        return []
    (_, old), (observed, new) = prices[-2], prices[-1]
    delta = new - old
    if delta == 0:
        return []
    pct = (delta / old) if old else Decimal("0")
    if abs(pct) <= PRICE_PCT and abs(delta) <= PRICE_ABS:
        return []
    currency = c.amount.currency
    pct_text = str((pct * 100).quantize(Decimal("0.01")))
    if c.kind == "income":
        kind, severity = "income_changed", "info"
    else:
        kind, severity = ("price_increase", "warn") if delta > 0 else ("price_decrease", "info")
    explain = Explain(summary=i18n_t(f"organizer.alert.{kind}", lang, name=c.name,
                                     old=f.money(q2(old), currency), new=f.money(q2(new), currency),
                                     pct=pct_text))
    explain.add_step("previous_price", f"{q2(old)} {currency}")
    explain.add_step("new_price", f"{q2(new)} {currency}", formula=f"observed {observed}")
    explain.add_step("delta", f"{q2(delta)} {currency}", formula="new − previous")
    explain.add_step("pct", pct_text, formula="delta / previous × 100")
    explain.add_step("threshold", f">{PRICE_PCT * 100:.0f}% or >{PRICE_ABS} {currency}")
    explain.add_step(
        "annual_impact", str(q2(delta * Decimal(str(_per_year(c))))),
        formula=f"delta × {_per_year(c)} charges/year",
    )
    return [
        Alert(
            id=_aid(ws_id, kind, c.id, str(q2(old)), str(q2(new))),
            kind=kind, severity=severity, commitment_id=c.id,
            title=i18n_t(f"organizer.alert.title.{kind}", lang, name=c.name),
            body=explain.summary,
            old_amount=Amount(amount=q2(old), currency=currency),
            new_amount=Amount(amount=q2(new), currency=currency),
            explain=explain,
        )
    ]


def _per_year(c: Commitment) -> float:
    from . import cadence as cad

    return cad.periods_per_year(c.cadence, c.interval_days)


def _trial_alert(ws_id: str, c: Commitment, f: _Fmt, today: date) -> list[Alert]:
    if c.status != "trial" or c.trial_ends is None:
        return []
    days = (c.trial_ends - today).days
    if days < 0 or days > TRIAL_DAYS:
        return []
    lang = f.lang
    explain = Explain(summary=i18n_t("organizer.alert.trial_ending", lang, name=c.name,
                                     date=f.date(c.trial_ends),
                                     amount=f.money(q2(c.amount.amount), c.amount.currency)))
    explain.add_step("trial_ends", c.trial_ends.isoformat())
    explain.add_step("days_left", days, formula="trial_ends − today")
    explain.add_step("threshold", f"≤ {TRIAL_DAYS} days")
    return [
        Alert(
            id=_aid(ws_id, "trial_ending", c.id, c.trial_ends.isoformat()),
            kind="trial_ending", severity="urgent" if days <= 2 else "warn", commitment_id=c.id,
            title=i18n_t("organizer.alert.title.trial_ending", lang, name=c.name),
            body=explain.summary, due=c.trial_ends, new_amount=c.amount, explain=explain,
        )
    ]


def _missed_alerts(ws_id: str, c: Commitment, f: _Fmt, today: date, txns: list | None) -> list[Alert]:
    if c.status not in ("active", "trial"):
        return []
    lang = f.lang
    start = today - timedelta(days=MISSED_LOOKBACK_DAYS)
    kind = "income_late" if c.kind == "income" else "missed_payment"
    out = []
    for o in occ.build(ws_id, c, start, today - timedelta(days=MISSED_AFTER_DAYS), today=today, txns=txns):
        if o.status != "missed":
            continue
        explain = Explain(summary=i18n_t(f"organizer.alert.{kind}", lang, name=c.name, date=f.date(o.due),
                                         amount=f.money(q2(o.amount.amount), o.amount.currency)))
        explain.add_step("due", o.due.isoformat())
        explain.add_step("expected", f"{q2(o.amount.amount)} {o.amount.currency}")
        explain.add_step("match_window", f"±{occ.DATE_WINDOW_DAYS} days, ±{occ.AMOUNT_TOLERANCE * 100:.0f}%")
        explain.add_step("days_overdue", (today - o.due).days)
        out.append(
            Alert(
                id=_aid(ws_id, kind, c.id, o.due.isoformat()),
                kind=kind, severity="warn" if kind == "income_late" else "urgent", commitment_id=c.id,
                title=i18n_t(f"organizer.alert.title.{kind}", lang, name=c.name),
                body=explain.summary, due=o.due, new_amount=o.amount, explain=explain,
            )
        )
    return out


def _upcoming_alert(ws_id: str, c: Commitment, f: _Fmt, today: date, next_due: date) -> list[Alert]:
    if c.status not in ("active", "trial"):
        return []
    days = (next_due - today).days
    if days < 0 or days > UPCOMING_DAYS:
        return []
    lang = f.lang
    kind = "income_expected" if c.kind == "income" else "upcoming"
    explain = Explain(summary=i18n_t(f"organizer.alert.{kind}", lang, name=c.name, date=f.date(next_due),
                                     amount=f.money(q2(c.amount.amount), c.amount.currency)))
    explain.add_step("next_due", next_due.isoformat())
    explain.add_step("days_until", days, formula="next_due − today")
    explain.add_step("threshold", f"≤ {UPCOMING_DAYS} days")
    return [
        Alert(
            id=_aid(ws_id, kind, c.id, next_due.isoformat()),
            kind=kind, severity="info", commitment_id=c.id,
            title=i18n_t(f"organizer.alert.title.{kind}", lang, name=c.name),
            body=explain.summary, due=next_due, new_amount=c.amount, explain=explain,
        )
    ]


def _renewal_alert(ws_id: str, c: Commitment, f: _Fmt, today: date, next_due: date) -> list[Alert]:
    if c.cadence not in ("annual", "semiannual") or c.status != "active" or c.kind == "income":
        return []
    days = (next_due - today).days
    if days < 0 or days > RENEWAL_DAYS:
        return []
    lang = f.lang
    explain = Explain(summary=i18n_t("organizer.alert.annual_renewal", lang, name=c.name, date=f.date(next_due),
                                     amount=f.money(q2(c.amount.amount), c.amount.currency)))
    explain.add_step("cadence", c.cadence)
    explain.add_step("renews", next_due.isoformat())
    explain.add_step("days_until", days)
    explain.add_step("threshold", f"≤ {RENEWAL_DAYS} days")
    return [
        Alert(
            id=_aid(ws_id, "annual_renewal", c.id, next_due.isoformat()),
            kind="annual_renewal", severity="warn", commitment_id=c.id,
            title=i18n_t("organizer.alert.title.annual_renewal", lang, name=c.name),
            body=explain.summary, due=next_due, new_amount=c.amount, explain=explain,
        )
    ]


def _forgotten_alert(ws_id: str, c: Commitment, f: _Fmt, today: date) -> list[Alert]:
    if c.cadence not in ("annual", "semiannual") or c.status != "active" or c.kind == "income":
        return []
    reference = c.reviewed_at or c.started or c.last_seen
    if reference is None:
        return []
    months = (today.year - reference.year) * 12 + (today.month - reference.month)
    if months < FORGOTTEN_MONTHS:
        return []
    lang = f.lang
    explain = Explain(summary=i18n_t("organizer.alert.forgotten", lang, name=c.name, months=months))
    explain.add_step("last_review", reference.isoformat())
    explain.add_step("months_since", months, formula="months(today − last_review)")
    explain.add_step("threshold", f"≥ {FORGOTTEN_MONTHS} months")
    return [
        Alert(
            id=_aid(ws_id, "forgotten", c.id, reference.isoformat()),
            kind="forgotten", severity="info", commitment_id=c.id,
            title=i18n_t("organizer.alert.title.forgotten", lang, name=c.name),
            body=explain.summary, explain=explain,
        )
    ]


def _duplicate_alerts(ws_id: str, active: list[Commitment], f: _Fmt) -> list[Alert]:
    lang = f.lang
    by_hint: dict[str, list[Commitment]] = {}
    for c in active:
        if c.kind != "subscription" or not c.category_hint:
            continue
        if c.category_hint not in DUPLICATE_HINTS:
            continue
        by_hint.setdefault(c.category_hint, []).append(c)
    out = []
    for hint, group in sorted(by_hint.items()):
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda c: c.name)
        currency = group[0].amount.currency
        total = sum((cmt.monthly_equivalent(c) for c in group), Decimal("0"))
        names = ", ".join(c.name for c in group)
        explain = Explain(summary=i18n_t("organizer.alert.duplicate", lang, names=names, hint=hint,
                                         amount=f.money(q2(total), currency)))
        explain.add_step("category_hint", hint)
        explain.add_step("services", names)
        explain.add_step("monthly_total", q2(total), formula="Σ monthly_equivalent")
        out.append(
            Alert(
                id=_aid(ws_id, "duplicate", hint, *[c.id for c in group]),
                kind="duplicate", severity="info", commitment_id=group[0].id,
                title=i18n_t("organizer.alert.title.duplicate", lang),
                body=explain.summary, new_amount=Amount(amount=q2(total), currency=currency),
                explain=explain,
            )
        )
    return out


def _cancelled_still_charging(ws_id: str, f: _Fmt) -> list[Alert]:
    """Open candidates flagged by detection because a cancelled commitment's merchant kept charging."""
    from . import detect

    lang = f.lang
    out = []
    try:
        candidates = detect.list_candidates(ws_id, "open")
    except Exception:  # noqa: BLE001
        return out
    for cand in candidates:
        if "cancelled_still_charging" not in cand.flags:
            continue
        last = max((e.date for e in cand.evidence), default=None)
        amount = cand.preview.amount
        explain = Explain(summary=i18n_t(
            "organizer.alert.cancelled_still_charging", lang, name=cand.preview.name,
            date=f.date(last) if last else "", amount=f.money(q2(amount.amount), amount.currency),
        ))
        explain.add_step("candidate", cand.id)
        explain.add_step("charges_after_cancel", len(cand.evidence))
        if last:
            explain.add_step("last_charge", last.isoformat())
        out.append(
            Alert(
                id=_aid(ws_id, "cancelled_still_charging", cand.existing_commitment_id or "", cand.id),
                kind="cancelled_still_charging", severity="warn",
                commitment_id=cand.existing_commitment_id,
                title=i18n_t("organizer.alert.title.cancelled_still_charging", lang, name=cand.preview.name),
                body=explain.summary, due=last, new_amount=amount, explain=explain,
            )
        )
    return out


# --------------------------------------------------------------------------- entry point

_SEVERITY_ORDER = {"urgent": 0, "warn": 1, "info": 2}


def compute_alerts(ws_id: str, today: date | None = None, lang: str | None = None,
                   include_dismissed: bool = False, txns: list | None = None) -> list[Alert]:
    """Every alert the workspace currently has, most severe first. Never raises for a bare workspace.
    One ledger read is shared by every commitment (pass ``txns`` to share it further)."""
    today = today or date.today()
    lang = lang or ws_lang(ws_id)
    try:
        all_commitments = cmt.list_commitments(ws_id)
    except Exception:  # noqa: BLE001 — schema not applied yet
        return []
    f = _Fmt(ws_id, lang)
    if txns is None and all_commitments:
        txns = pf_bridge.live_txns(ws_id, today - timedelta(days=MISSED_LOOKBACK_DAYS + occ.DATE_WINDOW_DAYS),
                                   today + timedelta(days=2 * 365 + occ.DATE_WINDOW_DAYS))
    active = [c for c in all_commitments if c.status in ("active", "trial")]
    out: list[Alert] = []
    for c in all_commitments:
        next_due = cmt.effective_next_due(ws_id, c, today, txns=txns)
        out.extend(_price_alerts(ws_id, c, f))
        out.extend(_trial_alert(ws_id, c, f, today))
        out.extend(_missed_alerts(ws_id, c, f, today, txns))
        out.extend(_upcoming_alert(ws_id, c, f, today, next_due))
        out.extend(_renewal_alert(ws_id, c, f, today, next_due))
        out.extend(_forgotten_alert(ws_id, c, f, today))
    out.extend(_duplicate_alerts(ws_id, active, f))
    out.extend(_cancelled_still_charging(ws_id, f))
    if not include_dismissed:
        gone = dismissed_ids(ws_id)
        out = [a for a in out if a.id not in gone]
    # language-independent order: severity, due date, kind, then the stable id
    out.sort(key=lambda a: (_SEVERITY_ORDER.get(a.severity, 3), a.due or date.max, a.kind, a.id))
    return out
