"""Regression coverage for discount arithmetic (SPEC-ORD-005)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ordermesh import apply_percent_discount


@pytest.mark.spec("SPEC-ORD-005#R1")
def test_percent_discount_rounds_half_up_to_cents():
    assert apply_percent_discount(Decimal("19.99"), 10) == Decimal("17.99")


@pytest.mark.spec("SPEC-ORD-005#R2")
def test_zero_percent_keeps_the_total():
    assert apply_percent_discount(Decimal("42.00"), 0) == Decimal("42.00")


@pytest.mark.spec("SPEC-ORD-005#R3")
def test_out_of_range_percent_is_rejected():
    with pytest.raises(ValueError, match="percent"):
        apply_percent_discount(Decimal("10.00"), 101)


@pytest.mark.spec("SPEC-ORD-005#R3")
def test_non_decimal_total_is_rejected():
    with pytest.raises(TypeError, match="Decimal"):
        apply_percent_discount(10.0, 10)  # type: ignore[arg-type]
