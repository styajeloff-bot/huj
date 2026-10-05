"""Bulk delete distributor-scoped vehicles.

All-or-nothing semantics: pre-flight scope check rejects the whole batch
if any id is missing or out of scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.errors import VehicleNotFoundError
from infrastructure.repositories import distributor_repository as repo


@dataclass
class BulkDeleteDistributorVehiclesCommand:
    actor_id: UUID
    actor_role: str
    vehicle_ids: list[UUID]
    company_id: UUID | None = None


async def handle_bulk_delete_distributor_vehicles(
    cmd: BulkDeleteDistributorVehiclesCommand, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id, actor_role=cmd.actor_role,
        company_id=cmd.company_id
    )

    if not cmd.vehicle_ids:
        return {
            "message": "Нет данных для удаления",
            "deleted_count": 0,
            "ids": [],
        }

    # Pre-flight: every id must exist and be writable by the actor.
    for vid in cmd.vehicle_ids:
        row = await repo.get_distributor_vehicle(session, vid)
        if row is None:
            raise VehicleNotFoundError(vid)
        scope.ensure_can_write(row.get("dealer_id"))

    dealer_filter = scope.dealer_filter()
    deleted_ids: list[UUID] = []
    for vid in cmd.vehicle_ids:
        ok = await repo.delete_vehicle_in_scope(
            session, vehicle_id=vid, dealer_filter=dealer_filter
        )
        if not ok:
            # Pre-flight should have caught this — guard against races.
            raise VehicleNotFoundError(vid)
        deleted_ids.append(vid)

    return {
        "message": f"Удалено {len(deleted_ids)} автомобилей",
        "deleted_count": len(deleted_ids),
        "ids": deleted_ids,
    }
