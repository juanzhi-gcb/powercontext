"""Read-side order queries."""

from __future__ import annotations

from decimal import Decimal

from .models import Order, OrderStatus
from .repository import InMemoryOrderRepository


class OrderService:
    """Order listing API consumed by the storefront."""

    def __init__(self, repository: InMemoryOrderRepository) -> None:
        self._repository = repository

    def list_orders(
        self,
        customer_id: str,
        status: OrderStatus | str | None = None,
        min_total: Decimal | int | str | None = None,
    ) -> list[Order]:
        """Return one customer's orders, newest first.

        ``status`` keeps only orders in that lifecycle state. ``min_total`` is the
        optional lower bound for the order total; the exact boundary semantics
        are owned by SPEC-ORD-003.

        Raises:
            ValueError: when ``status`` is not a known order status.
        """

        orders = self._repository.list_for_customer(customer_id)

        if status is not None:
            if not isinstance(status, OrderStatus):
                try:
                    status = OrderStatus(status)
                except ValueError as exc:
                    raise ValueError(f"unknown status: {status!r}") from exc
            orders = [order for order in orders if order.status is status]

        if min_total is not None:
            # TODO(SPEC-ORD-003): the lower bound is exclusive today and negative
            # input is not validated yet.
            threshold = min_total if isinstance(min_total, Decimal) else Decimal(min_total)
            orders = [order for order in orders if order.total > threshold]

        orders.sort(key=lambda order: order.created_at, reverse=True)
        return orders
