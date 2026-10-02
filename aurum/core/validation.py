"""Shared request validators. Pydantic-annotated types for bodies and small helpers for
query params, so ordinary bad input is a 422 with a field name — never a 500.

Usage::

    from aurum.core.validation import IsoDate, Period, DayOfMonth, PositiveAmount, period_q, date_q

    class BudgetIn(BaseModel):
        period: Period
        amount: PositiveAmount

    @router.get("/{ws}/review/{period}")
    def review(ws: str, period: str = Depends(period_q)) -> dict: ...
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import HTTPException, Query
from pydantic import AfterValidator, BeforeValidator, Field

from .money import Amount

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
TAG_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
CURRENCY_RE = re.compile(r"^[A-Z][A-Z0-9]{2}$")


def _iso_date(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError("must be a date YYYY-MM-DD") from exc


def _period(value: object) -> str:
    text = str(value)
    if not PERIOD_RE.match(text):
        raise ValueError("must be a period YYYY-MM")
    return text


def _currency(value: object) -> str:
    text = str(value).strip().upper()
    if not CURRENCY_RE.match(text):
        raise ValueError("must be a 3-letter currency code")
    return text


def _tag(value: object) -> str:
    text = str(value).strip()
    if not TAG_RE.match(text):
        raise ValueError("tags may only contain letters, digits, '_' and '-'")
    return text


def _positive_amount(value: Amount) -> Amount:
    if value.amount <= 0:
        raise ValueError("amount must be greater than zero")
    return value


IsoDate = Annotated[str, BeforeValidator(_iso_date)]
Period = Annotated[str, BeforeValidator(_period)]
DayOfMonth = Annotated[int, Field(ge=1, le=31)]
Weekday = Annotated[int, Field(ge=0, le=6)]
PositiveInt = Annotated[int, Field(ge=1)]
Currency = Annotated[str, BeforeValidator(_currency)]
Tag = Annotated[str, BeforeValidator(_tag)]
PositiveAmount = Annotated[Amount, AfterValidator(_positive_amount)]


def parse_decimal(value: object, field: str = "amount") -> Decimal:
    """Strict decimal from a string (floats rejected: they are not exact money)."""
    if isinstance(value, float):
        raise ValueError(f"{field}: send money as a string, not a float")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field}: not a number") from exc
    if not result.is_finite():
        raise ValueError(f"{field}: not a finite number")
    return result


# --- query-param dependencies (raise 422 like pydantic bodies do) ---------------------------------


def _unprocessable(field: str, msg: str) -> HTTPException:
    return HTTPException(422, [{"loc": ["query", field], "msg": msg, "type": "value_error"}])


def period_q(period: str = Query(..., description="YYYY-MM")) -> str:
    try:
        return _period(period)
    except ValueError as exc:
        raise _unprocessable("period", str(exc)) from exc


def optional_period_q(period: str | None = Query(None, description="YYYY-MM")) -> str | None:
    if period is None:
        return None
    try:
        return _period(period)
    except ValueError as exc:
        raise _unprocessable("period", str(exc)) from exc


def date_q(name: str):
    """Factory: ``Depends(date_q("from"))`` validates an optional ``YYYY-MM-DD`` query param."""

    def dep(value: str | None = Query(None, alias=name, description="YYYY-MM-DD")) -> str | None:
        if value is None or value == "":
            return None
        try:
            return _iso_date(value)
        except ValueError as exc:
            raise _unprocessable(name, str(exc)) from exc

    dep.__name__ = f"date_q_{name}"
    return dep


def validate_period(period: str) -> str:
    """For handlers that take the period as a path param: 422 on a bad value."""
    try:
        return _period(period)
    except ValueError as exc:
        raise _unprocessable("period", str(exc)) from exc


def validate_date(value: str, field: str = "date") -> str:
    try:
        return _iso_date(value)
    except ValueError as exc:
        raise _unprocessable(field, str(exc)) from exc
