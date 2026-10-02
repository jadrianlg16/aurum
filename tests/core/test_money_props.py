"""Property tests for aurum.core.money."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from aurum.core.money import Amount, q2

CENTS = st.decimals(min_value=Decimal("-1e9"), max_value=Decimal("1e9"), places=2, allow_nan=False, allow_infinity=False)
ANY_DEC = st.decimals(min_value=Decimal("-1e9"), max_value=Decimal("1e9"), places=6, allow_nan=False, allow_infinity=False)


@settings(max_examples=200, deadline=None)
@given(ANY_DEC)
def test_q2_is_idempotent_and_two_places(value: Decimal):
    once = q2(value)
    assert q2(once) == once
    assert once == once.quantize(Decimal("0.01"))
    assert once == value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@settings(max_examples=200, deadline=None)
@given(st.floats(allow_nan=False, allow_infinity=False))
def test_amount_float_raises_value_error_not_type_error(value: float):
    with pytest.raises(ValidationError) as info:
        Amount(amount=value)
    assert info.value.errors()[0]["type"] == "value_error"


@settings(max_examples=200, deadline=None)
@given(CENTS, st.lists(ANY_DEC.filter(lambda d: d > 0), min_size=1, max_size=6))
def test_split_sum_half_up_contract(total: Decimal, weights: list[Decimal]):
    """Splitting a 2-decimal total by weights, rounding each part HALF_UP and putting the remainder on
    the last part, always sums back to the exact total."""
    total = q2(total)
    denominator = sum(weights)
    parts = [q2(total * w / denominator) for w in weights[:-1]]
    parts.append(q2(total - sum(parts)))
    assert sum(parts) == total
    assert all(p == q2(p) for p in parts)


@settings(max_examples=200, deadline=None)
@given(CENTS, CENTS)
def test_amount_add_sub_round_trip(a: Decimal, b: Decimal):
    x = Amount(amount=a, currency="mxn")
    y = Amount(amount=b, currency="MXN")
    assert (x + y - y).amount == a
    assert x.currency == "MXN"
    assert str(x.model_dump()["amount"]) == str(a)
