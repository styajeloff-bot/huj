"""Dealer group repository — company-based async, dict-only API."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, Distributor, DistributorDealerLink
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.repository_timing import timed_repository


def _row_to_dict(row: DealerGroup) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "distributor_company_id": row.distributor_company_id,
        "distributor_id": row.distributor_company_id,
        "is_active": row.is_active,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def _distributor_summary(
    session: AsyncSession, distributor_company_id: UUID
) -> dict[str, Any] | None:
    stmt = select(Company.id, Company.name, Company.inn).where(
        Company.id == distributor_company_id,
        Company.company_type == "distributor",
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return {"id": row.id, "name": row.name, "inn": row.inn}


async def _attach_relations(
    session: AsyncSession, base: dict[str, Any]
) -> dict[str, Any]:
    dealers = await _list_dealers(session, cast("UUID", base["id"]))
    base["dealers"] = dealers
    base["dealer_company_ids"] = [dealer["id"] for dealer in dealers]
    base["dealer_ids"] = base["dealer_company_ids"]
    base["dealers_count"] = len(dealers)
    base["distributor"] = await _distributor_summary(
        session, cast("UUID", base["distributor_company_id"])
    )
    return base


@timed_repository
async def name_exists(
    session: AsyncSession,
    name: str,
    *,
    distributor_company_id: UUID,
    exclude_id: UUID | None = None,
) -> bool:
    stmt = select(DealerGroup.id).where(
        DealerGroup.distributor_company_id == distributor_company_id,
        DealerGroup.is_active.is_(True),
        func.lower(DealerGroup.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(DealerGroup.id != exclude_id)
    result = await session.execute(stmt)
    return result.first() is not None


@timed_repository
async def get_id_by_name(
    session: AsyncSession, name: str, *, distributor_company_id: UUID
) -> UUID | None:
    stmt = select(DealerGroup.id).where(
        DealerGroup.distributor_company_id == distributor_company_id,
        DealerGroup.is_active.is_(True),
        func.lower(DealerGroup.name) == name.lower(),
    )
    result = await session.execute(stmt)
    row = result.first()
    return row[0] if row is not None else None


@timed_repository
async def get_by_id(session: AsyncSession, group_id: UUID) -> dict[str, Any] | None:
    row = await session.get(DealerGroup, group_id)
    if row is None:
        return None
    return await _attach_relations(session, _row_to_dict(row))


@timed_repository
async def _list_dealers(
    session: AsyncSession, group_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(Company.id, Company.name, Company.inn)
        .join(
            DealerGroupMember,
            DealerGroupMember.dealer_company_id == Company.id,
        )
        .where(DealerGroupMember.dealer_group_id == group_id)
        .order_by(func.coalesce(Company.name, "").asc(), Company.id.asc())
    )
    result = await session.execute(stmt)
    return [
        {"id": row.id, "name": row.name, "inn": row.inn}
        for row in result.all()
    ]


@timed_repository
async def list_dealer_groups(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    distributor_id: UUID | None = None,
    dealer_id: UUID | None = None,
    is_active: bool | None = None,
) -> tuple[list[dict[str, Any]], int]:
    conditions: list[Any] = []
    if is_active is not None:
        conditions.append(DealerGroup.is_active.is_(is_active))
    if distributor_id is not None:
        conditions.append(DealerGroup.distributor_company_id == distributor_id)
    if dealer_id is not None:
        dealer_match = (
            select(DealerGroupMember.id)
            .where(
                DealerGroupMember.dealer_group_id == DealerGroup.id,
                DealerGroupMember.dealer_company_id == dealer_id,
            )
            .exists()
        )
        conditions.append(dealer_match)
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                DealerGroup.name.ilike(pattern),
                func.coalesce(DealerGroup.description, "").ilike(pattern),
            )
        )

    where_clause = and_(*conditions) if conditions else None
    count_stmt = select(func.count(DealerGroup.id))
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = int((await session.execute(count_stmt)).scalar() or 0)

    stmt = (
        select(DealerGroup)
        .order_by(
            DealerGroup.is_active.desc(),
            DealerGroup.created_at.desc().nullslast(),
            DealerGroup.id.desc(),
        )
        .offset((max(page, 1) - 1) * max(limit, 1))
        .limit(max(limit, 1))
    )
    if where_clause is not None:
        stmt = stmt.where(where_clause)
    rows = (await session.execute(stmt)).scalars().all()
    items = [
        await _attach_relations(session, _row_to_dict(row))
        for row in rows
    ]
    return items, total


@timed_repository
async def create_dealer_group(
    session: AsyncSession,
    *,
    name: str,
    description: str | None,
    distributor_company_id: UUID,
    created_by: UUID,
) -> UUID:
    row = DealerGroup(
        name=name,
        description=description,
        distributor_company_id=distributor_company_id,
        created_by=created_by,
        is_active=True,
    )
    session.add(row)
    await session.flush()
    return row.id


@timed_repository
async def update_dealer_group(
    session: AsyncSession,
    group_id: UUID,
    *,
    name: str,
    description: str | None,
    distributor_company_id: UUID,
    updated_by: UUID,
) -> bool:
    row = await session.get(DealerGroup, group_id)
    if row is None:
        return False
    row.name = name
    row.description = description
    row.distributor_company_id = distributor_company_id
    row.updated_by = updated_by
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True


@timed_repository
async def delete_dealer_group(
    session: AsyncSession, group_id: UUID, *, updated_by: UUID | None = None
) -> bool:
    row = await session.get(DealerGroup, group_id)
    if row is None:
        return False
    row.is_active = False
    if updated_by is not None:
        row.updated_by = updated_by
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True


@timed_repository
async def replace_members(
    session: AsyncSession,
    group_id: UUID,
    dealer_company_ids: list[UUID],
    *,
    created_by: UUID,
) -> None:
    await session.execute(
        delete(DealerGroupMember).where(DealerGroupMember.dealer_group_id == group_id)
    )
    for dealer_company_id in dealer_company_ids:
        session.add(
            DealerGroupMember(
                dealer_group_id=group_id,
                dealer_company_id=dealer_company_id,
                created_by=created_by,
            )
        )
    await session.flush()


@timed_repository
async def get_existing_group_ids(
    session: AsyncSession, group_ids: list[UUID]
) -> set[UUID]:
    if not group_ids:
        return set()
    stmt = select(DealerGroup.id).where(
        DealerGroup.id.in_(group_ids),
        DealerGroup.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


@timed_repository
async def get_group_distributor_ids(
    session: AsyncSession, group_ids: list[UUID]
) -> dict[UUID, UUID]:
    if not group_ids:
        return {}
    stmt = select(DealerGroup.id, DealerGroup.distributor_company_id).where(
        DealerGroup.id.in_(group_ids),
        DealerGroup.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return {row.id: row.distributor_company_id for row in result.all()}


@timed_repository
async def get_existing_dealer_company_ids(
    session: AsyncSession,
    dealer_company_ids: list[UUID],
    *,
    distributor_company_id: UUID | None = None,
) -> set[UUID]:
    if not dealer_company_ids:
        return set()
    stmt = select(Company.id).where(
        Company.id.in_(dealer_company_ids),
        Company.company_type == "dealer",
        Company.is_active.is_(True),
    )
    if distributor_company_id is not None:
        link_exists = exists().where(
            DistributorDealerLink.distributor_company_id == distributor_company_id,
            DistributorDealerLink.dealer_company_id == Company.id,
        )
        stmt = stmt.where(link_exists)
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


@timed_repository
async def distributor_company_exists(
    session: AsyncSession, distributor_company_id: UUID
) -> bool:
    stmt = select(Company.id).where(
        Company.id == distributor_company_id,
        Company.company_type == "distributor",
        Company.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.first() is not None


@timed_repository
async def distributor_can_manage_dealer_groups(
    session: AsyncSession, distributor_company_id: UUID
) -> bool:
    stmt = select(Distributor.can_manage_dealer_groups).where(
        Distributor.company_id == distributor_company_id,
        Distributor.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return bool(result.scalar_one_or_none())
