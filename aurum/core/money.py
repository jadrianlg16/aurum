"""Money is Decimal, serialized as a string with an explicit currency. Never float."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer, field_validator

CENT = Decimal("0.01")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

DecimalStr = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str)]


def q2(value: Decimal | str | int) -> Decimal:
    """Quantize to cents, half-up (what SAT and banks do)."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def to_decimal(value) -> Decimal:
    """Strict conversion: Decimal/int/str only (no float, no NaN/Infinity, no junk). Raises ``ValueError``
    so pydantic reports it as a 422 instead of a 500 (a ``TypeError`` is not converted)."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("amount must be a decimal string, int or Decimal, not float/bool")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation as e:
            raise ValueError(f"amount is not a decimal: {value!r}") from e
    else:
        raise ValueError(f"amount must be a decimal string, int or Decimal, got {type(value).__name__}")
    if not result.is_finite():
        raise ValueError("amount must be finite")
    return result


class Amount(BaseModel):
    amount: DecimalStr
    currency: str = Field(default="MXN")

    @field_validator("amount", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        return to_decimal(v)

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, v):
        if not isinstance(v, str):
            raise ValueError("currency must be a 3-letter code")
        code = v.strip().upper()
        if not CURRENCY_RE.match(code):
            raise ValueError(f"currency must match ^[A-Z]{{3}}$: {v!r}")
        return code

    def __add__(self, other: Amount) -> Amount:
        self._same(other)
        return Amount(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Amount) -> Amount:
        self._same(other)
        return Amount(amount=self.amount - other.amount, currency=self.currency)

    def _same(self, other: Amount) -> None:
        if other.currency != self.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    @classmethod
    def zero(cls, currency: str = "MXN") -> Amount:
        return cls(amount=Decimal("0"), currency=currency)

    def quantized(self) -> Amount:
        return Amount(amount=q2(self.amount), currency=self.currency)
