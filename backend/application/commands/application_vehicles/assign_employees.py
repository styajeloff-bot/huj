"""Partially update employees assigned to one application vehicle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.application_vehicles.employees import (
    ensure_vehicle_employee_assignment_access,
)
from domain.errors import (
    ApplicationVehicleNotFoundError,
    EmployeeAssignmentNotAllowedError,
)
from infrastructure.repositories import (
    application_assignment_repository as employee_repo,
)
from infrastructure.repositories import application_repository
from infrastructure.repositories import (
    application_vehicle_assignment_repository as assignment_repo,
)


@dataclass(frozen=True)
class AssignApplicationVehicleEmployeesCommand:
    application_id: UUID
    application_vehicle_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    update_primary: bool = False
    primary_employee_id: UUID | None = None
    update_additional: bool = False
    additional_employee_id: UUID | None = None


async def handle_assign_application_vehicle_employees(
    command: AssignApplicationVehicleEmployeesCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    if not command.update_primary and not command.update_additional:
        raise ServiceError(
            "Укажите primary_employee_id и/или additional_employee_id",
            400,
        )
    assignment = await ensure_vehicle_employee_assignment_access(
        application_id=command.application_id,
        application_vehicle_id=command.application_vehicle_id,
        actor_id=command.actor_id,
        actor_role=command.actor_role,
        actor_company_id=command.actor_company_id,
        session=session,
    )
    effective_primary = (
        command.primary_employee_id
        if command.update_primary
        else assignment["primary_employee_id"]
    )
    effective_additional = (
        command.additional_employee_id
        if command.update_additional
        else assignment["additional_employee_id"]
    )
    if effective_primary is not None and effective_primary == effective_additional:
        raise EmployeeAssignmentNotAllowedError(
            "Основной и дополнительный сотрудники должны различаться"
        )

    fields: dict[str, UUID | None] = {}
    for update, field, employee_id in (
        (command.update_primary, "primary_employee_id", command.primary_employee_id),
        (
            command.update_additional,
            "additional_employee_id",
            command.additional_employee_id,
        ),
    ):
        if not update:
            continue
        if employee_id is not None:
            employee = await employee_repo.get_active_company_employee(
                session,
                company_id=assignment["dealer_company_id"],
                employee_id=employee_id,
            )
            if employee is None:
                raise EmployeeAssignmentNotAllowedError(
                    "Сотрудник не принадлежит назначенному дилеру"
                )
        fields[field] = employee_id

    updated = await assignment_repo.update_employee_assignment(
        session,
        application_id=command.application_id,
        application_vehicle_id=command.application_vehicle_id,
        employee_fields=fields,
        assigned_by=command.actor_id,
    )
    if not updated:
        raise ApplicationVehicleNotFoundError(command.application_vehicle_id)
    vehicles = await application_repository.list_application_vehicles_with_catalog(
        session,
        command.application_id,
    )
    vehicle = next(
        (item for item in vehicles if item["id"] == command.application_vehicle_id),
        None,
    )
    if vehicle is None:
        raise ApplicationVehicleNotFoundError(command.application_vehicle_id)
    details = await assignment_repo.get_assignment_details(
        session,
        application_vehicle_id=command.application_vehicle_id,
    )
    vehicle.update(details)
    return {"application_vehicle": vehicle}


__all__ = [
    "AssignApplicationVehicleEmployeesCommand",
    "handle_assign_application_vehicle_employees",
]
