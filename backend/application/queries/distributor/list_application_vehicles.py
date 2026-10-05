"""List vehicles attached to a leasing application, scoped to distributor."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_application_dealer_filter
from application.permissions import require_distributor_application_read
from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import application_repository as application_repo
from infrastructure.repositories import distributor_repository as repo


@dataclass
class ListApplicationVehiclesQuery:
    actor_id: UUID
    actor_role: str
    application_id: uuid.UUID
    company_id: UUID | None = None


async def handle_list_application_vehicles(
    query: ListApplicationVehiclesQuery, session: AsyncSession
) -> dict[str, Any]:
    await require_distributor_application_read(session, user_id=query.actor_id,
        actor_role=query.actor_role, actor_company_id=query.company_id)
    dealer_filter = await resolve_distributor_application_dealer_filter(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role, company_id=query.company_id
    )
    if query.actor_role == "distributor" and not await application_repo.distributor_can_view_application(
        session,
        application_id=query.application_id,
        dealer_ids=dealer_filter,
        distributor_company_id=query.company_id,
    ):
        raise ApplicationNotFoundError(query.application_id)
    vehicles = await repo.list_vehicles_for_application(
        session,
        application_id=query.application_id,
        dealer_filter=dealer_filter,
        distributor_company_id=query.company_id if query.actor_role == "distributor" else None,
    )
    return {"vehicles": vehicles}
