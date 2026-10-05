"""Partially update the primary/additional employees of an application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.application_employees import (
    ensure_employee_assignment_access,
)
from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import (
    application_assignment_repository as assignment_repo,
)
from infrastructure.repositories import application_repository


@dataclass(frozen=True)
class AssignApplicationEmployeesCommand:
    application_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    update_primary: bool = False
    primary_employee_id: UUID | None = None
    update_additional: bool = False
    additional_employee_id: UUID | None = None


async def handle_assign_application_employees(
    command: AssignApplicationEmployeesCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    if not command.update_primary and not command.update_additional:
        raise ServiceError(
            "Укажите primary_employee_id и/или additional_employee_id",
            400,
        )
    application, entity = await ensure_employee_assignment_access(
        application_id=command.application_id,
        actor_id=command.actor_id,
        actor_role=command.actor_role,
        actor_company_id=command.actor_company_id,
        session=session,
    )
    del application
    effective_primary_employee_id = (
        command.primary_employee_id
        if command.update_primary
        else entity.primary_employee_id
    )
    effective_additional_employee_id = (
        command.additional_employee_id
        if command.update_additional
        else entity.additional_employee_id
    )
    entity.ensure_employee_assignments_are_distinct(
        primary_employee_id=effective_primary_employee_id,
        additional_employee_id=effective_additional_employee_id,
    )

    fields: dict[str, UUID | None] = {}
    if command.update_primary:
        if command.primary_employee_id is not None:
            employee = await _get_assignable_employee(
                session,
                actor_company_id=command.actor_company_id,
                employee_id=command.primary_employee_id,
            )
            entity.ensure_employee_is_assignable(
                employee_is_active_company_member=employee is not None
            )
        fields["primary_employee_id"] = command.primary_employee_id

    if command.update_additional:
        if command.additional_employee_id is not None:
            employee = await _get_assignable_employee(
                session,
                actor_company_id=command.actor_company_id,
                employee_id=command.additional_employee_id,
            )
            entity.ensure_employee_is_assignable(
                employee_is_active_company_member=employee is not None
            )
        fields["additional_employee_id"] = command.additional_employee_id

    updated = await assignment_repo.update_employee_assignment(
        session,
        application_id=command.application_id,
        employee_fields=fields,
        assigned_by=command.actor_id,
    )
    if not updated:
        raise ApplicationNotFoundError(command.application_id)
    saved = await application_repository.get_by_id(
        session,
        command.application_id,
    )
    if saved is None:
        raise ApplicationNotFoundError(command.application_id)
    saved.update(
        await assignment_repo.get_assignment_details(
            session,
            application_id=command.application_id,
            actor_company_id=command.actor_company_id,
        )
    )
    return {"application": saved}


async def _get_assignable_employee(
    session: AsyncSession,
    *,
    actor_company_id: UUID | None,
    employee_id: UUID,
) -> dict[str, Any] | None:
    if actor_company_id is None:
        raise ServiceError("У пользователя не выбрана компания", 400)
    return cast(
        "dict[str, Any] | None",
        await assignment_repo.get_active_company_employee(
            session,
            company_id=actor_company_id,
            employee_id=employee_id,
        ),
    )


__all__ = [
    "AssignApplicationEmployeesCommand",
    "handle_assign_application_employees",
]
