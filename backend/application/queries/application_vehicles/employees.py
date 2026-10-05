"""Search employees assignable to one application vehicle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.dealer_distribution_access import ensure_whole_vehicle_write_allowed
from application.errors import ServiceError
from application.permissions import require_distributor_application_read
from domain.errors import ApplicationNotOwnedError, ApplicationVehicleNotFoundError
from infrastructure.repositories import (
    application_assignment_repository as employee_repo,
)
from infrastructure.repositories import application_repository
from infrastructure.repositories import (
    application_vehicle_assignment_repository as assignment_repo,
)

_ALLOWED_ROLES = {"dealer", "distributor", "carcraft_employee"}


@dataclass(frozen=True)
class SearchApplicationVehicleEmployeesQuery:
    application_id: UUID
    application_vehicle_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    query: str | None = None
    limit: int = 20


async def ensure_vehicle_employee_assignment_access(
    *,
    application_id: UUID,
    application_vehicle_id: UUID,
    actor_id: UUID,
    actor_role: str,
    actor_company_id: UUID | None,
    session: AsyncSession,
) -> dict[str, Any]:
    if actor_role not in _ALLOWED_ROLES:
        raise ApplicationNotOwnedError(
            "Назначение сотрудников недоступно для этой роли"
        )
    assignment = cast(
        "dict[str, Any] | None",
        await assignment_repo.get_assignment(
            session,
            application_id=application_id,
            application_vehicle_id=application_vehicle_id,
        ),
    )
    if assignment is None:
        raise ApplicationVehicleNotFoundError(application_vehicle_id)
    distribution_scope = await ensure_whole_vehicle_write_allowed(session,
        application_vehicle_id=application_vehicle_id,
        actor_role=actor_role, actor_company_id=actor_company_id)
    if (
        assignment["dealer_company_id"] is None
        and distribution_scope["distributed_quantity"] == distribution_scope["quantity"]
        and distribution_scope["sole_dealer_id"] is not None
    ):
        assignment["dealer_company_id"] = distribution_scope["sole_dealer_id"]
    if actor_role == "dealer":
        if (
            actor_company_id is None
            or assignment["dealer_company_id"] != actor_company_id
        ):
            raise ApplicationNotOwnedError()
    elif actor_role == "distributor":
        if actor_company_id is None:
            raise ServiceError("У пользователя не выбрана компания", 400)
        await require_distributor_application_read(
            session, user_id=actor_id, actor_role=actor_role,
            actor_company_id=actor_company_id,
        )
        owns_vehicle = await application_repository.distributor_can_view_application_vehicle(
            session,
            application_vehicle_id=application_vehicle_id,
            dealer_ids=None,
            distributor_company_id=actor_company_id,
        )
        if not owns_vehicle:
            raise ApplicationNotOwnedError()
    if assignment["dealer_company_id"] is None:
        raise ServiceError("Сначала назначьте дилера автомобилю", 400)
    return assignment


async def handle_search_application_vehicle_employees(
    query: SearchApplicationVehicleEmployeesQuery,
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    assignment = await ensure_vehicle_employee_assignment_access(
        application_id=query.application_id,
        application_vehicle_id=query.application_vehicle_id,
        actor_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        session=session,
    )
    employees = await employee_repo.search_company_employees(
        session,
        company_id=assignment["dealer_company_id"],
        query=query.query,
        limit=min(max(query.limit, 1), 100),
    )
    return {"employees": employees}


__all__ = [
    "SearchApplicationVehicleEmployeesQuery",
    "ensure_vehicle_employee_assignment_access",
    "handle_search_application_vehicle_employees",
]
