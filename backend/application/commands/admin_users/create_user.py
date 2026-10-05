
"""Create user (admin) command."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.user_companies import (
    AddCompanyToUserCommand,
    handle_add_company_to_user,
)
from application.common import _isoformat
from application.errors import ServiceError
from domain.errors import (
    CompanyNotFoundError,
    InvalidRoleError,
    UserAlreadyExistsError,
    UserEmailAlreadyExistsError,
)
from infrastructure.messaging.dwh_events import emit_user_changed
from infrastructure.repositories import admin_users_repository as repo

ALLOWED_ROLES: frozenset[str] = frozenset(
    {"carcraft_employee", "dealer", "client", "leasing_company", "distributor"}
)


@dataclass
class CreateUserCommand:
    name: str | None
    email: str | None
    phone: str
    role: str
    company_id: UUID | None = None
    company: dict[str, Any] | None = None
    is_active: bool = True
    email_verified: bool = True
    user_id: UUID | None = None


async def handle_create_user(
    cmd: CreateUserCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.role not in ALLOWED_ROLES:
        raise InvalidRoleError(cmd.role)
    if cmd.company is not None and cmd.role != "client":
        raise ServiceError("Компанию объектом можно привязать только клиенту", 400)
    if cmd.company is not None and cmd.company_id is not None:
        raise ServiceError("Укажите компанию только одним способом", 400)

    if cmd.email and await repo.email_exists(session, cmd.email):
        raise UserEmailAlreadyExistsError(cmd.email)

    if await repo.phone_exists(session, cmd.phone):
        raise UserAlreadyExistsError()

    if cmd.company_id is not None and not await repo.company_exists(
        session, cmd.company_id
    ):
        raise CompanyNotFoundError()

    user_id = await repo.create_user(
        session,
        name=cmd.name,
        email=cmd.email,
        phone=cmd.phone,
        role=cmd.role,
        company_id=cmd.company_id,
        is_active=cmd.is_active,
        email_verified=cmd.email_verified,
        user_id=cmd.user_id,
    )
    if cmd.company is not None:
        await handle_add_company_to_user(
            session,
            AddCompanyToUserCommand(
                user_id=user_id,
                company=cmd.company,
                grant_administrator=True,
            ),
        )
    saved = await repo.get_by_id(session, user_id)
    if saved is None:
        raise ServiceError("Не удалось создать пользователя")
    emit_user_changed({
        "user_id": user_id,
        "email": saved.get("email"),
        "name": saved.get("name"),
        "role": saved.get("role"),
        "company_id": saved.get("company_id"),
        "phone": saved.get("phone"),
        "is_active": saved.get("is_active"),
        "email_verified": saved.get("email_verified"),
        "phone_verified": saved.get("phone_verified"),
        "last_login": _isoformat(saved.get("last_login")),
        "deleted_at": _isoformat(saved.get("deleted_at")),
        "mfa_enabled": saved.get("mfa_enabled"),
        "created_at": _isoformat(saved.get("created_at")),
        "updated_at": _isoformat(saved.get("updated_at")),
        "_deleted": False,
    })
    return cast("dict[str, Any]", saved)
