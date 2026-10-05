"""Dealer command for agreeing a requested special-equipment item price."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.special_equipment_application_pricing import (
    DealerPriceTransition,
    RequestedPriceApplicationNotFoundError,
    RequestedPriceItemApplicationMismatchError,
    RequestedPriceItemNotFoundError,
)
from infrastructure.repositories import application_repository as repo


@dataclass(frozen=True, slots=True)
class SetDealerApplicationItemPriceCommand:
    application_id: UUID
    item_id: UUID
    actor_id: UUID
    actor_company_id: UUID | None
    agreed_price: Decimal | None
    source: str = "api"


def _price_on_request(item: dict[str, Any]) -> bool:
    snapshot = item.get("item_snapshot")
    return isinstance(snapshot, dict) and snapshot.get("price_on_request") is True


async def handle_set_dealer_application_item_price(
    cmd: SetDealerApplicationItemPriceCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    locked = await repo.lock_application_price_state(session, cmd.application_id)
    if locked is None:
        raise RequestedPriceApplicationNotFoundError()

    target = next(
        (item for item in locked["items"] if item["id"] == cmd.item_id),
        None,
    )
    if target is None:
        target = await repo.get_special_equipment_application_item(
            session, cmd.item_id
        )
        if target is None:
            raise RequestedPriceItemNotFoundError()
        if target.get("application_id") != cmd.application_id:
            raise RequestedPriceItemApplicationMismatchError()

    application = locked["application"]
    leasing_company_assigned = bool(
        application.get("selected_leasing_companies")
    ) or await repo.has_lc_children(session, cmd.application_id)
    changed_at = datetime.now(UTC)
    update = DealerPriceTransition(
        application_status=str(application.get("status") or ""),
        leasing_company_assigned=leasing_company_assigned,
        seller_company_id=target.get("seller_company_id"),
        item_role=str(target.get("item_role") or ""),
        item_status=str(target.get("item_status") or ""),
        price_status=str(target.get("price_status") or "none"),
        price_on_request=_price_on_request(target),
    ).apply(
        actor_company_id=cmd.actor_company_id,
        actor_id=cmd.actor_id,
        agreed_price=cmd.agreed_price,
        changed_at=changed_at,
    )

    old_price = target.get("unit_price")
    normalized_old_price = (
        Decimal(str(old_price)) if old_price is not None else None
    )
    updated_item = await repo.update_special_equipment_application_item_price(
        session,
        item_id=cmd.item_id,
        unit_price=update.agreed_price,
        total_price=update.total_price,
        price_status=update.price_status,
        price_set_by=update.price_set_by,
        price_set_at=update.price_set_at,
    )
    await repo.append_special_equipment_price_change(
        session,
        item_id=cmd.item_id,
        old_price=normalized_old_price,
        new_price=update.agreed_price,
        changed_by=cmd.actor_id,
        changed_at=update.price_set_at,
        source=cmd.source,
    )
    total = await repo.sum_active_application_items_total(
        session, cmd.application_id
    )
    if total is None:
        raise RuntimeError(
            "Requested-price transition left an unknown active application total"
        )
    await repo.update_application_total_amount(
        session,
        application_id=cmd.application_id,
        total_amount=total,
    )
    return {
        "item_id": cmd.item_id,
        "application_id": cmd.application_id,
        "agreed_price": update.agreed_price,
        "currency": updated_item.get("currency_code") or "RUB",
        "status": "price_set",
        "price_set_by": update.price_set_by,
        "price_set_at": update.price_set_at,
        "application_total_amount": total,
    }


__all__ = [
    "SetDealerApplicationItemPriceCommand",
    "handle_set_dealer_application_item_price",
]
