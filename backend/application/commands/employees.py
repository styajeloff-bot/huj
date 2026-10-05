"""Employee invitation and company-member permission management.

All handlers verify that the actor is an ``administrator`` or ``manager`` of
the target company before mutating anything.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.permissions import get_company_permissions, is_company_admin_or_manager
from infrastructure.messaging import auth_events
from infrastructure.repositories import auth_repository as repo
from infrastructure.repositories import company_registration_repository as company_repo
from infrastructure.repositories import magic_link_repository as magic_link_repo
from infrastructure.services.sms import send_text_sms
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@dataclass
class InviteEmployeeCommand:
    actor_user_id: UUID
    company_id: UUID
    phone: str
    actor_role: str | None = None


@dataclass
class UpdateEmployeePermissionsCommand:
    actor_user_id: UUID
    company_id: UUID
    target_user_id: UUID
    can_view_applications: bool | None = None
    can_create_applications: bool | None = None
    actor_role: str | None = None


@dataclass
class UpdateEmployeeSubRoleCommand:
    actor_user_id: UUID
    company_id: UUID
    target_user_id: UUID
    sub_role: str  # administrator | manager | employee
    actor_role: str | None = None


@dataclass
class RemoveCompanyMemberCommand:
    actor_user_id: UUID
    company_id: UUID
    target_user_id: UUID
    actor_role: str | None = None


@dataclass
class ListCompanyMembersQuery:
    actor_user_id: UUID
    company_id: UUID
    actor_role: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_placeholder_password_hash() -> str:
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()


async def _require_admin_or_manager(
    session: AsyncSession, *, user_id: UUID, user_role: str | None, company_id: UUID
) -> None:
    if user_role == "carcraft_employee":
        return
    perms = await get_company_permissions(session, user_id, company_id)
    if not is_company_admin_or_manager(perms):
        raise ServiceError("Доступ запрещён. Требуется роль администратора или менеджера.", 403)


async def _require_administrator(
    session: AsyncSession, *, user_id: UUID, user_role: str | None, company_id: UUID
) -> None:
    if user_role == "carcraft_employee":
        return
    perms = await get_company_permissions(session, user_id, company_id)
    if perms.get("sub_role") != "administrator":
        raise ServiceError("Доступ запрещён. Требуется роль администратора.", 403)


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


async def _ensure_employee_link(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> None:
    existing = await session.get(company_repo.UserCompany, (user_id, company_id))
    if existing is not None:
        return
    await company_repo.insert_user_company_links(
        session,
        user_id,
        [(company_id, "employee", False, False)],
    )
    history = await company_repo.get_company_select_history(session, user_id)
    if history is None:
        await company_repo.upsert_company_select_history(session, user_id, company_id)


async def _send_invite_sms_background(phone: str, token: str) -> None:
    try:
        url = f"{settings.public_url}/s/{token}"
        text = f"Вас пригласили в компанию Carcraft. Перейдите по ссылке: {url}"
        await send_text_sms(phone, text)
    except Exception as exc:
        logger.error("Invite SMS failed for %s: %s", phone, exc)


_invite_sms_tasks: set[asyncio.Task[None]] = set()


def _fire_invite_sms(phone: str, token: str) -> None:
    task = asyncio.create_task(_send_invite_sms_background(phone, token))
    _invite_sms_tasks.add(task)
    task.add_done_callback(_invite_sms_tasks.discard)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_invite_employee(
    cmd: InviteEmployeeCommand, session: AsyncSession
) -> dict[str, Any]:
    """Invite a new or existing user to join a company as an employee."""
    await _require_admin_or_manager(
        session,
        user_id=cmd.actor_user_id,
        user_role=cmd.actor_role,
        company_id=cmd.company_id,
    )

    phone = _normalize_phone(cmd.phone)

    user = await repo.find_user_by_phone(session, phone)
    if user is None:
        user = await repo.create_user(
            session,
            phone=phone,
            email=None,
            name=None,
            password_hash=_make_placeholder_password_hash(),
            company_id=None,
            phone_verified=False,
        )
        # Link to the inviting company as employee with no permissions.
        await _ensure_employee_link(session, user["id"], cmd.company_id)
    else:
        # Ensure link exists (upsert) — if the user is already linked we
        # do NOT downgrade an existing admin/manager to employee.
        await _ensure_employee_link(session, user["id"], cmd.company_id)

    # Invalidate any previous magic links for this user
    await magic_link_repo.delete_unused_for_user(session, user["id"])

    # Create magic link with 7-day TTL
    link = await magic_link_repo.create(
        session,
        user_id=user["id"],
        ttl_seconds=7 * 24 * 3600,
        purpose="employee_invite",
    )

    _fire_invite_sms(phone, link["token"])

    auth_events.emit(
        auth_events.INVITE_SENT,
        actor_id=cmd.actor_user_id,
        company_id=cmd.company_id,
        target_user_id=user["id"],
        phone=phone,
    )

    return {
        "message": "Приглашение отправлено",
        "user_id": str(user["id"]),
    }


async def handle_update_employee_permissions(
    cmd: UpdateEmployeePermissionsCommand, session: AsyncSession
) -> dict[str, Any]:
    """Toggle per-employee application permissions within a company."""
    await _require_admin_or_manager(
        session,
        user_id=cmd.actor_user_id,
        user_role=cmd.actor_role,
        company_id=cmd.company_id,
    )

    # Verify target user is linked to this company
    target_perms = await get_company_permissions(
        session, cmd.target_user_id, cmd.company_id
    )
    if target_perms.get("sub_role") is None:
        raise ServiceError("Пользователь не связан с этой компанией", 400)

    values: dict[str, Any] = {}
    if cmd.can_view_applications is not None:
        values["can_view_applications"] = cmd.can_view_applications
    if cmd.can_create_applications is not None:
        values["can_create_applications"] = cmd.can_create_applications

    if not values:
        return {"message": "Нет изменений"}

    await session.execute(
        sa.update(company_repo.UserCompany)
        .where(
            company_repo.UserCompany.user_id == cmd.target_user_id,
            company_repo.UserCompany.company_id == cmd.company_id,
        )
        .values(**values)
    )
    await session.flush()

    return {"message": "Права обновлены"}


async def handle_update_employee_sub_role(
    cmd: UpdateEmployeeSubRoleCommand, session: AsyncSession
) -> dict[str, Any]:
    """Promote / demote an employee's sub-role (admin-only)."""
    await _require_administrator(
        session,
        user_id=cmd.actor_user_id,
        user_role=cmd.actor_role,
        company_id=cmd.company_id,
    )

    if cmd.sub_role not in {"administrator", "manager", "employee"}:
        raise ServiceError("Недопустимая саб-роль", 400)

    current = await session.get(
        company_repo.UserCompany, (cmd.target_user_id, cmd.company_id)
    )
    if current is None:
        raise ServiceError("Пользователь не связан с этой компанией", 400)

    current.sub_role = cmd.sub_role
    await session.flush()

    return {"message": "Роль обновлена"}


async def handle_remove_company_member(
    cmd: RemoveCompanyMemberCommand, session: AsyncSession
) -> dict[str, Any]:
    """Remove a user's company link without deleting the user account."""
    await _require_administrator(
        session,
        user_id=cmd.actor_user_id,
        user_role=cmd.actor_role,
        company_id=cmd.company_id,
    )

    if cmd.actor_user_id == cmd.target_user_id and cmd.actor_role != "carcraft_employee":
        raise ServiceError("Нельзя удалить собственную связь с компанией", 403)

    current = await session.get(
        company_repo.UserCompany, (cmd.target_user_id, cmd.company_id)
    )
    if current is None:
        raise ServiceError("Пользователь не связан с этой компанией", 400)

    await session.delete(current)
    await session.execute(
        sa.update(repo.User)
        .where(
            repo.User.id == cmd.target_user_id,
            repo.User.company_id == cmd.company_id,
        )
        .values(company_id=None)
    )
    await session.flush()

    return {"message": "Сотрудник удалён из компании"}


async def handle_list_company_members(
    query: ListCompanyMembersQuery, session: AsyncSession
) -> list[dict[str, Any]]:
    """Return all users linked to the company with their sub-roles and permissions."""
    # Any linked user may view the member list (useful for employees to see
    # who their admin is).
    if query.actor_role != "carcraft_employee":
        actor_perms = await get_company_permissions(
            session, query.actor_user_id, query.company_id
        )
        if actor_perms.get("sub_role") is None:
            raise ServiceError("Доступ запрещён", 403)

    stmt = (
        sa.select(
            repo.User.id,
            repo.User.name,
            repo.User.phone,
            company_repo.UserCompany.user_id.label("user_company_user_id"),
            company_repo.UserCompany.sub_role,
            company_repo.UserCompany.can_view_applications,
            company_repo.UserCompany.can_create_applications,
        )
        .outerjoin(
            company_repo.UserCompany,
            sa.and_(
                repo.User.id == company_repo.UserCompany.user_id,
                company_repo.UserCompany.company_id == query.company_id,
            ),
        )
        .where(
            sa.or_(
                repo.User.company_id == query.company_id,
                company_repo.UserCompany.user_id.is_not(None),
            )
        )
        .order_by(repo.User.name)
    )
    result = await session.execute(stmt)
    return [
        {
            "user_id": str(r.id),
            "name": r.name,
            "phone": r.phone,
            "sub_role": (
                r.sub_role or "employee"
                if r.user_company_user_id is not None
                else "administrator"
            ),
            "can_view_applications": (
                r.can_view_applications
                if r.user_company_user_id is not None
                else True
            ),
            "can_create_applications": (
                r.can_create_applications
                if r.user_company_user_id is not None
                else True
            ),
        }
        for r in result.all()
    ]
