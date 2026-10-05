"""Mass-bind every unbound vehicle of a given mark to a warehouse."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    MarkNotFoundError,
    WarehouseNotFoundError,
)
from infrastructure.repositories import warehouse_repository as repo


@dataclass
class BindVehiclesByMarkCommand:
    warehouse_id: UUID
    mark_id: UUID | str


async def handle_bind_vehicles_by_mark(
    cmd: BindVehiclesByMarkCommand, session: AsyncSession
) -> dict[str, Any]:
    if await repo.get_by_id(session, cmd.warehouse_id) is None:
        raise WarehouseNotFoundError(cmd.warehouse_id)

    if not await repo.mark_exists(session, cmd.mark_id):
        raise MarkNotFoundError(str(cmd.mark_id))

    candidates = await repo.list_unbound_vehicle_ids_by_mark(session, cmd.mark_id)
    bound = await repo.bulk_create_bindings(
        session, cmd.warehouse_id, candidates
    )
    return {
        "message": "Автомобили марки привязаны к складу",
        "bound_count": bound,
        "total": len(candidates),
    }
