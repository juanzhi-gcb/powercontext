"""Regression coverage for behaviour that must not change (SPEC-ORD-001)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ordermesh import OrderStatus


@pytest.mark.spec("SPEC-ORD-001#R1")
def test_returns_every_order_of_one_customer_newest_first(service):
    orders = service.list_orders("c-1")

    assert [order.order_id for order in orders] == [
        "ORD-1004",
        "ORD-1003",
        "ORD-1002",
        "ORD-1001",
    ]


@pytest.mark.spec("SPEC-ORD-001#R1")
def test_unknown_customer_returns_empty_list(service):
    assert service.list_orders("c-404") == []


@pytest.mark.spec("SPEC-ORD-001#R2")
def test_status_filter_keeps_only_matching_orders(service):
    orders = service.list_orders("c-1", status=OrderStatus.PAID)

    assert [order.order_id for order in orders] == ["ORD-1002", "ORD-1001"]


@pytest.mark.spec("SPEC-ORD-001#R2")
def test_status_filter_accepts_the_enum_value(service):
    orders = service.list_orders("c-1", status="pending")

    assert [order.order_id for order in orders] == ["ORD-1003"]


@pytest.mark.spec("SPEC-ORD-001#R2")
def test_unknown_status_raises_value_error(service):
    with pytest.raises(ValueError, match="unknown status"):
        service.list_orders("c-1", status="lost")


@pytest.mark.regression
@pytest.mark.spec("SPEC-ORD-003#R2")
def test_omitting_min_total_does_not_filter(service):
    unfiltered = service.list_orders("c-1")
    explicit_none = service.list_orders("c-1", min_total=None)

    assert [order.order_id for order in explicit_none] == [
        order.order_id for order in unfiltered
    ]


@pytest.mark.spec("SPEC-ORD-001#R3")
def test_totals_are_exact_decimals(service):
    totals = [order.total for order in service.list_orders("c-1")]

    assert totals == [
        Decimal("150.00"),
        Decimal("200.00"),
        Decimal("150.00"),
        Decimal("100.00"),
    ]
