"""Discount arithmetic kept stable by the regression suite (SPEC-ORD-005)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def apply_percent_discount(total: Decimal, percent: int) -> Decimal:
    """Return ``total`` reduced by ``percent`` percent, rounded to cents."""

    if not isinstance(total, Decimal):
        raise TypeError("total must be a Decimal")
    if not isinstance(percent, int):
        raise TypeError("percent must be an int")
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")

    factor = Decimal(100 - percent) / Decimal(100)
    return (total * factor).quantize(_CENT, rounding=ROUND_HALF_UP)
