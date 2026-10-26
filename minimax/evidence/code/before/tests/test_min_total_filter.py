"""Target tests for the amount lower bound (SPEC-ORD-003).

These tests encode the behaviour the change must add. They fail on the current
implementation and must pass after the MiniMax-assisted change is applied.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ordermesh import OrderStatus


@pytest.mark.spec("SPEC-ORD-003#R1")
def test_min_total_includes_orders_equal_to_the_boundary(service):
    orders = service.list_orders("c-1", min_total=Decimal("150.00"))

    assert [order.order_id for order in orders] == ["ORD-1004", "ORD-1003", "ORD-1002"]


@pytest.mark.spec("SPEC-ORD-003#R1")
def test_min_total_accepts_a_decimal_string(service):
    orders = service.list_orders("c-1", min_total="150.00")

    assert [order.order_id for order in orders] == ["ORD-1004", "ORD-1003", "ORD-1002"]


@pytest.mark.spec("SPEC-ORD-003#R3")
def test_negative_min_total_is_rejected(service):
    with pytest.raises(ValueError, match="min_total"):
        service.list_orders("c-1", min_total=-1)


@pytest.mark.spec("SPEC-ORD-003#R3")
def test_unparseable_min_total_is_rejected(service):
    with pytest.raises(ValueError, match="min_total"):
        service.list_orders("c-1", min_total="not-a-number")


@pytest.mark.spec("SPEC-ORD-003#R1")
def test_min_total_composes_with_the_status_filter(service):
    orders = service.list_orders("c-1", status=OrderStatus.PAID, min_total="150")

    assert [order.order_id for order in orders] == ["ORD-1002"]


@pytest.mark.spec("SPEC-ORD-003#R4")
def test_filtering_keeps_the_newest_first_order(service):
    orders = service.list_orders("c-1", min_total=Decimal("150"))

    assert [order.order_id for order in orders] == ["ORD-1004", "ORD-1003", "ORD-1002"]