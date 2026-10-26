"""Core domain models for ordermesh."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class OrderStatus(str, Enum):
    """Lifecycle states an order can be in."""

    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Order:
    """A single customer order.

    ``total`` is always a :class:`~decimal.Decimal` so that money comparisons in
    :meth:`ordermesh.service.OrderService.list_orders` are exact.
    """

    order_id: str
    customer_id: str
    total: Decimal
    status: OrderStatus
    created_at: datetime

    def is_open(self) -> bool:
        """Return ``True`` while the order can still change state."""

        return self.status in (OrderStatus.PENDING, OrderStatus.PAID)
