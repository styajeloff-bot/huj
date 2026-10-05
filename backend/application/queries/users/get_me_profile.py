"""Query: unified ``GET /users/me`` profile — joins user + role-specific data.

Composes three repos (``client_repository``, ``dealer_repository``,
``distributor_repository``) into a single DTO so the router can return
one discriminated payload. For roles without a role-specific extension
(``carcraft_employee``, ``leasing_company``, unknown) the ``role_specific``
block is ``None``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import UserNotFoundError
from infrastructure.repositories import (
    client_repository,
    dealer_repository,
    distributor_repository,
)


@dataclass(frozen=True)
class GetMeProfileQuery:
    user_id: UUID
    role: str | None


@dataclass(frozen=True)
class MeProfileDto:
    """Shape consumed by the router — a plain dict for ``role_specific``."""

    base: dict[str, Any]
    role_specific: dict[str, Any] | None


_CLIENT_ONLY_KEYS: tuple[str, ...] = (
    "profile_id",
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
    "two_factor_enabled",
    "phone_verified",
    "identity_verified",
    "identity_verified_at",
    "identity_verification_provider",
)


def _client_role_specific(profile: dict[str, Any]) -> dict[str, Any]:
    return {key: profile.get(key) for key in _CLIENT_ONLY_KEYS}


def _base_from_client_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": profile["user_id"],
        "phone": profile.get("phone"),
        "email": profile.get("email"),
        "name": profile.get("name"),
        "role": profile.get("role"),
        "company_id": profile.get("company_id"),
        "is_active": profile.get("is_active"),
    }


async def handle_get_me_profile(
    query: GetMeProfileQuery, session: AsyncSession
) -> MeProfileDto:
    role = (query.role or "").strip().lower()

    if role == "client":
        profile = await client_repository.get_profile_with_user(
            session, query.user_id
        )
        if profile is None:
            raise UserNotFoundError()
        return MeProfileDto(
            base=_base_from_client_profile(profile),
            role_specific=_client_role_specific(profile),
        )

    if role == "dealer":
        profile = await dealer_repository.get_dealer_user(
            session, query.user_id
        )
        if profile is None:
            raise UserNotFoundError()
        stats = await dealer_repository.dealer_sales_stats(
            session, profile["user"]["company_id"]
        )
        user = profile["user"]
        return MeProfileDto(
            base={
                "id": user["id"],
                "phone": user.get("phone"),
                "email": user.get("email"),
                "name": user.get("name"),
                "role": user.get("role"),
                "company_id": user.get("company_id"),
                "is_active": user.get("is_active"),
            },
            role_specific={
                "company": profile.get("company"),
                "stats": stats,
            },
        )

    if role == "distributor":
        profile = await distributor_repository.get_distributor_profile(
            session, query.user_id
        )
        if profile is None:
            raise UserNotFoundError()
        user = profile["user"]
        return MeProfileDto(
            base={
                "id": user["id"],
                "phone": user.get("phone"),
                "email": user.get("email"),
                "name": user.get("name"),
                "role": user.get("role"),
                "company_id": user.get("company_id"),
                # distributor profile repo doesn't return is_active on the
                # user block — leave it unset rather than faking a value.
                "is_active": None,
            },
            role_specific={
                "company": profile.get("company"),
                "distributor": profile.get("distributor"),
            },
        )

    # Fallback: unknown / employee / leasing_company — return base identity
    # from whatever repo happens to have the user. client_repository's
    # ``get_profile_with_user`` is a LEFT JOIN, so it works for any user.
    profile = await client_repository.get_profile_with_user(
        session, query.user_id
    )
    if profile is None:
        raise UserNotFoundError()
    return MeProfileDto(
        base=_base_from_client_profile(profile),
        role_specific=None,
    )
