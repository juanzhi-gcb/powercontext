"""Persistence adapters for orders."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Order


class InMemoryOrderRepository:
    """Small in-memory store used by the service and by the tests."""

    def __init__(self, orders: Iterable[Order] = ()) -> None:
        self._orders: list[Order] = list(orders)

    def add(self, order: Order) -> None:
        self._orders.append(order)

    def list_for_customer(self, customer_id: str) -> list[Order]:
        """Return every order that belongs to ``customer_id``.

        The repository intentionally keeps insertion order; ordering guarantees
        belong to the service layer (see SPEC-ORD-001 R1).
        """

        return [order for order in self._orders if order.customer_id == customer_id]

    def __len__(self) -> int:
        return len(self._orders)