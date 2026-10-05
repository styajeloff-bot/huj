"""Client repository — profile, favorites, saved calculations.

All public functions return plain ``dict`` / ``list[dict]`` — never ORM
objects. ORM models exist only to build queries here.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import CatalogScope
from infrastructure.models.misc import LeasingCalculation
from infrastructure.models.special_equipment import (
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.users import (
    ClientProfile,
    User,
    UserFavorite,
    UserIdentityVerification,
)
from infrastructure.repositories.catalog_scope import special_equipment_visible_in
from infrastructure.repository_timing import timed_repository

# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


def _rowcount(result: object) -> int:
    return int(cast("CursorResult[Any]", result).rowcount or 0)

@timed_repository
async def get_profile_with_user(
    session: AsyncSession, user_id: UUID
) -> dict[str, Any] | None:
    """Return a flat dict joining ``users`` + ``client_profiles`` (LEFT JOIN).

    Returns ``None`` if the user doesn't exist. If the user exists but has
    no ``client_profiles`` row, profile-specific keys come back as ``None``.
    """
    latest_verified_at = (
        sa.select(UserIdentityVerification.verified_at)
        .where(
            UserIdentityVerification.user_id == User.id,
            UserIdentityVerification.status == "verified",
        )
        .order_by(UserIdentityVerification.verified_at.desc().nullslast())
        .limit(1)
        .scalar_subquery()
    )
    latest_verified_provider = (
        sa.select(UserIdentityVerification.provider)
        .where(
            UserIdentityVerification.user_id == User.id,
            UserIdentityVerification.status == "verified",
        )
        .order_by(UserIdentityVerification.verified_at.desc().nullslast())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        sa.select(
            User.id.label("user_id"),
            User.phone,
            User.email,
            User.name,
            User.role,
            User.company_id,
            User.is_active,
            User.phone_verified,
            ClientProfile.id.label("profile_id"),
            ClientProfile.client_type,
            ClientProfile.passport_series,
            ClientProfile.passport_issued_date,
            ClientProfile.passport_issued_by,
            ClientProfile.company_name,
            ClientProfile.inn,
            ClientProfile.kpp,
            ClientProfile.ogrn,
            ClientProfile.legal_address,
            ClientProfile.address,
            ClientProfile.birth_date,
            ClientProfile.notification_settings,
            ClientProfile.two_factor_enabled,
            (latest_verified_at.is_not(None)).label("identity_verified"),
            latest_verified_at.label("identity_verified_at"),
            latest_verified_provider.label("identity_verification_provider"),
            ClientProfile.created_at,
            ClientProfile.updated_at,
        )
        .select_from(User)
        .join(ClientProfile, ClientProfile.user_id == User.id, isouter=True)
        .where(User.id == user_id)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    return dict(row) if row else None

@timed_repository
async def update_user_basic(
    session: AsyncSession,
    user_id: UUID,
    *,
    name: str | None = None,
    email: str | None = None,
    has_name: bool = False,
    has_email: bool = False,
) -> bool:
    """Update ``users.name`` / ``users.email``. Only flags-on fields are touched."""
    values: dict[str, Any] = {}
    if has_name:
        values["name"] = name
    if has_email:
        values["email"] = email
    if not values:
        return True
    values["updated_at"] = datetime.now(UTC)
    result = await session.execute(
        sa.update(User).where(User.id == user_id).values(**values)
    )
    await session.flush()
    return _rowcount(result) > 0

@timed_repository
async def profile_exists(session: AsyncSession, user_id: UUID) -> bool:
    stmt = sa.select(
        sa.exists(sa.select(ClientProfile.id).where(ClientProfile.user_id == user_id))
    )
    result = await session.execute(stmt)
    return bool(result.scalar())

@timed_repository
async def upsert_profile(
    session: AsyncSession,
    user_id: UUID,
    profile_data: dict[str, Any],
) -> None:
    """Update existing ``client_profiles`` row or create a new one."""
    if not profile_data:
        return
    now = datetime.now(UTC)
    if await profile_exists(session, user_id):
        await session.execute(
            sa.update(ClientProfile)
            .where(ClientProfile.user_id == user_id)
            .values(updated_at=now, **profile_data)
        )
    else:
        session.add(
            ClientProfile(
                user_id=user_id,
                created_at=now,
                updated_at=now,
                **profile_data,
            )
        )
    await session.flush()

@timed_repository
async def fill_missing_profile_fields(
    session: AsyncSession,
    user_id: UUID,
    profile_data: dict[str, Any],
) -> None:
    """Create/update profile fields only when their current value is empty."""
    if not profile_data:
        return
    current = await get_profile_with_user(session, user_id)
    if current is None:
        return
    missing = {
        key: value
        for key, value in profile_data.items()
        if value is not None and not current.get(key)
    }
    if missing:
        await upsert_profile(session, user_id, missing)

@timed_repository
async def update_phone(
    session: AsyncSession, user_id: UUID, new_phone: str
) -> bool:
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(
            phone=new_phone,
            phone_verified=True,
            phone_verified_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    return _rowcount(result) > 0

@timed_repository
async def find_user_id_by_phone(
    session: AsyncSession, phone: str
) -> UUID | None:
    result = await session.execute(
        sa.select(User.id).where(User.phone == phone)
    )
    return result.scalar_one_or_none()

# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

@timed_repository
async def list_favorites(
    session: AsyncSession, user_id: UUID, scope: CatalogScope
) -> list[dict[str, Any]]:
    """List favorites with vehicle basic fields, newest-first."""
    stmt = (
        sa.select(
            UserFavorite.id,
            UserFavorite.storefront_id,
            UserFavorite.product_id.label("product_id"),
            UserFavorite.product_id.label("vehicle_id"),
            UserFavorite.added_at,
            SpecialEquipmentProduct.price.label("base_price"),
            SpecialEquipmentProduct.special_price.label("discount_price"),
            SpecialEquipmentProduct.manufacture_year.label("year"),
            sa.literal("").label("color"),
            SpecialEquipmentProduct.vin,
            SpecialEquipmentModel.mark_id,
            sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ).label("model_id"),
            SpecialEquipmentProduct.modification_id.label("complectation_id"),
            sa.literal([], type_=sa.JSON).label("images"),
        )
        .select_from(UserFavorite)
        .join(SpecialEquipmentProduct, SpecialEquipmentProduct.id == UserFavorite.product_id, isouter=True)
        .outerjoin(SpecialEquipmentModification, SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id)
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .where(
            UserFavorite.user_id == user_id,
            UserFavorite.storefront_id == scope.id,
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status == "available",
            special_equipment_visible_in(scope, product=SpecialEquipmentProduct),
        )
        .order_by(UserFavorite.added_at.desc().nullslast())
    )
    result = await session.execute(stmt)
    return [dict(row) for row in result.mappings().all()]

@timed_repository
async def is_favorite(
    session: AsyncSession,
    user_id: UUID,
    vehicle_id: UUID,
    scope: CatalogScope,
) -> bool:
    stmt = sa.select(
        sa.exists(
            sa.select(UserFavorite.id).where(
                UserFavorite.user_id == user_id,
                UserFavorite.storefront_id == scope.id,
                UserFavorite.product_id == vehicle_id,
            )
        )
    )
    result = await session.execute(stmt)
    return bool(result.scalar())

@timed_repository
async def add_favorite(
    session: AsyncSession,
    user_id: UUID,
    vehicle_id: UUID,
    scope: CatalogScope,
) -> dict[str, Any]:
    """Insert a favorite. Caller must check uniqueness via :func:`is_favorite`."""
    row = UserFavorite(
        user_id=user_id,
        storefront_id=scope.id,
        product_id=vehicle_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return {
        "id": row.id,
        "user_id": row.user_id,
        "storefront_id": row.storefront_id,
        "product_id": row.product_id,
        "vehicle_id": row.product_id,
        "added_at": row.added_at,
    }

@timed_repository
async def remove_favorite(
    session: AsyncSession,
    user_id: UUID,
    vehicle_id: UUID,
    scope: CatalogScope,
) -> bool:
    result = await session.execute(
        sa.delete(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.storefront_id == scope.id,
            UserFavorite.product_id == vehicle_id,
        )
    )
    await session.flush()
    return _rowcount(result) > 0

@timed_repository
async def bulk_remove_favorites(
    session: AsyncSession,
    user_id: UUID,
    vehicle_ids: Sequence[UUID],
    scope: CatalogScope,
) -> int:
    if not vehicle_ids:
        return 0
    result = await session.execute(
        sa.delete(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.storefront_id == scope.id,
            UserFavorite.product_id.in_(list(vehicle_ids)),
        )
    )
    await session.flush()
    return _rowcount(result)

@timed_repository
async def clear_favorites(
    session: AsyncSession, user_id: UUID, scope: CatalogScope
) -> int:
    """Remove all favorites for a user. Returns the number of rows deleted."""
    result = await session.execute(
        sa.delete(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.storefront_id == scope.id,
        )
    )
    await session.flush()
    return _rowcount(result)


@timed_repository
async def vehicle_visible_for_favorites(
    session: AsyncSession,
    vehicle_id: UUID,
    scope: CatalogScope,
) -> bool:
    result = await session.execute(
        sa.select(
            sa.exists(
                sa.select(SpecialEquipmentProduct.id).where(
                    SpecialEquipmentProduct.id == vehicle_id,
                    SpecialEquipmentProduct.publication_status == "published",
                    SpecialEquipmentProduct.sale_status == "available",
                    special_equipment_visible_in(scope, product=SpecialEquipmentProduct),
                )
            )
        )
    )
    return bool(result.scalar())

@timed_repository
async def get_two_factor_enabled(
    session: AsyncSession, user_id: UUID
) -> bool:
    """Return the two_factor_enabled flag from client_profiles, or False."""
    stmt = sa.select(ClientProfile.two_factor_enabled).where(
        ClientProfile.user_id == user_id
    )
    result = await session.execute(stmt)
    value = result.scalar_one_or_none()
    return bool(value) if value is not None else False

@timed_repository
async def set_two_factor_enabled(
    session: AsyncSession, user_id: UUID, enabled: bool
) -> None:
    """Set the client_profile.two_factor_enabled flag (upserting the row)."""
    now = datetime.now(UTC)
    if await profile_exists(session, user_id):
        await session.execute(
            sa.update(ClientProfile)
            .where(ClientProfile.user_id == user_id)
            .values(two_factor_enabled=enabled, updated_at=now)
        )
    else:
        session.add(
            ClientProfile(
                user_id=user_id,
                two_factor_enabled=enabled,
                created_at=now,
                updated_at=now,
            )
        )
    await session.flush()

# ---------------------------------------------------------------------------
# Saved calculations
# ---------------------------------------------------------------------------

@timed_repository
async def list_saved_calculations(
    session: AsyncSession, user_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        sa.select(LeasingCalculation)
        .where(LeasingCalculation.user_id == user_id)
        .order_by(LeasingCalculation.created_at.desc().nullslast())
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "name": r.name,
            "params": dict(r.params or {}),
            "calculation": dict(r.calculation or {}),
            "created_at": r.created_at,
        }
        for r in rows
    ]

@timed_repository
async def save_calculation(
    session: AsyncSession,
    user_id: UUID,
    *,
    name: str,
    params: dict[str, Any],
    calculation: dict[str, Any],
) -> dict[str, Any]:
    row = LeasingCalculation(
        user_id=user_id,
        name=name,
        params=params,
        calculation=calculation,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "params": dict(row.params or {}),
        "calculation": dict(row.calculation or {}),
        "created_at": row.created_at,
    }

@timed_repository
async def get_saved_calculation(
    session: AsyncSession, calculation_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(LeasingCalculation, calculation_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "params": dict(row.params or {}),
        "calculation": dict(row.calculation or {}),
        "created_at": row.created_at,
    }

@timed_repository
async def delete_saved_calculation(
    session: AsyncSession, calculation_id: UUID
) -> bool:
    result = await session.execute(
        sa.delete(LeasingCalculation).where(
            LeasingCalculation.id == calculation_id
        )
    )
    await session.flush()
    return _rowcount(result) > 0

# ---------------------------------------------------------------------------
# Phone-change verification codes
# ---------------------------------------------------------------------------

# Re-export the auth_repository helpers so the client commands don't have to
# reach into another bounded context. We keep them as thin wrappers to make
# the client repository the single source of truth for the client domain.

@timed_repository
async def save_phone_change_code(
    session: AsyncSession, phone: str, code: str, expires_at: datetime
) -> None:
    from infrastructure.repositories import auth_repository as auth_repo
    await auth_repo.save_verification_code(session, phone, code, expires_at)

@timed_repository
async def verify_phone_change_code(
    session: AsyncSession, phone: str, code: str
) -> bool:
    from infrastructure.repositories import auth_repository as auth_repo
    return await auth_repo.verify_code(session, phone, code)

@timed_repository
async def delete_phone_change_codes(
    session: AsyncSession, phone: str
) -> None:
    from infrastructure.repositories import auth_repository as auth_repo
    await auth_repo.delete_codes(session, phone)
