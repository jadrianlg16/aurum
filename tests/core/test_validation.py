"""core.validation + core.dates."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from aurum.core import dates
from aurum.core.money import Amount
from aurum.core.validation import Currency, IsoDate, Period, PositiveAmount, Tag, parse_decimal


class Body(BaseModel):
    when: IsoDate
    period: Period
    currency: Currency
    tag: Tag
    amount: PositiveAmount


def test_valid_body_normalises():
    b = Body(
        when="2026-09-12",
        period="2026-09",
        currency="mxn",
        tag="viaje-2026",
        amount=Amount(amount=Decimal("1"), currency="MXN"),
    )
    assert b.currency == "MXN" and b.when == "2026-09-12"


@pytest.mark.parametrize(
    "field,value",
    [
        ("when", "2026-13-01"),
        ("period", "2026-9"),
        ("currency", "M"),
        ("tag", "con espacio"),
        ("amount", Amount(amount=Decimal("0"), currency="MXN")),
    ],
)
def test_invalid_values_raise(field, value):
    good = dict(
        when="2026-09-12",
        period="2026-09",
        currency="MXN",
        tag="ok",
        amount=Amount(amount=Decimal("1"), currency="MXN"),
    )
    good[field] = value
    with pytest.raises(ValidationError):
        Body(**good)


def test_parse_decimal_rejects_floats_and_garbage():
    assert parse_decimal("12.50") == Decimal("12.50")
    with pytest.raises(ValueError):
        parse_decimal(12.5)
    with pytest.raises(ValueError):
        parse_decimal("abc")
    with pytest.raises(ValueError):
        parse_decimal("NaN")


def test_dates_helpers():
    assert dates.clamp_day(2026, 2, 31) == date(2026, 2, 28)
    assert dates.clamp_day(2028, 2, 31) == date(2028, 2, 29)
    assert dates.month_bounds("2026-09") == (date(2026, 9, 1), date(2026, 9, 30))
    # anchored on the 31st: Jan 31 -> Feb 28 -> Mar 31 (no permanent drift)
    feb = dates.add_months_keep_anchor(date(2026, 1, 31), 1, 31)
    mar = dates.add_months_keep_anchor(feb, 1, 31)
    assert (feb, mar) == (date(2026, 2, 28), date(2026, 3, 31))
    assert dates.shift_period("2026-01", -1) == "2025-12"
    assert dates.shift_period("2026-12", 1) == "2027-01"
