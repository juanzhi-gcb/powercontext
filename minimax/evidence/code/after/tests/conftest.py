"""Shared fixtures for the ordermesh test suite."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ordermesh import InMemoryOrderRepository, Order, OrderService, OrderStatus


def _created(day: int) -> datetime:
    return datetime(2026, 1, day, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def repository() -> InMemoryOrderRepository:
    return InMemoryOrderRepository(
        [
            Order("ORD-1001", "c-1", Decimal("100.00"), OrderStatus.PAID, _created(1)),
            Order("ORD-1002", "c-1", Decimal("150.00"), OrderStatus.PAID, _created(2)),
            Order("ORD-1003", "c-1", Decimal("200.00"), OrderStatus.PENDING, _created(3)),
            Order("ORD-1004", "c-1", Decimal("150.00"), OrderStatus.SHIPPED, _created(4)),
            Order("ORD-2001", "c-2", Decimal("300.00"), OrderStatus.PAID, _created(5)),
        ]
    )


@pytest.fixture
def service(repository: InMemoryOrderRepository) -> OrderService:
    return OrderService(repository)
