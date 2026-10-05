
"""Update user (admin) command."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.errors import ServiceError
from domain.errors import (
    CompanyNotFoundError,
    InvalidRoleError,
    PhoneAlreadyInUseError,
    UserEmailAlreadyExistsError,
    UserNotFoundError,
)
from infrastructure.messaging.dwh_events import emit_user_changed
from infrastructure.repositories import admin_users_repository as repo
from infrastructure.repositories import company_registration_repository as company_repo
from infrastructure.services.company_enrichment import (
    get_company_enrichment_scheduler,
)

_ALLOWED_ROLES: frozenset[str] = frozenset(
    {"carcraft_employee", "dealer", "client", "leasing_company", "distributor"}
)


@dataclass
class UpdateUserCommand:
    user_id: UUID
    fields: dict[str, Any] = field(default_factory=dict)


async def _ensure_user_company_link(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> None:
    """Add a user_companies link with administrator rights if not present."""
    existing_links = await company_repo.list_user_companies(session, user_id)
    if not any(c["id"] == company_id for c in existing_links):
        await company_repo.insert_user_company_links(
            session, user_id, [(company_id, "administrator", True, True)]
        )


async def handle_update_user(
    cmd: UpdateUserCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_by_id(session, cmd.user_id)
    if existing is None:
        raise UserNotFoundError()

    fields = dict(cmd.fields)

    if (
        "role" in fields
        and fields["role"] is not None
        and fields["role"] not in _ALLOWED_ROLES
    ):
        raise InvalidRoleError(str(fields["role"]))

    email = fields.get("email")
    if email and await repo.email_exists(
        session, str(email), exclude_id=cmd.user_id
    ):
        raise UserEmailAlreadyExistsError(str(email))

    phone = fields.get("phone")
    if phone and await repo.phone_exists(
        session, str(phone), exclude_id=cmd.user_id
    ):
        raise PhoneAlreadyInUseError()

    # Resolve company object → company_id (for clients).
    company_payload = fields.pop("company", None)
    if company_payload is not None:
        target_role = fields.get("role") or existing["role"]
        if target_role != "client":
            raise ServiceError(
                "Компанию объектом можно привязать только клиенту", 400
            )
        company = await company_repo.create_or_get_company(
            session, cast("company_repo.CompanyPayload", company_payload)
        )
        if not company:
            raise ServiceError("Не удалось сохранить компанию", 400)
        resolved_company_id: UUID = company["id"]

        # Ensure user_companies link exists.
        await _ensure_user_company_link(session, cmd.user_id, resolved_company_id)

        # Schedule enrichment for the company.
        inn = company_payload.get("inn")
        if inn:
            scheduler = get_company_enrichment_scheduler()
            await scheduler.schedule_refresh(str(inn))

        fields["company_id"] = resolved_company_id

    company_id = fields.get("company_id")
    if company_id is not None and not await repo.company_exists(
        session, company_id
    ):
        raise CompanyNotFoundError()

    # Ensure user_companies link when setting company_id for a client.
    if (
        company_id is not None
        and company_payload is None
        and (fields.get("role") or existing["role"]) == "client"
    ):
        await _ensure_user_company_link(session, cmd.user_id, company_id)

    updated = await repo.update_user(session, cmd.user_id, fields=fields)
    if not updated:
        return cast("dict[str, Any]", existing)
    saved = await repo.get_by_id(session, cmd.user_id)
    assert saved is not None
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
    return cast("dict[str, Any]", saved)
