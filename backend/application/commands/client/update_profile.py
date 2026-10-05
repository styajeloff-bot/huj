"""Update client profile (basic user fields + client_profiles upsert)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.client_profile import normalize_profile_field
from domain.errors import UserNotFoundError
from infrastructure.repositories import client_repository as repo
from infrastructure.repositories import (
    user_identity_verification_repository as identity_verification_repo,
)

# Set of fields routed to ``client_profiles``. Order is intentional —
# matches the Express implementation for parity in update statements.
_PROFILE_FIELDS: tuple[str, ...] = (
    "client_type",
    "passport_series",
    "passport_issued_date",
    "passport_issued_by",
    "company_name",
    "inn",
    "kpp",
    "ogrn",
    "legal_address",
    "address",
    "birth_date",
    "notification_settings",
)


def _normalize_identity_name(value: object) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized.casefold() or None


def _identity_fields_changed(
    existing: dict[str, Any], data: dict[str, Any]
) -> bool:
    if "name" in data:
        new_name = _normalize_identity_name(data.get("name") or None)
        old_name = _normalize_identity_name(existing.get("name"))
        if new_name != old_name:
            return True

    if "birth_date" in data:
        new_birth_date = normalize_profile_field(data["birth_date"])
        if new_birth_date != existing.get("birth_date"):
            return True

    return False


@dataclass
class UpdateClientProfileCommand:
    """Partial profile update; ``data`` carries only the keys the caller sent."""

    user_id: UUID
    data: dict[str, Any] = field(default_factory=dict)


async def handle_update_client_profile(
    cmd: UpdateClientProfileCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_profile_with_user(session, cmd.user_id)
    if existing is None:
        raise UserNotFoundError()

    reset_identity_verification = _identity_fields_changed(existing, cmd.data)

    has_name = "name" in cmd.data
    has_email = "email" in cmd.data

    if has_name or has_email:
        await repo.update_user_basic(
            session,
            cmd.user_id,
            name=cmd.data.get("name") or None if has_name else None,
            email=cmd.data.get("email") or None if has_email else None,
            has_name=has_name,
            has_email=has_email,
        )

    profile_payload: dict[str, Any] = {}
    for key in _PROFILE_FIELDS:
        if key in cmd.data:
            profile_payload[key] = normalize_profile_field(cmd.data[key])

    if profile_payload:
        await repo.upsert_profile(session, cmd.user_id, profile_payload)

    if reset_identity_verification:
        await identity_verification_repo.expire_verified_for_user(
            session,
            user_id=cmd.user_id,
            provider=identity_verification_repo.PROVIDER_MOBILE_ID,
        )

    refreshed = await repo.get_profile_with_user(session, cmd.user_id)
    assert refreshed is not None
    return cast("dict[str, Any]", refreshed)
