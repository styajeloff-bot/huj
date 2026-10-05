
"""Command: ``PATCH /users/me`` — unified partial profile update.

Accepts a base-user patch (``name`` / ``email``) plus an optional
role-specific block that must match the caller's role. Dispatches to the
existing role-scoped commands (``update_client_profile``,
``update_dealer_profile``). Distributor self-update is intentionally not
supported — the legacy ``PUT /distributor/profile`` endpoint didn't exist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.client import (
    UpdateClientProfileCommand,
    handle_update_client_profile,
)
from application.commands.dealer import (
    UpdateDealerProfileCommand,
    handle_update_dealer_profile,
)
from application.common import _isoformat
from application.errors import ServiceError
from application.queries.users.get_me_profile import (
    GetMeProfileQuery,
    MeProfileDto,
    handle_get_me_profile,
)
from domain.errors import UserNotFoundError
from infrastructure.messaging.dwh_events import emit_user_changed
from infrastructure.repositories import admin_users_repository, client_repository


class WrongRoleForRoleSpecificError(ServiceError):
    """Raised when ``role_specific`` fields don't match the caller's role."""

    def __init__(self, caller_role: str) -> None:
        super().__init__(
            f"role_specific fields do not match role '{caller_role}'",
            status_code=422,
        )


@dataclass
class UpdateMeProfileCommand:
    """Partial profile update for the authenticated user.

    ``role_specific_kind`` names the union branch the caller chose
    (``"client"`` or ``"dealer"``). ``None`` means no role-specific block
    was supplied. ``role_specific_data`` carries the decoded patch payload.
    """

    user_id: UUID
    role: str
    base_fields: dict[str, Any] = field(default_factory=dict)
    role_specific_kind: str | None = None
    role_specific_data: dict[str, Any] = field(default_factory=dict)


async def handle_update_me_profile(
    cmd: UpdateMeProfileCommand, session: AsyncSession
) -> MeProfileDto:
    caller_role = (cmd.role or "").strip().lower()

    # Reject role_specific blocks that don't match the caller's role.
    if cmd.role_specific_kind is not None and cmd.role_specific_kind != caller_role:
        raise WrongRoleForRoleSpecificError(caller_role or "unknown")

    if caller_role == "client":
        # Merge base-user fields (name/email) and client_profiles fields
        # into the single ``data`` dict expected by the legacy command.
        data: dict[str, Any] = dict(cmd.base_fields)
        if cmd.role_specific_kind == "client":
            data.update(cmd.role_specific_data)
        if data:
            await handle_update_client_profile(
                UpdateClientProfileCommand(user_id=cmd.user_id, data=data),
                session,
            )
    elif caller_role == "dealer":
        user_fields = dict(cmd.base_fields)
        company_fields: dict[str, Any] = {}
        if cmd.role_specific_kind == "dealer":
            company_block = cmd.role_specific_data.get("company") or {}
            if isinstance(company_block, dict):
                company_fields = dict(company_block)
        if user_fields or company_fields:
            await handle_update_dealer_profile(
                UpdateDealerProfileCommand(
                    user_id=cmd.user_id,
                    user_fields=user_fields,
                    company_fields=company_fields,
                ),
                session,
            )
    else:
        # Roles without a role-specific extension (employee, distributor,
        # leasing_company): only base-user fields are applicable.
        if cmd.role_specific_kind is not None:
            raise WrongRoleForRoleSpecificError(caller_role or "unknown")
        if cmd.base_fields:
            await _update_base_user(session, cmd.user_id, cmd.base_fields)

    # Re-read the merged projection — reuse the GET handler so the router
    # response shape stays identical.
    dto = await handle_get_me_profile(
        GetMeProfileQuery(user_id=cmd.user_id, role=cmd.role), session
    )
    user = await admin_users_repository.get_by_id(session, cmd.user_id)
    if user is not None:
        emit_user_changed({
            "user_id": cmd.user_id,
            "email": user.get("email"),
            "name": user.get("name"),
            "role": user.get("role"),
            "company_id": user.get("company_id"),
            "phone": user.get("phone"),
            "is_active": user.get("is_active"),
            "email_verified": user.get("email_verified"),
            "phone_verified": user.get("phone_verified"),
            "last_login": _isoformat(user.get("last_login")),
            "deleted_at": _isoformat(user.get("deleted_at")),
            "mfa_enabled": user.get("mfa_enabled"),
            "created_at": _isoformat(user.get("created_at")),
            "updated_at": _isoformat(user.get("updated_at")),
            "_deleted": False,
        })
    return dto


async def _update_base_user(
    session: AsyncSession,
    user_id: UUID,
    fields: dict[str, Any],
) -> None:
    """Base-user patch for roles without a role-specific extension."""
    has_name = "name" in fields
    has_email = "email" in fields
    if not (has_name or has_email):
        return
    # client_repository.update_user_basic writes to the ``users`` table —
    # the naming is a legacy artefact from when only clients owned that
    # column path. It's safe for any role.
    existing = await client_repository.get_profile_with_user(
        session, user_id
    )
    if existing is None:
        raise UserNotFoundError()
    await client_repository.update_user_basic(
        session,
        user_id,
        name=fields.get("name"),
        email=fields.get("email"),
        has_name=has_name,
        has_email=has_email,
    )
