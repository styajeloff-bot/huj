"""Atomically transfer current vehicle warehouse bindings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import warehouse_repository as repository


@dataclass(frozen=True)
class TransferVehiclesCommand:
    actor_id: UUID
    actor_role: str
    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    vehicle_ids: list[UUID]
    all_filtered: bool = False
    company_id: UUID | None = None


async def handle_transfer_vehicles(
    command: TransferVehiclesCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    if command.source_warehouse_id == command.destination_warehouse_id:
        raise ValueError("Исходный и целевой склады должны отличаться")
    if command.all_filtered and command.vehicle_ids:
        raise ValueError("Режимы выбора автомобилей нельзя совмещать")
    if not command.all_filtered and not command.vehicle_ids:
        raise ValueError("Необходимо выбрать хотя бы один автомобиль")
    if await repository.get_by_id(session, command.source_warehouse_id) is None:
        raise ValueError("Исходный склад не найден")
    if await repository.get_by_id(session, command.destination_warehouse_id) is None:
        raise ValueError("Целевой склад не найден")

    scope = await resolve_distributor_scope(
        session,
        actor_id=command.actor_id,
        actor_role=command.actor_role,
        company_id=command.company_id,
    )
    vehicle_ids = command.vehicle_ids
    available_vehicle_ids: set[UUID] | None = None
    if command.all_filtered:
        vehicle_ids = await repository.list_source_warehouse_vehicle_ids(
            session,
            source_warehouse_id=command.source_warehouse_id,
            dealer_filter=scope.dealer_filter(),
        )
    else:
        available_vehicle_ids = set(
            await repository.list_source_warehouse_vehicle_ids(
                session,
                source_warehouse_id=command.source_warehouse_id,
                dealer_filter=scope.dealer_filter(),
            )
        )

    results: list[dict[str, Any]] = []
    for vehicle_id in vehicle_ids:
        if available_vehicle_ids is not None and vehicle_id not in available_vehicle_ids:
            results.append({"vehicle_id": vehicle_id, "status": "unavailable"})
            continue
        transferred = await repository.transfer_vehicle_if_current(
            session,
            vehicle_id=vehicle_id,
            source_warehouse_id=command.source_warehouse_id,
            destination_warehouse_id=command.destination_warehouse_id,
            actor_user_id=command.actor_id,
        )
        results.append(
            {
                "vehicle_id": vehicle_id,
                "status": "transferred" if transferred else "conflict",
            }
        )
    transferred_count = sum(item["status"] == "transferred" for item in results)
    return {
        "transferred_count": transferred_count,
        "failed_count": len(results) - transferred_count,
        "results": results,
    }
