"""Cash-flow forecast and the one "Disponible" (safe to spend) — code only, no model.

    balance           = Σ balances(Assets:Bank:*) + balances(Assets:Cash)
    balance(d)        = balance(d−1) + Σ income due on d − Σ commitments due on d
    fixed_pending     = unpaid occurrences (due, upcoming, missed ≤ 7 days back) of active non-income
                        commitments up to ``until`` (the next projected income, else today + 30 days)
    budgets_remaining = Σ max(0, effective − spent) over this month's budgets, excluding budgets whose
                        category is already carried by a commitment (no double count)
    buffer            = organizer_settings.buffer, default 10 % of the monthly committed total
    safe_to_spend     = balance − fixed_pending − budgets_remaining − buffer

Nothing is smoothed, sampled or estimated: every movement in the series is a projected occurrence of
a commitment the user can open and inspect.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ..core.explain import Explain
from ..core.i18n import fmt_date, fmt_money, ws_lang
from ..core.i18n import t as i18n_t
from ..core.money import q2
from . import commitments as cmt
from . import occurrences as occ
from . import pf_bridge, store
from .models import Commitment

LIQUID_PREFIXES = ("Assets:Bank", "Assets:Cash")
DEFAULT_BUFFER_PCT = Decimal("0.10")
PENDING_LOOKBACK_DAYS = 7
NO_INCOME_HORIZON_DAYS = 30
INCOME_SEARCH_DAYS = 60
UNPAID = ("due", "upcoming", "missed")


def liquid_balance(ws_id: str, as_of: date | None = None) -> Decimal:
    """Checking + cash. Savings accounts share the ``Assets:Bank`` prefix but are excluded: what a
    person set aside (a trip fund, say) is not free to spend."""
    return q2(pf_bridge.liquid_balance(ws_id, LIQUID_PREFIXES, as_of=as_of,
                                       exclude=pf_bridge.savings_accounts(ws_id)))


def get_buffer(ws_id: str) -> Decimal | None:
    conn = store.db()
    row = conn.execute("SELECT buffer FROM organizer_settings WHERE ws_id=?", (ws_id,)).fetchone()
    if row is None or row["buffer"] is None:
        return None
    return Decimal(row["buffer"])


def set_buffer(ws_id: str, value: Decimal | None) -> Decimal | None:
    conn = store.db()
    conn.execute(
        "INSERT INTO organizer_settings (ws_id, buffer, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(ws_id) DO UPDATE SET buffer=excluded.buffer, updated_at=excluded.updated_at",
        (ws_id, None if value is None else str(q2(value)), store.now()),
    )
    conn.commit()
    return value


def monthly_committed(commitments: list[Commitment]) -> Decimal:
    return q2(sum(
        (cmt.monthly_equivalent(c) for c in commitments
         if c.status in ("active", "trial") and c.kind != "income"),
        Decimal("0"),
    ))


def effective_buffer(ws_id: str, commitments: list[Commitment]) -> tuple[Decimal, str]:
    explicit = get_buffer(ws_id)
    if explicit is not None:
        return q2(explicit), "organizer_settings.buffer"
    return q2(monthly_committed(commitments) * DEFAULT_BUFFER_PCT), "10% × monthly_committed (default)"


def _active(commitments: list[Commitment]) -> list[Commitment]:
    return [c for c in commitments if c.status in ("active", "trial")]


def _movements(ws_id: str, commitments: list[Commitment], start: date, end: date,
               today: date, txns: list | None = None) -> dict[date, dict[str, Decimal]]:
    """Unpaid projected movements per day, from ``today`` on (day 0 carries today's unpaid items)."""
    days: dict[date, dict[str, Decimal]] = {}
    for c in _active(commitments):
        for o in occ.build(ws_id, c, start, end, today=today, txns=txns):
            if o.status not in UNPAID:
                continue
            bucket = days.setdefault(o.due, {"in": Decimal("0"), "out": Decimal("0")})
            key = "in" if c.kind == "income" else "out"
            bucket[key] += q2(o.amount.amount)
    return days


def next_income_date(ws_id: str, commitments: list[Commitment], today: date,
                     txns: list | None = None) -> date | None:
    horizon = today + timedelta(days=INCOME_SEARCH_DAYS)
    best: date | None = None
    for c in _active(commitments):
        if c.kind != "income":
            continue
        for o in occ.build(ws_id, c, today + timedelta(days=1), horizon, today=today, txns=txns):
            if best is None or o.due < best:
                best = o.due
    return best


def budgets_remaining(ws_id: str, period: str, commitments: list[Commitment]) -> tuple[Decimal, list[str]]:
    """Σ max(0, effective − spent) over the period's budgets, skipping categories a commitment carries."""
    carried = {c.label_id for c in _active(commitments) if c.kind != "income" and c.label_id}
    total = Decimal("0")
    names: list[str] = []
    for row in pf_bridge.budget_rows(ws_id, period):
        if row["label_id"] in carried:
            continue
        left = max(Decimal("0"), row["effective"] - row["spent"])
        if left > 0:
            total += left
            names.append(row["label_name"] or str(row["label_id"]))
    return q2(total), names


def safe_to_spend(ws_id: str, today: date | None = None, lang: str | None = None,
                  commitments: list[Commitment] | None = None, budgets: list[dict] | None = None,
                  txns: list | None = None) -> dict:
    """The one safe-to-spend figure:
    ``{amount, until, currency, parts:{balance, fixed_pending, budgets_remaining, buffer}, explain}``
    with step ids exactly ``liquid_balance, until, committed_until, budgeted_remaining, buffer,
    safe_to_spend`` and human formulas (no ledger globs, no Σ)."""
    today = today or date.today()
    lang = lang or ws_lang(ws_id)
    commitments = commitments if commitments is not None else cmt.list_commitments(ws_id)
    currency = pf_bridge.base_currency(ws_id)
    balance = liquid_balance(ws_id)
    if txns is None:
        txns = pf_bridge.live_txns(ws_id, today - timedelta(days=PENDING_LOOKBACK_DAYS + occ.DATE_WINDOW_DAYS),
                                   today + timedelta(days=INCOME_SEARCH_DAYS + occ.DATE_WINDOW_DAYS))

    next_income = next_income_date(ws_id, commitments, today, txns=txns)
    until = next_income or (today + timedelta(days=NO_INCOME_HORIZON_DAYS))

    fixed_pending = Decimal("0")
    lines: list[str] = []
    for c in _active(commitments):
        if c.kind == "income":
            continue
        for o in occ.build(ws_id, c, today - timedelta(days=PENDING_LOOKBACK_DAYS), until, today=today, txns=txns):
            if o.status not in UNPAID:
                continue
            fixed_pending += q2(o.amount.amount)
            lines.append(f"{c.name} {fmt_money(o.amount.amount, o.amount.currency, lang, currency)}")
    fixed_pending = q2(fixed_pending)

    period = today.strftime("%Y-%m")
    if budgets is None:
        budgeted, budget_names = budgets_remaining(ws_id, period, commitments)
    else:
        budgeted = q2(sum((max(Decimal("0"), Decimal(str(b["effective"])) - Decimal(str(b["spent"])))
                           for b in budgets), Decimal("0")))
        budget_names = [str(b.get("label_name") or b.get("label_id")) for b in budgets]
    buffer_value, buffer_formula = effective_buffer(ws_id, commitments)
    amount = q2(balance - fixed_pending - budgeted - buffer_value)

    money = lambda v: fmt_money(v, currency, lang, currency)  # noqa: E731
    explain = Explain(summary=i18n_t("organizer.safe_to_spend", lang))
    explain.add_step("liquid_balance", balance, formula=i18n_t("organizer.step.liquid_balance", lang))
    explain.add_step(
        "until", until.isoformat(),
        formula=i18n_t("organizer.step.until_income", lang, date=fmt_date(until, lang)) if next_income
        else i18n_t("organizer.step.until_default", lang, days=NO_INCOME_HORIZON_DAYS),
    )
    explain.add_step(
        "committed_until", fixed_pending,
        formula=i18n_t("organizer.step.committed_until", lang, date=fmt_date(until, lang),
                       items=", ".join(lines) if lines else i18n_t("organizer.step.none", lang)),
    )
    explain.add_step(
        "budgeted_remaining", budgeted,
        formula=i18n_t("organizer.step.budgeted_remaining", lang,
                       items=", ".join(budget_names) if budget_names else i18n_t("organizer.step.none", lang)),
    )
    explain.add_step(
        "buffer", buffer_value,
        formula=i18n_t("organizer.step.buffer_explicit", lang) if buffer_formula == "organizer_settings.buffer"
        else i18n_t("organizer.step.buffer_default", lang),
    )
    explain.add_step(
        "safe_to_spend", amount,
        formula=i18n_t("organizer.step.safe_to_spend", lang, balance=money(balance), fixed=money(fixed_pending),
                       budgets=money(budgeted), buffer=money(buffer_value)),
    )
    return {
        "amount": {"amount": str(amount), "currency": currency},
        "until": until.isoformat(),
        "currency": currency,
        "parts": {
            "balance": {"amount": str(balance), "currency": currency},
            "fixed_pending": {"amount": str(fixed_pending), "currency": currency},
            "budgets_remaining": {"amount": str(budgeted), "currency": currency},
            "buffer": {"amount": str(buffer_value), "currency": currency},
        },
        "explain": explain.model_dump(),
    }


def forecast(ws_id: str, days: int = 90, today: date | None = None, lang: str | None = None) -> dict:
    today = today or date.today()
    lang = lang or ws_lang(ws_id)
    commitments = cmt.list_commitments(ws_id)
    currency = pf_bridge.base_currency(ws_id)
    start_balance = liquid_balance(ws_id)
    end = today + timedelta(days=days)
    txns = pf_bridge.live_txns(ws_id, today - timedelta(days=PENDING_LOOKBACK_DAYS + occ.DATE_WINDOW_DAYS),
                               max(end, today + timedelta(days=INCOME_SEARCH_DAYS)) + timedelta(days=occ.DATE_WINDOW_DAYS))
    movements = _movements(ws_id, commitments, today, end, today, txns=txns)

    series = []
    balance = start_balance
    low = (today, start_balance)
    for offset in range(days + 1):
        day = today + timedelta(days=offset)
        mv = movements.get(day, {"in": Decimal("0"), "out": Decimal("0")})
        balance = q2(balance + mv["in"] - mv["out"])
        if balance < low[1]:
            low = (day, balance)
        series.append({
            "date": day.isoformat(),
            "balance": {"amount": str(balance), "currency": currency},
            "in": {"amount": str(q2(mv["in"])), "currency": currency},
            "out": {"amount": str(q2(mv["out"])), "currency": currency},
        })

    explain = Explain(summary=i18n_t("organizer.forecast", lang))
    explain.add_step("start_balance", start_balance, formula=i18n_t("organizer.step.liquid_balance", lang))
    explain.add_step("horizon_days", days)
    explain.add_step("commitments_projected", len(_active(commitments)))
    explain.add_step("low_point", f"{low[0].isoformat()} → {low[1]}", formula="min(balance) over the horizon")
    return {
        "start_balance": {"amount": str(start_balance), "currency": currency},
        "series": series,
        "low_point": {"date": low[0].isoformat(), "balance": {"amount": str(low[1]), "currency": currency}},
        "safe_to_spend": safe_to_spend(ws_id, today, lang, commitments, txns=txns),
        "buffer": {"amount": str(effective_buffer(ws_id, commitments)[0]), "currency": currency},
        "explain": explain.model_dump(),
    }
