"""Add a vehicle to the LC exchange cart (dedupe by (user, vehicle))."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_supports import (
    resolve_exchange_support_selection,
)
from domain.errors import VehicleNotFoundError
from infrastructure.repositories import exchange_cart_repository as repo


@dataclass
class AddToExchangeCartCommand:
    user_id: UUID
    vehicle_id: UUID
    quantity: int = 1
    warehouse_id: UUID | None = None
    selected_support_ids: list[UUID] | None = None


async def handle_add_to_exchange_cart(
    cmd: AddToExchangeCartCommand, session: AsyncSession
) -> dict[str, Any]:
    if not await repo.vehicle_exists(session, cmd.vehicle_id):
        raise VehicleNotFoundError(cmd.vehicle_id)

    quantity = max(int(cmd.quantity), 1)
    existing = await repo.find_by_user_and_vehicle(
        session, user_id=cmd.user_id, vehicle_id=cmd.vehicle_id
    )
    requested_support_ids = (
        list(cmd.selected_support_ids)
        if cmd.selected_support_ids is not None
        else list(existing.get("selected_support_ids") or [])
        if existing is not None
        else []
    )
    support_selection = await resolve_exchange_support_selection(
        session,
        user_id=cmd.user_id,
        vehicle_id=cmd.vehicle_id,
        requested_ids=requested_support_ids,
        select_default=existing is None and cmd.selected_support_ids is None,
    )

    if existing is not None:
        new_qty = int(existing["quantity"] or 0) + quantity
        await repo.update_item(
            session,
            existing["id"],
            user_id=cmd.user_id,
            quantity=new_qty,
            selected_support_ids=support_selection.selected_ids,
        )
        if cmd.warehouse_id is not None:
            await repo.add_warehouse_if_missing(
                session,
                cart_item_id=existing["id"],
                warehouse_id=cmd.warehouse_id,
            )
        updated = await repo.get_by_id(session, existing["id"])
        assert updated is not None
        return {
            "message": "Количество обновлено",
            "item": updated,
            "created": False,
        }

    item_id = await repo.add_item(
        session,
        user_id=cmd.user_id,
        vehicle_id=cmd.vehicle_id,
        quantity=quantity,
    )
    await repo.update_item(
        session,
        item_id,
        user_id=cmd.user_id,
        selected_support_ids=support_selection.selected_ids,
    )
    if cmd.warehouse_id is not None:
        await repo.set_warehouses(
            session,
            cart_item_id=item_id,
            warehouse_ids=[cmd.warehouse_id],
        )
    saved = await repo.get_by_id(session, item_id)
    assert saved is not None
    return {
        "message": "Автомобиль добавлен в корзину биржи",
        "item": saved,
        "created": True,
    }
