"""Credit cards, loans, MSI schedules, manual credit scores.

Cards and loans that belong to an archived ``pf_accounts`` row drop out of every list here. A card's
ledger balance is negative when money is owed: ``balance`` keeps the signed ledger number and
``owed`` carries the positive amount the person has to pay."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.dates import clamp_day
from ..core.explain import Explain
from ..core.i18n import t as i18n_t
from ..core.i18n import ws_lang
from ..core.money import q2
from ..core.validation import DayOfMonth, PositiveInt
from ..ledger.base import get_ledger
from . import finance, store

router = APIRouter()


# --- models -------------------------------------------------------------------------------------


class CreditCard(BaseModel):
    id: str = ""
    ws_id: str = ""
    account: str
    name: str
    cut_day: DayOfMonth
    due_day: DayOfMonth
    limit_amount: str
    currency: str = "MXN"
    apr: str | None = None


class Loan(BaseModel):
    id: str = ""
    ws_id: str = ""
    account: str
    name: str
    principal: str
    currency: str = "MXN"
    annual_rate: str
    months: int
    start: str  # YYYY-MM-DD


class MSI(BaseModel):
    id: str = ""
    ws_id: str = ""
    card_id: str
    purchase: str
    amount: str
    currency: str = "MXN"
    months: PositiveInt
    started: str
    paid_months: int = 0


class CreditScore(BaseModel):
    id: str = ""
    ws_id: str = ""
    bureau: str
    score: int
    date: str


# --- cards ---------------------------------------------------------------------------------------


def _archived_accounts(ws_id: str) -> set[str]:
    conn = store.db()
    return {r["account"] for r in conn.execute(
        "SELECT account FROM pf_accounts WHERE ws_id=? AND archived=1", (ws_id,)).fetchall()}


def list_cards(ws_id: str) -> list[dict]:
    conn = store.db()
    archived = _archived_accounts(ws_id)
    return [store.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM pf_credit_cards WHERE ws_id=?", (ws_id,)).fetchall() if r["account"] not in archived]


def create_card(ws_id: str, c: CreditCard) -> dict:
    conn = store.db()
    card_id = store.new_id("card")
    conn.execute(
        "INSERT INTO pf_credit_cards (id, ws_id, account, name, cut_day, due_day, limit_amount, currency, apr) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (card_id, ws_id, c.account, c.name, c.cut_day, c.due_day, str(Decimal(c.limit_amount)), c.currency, c.apr),
    )
    conn.commit()
    return get_card(ws_id, card_id)


def get_card(ws_id: str, card_id: str) -> dict:
    conn = store.db()
    row = conn.execute("SELECT * FROM pf_credit_cards WHERE ws_id=? AND id=?", (ws_id, card_id)).fetchone()
    if row is None:
        raise KeyError(card_id)
    return store.row_to_dict(row)


def _next_day(today: date, day: int) -> date:
    """Next occurrence of a day-of-month on or after ``today`` (31 → month end, never the 28th)."""
    candidate = clamp_day(today.year, today.month, day)
    if candidate < today:
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        candidate = clamp_day(year, month, day)
    return candidate


def _msi_for_card(ws_id: str, card_id: str) -> list[dict]:
    conn = store.db()
    out = []
    for r in conn.execute("SELECT * FROM pf_msi WHERE ws_id=? AND card_id=?", (ws_id, card_id)).fetchall():
        d = store.row_to_dict(r)
        amount = Decimal(d["amount"])
        monthly = (amount / d["months"]).quantize(Decimal("0.01"))
        remaining = max(0, d["months"] - d["paid_months"])
        out.append(
            {
                **d,
                "monthly": str(monthly),
                "remaining_amount": str(monthly * remaining),
                "remaining_months": remaining,
            }
        )
    return out


def card_status(ws_id: str, card: dict, today: date | None = None, lang: str | None = None) -> dict:
    today = today or date.today()
    ledger = get_ledger()
    balances = ledger.balances(ws_id)
    amounts = balances.get(card["account"], [])
    balance = sum((a.amount for a in amounts if a.currency == card["currency"]), Decimal("0"))
    owed = max(Decimal("0"), -balance)  # liabilities are negative in the ledger
    cut_date = _next_day(today, card["cut_day"])
    due_date = _next_day(today, card["due_day"])
    limit_amount = Decimal(card["limit_amount"])
    utilization = (owed / limit_amount) if limit_amount else Decimal("0")
    explain = Explain(summary=i18n_t("pf.card_status", ws_lang(ws_id, lang)))
    explain.add_step("balance", q2(balance))
    explain.add_step("owed", q2(owed), formula="-balance")
    explain.add_step("utilization", utilization.quantize(Decimal("0.0001")), formula="owed / limit")
    return {
        "id": card["id"],
        "name": card["name"],
        "account": card["account"],
        "balance": store.money(balance, card["currency"]),
        "balance_signed": store.money(balance, card["currency"]),
        "owed": store.money(owed, card["currency"]),
        "limit": store.money(limit_amount, card["currency"]),
        "utilization": str(utilization.quantize(Decimal("0.0001"))),
        "next_cut_date": cut_date.isoformat(),
        "next_due_date": due_date.isoformat(),
        "pago_no_intereses": store.money(owed, card["currency"]),
        "minimum_payment_note": "(verify) minimum payment is set by the issuer's cardholder agreement",
        "msi": _msi_for_card(ws_id, card["id"]),
        "explain": explain.model_dump(),
    }


# --- loans ---------------------------------------------------------------------------------------


def list_loans(ws_id: str) -> list[dict]:
    conn = store.db()
    archived = _archived_accounts(ws_id)
    return [store.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM pf_loans WHERE ws_id=?", (ws_id,)).fetchall() if r["account"] not in archived]


def create_loan(ws_id: str, loan: Loan) -> dict:
    conn = store.db()
    loan_id = store.new_id("loan")
    conn.execute(
        "INSERT INTO pf_loans (id, ws_id, account, name, principal, currency, annual_rate, months, start) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (loan_id, ws_id, loan.account, loan.name, str(Decimal(loan.principal)), loan.currency,
         str(Decimal(loan.annual_rate)), loan.months, loan.start),
    )
    conn.commit()
    return get_loan(ws_id, loan_id)


def get_loan(ws_id: str, loan_id: str) -> dict:
    conn = store.db()
    row = conn.execute("SELECT * FROM pf_loans WHERE ws_id=? AND id=?", (ws_id, loan_id)).fetchone()
    if row is None:
        raise KeyError(loan_id)
    return store.row_to_dict(row)


def loan_amortization(ws_id: str, loan_id: str, lang: str | None = None) -> dict:
    loan = get_loan(ws_id, loan_id)
    am = finance.build_amortization(Decimal(loan["principal"]), Decimal(loan["annual_rate"]), loan["months"])
    explain = Explain(summary=i18n_t("pf.loan_amortization", ws_lang(ws_id, lang)))
    explain.add_step("payment", am.payment.quantize(Decimal("0.01")))
    explain.add_step("total_interest", am.total_interest.quantize(Decimal("0.01")))
    return {
        "loan_id": loan_id,
        "payment": str(am.payment.quantize(Decimal("0.01"))),
        "total_paid": str(am.total_paid.quantize(Decimal("0.01"))),
        "total_interest": str(am.total_interest.quantize(Decimal("0.01"))),
        "rows": [
            {
                "month": r.month,
                "payment": str(r.payment.quantize(Decimal("0.01"))),
                "interest": str(r.interest.quantize(Decimal("0.01"))),
                "principal": str(r.principal.quantize(Decimal("0.01"))),
                "balance": str(r.balance.quantize(Decimal("0.01"))),
            }
            for r in am.rows
        ],
        "explain": explain.model_dump(),
    }


def loan_whatif(ws_id: str, loan_id: str, extra_monthly: Decimal, lang: str | None = None) -> dict:
    loan = get_loan(ws_id, loan_id)
    principal = Decimal(loan["principal"])
    rate = Decimal(loan["annual_rate"])
    months = loan["months"]
    base = finance.build_amortization(principal, rate, months)
    payment = base.payment + extra_monthly
    bal = principal
    r = rate / 12
    total_interest = Decimal("0")
    m = 0
    while bal > 0 and m < months * 3:
        m += 1
        interest = bal * r
        principal_part = min(bal, payment - interest)
        bal = max(Decimal("0"), bal - principal_part)
        total_interest += interest
    interest_saved = base.total_interest - total_interest
    explain = Explain(summary=i18n_t("pf.loan_whatif", ws_lang(ws_id, lang)))
    explain.add_step("base_months", months)
    explain.add_step("new_months", m)
    explain.add_step("interest_saved", interest_saved.quantize(Decimal("0.01")))
    return {
        "loan_id": loan_id,
        "months_to_payoff": m,
        "months_saved": months - m,
        "new_total_interest": str(total_interest.quantize(Decimal("0.01"))),
        "interest_saved": {"amount": str(interest_saved.quantize(Decimal("0.01"))), "currency": loan["currency"]},
        "explain": explain.model_dump(),
    }


# --- msi -------------------------------------------------------------------------------------


def create_msi(ws_id: str, m: MSI) -> dict:
    conn = store.db()
    msi_id = store.new_id("msi")
    conn.execute(
        "INSERT INTO pf_msi (id, ws_id, card_id, purchase, amount, currency, months, started, paid_months) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (msi_id, ws_id, m.card_id, m.purchase, str(Decimal(m.amount)), m.currency, m.months, m.started,
         m.paid_months),
    )
    conn.commit()
    return store.row_to_dict(conn.execute("SELECT * FROM pf_msi WHERE id=?", (msi_id,)).fetchone())


# --- credit scores -----------------------------------------------------------------------------


def list_scores(ws_id: str) -> list[dict]:
    conn = store.db()
    return [store.row_to_dict(r) for r in conn.execute(
        "SELECT * FROM pf_credit_scores WHERE ws_id=? ORDER BY date", (ws_id,)).fetchall()]


def create_score(ws_id: str, s: CreditScore) -> dict:
    conn = store.db()
    score_id = store.new_id("score")
    conn.execute(
        "INSERT INTO pf_credit_scores (id, ws_id, bureau, score, date) VALUES (?,?,?,?,?)",
        (score_id, ws_id, s.bureau, s.score, s.date),
    )
    conn.commit()
    return store.row_to_dict(conn.execute("SELECT * FROM pf_credit_scores WHERE id=?", (score_id,)).fetchone())


def delete_score(ws_id: str, score_id: str) -> None:
    conn = store.db()
    cur = conn.execute("DELETE FROM pf_credit_scores WHERE ws_id=? AND id=?", (ws_id, score_id))
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(score_id)


# --- router --------------------------------------------------------------------------------------


@router.get("/{ws}/credit/cards")
def api_cards(ws: str, lang: str | None = None) -> list[dict]:
    return [card_status(ws, c, lang=lang) for c in list_cards(ws)]


@router.post("/{ws}/credit/cards")
def api_create_card(ws: str, c: CreditCard) -> dict:
    return create_card(ws, c)


@router.post("/{ws}/credit/cards/{card_id}/msi")
def api_create_msi(ws: str, card_id: str, m: MSI) -> dict:
    m.card_id = card_id
    return create_msi(ws, m)


@router.get("/{ws}/credit/loans")
def api_loans(ws: str) -> list[dict]:
    return list_loans(ws)


@router.post("/{ws}/credit/loans")
def api_create_loan(ws: str, loan: Loan) -> dict:
    return create_loan(ws, loan)


@router.get("/{ws}/credit/loans/{loan_id}/amortization")
def api_loan_amortization(ws: str, loan_id: str, lang: str | None = None) -> dict:
    try:
        return loan_amortization(ws, loan_id, lang)
    except KeyError as e:
        raise HTTPException(404, f"loan {loan_id} not found") from e


class WhatIf(BaseModel):
    extra_monthly: str


@router.post("/{ws}/credit/loans/{loan_id}/whatif")
def api_loan_whatif(ws: str, loan_id: str, body: WhatIf, lang: str | None = None) -> dict:
    try:
        return loan_whatif(ws, loan_id, Decimal(body.extra_monthly), lang)
    except KeyError as e:
        raise HTTPException(404, f"loan {loan_id} not found") from e


@router.get("/{ws}/credit/scores")
def api_scores(ws: str) -> list[dict]:
    return list_scores(ws)


@router.post("/{ws}/credit/scores")
def api_create_score(ws: str, s: CreditScore) -> dict:
    return create_score(ws, s)


@router.delete("/{ws}/credit/scores/{score_id}")
def api_delete_score(ws: str, score_id: str) -> dict:
    try:
        delete_score(ws, score_id)
    except KeyError as e:
        raise HTTPException(404, f"score {score_id} not found") from e
    return {"ok": True}
