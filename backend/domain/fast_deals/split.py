"""DL split: one draft with positions of several dealers becomes one deal per dealer."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from domain.fast_deals.errors import FastDealValidationError
from domain.fast_deals.values import ItemStatus


def split_groups(
    vehicles: Sequence[Mapping[str, Any]],
) -> list[tuple[UUID, list[Mapping[str, Any]]]]:
    """Dealer groups in a stable order.

    Positions are ordered by ``position`` then ``id``; the first dealer met keeps the
    original deal (its id and number), the others get new ones.
    """
    active = sorted(
        (item for item in vehicles if item["item_status"] == ItemStatus.ACTIVE),
        key=lambda item: (item["position"], str(item["id"])),
    )
    if not active:
        raise FastDealValidationError("Добавьте хотя бы одну позицию техники")
    groups: dict[UUID, list[Mapping[str, Any]]] = {}
    for item in active:
        dealer = item.get("dealer_company_id")
        if dealer is None:
            raise FastDealValidationError(
                "Для каждой позиции должен быть определён дилер", field="dealer_company_id"
            )
        groups.setdefault(dealer, []).append(item)
    return list(groups.items())
