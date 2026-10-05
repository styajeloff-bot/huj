"""Query: warehouses where the given vehicle's modification is in stock."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import exchange_cart_repository as repo


@dataclass
class ListWarehousesForVehicleQuery:
    vehicle_id: UUID


async def handle_list_warehouses_for_vehicle(
    query: ListWarehousesForVehicleQuery, session: AsyncSession
) -> dict[str, Any]:
    warehouses = await repo.list_available_warehouses_for_vehicle(
        session, query.vehicle_id
    )
    return {"warehouses": warehouses}
