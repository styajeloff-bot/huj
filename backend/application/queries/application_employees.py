"""Search assignable employees for a role-accessible application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.permissions import ensure_application_visible_to
from domain.entities.leasing_application import LeasingApplication
from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import (
    application_assignment_repository as assignment_repo,
)
from infrastructure.repositories import application_repository

_EMPLOYEE_ASSIGNMENT_ROLES = {
    "dealer",
    "distributor",
    "carcraft_employee",
}


@dataclass(frozen=True)
class SearchApplicationEmployeesQuery:
    application_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    query: str | None = None
    limit: int = 20


async def ensure_employee_assignment_access(
    *,
    application_id: UUID,
    actor_id: UUID,
    actor_role: str,
    actor_company_id: UUID | None,
    session: AsyncSession,
) -> tuple[dict[str, Any], LeasingApplication]:
    if actor_role not in _EMPLOYEE_ASSIGNMENT_ROLES:
        raise ServiceError("Назначение сотрудников недоступно для этой роли", 403)
    if actor_company_id is None:
        raise ServiceError("У пользователя не выбрана компания", 400)

    application = await application_repository.get_by_id(session, application_id)
    if application is None:
        raise ApplicationNotFoundError(application_id)
    entity = LeasingApplication.from_dict(application)
    if actor_role == "distributor":
        entity = await ensure_application_visible_to(
            session,
            application=application,
            user_id=actor_id,
            actor_role=actor_role,
            actor_company_id=actor_company_id,
        )
    entity.ensure_owned_by(
        user_id=actor_id,
        role=actor_role,
        company_id=actor_company_id,
    )
    has_distributor_vehicle = False
    if actor_role == "distributor":
        has_distributor_vehicle = (
            await assignment_repo.application_has_company_warehouse_vehicle(
                session,
                application_id=application_id,
                company_id=actor_company_id,
            )
        )
    entity.ensure_can_manage_employees(
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        has_vehicle_on_actor_warehouse=has_distributor_vehicle,
    )
    return application, entity


async def handle_search_application_employees(
    query: SearchApplicationEmployeesQuery,
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    await ensure_employee_assignment_access(
        application_id=query.application_id,
        actor_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        session=session,
    )
    if query.actor_company_id is None:
        raise ServiceError("У пользователя не выбрана компания", 400)
    employees = await assignment_repo.search_company_employees(
        session,
        company_id=query.actor_company_id,
        query=query.query,
        limit=min(max(query.limit, 1), 100),
    )
    return {"employees": employees}


__all__ = [
    "SearchApplicationEmployeesQuery",
    "ensure_employee_assignment_access",
    "handle_search_application_employees",
]
