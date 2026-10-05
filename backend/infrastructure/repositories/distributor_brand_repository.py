"""Persistence for distributor-company vehicle brand assignments."""

from __future__ import annotations

import contextlib
from collections.abc import Collection
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, DistributorBrand
from infrastructure.models.special_equipment import SpecialEquipmentMark
from infrastructure.repository_timing import timed_repository


class CompanyIdentityDict(TypedDict):
    id: UUID
    company_type: str


class BrandDict(TypedDict):
    id: str
    name: str


@timed_repository
async def get_company(
    session: AsyncSession,
    company_id: UUID,
    *,
    for_update: bool = False,
) -> CompanyIdentityDict | None:
    """Return the company identity, optionally locking it for set replacement."""
    stmt = sa.select(Company.id, Company.company_type).where(
        Company.id == company_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None
    return {"id": row.id, "company_type": row.company_type}


@timed_repository
async def list_available_brands(session: AsyncSession) -> list[BrandDict]:
    """Return the complete mark directory, independent of vehicle inventory."""
    rows = (
        await session.execute(
            sa.select(SpecialEquipmentMark.id, SpecialEquipmentMark.name).order_by(
                sa.func.lower(SpecialEquipmentMark.name).asc(),
                SpecialEquipmentMark.id.asc(),
            )
        )
    ).all()
    return [{"id": str(row.id), "name": row.name} for row in rows]


@timed_repository
async def get_existing_brand_ids(
    session: AsyncSession,
    brand_ids: Collection[str],
) -> set[str]:
    """Return IDs from SpecialEquipmentMark that exist in the requested set."""
    if not brand_ids:
        return set()
    uids: list[UUID] = []
    for bid in brand_ids:
        with contextlib.suppress(ValueError, TypeError):
            uids.append(UUID(bid))
    if not uids:
        return set()
    rows = await session.scalars(
        sa.select(SpecialEquipmentMark.id).where(SpecialEquipmentMark.id.in_(uids))
    )
    return {str(uid) for uid in rows.all()}


@timed_repository
async def list_active_brand_ids(
    session: AsyncSession,
    distributor_company_id: UUID,
) -> list[str]:
    rows = await session.scalars(
        sa.select(DistributorBrand.brand_id)
        .where(
            DistributorBrand.distributor_company_id == distributor_company_id,
            DistributorBrand.is_active.is_(True),
        )
        .order_by(DistributorBrand.brand_id.asc())
    )
    return [str(uid) for uid in rows.all()]


@timed_repository
async def replace_active_brand_ids(
    session: AsyncSession,
    *,
    distributor_company_id: UUID,
    brand_ids: Collection[str],
) -> list[str]:
    """Replace the active set using soft-deactivate/reactivate/insert semantics.

    The application layer locks the owning ``companies`` row before calling
    this function. That row is the serialization point even when no assignment
    rows exist yet, so concurrent replacements for one company cannot both
    create the same active pair.
    """
    desired_ids: set[UUID] = set()
    for bid in brand_ids:
        with contextlib.suppress(ValueError, TypeError):
            desired_ids.add(UUID(bid))
    rows = list(
        (
            await session.scalars(
                sa.select(DistributorBrand)
                .where(
                    DistributorBrand.distributor_company_id
                    == distributor_company_id
                )
                .order_by(
                    DistributorBrand.created_at.desc(),
                    DistributorBrand.id.desc(),
                )
                .with_for_update()
            )
        ).all()
    )
    now = datetime.now(UTC)

    active_by_brand: dict[UUID, DistributorBrand] = {}
    inactive_by_brand: dict[UUID, DistributorBrand] = {}
    for row in rows:
        target = active_by_brand if row.is_active else inactive_by_brand
        target.setdefault(row.brand_id, row)

    for brand_id, row in active_by_brand.items():
        if brand_id not in desired_ids:
            row.is_active = False
            row.updated_at = now

    for brand_id in sorted(desired_ids):
        if brand_id in active_by_brand:
            continue
        inactive = inactive_by_brand.get(brand_id)
        if inactive is not None:
            inactive.is_active = True
            inactive.updated_at = now
            continue
        session.add(
            DistributorBrand(
                distributor_company_id=distributor_company_id,
                brand_id=brand_id,
                is_active=True,
            )
        )

    await session.flush()
    return await list_active_brand_ids(session, distributor_company_id)
