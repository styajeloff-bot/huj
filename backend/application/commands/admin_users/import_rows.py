"""Application-layer per-row user upsert for the async CSV import pipeline.

Extracted from the users router so the taskiq worker (application layer) can
reuse it without importing presentation. Behaviour is unchanged.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.admin_users import (
    CreateUserCommand,
    UpdateUserCommand,
    handle_create_user,
    handle_update_user,
)
from application.queries.admin_users import find_user_by_id, find_user_by_phone


async def upsert_user_row(
    session: AsyncSession, row: dict[str, str]
) -> tuple[str, str | None]:
    """Upsert one user CSV row. Returns ``(action, error)``."""
    user_id: UUID | None = None
    user_id_raw = (row.get("id") or "").strip()
    if user_id_raw:
        try:
            user_id = UUID(user_id_raw)
        except ValueError:
            user_id = None

    phone = (row.get("phone") or "").strip()
    role = (row.get("role") or "").strip()
    if not phone or not role:
        return ("error", "пропущены обязательные поля phone/role")

    name = (row.get("name") or "").strip() or None
    email = (row.get("email") or "").strip() or None
    is_active_str = (row.get("is_active") or "").strip().lower()
    is_active = is_active_str not in ("false", "0", "no", "")

    company_id_raw = (row.get("company_id") or "").strip()
    company_id: UUID | None = None
    if company_id_raw:
        try:
            company_id = UUID(company_id_raw)
        except ValueError:
            company_id = None

    existing_user: dict[str, Any] | None = None
    if user_id is not None:
        existing_user = await find_user_by_id(session, user_id)
    if existing_user is None:
        existing_user = await find_user_by_phone(session, phone)

    if existing_user is not None:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if email is not None:
            fields["email"] = email
        if role:
            fields["role"] = role
        if company_id is not None:
            fields["company_id"] = company_id
        fields["is_active"] = is_active
        fields["email_verified"] = True
        await handle_update_user(
            UpdateUserCommand(user_id=existing_user["id"], fields=fields), session
        )
        return ("updated", None)

    await handle_create_user(
        CreateUserCommand(
            name=name,
            email=email,
            phone=phone,
            role=role,
            company_id=company_id,
            is_active=is_active,
            email_verified=True,
            user_id=user_id,
        ),
        session,
    )
    return ("created", None)
