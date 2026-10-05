"""Employees command handlers (task 21674 & task 21952).

Manages creating, updating, deactivating employees and personal access settings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.access_delegation import validate_delegation
from infrastructure.repositories import employees_repository
from infrastructure.repositories.user_company_access_repository import (
    get_user_company_access_rules,
    get_user_company_by_user_and_company,
    get_user_company_section_access,
    save_full_employee_access,
)

ALLOWED_ROLES = {"client", "dealer", "distributor", "leasing_company"}


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone)
    if digits.startswith("8") and len(digits) == 11:
        normalized = "+7" + digits[1:]
    elif digits.startswith("7") and len(digits) == 11:
        normalized = "+" + digits
    elif len(digits) == 10:
        normalized = "+7" + digits
    else:
        normalized = "+7" + digits
    if not re.fullmatch(r"\+7\d{10}", normalized):
        raise ServiceError("Некорректный формат телефона", 400)
    return normalized


def _sanitize_additional_phone(additional_phone: str | None) -> str | None:
    if additional_phone is None:
        return None
    val = additional_phone.strip()
    return val[:20] if val else None


@dataclass
class CreateEmployeeCommand:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    name: str
    phone: str
    company_id: UUID
    role: str
    additional_phone: str | None = None
    position_id: UUID | None = None
    can_view_applications: bool = True
    can_create_applications: bool = False
    can_create_employees: bool = False
    is_active: bool = True


@dataclass
class UpdateEmployeeCommand:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    user_id: UUID
    company_id: UUID
    name: str | None = None
    phone: str | None = None
    additional_phone: str | None = None
    role: str = "client"
    position_id: UUID | None = None
    can_view_applications: bool = True
    can_create_applications: bool = False
    can_create_employees: bool | None = None
    is_active: bool = True


@dataclass
class DeactivateEmployeeCommand:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    user_id: UUID
    company_id: UUID


@dataclass
class UpdateEmployeeAccessSettingsCommand:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    user_id: UUID
    company_id: UUID
    additional_phone: str | None = None
    can_create_employees: bool = False
    rules: list[Any] = field(default_factory=list)
    sections: dict[str, bool] = field(default_factory=dict)


async def handle_create_employee(
    cmd: CreateEmployeeCommand, session: AsyncSession
) -> dict[str, Any]:
    """Create or link an employee to a company."""
    active_company_id = cmd.actor_company_id
    active_role = cmd.actor_role
    if active_role != "carcraft_employee" and active_company_id is None:
        active_company_id, active_role = (
            await employees_repository.get_active_company_and_role(
                session, cmd.actor_user_id, cmd.actor_role
            )
        )

    if active_role != "carcraft_employee" and (
        active_company_id is None or cmd.company_id != active_company_id
    ):
        raise ServiceError("Недостаточно прав", 403)

    can_manage = await employees_repository.check_can_create_employees(
        session,
        actor_user_id=cmd.actor_user_id,
        actor_role=active_role,
        target_company_id=cmd.company_id,
    )
    if not can_manage:
        raise ServiceError("Недостаточно прав для управления сотрудниками", 403)

    if cmd.role not in ALLOWED_ROLES:
        raise ServiceError("Недопустимая роль сотрудника", 400)

    phone = _normalize_phone(cmd.phone)
    additional_phone = _sanitize_additional_phone(cmd.additional_phone)
    position_id = cmd.position_id if cmd.role in {"dealer", "distributor"} else None

    return await employees_repository.upsert_employee(
        session,
        name=cmd.name.strip(),
        phone=phone,
        additional_phone=additional_phone,
        company_id=cmd.company_id,
        role=cmd.role,
        position_id=position_id,
        can_view_applications=cmd.can_view_applications,
        can_create_applications=cmd.can_create_applications,
        can_create_employees=cmd.can_create_employees,
        is_active=cmd.is_active,
        granter_user_id=cmd.actor_user_id,
    )


async def handle_update_employee(
    cmd: UpdateEmployeeCommand, session: AsyncSession
) -> dict[str, Any]:
    """Update employee details and user_companies link row."""
    active_company_id = cmd.actor_company_id
    active_role = cmd.actor_role
    if active_role != "carcraft_employee" and active_company_id is None:
        active_company_id, active_role = (
            await employees_repository.get_active_company_and_role(
                session, cmd.actor_user_id, cmd.actor_role
            )
        )

    if active_role != "carcraft_employee" and (
        active_company_id is None or cmd.company_id != active_company_id
    ):
        raise ServiceError("Недостаточно прав", 403)

    can_manage = await employees_repository.check_can_create_employees(
        session,
        actor_user_id=cmd.actor_user_id,
        actor_role=active_role,
        target_company_id=cmd.company_id,
    )
    if not can_manage:
        raise ServiceError("Недостаточно прав для управления сотрудниками", 403)

    if cmd.role not in ALLOWED_ROLES:
        raise ServiceError("Недопустимая роль сотрудника", 400)

    position_id = cmd.position_id if cmd.role in {"dealer", "distributor"} else None
    additional_phone = _sanitize_additional_phone(cmd.additional_phone)

    result = await employees_repository.update_employee(
        session,
        user_id=cmd.user_id,
        company_id=cmd.company_id,
        name=cmd.name.strip() if cmd.name is not None else None,
        phone=_normalize_phone(cmd.phone) if cmd.phone is not None else None,
        additional_phone=additional_phone,
        role=cmd.role,
        position_id=position_id,
        can_view_applications=cmd.can_view_applications,
        can_create_applications=cmd.can_create_applications,
        can_create_employees=cmd.can_create_employees,
        is_active=cmd.is_active,
        granter_user_id=cmd.actor_user_id,
    )
    if result is None:
        raise ServiceError("Сотрудник не найден", 404)
    return result


async def handle_deactivate_employee(
    cmd: DeactivateEmployeeCommand, session: AsyncSession
) -> bool:
    """Soft-deactivate an employee link (user_companies.is_active = False)."""
    active_company_id = cmd.actor_company_id
    active_role = cmd.actor_role
    if active_role != "carcraft_employee" and active_company_id is None:
        active_company_id, active_role = (
            await employees_repository.get_active_company_and_role(
                session, cmd.actor_user_id, cmd.actor_role
            )
        )

    if active_role != "carcraft_employee" and (
        active_company_id is None or cmd.company_id != active_company_id
    ):
        raise ServiceError("Недостаточно прав", 403)

    can_manage = await employees_repository.check_can_create_employees(
        session,
        actor_user_id=cmd.actor_user_id,
        actor_role=active_role,
        target_company_id=cmd.company_id,
    )
    if not can_manage:
        raise ServiceError("Недостаточно прав для управления сотрудниками", 403)

    if cmd.actor_user_id == cmd.user_id and active_role != "carcraft_employee":
        raise ServiceError("Нельзя отключить собственную запись сотрудника", 403)

    success = await employees_repository.deactivate_employee(
        session,
        user_id=cmd.user_id,
        company_id=cmd.company_id,
    )
    if not success:
        raise ServiceError("Сотрудник не найден", 404)
    return True


async def handle_update_employee_access_settings(
    cmd: UpdateEmployeeAccessSettingsCommand, session: AsyncSession
) -> dict[str, Any]:
    """Update personal object rules, section visibility, and employee creation rights."""
    active_company_id = cmd.actor_company_id
    active_role = cmd.actor_role
    if active_role != "carcraft_employee" and active_company_id is None:
        active_company_id, active_role = (
            await employees_repository.get_active_company_and_role(
                session, cmd.actor_user_id, cmd.actor_role
            )
        )

    target_uc = await get_user_company_by_user_and_company(session, cmd.user_id, cmd.company_id)
    if target_uc is None:
        raise ServiceError("Сотрудник не найден", 404)

    rules_dicts: list[dict[str, Any]] = [
        r.model_dump() if hasattr(r, "model_dump") else dict(r)
        for r in cmd.rules
    ]
    additional_phone = _sanitize_additional_phone(cmd.additional_phone)

    # Validate delegation and anti-escalation rules
    await validate_delegation(
        session,
        granter_user_id=cmd.actor_user_id,
        granter_role=active_role,
        granter_company_id=active_company_id,
        target_user_id=cmd.user_id,
        target_company_id=cmd.company_id,
        target_user_company_id=target_uc.id,
        target_rules=rules_dicts,
        target_sections=cmd.sections,
        target_can_create_employees=cmd.can_create_employees,
    )

    # Perform transactional save
    await save_full_employee_access(
        session,
        user_company_id=target_uc.id,
        target_user_id=cmd.user_id,
        rules=rules_dicts,
        sections=cmd.sections,
        can_create_employees=cmd.can_create_employees,
        additional_phone=additional_phone,
        granter_user_id=cmd.actor_user_id,
    )

    # Build response
    updated_rules = await get_user_company_access_rules(session, target_uc.id)
    updated_sections = await get_user_company_section_access(session, target_uc.id)

    return {
        "user_company_id": target_uc.id,
        "user_id": cmd.user_id,
        "company_id": cmd.company_id,
        "can_create_employees": cmd.can_create_employees,
        "additional_phone": additional_phone,
        "rules": [
            {
                "id": r.id,
                "access_object": r.access_object,
                "access_type": r.access_type,
                "object_id": r.object_id,
                "object_name": r.object_name,
                "is_active": r.is_active,
            }
            for r in updated_rules
        ],
        "sections": updated_sections,
        "can_edit": True,
    }
