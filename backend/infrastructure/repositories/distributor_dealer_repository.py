"""Distributor–dealer link repository — async, dict-only API.

Provides company-level bridge-table access for the distributor↔dealer
relationship.  One distributor may own many dealers; a dealer may belong to
exactly one distributor (enforced by UNIQUE on ``dealer_company_id``).
"""
from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.repository_timing import timed_repository


@timed_repository
async def list_dealers_for_distributor(
    session: AsyncSession,
    *,
    distributor_company_id: UUID,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Paginated list of dealer companies linked to a distributor."""
    count_stmt = (
        sa.select(sa.func.count(sa.func.distinct(Company.id)))
        .select_from(DistributorDealerLink)
        .join(Company, Company.id == DistributorDealerLink.dealer_company_id)
        .where(DistributorDealerLink.distributor_company_id == distributor_company_id)
    )
    total = int((await session.execute(count_stmt)).scalar() or 0)

    rows_stmt = (
        sa.select(
            Company.id,
            Company.name,
            Company.inn,
            Company.company_type,
            Company.is_active,
            Company.phone,
            Company.email,
        )
        .select_from(DistributorDealerLink)
        .join(Company, Company.id == DistributorDealerLink.dealer_company_id)
        .where(DistributorDealerLink.distributor_company_id == distributor_company_id)
        .order_by(Company.name.nullslast(), Company.id)
        .offset(max(0, (page - 1) * limit))
        .limit(limit)
    )
    rows = (await session.execute(rows_stmt)).all()

    items = [
        {
            "id": r.id,
            "name": r.name,
            "inn": r.inn,
            "company_type": r.company_type,
            "is_active": r.is_active,
            "phone": r.phone,
            "email": r.email,
        }
        for r in rows
    ]
    return items, total


@timed_repository
async def get_linked_dealer_ids(
    session: AsyncSession,
    distributor_company_id: UUID,
) -> list[UUID]:
    """Return all active dealer ids owned directly or through a dealer group."""
    direct_dealers = sa.select(DistributorDealerLink.dealer_company_id).where(
        DistributorDealerLink.distributor_company_id == distributor_company_id
    )
    group_dealers = (
        sa.select(DealerGroupMember.dealer_company_id)
        .join(DealerGroup, DealerGroup.id == DealerGroupMember.dealer_group_id)
        .where(
            DealerGroup.distributor_company_id == distributor_company_id,
            DealerGroup.is_active.is_(True),
        )
    )
    stmt = sa.select(sa.distinct(direct_dealers.union(group_dealers).subquery().c.dealer_company_id))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@timed_repository
async def add_link(
    session: AsyncSession,
    distributor_company_id: UUID,
    dealer_company_id: UUID,
) -> None:
    """Insert a link row.  Caller must guard the UNIQUE constraint."""
    session.add(
        DistributorDealerLink(
            distributor_company_id=distributor_company_id,
            dealer_company_id=dealer_company_id,
        )
    )
    await session.flush()


@timed_repository
async def remove_link(
    session: AsyncSession,
    distributor_company_id: UUID,
    dealer_company_id: UUID,
) -> bool:
    """Delete a link row.  Return True if a row was deleted."""
    result = await session.execute(
        sa.delete(DistributorDealerLink)
        .where(
            DistributorDealerLink.distributor_company_id == distributor_company_id,
            DistributorDealerLink.dealer_company_id == dealer_company_id,
        )
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0) > 0


@timed_repository
async def dealer_is_linked(
    session: AsyncSession,
    dealer_company_id: UUID,
    exclude_distributor_id: UUID | None = None,
) -> bool:
    """Return True if the dealer is already linked to any distributor."""
    stmt = sa.select(sa.func.count(DistributorDealerLink.dealer_company_id)).where(
        DistributorDealerLink.dealer_company_id == dealer_company_id
    )
    if exclude_distributor_id is not None:
        stmt = stmt.where(
            DistributorDealerLink.distributor_company_id != exclude_distributor_id
        )
    result = await session.execute(stmt)
    return int(result.scalar() or 0) > 0


@timed_repository
async def get_distributor_for_dealer(
    session: AsyncSession,
    dealer_company_id: UUID,
) -> UUID | None:
    """Return the distributor company id for this dealer, or None."""
    stmt = (
        sa.select(DistributorDealerLink.distributor_company_id)
        .where(DistributorDealerLink.dealer_company_id == dealer_company_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
