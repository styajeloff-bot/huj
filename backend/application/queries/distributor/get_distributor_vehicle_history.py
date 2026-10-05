"""Change history for a distributor-scoped vehicle.

The ORM schema has no dedicated ``vehicle_status_history`` table — vehicle
mutations are not currently journaled. Rather than 404 the UI, which calls
this on every vehicle-detail open, we surface a minimal two-event history
derived from the vehicle's own ``created_at`` / ``updated_at`` timestamps
so the component renders a timeline. Scope ownership is still enforced so
foreign distributors cannot probe for existence.

When a real status-history table is introduced this handler becomes the
single rewrite point — the router and UI contract already accept
``{history: [...]}`` and will work with any richer payload shape.
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
class GetDistributorVehicleHistoryQuery:
    actor_id: UUID
    actor_role: str
    vehicle_id: UUID
    company_id: UUID | None = None


async def handle_get_distributor_vehicle_history(
    query: GetDistributorVehicleHistoryQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role,
        company_id=query.company_id
    )
    vehicle = await repo.get_distributor_vehicle(session, query.vehicle_id)
    if vehicle is None:
        raise VehicleNotFoundError(query.vehicle_id)
    scope.ensure_can_write(vehicle.get("dealer_id"))

    history: list[dict[str, Any]] = []
    if vehicle.get("created_at") is not None:
        history.append(
            {
                "action": "created",
                "status": vehicle.get("status"),
                "timestamp": vehicle["created_at"],
                "user_id": vehicle.get("dealer_id"),
            }
        )
    updated_at = vehicle.get("updated_at")
    created_at = vehicle.get("created_at")
    if updated_at is not None and updated_at != created_at:
        history.append(
            {
                "action": "updated",
                "status": vehicle.get("status"),
                "timestamp": updated_at,
                "user_id": vehicle.get("dealer_id"),
            }
        )
    return {"history": history}
