
"""Soft-delete user (admin) command."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from domain.errors import UserNotFoundError
from infrastructure.messaging.dwh_events import emit_user_changed
from infrastructure.repositories import admin_users_repository as repo


@dataclass
class DeleteUserCommand:
    user_id: UUID


async def handle_delete_user(
    cmd: DeleteUserCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_by_id(session, cmd.user_id)
    if existing is None:
        raise UserNotFoundError()

    await repo.deactivate_user(session, cmd.user_id)
    saved = await repo.get_by_id(session, cmd.user_id)
    if saved is not None:
        emit_user_changed({
            "user_id": cmd.user_id,
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
    return {
        "id": cmd.user_id,
        "message": "Пользователь деактивирован",
    }
