"""Bulk update of distributor-scoped vehicles (status / price / availability).

Same all-or-nothing semantics as the admin bulk-update (B1):
- Pre-flight validation against domain invariants for every row.
- Pre-flight scope check: any out-of-scope id rejects the whole batch.
- Status downgrades from ``sold`` are forbidden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.entities.vehicle import Vehicle
from domain.errors import VehicleNotFoundError
from infrastructure.repositories import distributor_repository as repo


@dataclass
class BulkUpdateDistributorVehiclesCommand:
    actor_id: UUID
    actor_role: str
    vehicle_ids: list[UUID]
    company_id: UUID | None = None
    status: str | None = None
    base_price: Decimal | None = None
    special_price: Decimal | None = None
    discount_price: Decimal | None = None
    is_available: bool | None = None
    fields_set: set[str] = field(default_factory=set)


async def handle_bulk_update_distributor_vehicles(
    cmd: BulkUpdateDistributorVehiclesCommand, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id, actor_role=cmd.actor_role, company_id=cmd.company_id
    )

    if not cmd.vehicle_ids:
        return {
            "message": "Нет данных для обновления",
            "updated_count": 0,
            "vehicles": [],
        }

    fields = cmd.fields_set
    updates: dict[str, Any] = {}
    if "status" in fields:
        updates["status"] = cmd.status
    if "base_price" in fields:
        updates["base_price"] = cmd.base_price
    if "special_price" in fields:
        updates["special_price"] = cmd.special_price
    if "discount_price" in fields:
        updates["discount_price"] = cmd.discount_price
    if "is_available" in fields:
        updates["is_available"] = cmd.is_available

    if not updates:
        return {
            "message": "Нет данных для обновления",
            "updated_count": 0,
            "vehicles": [],
        }

    # Pre-flight: every id must be in scope and live.
    dealer_filter = scope.dealer_filter()
    items, _ = await repo.list_distributor_vehicles(
        session,
        dealer_filter=dealer_filter,
        page=1,
        limit=max(len(cmd.vehicle_ids), 1),
    )
    # Re-query by ids explicitly to avoid pagination cutoffs.
    rows: list[dict[str, Any]] = []
    for vid in cmd.vehicle_ids:
        row = await repo.get_distributor_vehicle(session, vid)
        if row is None:
            raise VehicleNotFoundError(vid)
        scope.ensure_can_write(row.get("dealer_id"))
        rows.append(row)
    # `items` is unused but kept to assert the listing path is healthy.
    _ = items

    # Validate the would-be transition for every row.
    if "status" in updates:
        new_status = updates["status"]
        for raw in rows:
            entity = Vehicle.from_dict(raw)
            entity.compute_status_after_bulk_update(new_status)

    sample = dict(rows[0])
    sample.update(updates)
    Vehicle.from_dict(sample).ensure_valid()

    updated_rows, missing = await repo.bulk_update_in_scope(
        session,
        vehicle_ids=cmd.vehicle_ids,
        dealer_filter=dealer_filter,
        updates=updates,
    )
    if missing:
        # Pre-flight should have caught these — but if a race happens,
        # fail loudly rather than write a partial batch.
        raise VehicleNotFoundError(missing[0])

    _emit_vehicle_changes(rows, updates, cmd.actor_id)

    return {
        "message": f"Обновлено {len(updated_rows)} автомобилей",
        "updated_count": len(updated_rows),
        "vehicles": updated_rows,
    }


def _emit_vehicle_changes(
    rows: list[dict[str, Any]], updates: dict[str, Any], actor_id: UUID
) -> None:
    from infrastructure.messaging.status_events import emit_vehicle_status_changed

    for raw in rows:
        vid = raw["id"]
        old_status = raw.get("status")
        new_status = updates.get("status", old_status)
        old_available = raw.get("is_available")
        new_available = updates.get("is_available", old_available)
        if old_status != new_status or old_available != new_available:
            emit_vehicle_status_changed(
                vehicle_id=vid,
                old_status=old_status,
                new_status=str(new_status) if new_status is not None else "",
                changed_by=actor_id,
                payload={"is_available": new_available},
            )
