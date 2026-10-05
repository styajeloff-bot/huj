"""Unified "available VINs for application_vehicle" query.

Phase 13 R13c — collapses:

* ``GET /applications/vehicle/:id/available-vins`` (self-owner scope).
* ``GET /admin/application-vehicles/:id/available-vins`` (admin scope).

into a single query handler. ``carcraft_employee`` skips the owner /
status guards (matching the legacy admin handler); any other role must
own the parent application and the application must be ``approved``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from application.permissions import (
    ensure_application_vehicle_action_allowed,
    require_distributor_application_read,
)
from domain.errors import (
    ApplicationNotFoundError,
    ApplicationVehicleNotFoundError,
)
from infrastructure.repositories import (
    application_repository as app_repo,
)
from infrastructure.repositories import (
    application_vehicle_repository as av_repo,
)


@dataclass
class ListAvailableVinsQuery:
    application_vehicle_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None = None
    actor_leasing_company_id: UUID | None = None


async def handle_list_available_vins(
    query: ListAvailableVinsQuery, session: AsyncSession
) -> dict[str, Any]:
    await require_distributor_application_read(
        session, user_id=query.actor_id, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    if query.actor_role == "carcraft_employee":
        return await _handle_admin(query, session)
    return await _handle_owner(query, session)


async def _handle_admin(
    query: ListAvailableVinsQuery, session: AsyncSession
) -> dict[str, Any]:
    av = await av_repo.get_by_id(session, query.application_vehicle_id)
    if av is None:
        raise ApplicationVehicleNotFoundError(query.application_vehicle_id)

    vehicles = await av_repo.list_available_vins_for_application_vehicle(
        session,
        complectation_id=av.get("modification_id"),
        color=None,
    )
    return {
        "success": True,
        "vehicles": vehicles,
        "application_vehicle_id": query.application_vehicle_id,
        "modification_id": av.get("modification_id"),
    }


async def _handle_owner(
    query: ListAvailableVinsQuery, session: AsyncSession
) -> dict[str, Any]:
    av = await app_repo.get_application_vehicle(
        session, query.application_vehicle_id
    )
    if av is None:
        raise ApplicationVehicleNotFoundError(query.application_vehicle_id)

    app_dict = await app_repo.get_by_id(session, av["application_id"])
    if app_dict is None:
        raise ApplicationNotFoundError(av["application_id"])
    dealer_filter: list[UUID] | None = None
    if query.actor_role == "distributor":
        scope = await resolve_distributor_scope(
            session,
            actor_id=query.actor_id,
            actor_role=query.actor_role,
            company_id=query.actor_company_id,
        )
        dealer_filter = scope.dealer_filter()
        if not await app_repo.distributor_can_view_application_vehicle(
            session,
            application_vehicle_id=query.application_vehicle_id,
            dealer_ids=dealer_filter,
            distributor_company_id=query.actor_company_id,
        ):
            raise ApplicationVehicleNotFoundError(query.application_vehicle_id)
    else:
        entity = await ensure_application_vehicle_action_allowed(
            session,
            application=app_dict,
            application_vehicle_id=query.application_vehicle_id,
            user_id=query.actor_id,
            actor_role=query.actor_role,
            actor_company_id=query.actor_company_id,
            actor_leasing_company_id=query.actor_leasing_company_id,
        )
        entity.ensure_can_assign_vin()

    vehicles = await app_repo.list_available_vins_for_application_vehicle(
        session,
        modification_id=av.get("modification_id"),
        color=av.get("color"),
        dealer_filter=dealer_filter,
    )
    return {
        "success": True,
        "vehicles": vehicles,
        "application_vehicle_id": query.application_vehicle_id,
        "modification_id": av.get("modification_id"),
    }
