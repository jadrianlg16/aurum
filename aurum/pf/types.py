"""pf request types layered over ``core.validation``.

``MoneyIn`` checks the raw payload before ``core.money.Amount`` sees it (float → "send money as a string";
text → "not a number") so every pf body fails with a field-level 422 and a plain message. ``Amount``
itself also rejects floats and text with a ``ValueError``; this pre-check keeps the pf messages short and
consistent.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator

from ..core.money import Amount


def _raw_money(value: object) -> object:
    if isinstance(value, Amount):
        return value
    if isinstance(value, dict):
        raw = value.get("amount")
        if isinstance(raw, float):
            raise ValueError("amount: send money as a string, not a float")
        if isinstance(raw, bool) or raw is None:
            raise ValueError("amount: not a number")
        try:
            parsed = Decimal(str(raw))
        except InvalidOperation as exc:
            raise ValueError("amount: not a number") from exc
        if not parsed.is_finite():
            raise ValueError("amount: not a finite number")
        return {**value, "amount": str(parsed)}
    return value


def _positive(value: Amount) -> Amount:
    if not value.amount > Decimal("0"):
        raise ValueError("amount must be greater than zero")
    return value


MoneyIn = Annotated[Amount, BeforeValidator(_raw_money)]
PositiveMoney = Annotated[Amount, BeforeValidator(_raw_money), AfterValidator(_positive)]
