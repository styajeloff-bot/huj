"""Distributor-scoped read model for assignable dealer groups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.entities.leasing_application import LeasingApplication
from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import (
    application_assignment_repository as assignment_repo,
)
from infrastructure.repositories import application_repository


@dataclass(frozen=True)
class ListAssignableDealerGroupsQuery:
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    application_id: UUID | None = None
    brand: str | None = None


async def handle_list_assignable_dealer_groups(
    query: ListAssignableDealerGroupsQuery,
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    _ = query.actor_id
    if query.actor_role != "distributor":
        raise ServiceError("Назначение дилера доступно только дистрибьютору", 403)
    if query.actor_company_id is None:
        raise ServiceError("У пользователя не выбрана компания дистрибьютора", 403)

    if query.application_id is not None:
        application = await application_repository.get_by_id(
            session,
            query.application_id,
        )
        if application is None:
            raise ApplicationNotFoundError(query.application_id)
        has_distributor_vehicle = (
            await assignment_repo.application_has_company_warehouse_vehicle(
                session,
                application_id=query.application_id,
                company_id=query.actor_company_id,
            )
        )
        LeasingApplication.from_dict(application).ensure_can_assign_dealer(
            actor_role=query.actor_role,
            actor_company_id=query.actor_company_id,
            has_vehicle_on_actor_warehouse=has_distributor_vehicle,
        )

    groups = await assignment_repo.list_assignable_dealer_groups(
        session,
        distributor_company_id=query.actor_company_id,
        brand=query.brand,
    )
    return {"groups": groups}


__all__ = [
    "ListAssignableDealerGroupsQuery",
    "handle_list_assignable_dealer_groups",
]
