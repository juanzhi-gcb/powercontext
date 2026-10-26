"""Read-side order queries."""

from __future__ import annotations

from decimal import Decimal, DecimalException

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
        optional inclusive lower bound for the order total; the exact boundary
        semantics are owned by SPEC-ORD-003.

        Raises:
            ValueError: when ``status`` is not a known order status, or when
                ``min_total`` is invalid or negative.
        """

        orders = self._repository.list_for_customer(customer_id)

        if status is not None:
            if not isinstance(status, OrderStatus):
                try:
                    status = OrderStatus(status)
                except (TypeError, ValueError):
                    raise ValueError(f"unknown status: {status!r}") from None
            orders = [order for order in orders if order.status is status]

        if min_total is not None:
            if isinstance(min_total, bool) or not isinstance(
                min_total, (Decimal, int, str)
            ):
                raise ValueError(f"invalid min_total: {min_total!r}")

            try:
                threshold = (
                    min_total
                    if isinstance(min_total, Decimal)
                    else Decimal(min_total)
                )
            except (DecimalException, TypeError, ValueError):
                raise ValueError(f"invalid min_total: {min_total!r}") from None

            if not threshold.is_finite():
                raise ValueError(f"invalid min_total: {min_total!r}")
            if threshold < 0:
                raise ValueError(f"min_total must be non-negative: {min_total!r}")

            orders = [order for order in orders if order.total >= threshold]

        orders.sort(key=lambda order: order.created_at, reverse=True)
        return orders
