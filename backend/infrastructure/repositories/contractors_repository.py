"""Repository helpers for SOPD contractors and LC-contractor links."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.contractors import (
    Contractor,
    LeasingCompanyContractor,
)
from infrastructure.repository_timing import timed_repository


class ContractorLinkDict(TypedDict):
    id: UUID
    leasing_company_id: UUID
    leasing_company_company_id: UUID | None
    leasing_company_name: str | None
    leasing_company_inn: str | None
    contractor_id: UUID
    contractor_name: str
    contractor_inn: str
    created_at: Any
    updated_at: Any


class ContractorDict(TypedDict):
    id: UUID
    name: str
    inn: str
    created_at: Any
    updated_at: Any


class LeasingCompanyRefDict(TypedDict):
    id: UUID
    company_id: UUID | None
    name: str | None
    inn: str | None


def _contractor_to_dict(row: Contractor) -> ContractorDict:
    return {
        "id": row.id,
        "name": row.name,
        "inn": row.inn,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _row_to_link(row: Any) -> ContractorLinkDict:
    return {
        "id": row.link_id,
        "leasing_company_id": row.leasing_company_id,
        "leasing_company_company_id": row.leasing_company_company_id,
        "leasing_company_name": row.leasing_company_name,
        "leasing_company_inn": row.leasing_company_inn,
        "contractor_id": row.contractor_id,
        "contractor_name": row.contractor_name,
        "contractor_inn": row.contractor_inn,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _link_select() -> sa.Select[Any]:
    return (
        sa.select(
            LeasingCompanyContractor.id.label("link_id"),
            LeasingCompany.id.label("leasing_company_id"),
            Company.id.label("leasing_company_company_id"),
            Company.name.label("leasing_company_name"),
            Company.inn.label("leasing_company_inn"),
            Contractor.id.label("contractor_id"),
            Contractor.name.label("contractor_name"),
            Contractor.inn.label("contractor_inn"),
            LeasingCompanyContractor.created_at,
            LeasingCompanyContractor.updated_at,
        )
        .select_from(LeasingCompanyContractor)
        .join(
            LeasingCompany,
            LeasingCompany.id == LeasingCompanyContractor.leasing_company_id,
        )
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .join(Contractor, Contractor.id == LeasingCompanyContractor.contractor_id)
    )


@timed_repository
async def list_links(
    session: AsyncSession,
    *,
    page: int,
    limit: int,
    leasing_company_id: UUID | None = None,
    contractor_name: str | None = None,
    inn: str | None = None,
) -> tuple[list[ContractorLinkDict], int]:
    conditions: list[Any] = []
    if leasing_company_id is not None:
        conditions.append(
            LeasingCompanyContractor.leasing_company_id == leasing_company_id
        )
    if contractor_name:
        conditions.append(Contractor.name.ilike(f"%{contractor_name}%"))
    if inn:
        conditions.append(
            sa.or_(
                Contractor.inn.ilike(f"%{inn}%"),
                Company.inn.ilike(f"%{inn}%"),
            )
        )

    base = _link_select()
    count_stmt = sa.select(sa.func.count()).select_from(LeasingCompanyContractor)
    if conditions:
        base = base.where(*conditions)
        count_stmt = (
            count_stmt.join(
                LeasingCompany,
                LeasingCompany.id == LeasingCompanyContractor.leasing_company_id,
            )
            .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
            .join(
                Contractor,
                Contractor.id == LeasingCompanyContractor.contractor_id,
            )
            .where(*conditions)
        )

    total = int((await session.execute(count_stmt)).scalar() or 0)
    stmt = (
        base.order_by(Company.name.asc().nullslast(), Contractor.name.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [_row_to_link(row) for row in rows], total


@timed_repository
async def list_contractors(
    session: AsyncSession,
    *,
    page: int,
    limit: int,
    contractor_name: str | None = None,
    inn: str | None = None,
) -> tuple[list[ContractorDict], int]:
    conditions: list[Any] = []
    if contractor_name:
        conditions.append(Contractor.name.ilike(f"%{contractor_name}%"))
    if inn:
        conditions.append(Contractor.inn.ilike(f"%{inn}%"))

    count_stmt = sa.select(sa.func.count()).select_from(Contractor)
    stmt = sa.select(Contractor)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
        stmt = stmt.where(*conditions)

    total = int((await session.execute(count_stmt)).scalar() or 0)
    rows = (
        await session.execute(
            stmt.order_by(Contractor.name.asc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).scalars()
    return [_contractor_to_dict(row) for row in rows], total


@timed_repository
async def get_link_by_id(
    session: AsyncSession, link_id: UUID
) -> ContractorLinkDict | None:
    row = (
        await session.execute(
            _link_select().where(LeasingCompanyContractor.id == link_id)
        )
    ).first()
    return _row_to_link(row) if row else None


@timed_repository
async def get_leasing_company_by_id(
    session: AsyncSession, leasing_company_id: UUID
) -> LeasingCompanyRefDict | None:
    stmt = (
        sa.select(
            LeasingCompany.id,
            Company.id.label("company_id"),
            Company.name,
            Company.inn,
        )
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .where(LeasingCompany.id == leasing_company_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "company_id": row.company_id,
        "name": row.name,
        "inn": row.inn,
    }


@timed_repository
async def get_leasing_company_by_inn(
    session: AsyncSession, inn: str
) -> LeasingCompanyRefDict | None:
    stmt = (
        sa.select(
            LeasingCompany.id,
            Company.id.label("company_id"),
            Company.name,
            Company.inn,
        )
        .join(Company, Company.id == LeasingCompany.company_id)
        .where(
            Company.company_type == "leasing_company",
            Company.inn == inn,
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "company_id": row.company_id,
        "name": row.name,
        "inn": row.inn,
    }


@timed_repository
async def get_contractor_by_id(
    session: AsyncSession, contractor_id: UUID
) -> ContractorDict | None:
    row = await session.get(Contractor, contractor_id)
    return _contractor_to_dict(row) if row is not None else None


@timed_repository
async def get_contractor_by_inn(
    session: AsyncSession, inn: str
) -> ContractorDict | None:
    row = (
        await session.execute(sa.select(Contractor).where(Contractor.inn == inn))
    ).scalars().first()
    return _contractor_to_dict(row) if row is not None else None


@timed_repository
async def get_contractors_by_ids(
    session: AsyncSession, contractor_ids: set[UUID]
) -> list[ContractorDict]:
    if not contractor_ids:
        return []
    rows = (
        await session.execute(
            sa.select(Contractor).where(Contractor.id.in_(contractor_ids))
        )
    ).scalars()
    return [_contractor_to_dict(row) for row in rows]


@timed_repository
async def get_leasing_companies_by_ids(
    session: AsyncSession, leasing_company_ids: set[UUID]
) -> list[LeasingCompanyRefDict]:
    if not leasing_company_ids:
        return []
    stmt = (
        sa.select(
            LeasingCompany.id,
            Company.id.label("company_id"),
            Company.name,
            Company.inn,
        )
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .where(LeasingCompany.id.in_(leasing_company_ids))
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "company_id": row.company_id,
            "name": row.name,
            "inn": row.inn,
        }
        for row in rows
    ]


@timed_repository
async def create_contractor(
    session: AsyncSession, *, name: str, inn: str
) -> ContractorDict:
    row = Contractor(name=name, inn=inn)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return _contractor_to_dict(row)


@timed_repository
async def update_contractor_name(
    session: AsyncSession, *, contractor_id: UUID, name: str
) -> ContractorDict | None:
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(Contractor)
        .where(Contractor.id == contractor_id)
        .values(name=name, updated_at=now)
        .returning(Contractor)
    )
    row = result.scalars().first()
    return _contractor_to_dict(row) if row is not None else None


@timed_repository
async def get_link_by_pair(
    session: AsyncSession, *, leasing_company_id: UUID, contractor_id: UUID
) -> ContractorLinkDict | None:
    row = (
        await session.execute(
            _link_select().where(
                LeasingCompanyContractor.leasing_company_id == leasing_company_id,
                LeasingCompanyContractor.contractor_id == contractor_id,
            )
        )
    ).first()
    return _row_to_link(row) if row else None


@timed_repository
async def create_link(
    session: AsyncSession, *, leasing_company_id: UUID, contractor_id: UUID
) -> ContractorLinkDict:
    row = LeasingCompanyContractor(
        leasing_company_id=leasing_company_id,
        contractor_id=contractor_id,
    )
    session.add(row)
    await session.flush()
    link = await get_link_by_id(session, row.id)
    if link is None:
        raise RuntimeError("Created contractor link is not readable")
    return link


@timed_repository
async def list_links_for_leasing_company(
    session: AsyncSession, *, leasing_company_id: UUID
) -> list[ContractorLinkDict]:
    rows = (
        await session.execute(
            _link_select()
            .where(LeasingCompanyContractor.leasing_company_id == leasing_company_id)
            .order_by(Contractor.name.asc())
        )
    ).all()
    return [_row_to_link(row) for row in rows]


@timed_repository
async def list_links_for_leasing_companies(
    session: AsyncSession, *, leasing_company_ids: set[UUID]
) -> list[ContractorLinkDict]:
    if not leasing_company_ids:
        return []
    rows = (
        await session.execute(
            _link_select()
            .where(
                LeasingCompanyContractor.leasing_company_id.in_(
                    leasing_company_ids
                )
            )
            .order_by(Company.name.asc().nullslast(), Contractor.name.asc())
        )
    ).all()
    return [_row_to_link(row) for row in rows]


@timed_repository
async def list_links_for_contractor(
    session: AsyncSession, *, contractor_id: UUID
) -> list[ContractorLinkDict]:
    rows = (
        await session.execute(
            _link_select()
            .where(LeasingCompanyContractor.contractor_id == contractor_id)
            .order_by(Company.name.asc().nullslast())
        )
    ).all()
    return [_row_to_link(row) for row in rows]


@timed_repository
async def set_links_for_leasing_company(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    contractor_ids: set[UUID],
) -> list[ContractorLinkDict]:
    current_rows = (
        await session.execute(
            sa.select(
                LeasingCompanyContractor.id,
                LeasingCompanyContractor.contractor_id,
            ).where(LeasingCompanyContractor.leasing_company_id == leasing_company_id)
        )
    ).all()
    current_ids = {row.contractor_id for row in current_rows}

    delete_stmt = sa.delete(LeasingCompanyContractor).where(
        LeasingCompanyContractor.leasing_company_id == leasing_company_id
    )
    if contractor_ids:
        delete_stmt = delete_stmt.where(
            LeasingCompanyContractor.contractor_id.not_in(contractor_ids)
        )
    await session.execute(delete_stmt)

    for contractor_id in contractor_ids.difference(current_ids):
        session.add(
            LeasingCompanyContractor(
                leasing_company_id=leasing_company_id,
                contractor_id=contractor_id,
            )
        )
    await session.flush()
    return await list_links_for_leasing_company(
        session, leasing_company_id=leasing_company_id
    )


@timed_repository
async def set_links_for_contractor(
    session: AsyncSession,
    *,
    contractor_id: UUID,
    leasing_company_ids: set[UUID],
) -> list[ContractorLinkDict]:
    current_rows = (
        await session.execute(
            sa.select(
                LeasingCompanyContractor.id,
                LeasingCompanyContractor.leasing_company_id,
            ).where(LeasingCompanyContractor.contractor_id == contractor_id)
        )
    ).all()
    current_ids = {row.leasing_company_id for row in current_rows}

    delete_stmt = sa.delete(LeasingCompanyContractor).where(
        LeasingCompanyContractor.contractor_id == contractor_id
    )
    if leasing_company_ids:
        delete_stmt = delete_stmt.where(
            LeasingCompanyContractor.leasing_company_id.not_in(leasing_company_ids)
        )
    await session.execute(delete_stmt)

    for leasing_company_id in leasing_company_ids.difference(current_ids):
        session.add(
            LeasingCompanyContractor(
                leasing_company_id=leasing_company_id,
                contractor_id=contractor_id,
            )
        )
    await session.flush()
    return await list_links_for_contractor(session, contractor_id=contractor_id)


@timed_repository
async def delete_link(session: AsyncSession, *, link_id: UUID) -> bool:
    result = await session.execute(
        sa.delete(LeasingCompanyContractor).where(
            LeasingCompanyContractor.id == link_id
        )
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0) > 0
