"""Accounts a person can create by hand.

``pf_accounts`` is the friendly registry: id <-> ledger account, friendly name, type, institution,
card/loan fields, archived flag. Balances are never stored here — always read live from the ledger
(``aurum.ledger.base.get_ledger``), so this file never drifts from the store of record.

Ledger account name derivation (``derive_ledger_account``) is a pure function of
``(existing accounts in the workspace, type, name)``: same name + type always yields the same ledger
account, and two different names never collide (a numeric suffix is appended when they would).

Liabilities are typed positive, stored signed: the person types what they owe as a positive number
(opening balance and "Ajustar saldo"); the server negates on write, so a credit card or loan always
carries a negative ledger balance.
Rows expose ``balance`` (owed, positive, for liabilities), ``balance_signed`` (the ledger number) and
``owed``. A duplicate (case-insensitive, non-archived) name is a 409 with the existing id — the name
check and the insert happen in one ``BEGIN IMMEDIATE`` transaction.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, model_validator

from ..core.money import Amount, q2
from ..core.validation import Currency, DayOfMonth, IsoDate, PositiveInt
from ..ledger.base import Posting, Transaction, get_ledger
from . import ledger_view, store
from .types import MoneyIn

router = APIRouter()

AccountType = Literal["checking", "savings", "cash", "credit_card", "loan", "investment", "other"]
LIABILITY_TYPES = {"credit_card", "loan"}
OPENING_EQUITY = "Equity:Opening"
SYSTEM_TAGS = {"opening-balance", "balance-adjustment", "sign-migration"}

_PREFIX: dict[str, str] = {
    "checking": "Assets:Bank:",
    "savings": "Assets:Bank:",
    "cash": "Assets:Cash",
    "credit_card": "Liabilities:CreditCard:",
    "loan": "Liabilities:Loans:",
    "investment": "Assets:Investments:",
    "other": "Assets:Other:",
}

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class AccountExists(Exception):
    def __init__(self, existing_id: str, name: str) -> None:
        super().__init__(f"an account named {name!r} already exists")
        self.existing_id = existing_id


class AccountHasMovements(Exception):
    """DELETE refused: the ledger account has live movements beyond opening/adjust rows → 409 + hint."""


class Unprocessable(ValueError):
    """A semantic 422 raised from business code (e.g. a negative owed amount)."""

    def __init__(self, field: str, msg: str) -> None:
        super().__init__(msg)
        self.field = field


def _clean_name(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or len(text) > 80:
        raise ValueError("must be 1 to 80 characters")
    if _CONTROL.search(text):
        raise ValueError("must not contain control characters")
    return text


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return _clean_name(text) if text else None


AccountName = Annotated[str, BeforeValidator(_clean_name)]
OptionalName = Annotated[str | None, BeforeValidator(_clean_optional)]


def slugify(name: str) -> str:
    """Deterministic CamelCase, ASCII-only beancount account segment. Never empty."""
    norm = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    parts = re.findall(r"[A-Za-z0-9]+", norm)
    slug = "".join(p.capitalize() for p in parts)
    return slug or "Account"


def derive_ledger_account(ws_id: str, type_: str, name: str) -> str:
    """Collision-safe: appends a numeric suffix only when a *different* name maps to the same slug."""
    conn = store.db()
    existing = {
        r["account"] for r in conn.execute("SELECT account FROM pf_accounts WHERE ws_id=?", (ws_id,)).fetchall()
    }
    if type_ == "cash" and "Assets:Cash" not in existing:
        return "Assets:Cash"
    prefix = _PREFIX[type_] if type_ != "cash" else "Assets:Cash:"
    candidate = f"{prefix}{slugify(name)}"
    final = candidate
    n = 2
    while final in existing:
        final = f"{candidate}{n}"
        n += 1
    return final


def _row(r) -> dict:
    return store.row_to_dict(r)


# --------------------------------------------------------------------------- apr helpers


def _apr_fraction(apr: str | None, apr_percent: str | None) -> str | None:
    """Stored form is a fraction string (``0.14``); ``apr_percent`` (``14``) wins when both are sent."""
    if apr_percent is not None and str(apr_percent).strip() != "":
        return str(Decimal(str(apr_percent)) / Decimal("100"))
    if apr is not None and str(apr).strip() != "":
        return str(Decimal(str(apr)))
    return None


def _apr_percent(apr: str | None) -> str | None:
    """``0.14`` → ``"14"``, ``0.425`` → ``"42.5"`` (plain digits, never exponent notation)."""
    if apr is None or str(apr).strip() == "":
        return None
    value = (Decimal(str(apr)) * 100).normalize()
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


# --------------------------------------------------------------------------- balances


def account_balance(ws_id: str, ledger_account: str, currency: str, balances: dict | None = None) -> Amount:
    balances = balances if balances is not None else get_ledger().balances(ws_id)
    for amt in balances.get(ledger_account, []):
        if amt.currency == currency:
            return amt
    return Amount.zero(currency)


def openings(ws_id: str) -> dict[str, tuple[Decimal, str]]:
    """``pf_account_id -> (signed amount, date)`` from the ``#opening-balance`` transactions."""
    out: dict[str, tuple[Decimal, str]] = {}
    for txn in get_ledger().journal(ws_id):
        if "opening-balance" not in txn.tags:
            continue
        pf_id = txn.meta.get("pf_account_id")
        if not pf_id or pf_id in out:
            continue
        leg = next((p for p in txn.postings if p.amount is not None and p.account != OPENING_EQUITY), None)
        if leg is not None and leg.amount is not None:
            out[pf_id] = (leg.amount.amount, txn.date.isoformat())
    return out


def _loan_months(ws_id: str, ledger_account: str, loans: dict | None = None) -> int | None:
    if loans is None:
        conn = store.db()
        row = conn.execute(
            "SELECT months FROM pf_loans WHERE ws_id=? AND account=?", (ws_id, ledger_account)
        ).fetchone()
        return int(row["months"]) if row and row["months"] else None
    months = loans.get(ledger_account)
    return int(months) if months else None


def with_balance(
    ws_id: str,
    row: dict,
    balances: dict | None = None,
    opening: dict[str, tuple[Decimal, str]] | None = None,
    loans: dict | None = None,
) -> dict:
    """One AccountRow (see docs/modules/pf-personal.md). Pass one ``balances()`` / ``openings()``
    result through ``list_accounts`` so a list costs one ledger load, not one per row."""
    out = dict(row)
    liability = row["type"] in LIABILITY_TYPES
    signed = account_balance(ws_id, row["account"], row["currency"], balances)
    out["archived"] = bool(row["archived"])
    out["ledger_account"] = row["account"]
    out["balance_signed"] = store.money(signed.amount, row["currency"])
    out["balance"] = store.money(-signed.amount if liability else signed.amount, row["currency"])
    out["owed"] = liability
    opening = opening if opening is not None else openings(ws_id)
    op = opening.get(row["id"])
    if op is None:
        out["opening_balance"] = None
        out["opening_date"] = None
    else:
        amount, when = op
        out["opening_balance"] = store.money(-amount if liability else amount, row["currency"])
        out["opening_date"] = when
    out["credit_limit"] = store.money(row["credit_limit"], row["currency"]) if row.get("credit_limit") else None
    out["apr"] = row.get("apr") or None
    out["apr_percent"] = _apr_percent(row.get("apr"))
    out["loan_months"] = _loan_months(ws_id, row["account"], loans) if row["type"] == "loan" else None
    return out


# --------------------------------------------------------------------------- models


class AccountIn(BaseModel):
    name: AccountName
    type: AccountType
    institution: OptionalName = None
    currency: Currency = "MXN"
    opening_balance: MoneyIn | None = None
    opening_date: IsoDate | None = None
    credit_limit: MoneyIn | None = None
    cut_day: DayOfMonth | None = None
    due_day: DayOfMonth | None = None
    apr: str | None = None
    apr_percent: str | None = None
    loan_months: PositiveInt | None = None
    loan_principal: MoneyIn | None = None

    @model_validator(mode="after")
    def _liability_opening_is_owed(self) -> AccountIn:
        if self.type in LIABILITY_TYPES and self.opening_balance is not None and self.opening_balance.amount < 0:
            raise ValueError("opening_balance for a credit card or loan is what you owe: send a positive number")
        if self.credit_limit is not None and self.credit_limit.amount < 0:
            raise ValueError("credit_limit must be >= 0")
        for field in ("apr", "apr_percent"):
            value = getattr(self, field)
            if value is not None and str(value).strip() != "":
                try:
                    Decimal(str(value))
                except ArithmeticError as exc:
                    raise ValueError(f"{field} must be a number") from exc
        return self


class AccountUpdate(BaseModel):
    name: OptionalName = None
    institution: OptionalName = None
    credit_limit: MoneyIn | None = None
    cut_day: DayOfMonth | None = None
    due_day: DayOfMonth | None = None
    apr: str | None = None
    apr_percent: str | None = None
    archived: bool | None = None
    loan_months: PositiveInt | None = None
    loan_principal: MoneyIn | None = None


class AdjustBody(BaseModel):
    balance: MoneyIn
    date: IsoDate | None = None
    note: str | None = None


# --------------------------------------------------------------------------- CRUD


def _sync_card(conn, ws_id: str, ledger_account: str, name: str, currency: str, cut_day, due_day,
               credit_limit: Amount | None, apr: str | None, existing_limit: str | None = None) -> None:
    limit = str(q2(credit_limit.amount)) if credit_limit is not None else (existing_limit or "0")
    row = conn.execute(
        "SELECT id FROM pf_credit_cards WHERE ws_id=? AND account=?", (ws_id, ledger_account)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO pf_credit_cards (id, ws_id, account, name, cut_day, due_day, limit_amount, currency, apr) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (store.new_id("card"), ws_id, ledger_account, name, cut_day or 1, due_day or 1, limit, currency, apr),
        )
    else:
        conn.execute(
            "UPDATE pf_credit_cards SET name=?, cut_day=?, due_day=?, limit_amount=?, apr=? WHERE id=?",
            (name, cut_day or 1, due_day or 1, limit, apr, row["id"]),
        )


def _sync_loan(conn, ws_id: str, ledger_account: str, name: str, currency: str, principal: Decimal | None,
               apr: str | None, months: int | None, start: str) -> None:
    row = conn.execute("SELECT * FROM pf_loans WHERE ws_id=? AND account=?", (ws_id, ledger_account)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO pf_loans (id, ws_id, account, name, principal, currency, annual_rate, months, start) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (store.new_id("loan"), ws_id, ledger_account, name, str(q2(principal or Decimal("0"))), currency,
             apr or "0", months or 0, start),
        )
    else:
        conn.execute(
            "UPDATE pf_loans SET name=?, principal=?, annual_rate=?, months=? WHERE id=?",
            (name, str(q2(principal)) if principal is not None else row["principal"],
             apr if apr is not None else row["annual_rate"], months if months is not None else row["months"],
             row["id"]),
        )


def create_account(ws_id: str, body: AccountIn, today: date | None = None) -> dict:
    conn = store.db()
    ledger_account = derive_ledger_account(ws_id, body.type, body.name)
    apr = _apr_fraction(body.apr, body.apr_percent)
    account_id = store.new_id("acct")
    ts = store.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        dup = conn.execute(
            "SELECT id FROM pf_accounts WHERE ws_id=? AND lower(name)=lower(?) AND archived=0",
            (ws_id, body.name),
        ).fetchone()
        if dup is not None:
            conn.rollback()
            raise AccountExists(dup["id"], body.name)
        conn.execute(
            "INSERT INTO pf_accounts (id, ws_id, name, type, institution, currency, account, credit_limit, "
            "cut_day, due_day, apr, archived, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
            (
                account_id, ws_id, body.name, body.type, body.institution, body.currency, ledger_account,
                str(q2(body.credit_limit.amount)) if body.credit_limit else None,
                body.cut_day, body.due_day, apr, ts, ts,
            ),
        )
        if body.type == "credit_card":
            _sync_card(conn, ws_id, ledger_account, body.name, body.currency, body.cut_day, body.due_day,
                       body.credit_limit, apr)
        elif body.type == "loan":
            principal = (
                body.loan_principal.amount if body.loan_principal is not None
                else abs(body.opening_balance.amount) if body.opening_balance is not None else None
            )
            if principal is not None or body.loan_months is not None:
                _sync_loan(conn, ws_id, ledger_account, body.name, body.currency, principal, apr, body.loan_months,
                           body.opening_date or (today or date.today()).isoformat())
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise

    if body.opening_balance is not None and body.opening_balance.amount != Decimal("0"):
        amount = q2(body.opening_balance.amount)
        if body.type in LIABILITY_TYPES:
            amount = -amount
        get_ledger().append(
            ws_id,
            Transaction(
                date=date.fromisoformat(body.opening_date) if body.opening_date else (today or date.today()),
                payee=None,
                narration="Saldo inicial",
                postings=[
                    Posting(account=ledger_account, amount=Amount(amount=amount, currency=body.currency)),
                    Posting(account=OPENING_EQUITY),
                ],
                tags=["opening-balance"],
                meta={"pf_account_id": account_id},
            ),
        )

    return get_account(ws_id, account_id)


def get_row(ws_id: str, account_id: str) -> dict:
    """The registry row only (no ledger load)."""
    conn = store.db()
    row = conn.execute("SELECT * FROM pf_accounts WHERE ws_id=? AND id=?", (ws_id, account_id)).fetchone()
    if row is None:
        raise KeyError(account_id)
    return _row(row)


def get_account(ws_id: str, account_id: str) -> dict:
    return with_balance(ws_id, get_row(ws_id, account_id))


def list_rows(ws_id: str, include_archived: bool = True) -> list[dict]:
    """Registry rows without balances (cheap: no ledger load)."""
    conn = store.db()
    sql = "SELECT * FROM pf_accounts WHERE ws_id=?"
    if not include_archived:
        sql += " AND archived=0"
    sql += " ORDER BY type, name"
    return [_row(r) for r in conn.execute(sql, (ws_id,)).fetchall()]


def list_accounts(ws_id: str, include_archived: bool = False, balances: dict | None = None) -> list[dict]:
    rows = list_rows(ws_id, include_archived)
    if not rows:
        return []
    balances = balances if balances is not None else get_ledger().balances(ws_id)
    opening = openings(ws_id)
    conn = store.db()
    loans = {r["account"]: r["months"] for r in conn.execute(
        "SELECT account, months FROM pf_loans WHERE ws_id=?", (ws_id,)).fetchall()}
    return [with_balance(ws_id, r, balances, opening, loans) for r in rows]


def update_account(ws_id: str, account_id: str, body: AccountUpdate) -> dict:
    existing = get_row(ws_id, account_id)
    conn = store.db()
    apr = _apr_fraction(body.apr, body.apr_percent)
    fields = {
        "name": body.name if body.name is not None else existing["name"],
        "institution": body.institution if body.institution is not None else existing["institution"],
        "credit_limit": str(q2(body.credit_limit.amount)) if body.credit_limit is not None
        else existing["credit_limit"],
        "cut_day": body.cut_day if body.cut_day is not None else existing["cut_day"],
        "due_day": body.due_day if body.due_day is not None else existing["due_day"],
        "apr": apr if apr is not None else existing["apr"],
        "archived": int(body.archived) if body.archived is not None else int(existing["archived"]),
    }
    if body.name is not None and body.name.lower() != str(existing["name"]).lower():
        dup = conn.execute(
            "SELECT id FROM pf_accounts WHERE ws_id=? AND lower(name)=lower(?) AND archived=0 AND id<>?",
            (ws_id, body.name, account_id),
        ).fetchone()
        if dup is not None:
            raise AccountExists(dup["id"], body.name)
    conn.execute(
        "UPDATE pf_accounts SET name=?, institution=?, credit_limit=?, cut_day=?, due_day=?, apr=?, "
        "archived=?, updated_at=? WHERE ws_id=? AND id=?",
        (*fields.values(), store.now(), ws_id, account_id),
    )
    if existing["type"] == "credit_card":
        _sync_card(conn, ws_id, existing["account"], fields["name"], existing["currency"], fields["cut_day"],
                   fields["due_day"], body.credit_limit, fields["apr"], existing_limit=existing["credit_limit"])
    elif existing["type"] == "loan" and (
        body.loan_months is not None or body.loan_principal is not None or body.name is not None or apr is not None
    ):
        _sync_loan(conn, ws_id, existing["account"], fields["name"], existing["currency"],
                   body.loan_principal.amount if body.loan_principal is not None else None,
                   fields["apr"], body.loan_months, date.today().isoformat())
    conn.commit()
    return get_account(ws_id, account_id)


def has_movements(ws_id: str, ledger_account: str) -> bool:
    """Live (void-aware) postings on the account other than opening/adjust system rows."""
    for txn, _posting in ledger_view.live_postings(ws_id, account_prefix=ledger_account):
        if SYSTEM_TAGS.intersection(txn.tags):
            continue
        return True
    return False


def delete_account(ws_id: str, account_id: str) -> dict:
    """Archive (never a hard delete of ledger history). Refuses if the ledger account has movements."""
    existing = get_row(ws_id, account_id)
    if has_movements(ws_id, existing["account"]):
        raise AccountHasMovements(
            f"account {account_id} has movements; archive it instead of deleting, or remove its entries first"
        )
    return update_account(ws_id, account_id, AccountUpdate(archived=True))


def adjust_account(ws_id: str, account_id: str, body: AdjustBody, today: date | None = None) -> dict:
    """Post a reconciling entry against Equity:Opening so the ledger balance matches ``body.balance``
    (liabilities: ``balance`` is what is owed, positive; the server posts the signed delta)."""
    existing = get_row(ws_id, account_id)
    liability = existing["type"] in LIABILITY_TYPES
    if liability and body.balance.amount < 0:
        raise Unprocessable("balance", "for a credit card or loan send what you owe as a positive number")
    target = -body.balance.amount if liability else body.balance.amount
    current = account_balance(ws_id, existing["account"], body.balance.currency)
    delta = q2(target - current.amount)
    if delta != Decimal("0"):
        get_ledger().append(
            ws_id,
            Transaction(
                date=date.fromisoformat(body.date) if body.date else (today or date.today()),
                payee=None,
                narration=body.note or "Ajuste de saldo",
                postings=[
                    Posting(account=existing["account"], amount=Amount(amount=delta, currency=body.balance.currency)),
                    Posting(account=OPENING_EQUITY),
                ],
                tags=["balance-adjustment"],
                meta={"pf_account_id": account_id},
            ),
        )
    return get_account(ws_id, account_id)


# --- router -----------------------------------------------------------------------------------


def _conflict(e: AccountExists) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(e), "existing_id": e.existing_id})


@router.post("/{ws}/accounts")
def api_create_account(ws: str, body: AccountIn):
    try:
        return create_account(ws, body)
    except AccountExists as e:
        return _conflict(e)


@router.get("/{ws}/accounts/{account_id}")
def api_get_account(ws: str, account_id: str) -> dict:
    try:
        return get_account(ws, account_id)
    except KeyError as e:
        raise HTTPException(404, f"account {account_id} not found") from e


@router.put("/{ws}/accounts/{account_id}")
def api_update_account(ws: str, account_id: str, body: AccountUpdate):
    try:
        return update_account(ws, account_id, body)
    except KeyError as e:
        raise HTTPException(404, f"account {account_id} not found") from e
    except AccountExists as e:
        return _conflict(e)


@router.delete("/{ws}/accounts/{account_id}")
def api_delete_account(ws: str, account_id: str):
    try:
        return delete_account(ws, account_id)
    except KeyError as e:
        raise HTTPException(404, f"account {account_id} not found") from e
    except AccountHasMovements as e:
        return JSONResponse(status_code=409, content={"detail": str(e), "hint": "archive"})


@router.post("/{ws}/accounts/{account_id}/adjust")
def api_adjust_account(ws: str, account_id: str, body: AdjustBody) -> dict:
    try:
        return adjust_account(ws, account_id, body)
    except KeyError as e:
        raise HTTPException(404, f"account {account_id} not found") from e
    except Unprocessable as e:
        raise HTTPException(422, [{"loc": ["body", e.field], "msg": str(e), "type": "value_error"}]) from e
