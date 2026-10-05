"""Support program repository — async, dict-only API."""

from __future__ import annotations

import contextlib
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from infrastructure.models.companies import (
    Company,
    DistributorDealerLink,
    LeasingCompany,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
)
from infrastructure.models.support import (
    DealerGroup,
    DealerGroupMember,
    SupportBillOfLading,
    SupportProgram,
    SupportProgramCompatibility,
    SupportProgramDealerGroup,
    SupportProgramDistributor,
    SupportProgramLeasingCompany,
    SupportProgramMark,
)
from infrastructure.repositories import compensation_repository
from infrastructure.repository_timing import timed_repository


def _row_to_base_dict(row: SupportProgram) -> dict[str, Any]:
    status = "active" if row.is_active else "inactive"
    today = datetime.now(UTC).date()
    if row.is_active and row.ends_at is not None and row.ends_at < today:
        status = "completed"
    return {
        "id": row.id,
        "name": row.name,
        "mark_id": row.mark_id,
        "mark_ids": [],
        "model_id": row.model_id,
        "model_ids": list(row.model_ids) if row.model_ids else [],
        "complectation_ids": list(row.complectation_ids)
        if row.complectation_ids
        else [],
        "vin": row.vin,
        "vins": list(row.vins) if row.vins else [],
        "dealer_group_id": row.dealer_group_id,
        "distributor_id": row.distributor_id,
        "distributor_ids": [],
        "support_type": row.support_type,
        "support_params": dict(row.support_params or {}),
        "production_year_from": row.production_year_from,
        "production_year_to": row.production_year_to,
        "production_date_from": row.production_date_from,
        "production_date_to": row.production_date_to,
        "delivery_date_from": row.delivery_date_from,
        "delivery_date_to": row.delivery_date_to,
        "starts_at": row.starts_at,
        "ends_at": row.ends_at,
        "is_active": bool(row.is_active) if row.is_active is not None else True,
        "is_compatible": row.is_compatible,
        "compatible_support_ids": [],
        "status": status,
        "show_to_leasing_company": (
            bool(row.show_to_leasing_company)
            if row.show_to_leasing_company is not None
            else True
        ),
        "show_to_client": (
            bool(row.show_to_client) if row.show_to_client is not None else True
        ),
        "comment": row.comment,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@timed_repository
async def _attach_relations(
    session: AsyncSession, program: dict[str, Any]
) -> dict[str, Any]:
    program_id = program["id"]
    program["mark_ids"] = await _list_mark_ids(session, program_id)
    if not program["mark_ids"] and program.get("mark_id"):
        program["mark_ids"] = [program["mark_id"]]
    program["mark_name"] = await _resolve_mark_names(session, program["mark_ids"])

    model_ids = list(program.get("model_ids") or [])
    if not model_ids and program.get("model_id"):
        model_ids = [program["model_id"]]
    program["model_name"] = await _resolve_model_names(session, model_ids)

    program["distributor_ids"] = await _list_distributor_ids(session, program_id)
    if not program["distributor_ids"] and program.get("distributor_id") is not None:
        program["distributor_ids"] = [program["distributor_id"]]
    program["distributors"] = await _list_distributor_details(session, program_id)
    if not program["distributors"] and program.get("distributor_id") is not None:
        program["distributors"] = await _list_distributor_details_by_ids(
            session, [program["distributor_id"]]
        )
    program["distributor_name"] = (
        program["distributors"][0]["name"] if program["distributors"] else None
    )

    program["leasing_company_ids"] = await _list_leasing_company_ids(
        session, program_id
    )
    program["leasing_companies"] = await _list_leasing_company_details(
        session, program_id
    )
    program["dealer_group_ids"] = await _list_dealer_group_ids(session, program_id)
    program["dealer_groups"] = await _list_dealer_group_details(session, program_id)
    program["compatible_support_ids"] = await list_compatible_support_ids(
        session, program_id
    )
    program["bill_of_lading"] = await _list_bill_of_lading(session, program_id)
    program[
        "compensation_templates"
    ] = await compensation_repository.list_compensation_templates(session, program_id)
    return program


async def _resolve_mark_names(session: AsyncSession, mark_ids: list[Any]) -> str | None:
    if not mark_ids:
        return None
    uids: list[UUID] = []
    for m in mark_ids:
        with contextlib.suppress(ValueError, TypeError):
            uids.append(UUID(str(m)))
    if not uids:
        return None
    stmt = select(SpecialEquipmentMark.id, SpecialEquipmentMark.name).where(SpecialEquipmentMark.id.in_(uids))
    rows = (await session.execute(stmt)).all()
    by_id = {row.id: (row.name or str(row.id)) for row in rows}
    names = [by_id.get(uid, str(uid)) for uid in uids]
    return ", ".join(names) if names else None


async def _resolve_model_names(
    session: AsyncSession, model_ids: list[Any]
) -> str | None:
    if not model_ids:
        return None
    uids: list[UUID] = []
    for m in model_ids:
        with contextlib.suppress(ValueError, TypeError):
            uids.append(UUID(str(m)))
    if not uids:
        return None
    stmt = select(SpecialEquipmentModel.id, SpecialEquipmentModel.name).where(
        SpecialEquipmentModel.id.in_(uids)
    )
    rows = (await session.execute(stmt)).all()
    by_id = {row.id: (row.name or str(row.id)) for row in rows}
    names = [by_id.get(uid, str(uid)) for uid in uids]
    return ", ".join(names) if names else None


@timed_repository
async def _list_mark_ids(session: AsyncSession, program_id: UUID) -> list[str]:
    stmt = (
        select(SupportProgramMark.mark_id)
        .where(SupportProgramMark.support_program_id == program_id)
        .order_by(SupportProgramMark.mark_id)
    )
    result = await session.execute(stmt)
    return [str(row[0]) for row in result.all()]


@timed_repository
async def _list_distributor_ids(session: AsyncSession, program_id: UUID) -> list[UUID]:
    stmt = (
        select(SupportProgramDistributor.distributor_id)
        .where(SupportProgramDistributor.support_program_id == program_id)
        .order_by(SupportProgramDistributor.distributor_id)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def _list_distributor_details_by_ids(
    session: AsyncSession, distributor_ids: list[UUID]
) -> list[dict[str, Any]]:
    if not distributor_ids:
        return []
    stmt = (
        select(Company.id, Company.name)
        .where(
            Company.id.in_(distributor_ids),
            Company.company_type == "distributor",
        )
        .order_by(func.coalesce(Company.name, "").asc(), Company.id)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "company_id": row.id,
            "name": row.name or str(row.id),
        }
        for row in rows
    ]


@timed_repository
async def _list_distributor_details(
    session: AsyncSession, program_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(Company.id, Company.name)
        .join(
            SupportProgramDistributor,
            SupportProgramDistributor.distributor_id == Company.id,
        )
        .where(SupportProgramDistributor.support_program_id == program_id)
        .order_by(func.coalesce(Company.name, "").asc(), Company.id)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "company_id": row.id,
            "name": row.name or str(row.id),
        }
        for row in rows
    ]


@timed_repository
async def _list_leasing_company_ids(
    session: AsyncSession, program_id: UUID
) -> list[UUID]:
    stmt = (
        select(SupportProgramLeasingCompany.leasing_company_id)
        .where(SupportProgramLeasingCompany.support_program_id == program_id)
        .order_by(SupportProgramLeasingCompany.leasing_company_id)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


@timed_repository
async def _list_leasing_company_details(
    session: AsyncSession, program_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(LeasingCompany.id, LeasingCompany.company_id, Company.name)
        .join(
            SupportProgramLeasingCompany,
            SupportProgramLeasingCompany.leasing_company_id == LeasingCompany.id,
        )
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .where(SupportProgramLeasingCompany.support_program_id == program_id)
        .order_by(func.coalesce(Company.name, "").asc(), LeasingCompany.id)
    )
    result = await session.execute(stmt)
    return [
        {
            "id": row.id,
            "company_id": row.company_id,
            "name": row.name or str(row.id),
        }
        for row in result.all()
    ]


@timed_repository
async def _list_dealer_group_ids(session: AsyncSession, program_id: UUID) -> list[UUID]:
    stmt = (
        select(SupportProgramDealerGroup.dealer_group_id)
        .where(SupportProgramDealerGroup.support_program_id == program_id)
        .order_by(SupportProgramDealerGroup.dealer_group_id)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


@timed_repository
async def _list_dealer_group_details(
    session: AsyncSession, program_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(DealerGroup.id, DealerGroup.name)
        .join(
            SupportProgramDealerGroup,
            SupportProgramDealerGroup.dealer_group_id == DealerGroup.id,
        )
        .where(SupportProgramDealerGroup.support_program_id == program_id)
        .order_by(DealerGroup.name)
    )
    result = await session.execute(stmt)
    return [{"id": row.id, "name": row.name} for row in result.all()]


@timed_repository
async def _list_bill_of_lading(
    session: AsyncSession, program_id: UUID
) -> dict[str, Any]:
    stmt = (
        select(SupportBillOfLading)
        .where(SupportBillOfLading.support_program_id == program_id)
        .order_by(SupportBillOfLading.created_at)
    )
    rows = (await session.execute(stmt)).scalars().all()
    files = [
        {
            "id": r.id,
            "bill_date": r.bill_date,
            "file_name": r.file_name,
            "file_path": r.file_path,
            "file_size": r.file_size,
            "comment": r.comment,
        }
        for r in rows
    ]
    comment = next((f["comment"] for f in reversed(files) if f["comment"]), None)
    return {"comment": comment, "files": files}


@timed_repository
async def list_compatible_support_ids(
    session: AsyncSession, program_id: UUID
) -> list[UUID]:
    stmt = select(
        SupportProgramCompatibility.support_program_id,
        SupportProgramCompatibility.compatible_support_program_id,
    ).where(
        or_(
            SupportProgramCompatibility.support_program_id == program_id,
            SupportProgramCompatibility.compatible_support_program_id == program_id,
        )
    )
    rows = (await session.execute(stmt)).all()
    neighbors = {
        right_id if left_id == program_id else left_id
        for left_id, right_id in rows
    }
    return sorted(neighbors, key=str)


@timed_repository
async def get_program_compatibility_flags(
    session: AsyncSession, program_ids: list[UUID]
) -> dict[UUID, bool]:
    unique_ids = list(dict.fromkeys(program_ids))
    if not unique_ids:
        return {}
    stmt = select(SupportProgram.id, SupportProgram.is_compatible).where(
        SupportProgram.id.in_(unique_ids)
    )
    rows = (await session.execute(stmt)).all()
    return {program_id: bool(is_compatible) for program_id, is_compatible in rows}


@timed_repository
async def enable_program_compatibility(
    session: AsyncSession, program_ids: list[UUID]
) -> None:
    unique_ids = list(dict.fromkeys(program_ids))
    if not unique_ids:
        return
    await session.execute(
        update(SupportProgram)
        .where(SupportProgram.id.in_(unique_ids))
        .values(is_compatible=True, updated_at=datetime.now(UTC))
    )
    await session.flush()


@timed_repository
async def get_compatibility_by_program_ids(
    session: AsyncSession, program_ids: list[UUID]
) -> dict[UUID, set[UUID]]:
    """Return symmetric adjacency for every existing requested program."""
    flags = await get_program_compatibility_flags(session, program_ids)
    result: dict[UUID, set[UUID]] = {program_id: set() for program_id in flags}
    if not result:
        return result
    requested_ids = list(result)
    stmt = select(
        SupportProgramCompatibility.support_program_id,
        SupportProgramCompatibility.compatible_support_program_id,
    ).where(
        or_(
            SupportProgramCompatibility.support_program_id.in_(requested_ids),
            SupportProgramCompatibility.compatible_support_program_id.in_(
                requested_ids
            ),
        )
    )
    rows = (await session.execute(stmt)).all()
    for left_id, right_id in rows:
        if left_id in result:
            result[left_id].add(right_id)
        if right_id in result:
            result[right_id].add(left_id)
    return result


@timed_repository
async def replace_compatible_supports(
    session: AsyncSession,
    program_id: UUID,
    compatible_support_ids: list[UUID],
) -> None:
    await session.execute(
        delete(SupportProgramCompatibility).where(
            or_(
                SupportProgramCompatibility.support_program_id == program_id,
                SupportProgramCompatibility.compatible_support_program_id == program_id,
            )
        )
    )
    for compatible_program_id in set(compatible_support_ids):
        left_id, right_id = sorted((program_id, compatible_program_id))
        session.add(
            SupportProgramCompatibility(
                support_program_id=left_id,
                compatible_support_program_id=right_id,
            )
        )
    await session.flush()


@timed_repository
async def get_program_by_id(
    session: AsyncSession,
    program_id: UUID,
    *,
    visible_distributor_id: UUID | None = None,
    restrict_to_distributor: bool = False,
) -> dict[str, Any] | None:
    conditions: list[Any] = [SupportProgram.id == program_id]
    if restrict_to_distributor:
        if visible_distributor_id is None:
            return None
        distributor_match = (
            select(SupportProgramDistributor.support_program_id)
            .where(
                SupportProgramDistributor.support_program_id == SupportProgram.id,
                SupportProgramDistributor.distributor_id == visible_distributor_id,
            )
            .exists()
        )
        conditions.append(
            or_(SupportProgram.distributor_id == visible_distributor_id, distributor_match)
        )
    row = (await session.execute(select(SupportProgram).where(*conditions))).scalar_one_or_none()
    if row is None:
        return None
    return await _attach_relations(session, _row_to_base_dict(row))


def _mark_filter_condition(mark_id: Any) -> ColumnElement[bool] | None:
    if not mark_id:
        return None
    with contextlib.suppress(ValueError, TypeError):
        m_uid = UUID(str(mark_id))
        mark_match = (
            select(SupportProgramMark.support_program_id)
            .where(
                SupportProgramMark.support_program_id == SupportProgram.id,
                SupportProgramMark.mark_id == m_uid,
            )
            .exists()
        )
        return or_(SupportProgram.mark_id == m_uid, mark_match)
    return None


def _model_filter_condition(model_id: Any) -> ColumnElement[bool] | None:
    if not model_id:
        return None
    with contextlib.suppress(ValueError, TypeError):
        mo_uid = UUID(str(model_id))
        return or_(
            SupportProgram.model_id == mo_uid,
            SupportProgram.model_ids.contains([mo_uid]),
        )
    return None


@timed_repository
async def list_programs(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    mark_id: str | None = None,
    model_id: str | None = None,
    dealer_group_id: UUID | None = None,
    distributor_id: UUID | None = None,
    is_active: bool | None = None,
    visible_distributor_id: UUID | None = None,
    restrict_to_distributor: bool = False,
    visible_dealer_company_id: UUID | None = None,
    visible_leasing_company_id: UUID | None = None,
) -> tuple[list[dict[str, Any]], int]:
    conditions: list[Any] = []
    if restrict_to_distributor:
        if visible_distributor_id is None:
            return [], 0
        visible_distributor_match = (
            select(SupportProgramDistributor.support_program_id)
            .where(
                SupportProgramDistributor.support_program_id == SupportProgram.id,
                SupportProgramDistributor.distributor_id == visible_distributor_id,
            )
            .exists()
        )
        conditions.append(
            or_(
                SupportProgram.distributor_id == visible_distributor_id,
                visible_distributor_match,
            )
        )
    if visible_dealer_company_id is not None:
        selected_dealer_group = (
            select(SupportProgramDealerGroup.support_program_id)
            .where(
                SupportProgramDealerGroup.support_program_id == SupportProgram.id,
            )
            .exists()
        )
        dealer_group_match = (
            select(SupportProgramDealerGroup.support_program_id)
            .join(
                DealerGroupMember,
                DealerGroupMember.dealer_group_id
                == SupportProgramDealerGroup.dealer_group_id,
            )
            .where(
                SupportProgramDealerGroup.support_program_id == SupportProgram.id,
                DealerGroupMember.dealer_company_id == visible_dealer_company_id,
            )
            .exists()
        )
        legacy_dealer_group_match = (
            select(DealerGroupMember.id)
            .where(
                DealerGroupMember.dealer_group_id == SupportProgram.dealer_group_id,
                DealerGroupMember.dealer_company_id == visible_dealer_company_id,
            )
            .exists()
        )
        linked_distributor_ids = (
            select(DistributorDealerLink.distributor_company_id)
            .where(DistributorDealerLink.dealer_company_id == visible_dealer_company_id)
            .union(
                select(DealerGroup.distributor_company_id)
                .join(DealerGroupMember, DealerGroupMember.dealer_group_id == DealerGroup.id)
                .where(
                    DealerGroupMember.dealer_company_id == visible_dealer_company_id,
                    DealerGroup.is_active.is_(True),
                )
            )
        )
        distributor_relation_match = (
            select(SupportProgramDistributor.support_program_id)
            .where(
                SupportProgramDistributor.support_program_id == SupportProgram.id,
                SupportProgramDistributor.distributor_id.in_(linked_distributor_ids),
            )
            .exists()
        )
        distributor_match = or_(
            SupportProgram.distributor_id.in_(linked_distributor_ids),
            distributor_relation_match,
        )
        no_selected_dealer_groups = and_(
            ~selected_dealer_group,
            SupportProgram.dealer_group_id.is_(None),
        )
        conditions.append(
            or_(
                dealer_group_match,
                legacy_dealer_group_match,
                and_(no_selected_dealer_groups, distributor_match),
            )
        )
    if visible_leasing_company_id is not None:
        selected_leasing_company = (
            select(SupportProgramLeasingCompany.support_program_id)
            .where(
                SupportProgramLeasingCompany.support_program_id == SupportProgram.id,
            )
            .exists()
        )
        leasing_company_match = (
            select(SupportProgramLeasingCompany.support_program_id)
            .where(
                SupportProgramLeasingCompany.support_program_id == SupportProgram.id,
                SupportProgramLeasingCompany.leasing_company_id
                == visible_leasing_company_id,
            )
            .exists()
        )
        conditions.append(
            or_(leasing_company_match, ~selected_leasing_company)
        )
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                SupportProgram.name.ilike(pattern),
                func.coalesce(SupportProgram.vin, "").ilike(pattern),
            )
        )
    if (mark_cond := _mark_filter_condition(mark_id)) is not None:
        conditions.append(mark_cond)
    if (model_cond := _model_filter_condition(model_id)) is not None:
        conditions.append(model_cond)
    if dealer_group_id is not None:
        dealer_group_match = (
            select(SupportProgramDealerGroup.support_program_id)
            .where(
                SupportProgramDealerGroup.support_program_id == SupportProgram.id,
                SupportProgramDealerGroup.dealer_group_id == dealer_group_id,
            )
            .exists()
        )
        conditions.append(dealer_group_match)
    if distributor_id is not None:
        distributor_match = (
            select(SupportProgramDistributor.support_program_id)
            .where(
                SupportProgramDistributor.support_program_id == SupportProgram.id,
                SupportProgramDistributor.distributor_id == distributor_id,
            )
            .exists()
        )
        conditions.append(
            or_(SupportProgram.distributor_id == distributor_id, distributor_match)
        )
    if is_active is not None:
        conditions.append(SupportProgram.is_active.is_(is_active))

    where_clause = and_(*conditions) if conditions else None

    count_stmt = select(func.count(SupportProgram.id))
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = (await session.execute(count_stmt)).scalar() or 0

    list_stmt = select(SupportProgram).order_by(SupportProgram.created_at.desc())
    if where_clause is not None:
        list_stmt = list_stmt.where(where_clause)
    list_stmt = list_stmt.offset((page - 1) * limit).limit(limit)

    rows = (await session.execute(list_stmt)).scalars().all()
    items: list[dict[str, Any]] = [
        await _attach_relations(session, _row_to_base_dict(row)) for row in rows
    ]

    return items, int(total)


@timed_repository
async def create_program(session: AsyncSession, data: dict[str, Any]) -> UUID:
    row = SupportProgram(
        name=data["name"],
        mark_id=data["mark_id"],
        model_id=data.get("model_id"),
        model_ids=data.get("model_ids"),
        complectation_ids=data.get("complectation_ids"),
        vin=data.get("vin"),
        vins=data.get("vins"),
        dealer_group_id=data.get("dealer_group_id"),
        distributor_id=data.get("distributor_id"),
        support_type=data["support_type"],
        support_params=data.get("support_params") or {},
        production_year_from=data.get("production_year_from"),
        production_year_to=data.get("production_year_to"),
        production_date_from=data.get("production_date_from"),
        production_date_to=data.get("production_date_to"),
        delivery_date_from=data.get("delivery_date_from"),
        delivery_date_to=data.get("delivery_date_to"),
        starts_at=data.get("starts_at"),
        ends_at=data.get("ends_at"),
        is_active=data.get("is_active", False),
        is_compatible=data.get("is_compatible", False),
        show_to_leasing_company=data.get("show_to_leasing_company", True),
        show_to_client=data.get("show_to_client", True),
        comment=data.get("comment"),
        created_by=data.get("created_by"),
    )
    session.add(row)
    await session.flush()
    return row.id


@timed_repository
async def update_program(
    session: AsyncSession, program_id: UUID, data: dict[str, Any]
) -> bool:
    row = await session.get(SupportProgram, program_id)
    if row is None:
        return False
    updatable = {
        "name",
        "mark_id",
        "model_id",
        "model_ids",
        "complectation_ids",
        "vin",
        "vins",
        "dealer_group_id",
        "distributor_id",
        "support_type",
        "support_params",
        "production_year_from",
        "production_year_to",
        "production_date_from",
        "production_date_to",
        "delivery_date_from",
        "delivery_date_to",
        "starts_at",
        "ends_at",
        "is_active",
        "is_compatible",
        "show_to_leasing_company",
        "show_to_client",
        "comment",
    }
    for key, value in data.items():
        if key in updatable:
            setattr(row, key, value)
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True


@timed_repository
async def set_program_active(
    session: AsyncSession, program_id: UUID, is_active: bool
) -> bool:
    row = await session.get(SupportProgram, program_id)
    if row is None:
        return False
    row.is_active = is_active
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True


@timed_repository
async def delete_program(session: AsyncSession, program_id: UUID) -> bool:
    row = await session.get(SupportProgram, program_id)
    if row is None:
        return False
    await session.execute(
        delete(SupportProgramCompatibility).where(
            or_(
                SupportProgramCompatibility.support_program_id == program_id,
                SupportProgramCompatibility.compatible_support_program_id == program_id,
            )
        )
    )
    await session.execute(
        delete(SupportBillOfLading).where(
            SupportBillOfLading.support_program_id == program_id
        )
    )
    await session.execute(
        delete(SupportProgramDealerGroup).where(
            SupportProgramDealerGroup.support_program_id == program_id
        )
    )
    await session.execute(
        delete(SupportProgramMark).where(
            SupportProgramMark.support_program_id == program_id
        )
    )
    await session.execute(
        delete(SupportProgramDistributor).where(
            SupportProgramDistributor.support_program_id == program_id
        )
    )
    await session.execute(
        delete(SupportProgramLeasingCompany).where(
            SupportProgramLeasingCompany.support_program_id == program_id
        )
    )
    await session.delete(row)
    await session.flush()
    return True


@timed_repository
async def replace_leasing_companies(
    session: AsyncSession, program_id: UUID, leasing_company_ids: list[UUID]
) -> None:
    await session.execute(
        delete(SupportProgramLeasingCompany).where(
            SupportProgramLeasingCompany.support_program_id == program_id
        )
    )
    for lc_id in leasing_company_ids:
        session.add(
            SupportProgramLeasingCompany(
                support_program_id=program_id,
                leasing_company_id=lc_id,
            )
        )
    await session.flush()


@timed_repository
async def replace_marks(
    session: AsyncSession, program_id: UUID, mark_ids: list[Any]
) -> None:
    await session.execute(
        delete(SupportProgramMark).where(
            SupportProgramMark.support_program_id == program_id
        )
    )
    for mark_id in mark_ids:
        try:
            uid = UUID(str(mark_id))
        except (ValueError, TypeError):
            continue
        session.add(
            SupportProgramMark(
                support_program_id=program_id,
                mark_id=uid,
            )
        )
    await session.flush()


@timed_repository
async def replace_distributors(
    session: AsyncSession, program_id: UUID, distributor_ids: list[UUID]
) -> None:
    await session.execute(
        delete(SupportProgramDistributor).where(
            SupportProgramDistributor.support_program_id == program_id
        )
    )
    for distributor_id in distributor_ids:
        session.add(
            SupportProgramDistributor(
                support_program_id=program_id,
                distributor_id=distributor_id,
            )
        )
    await session.flush()


@timed_repository
async def replace_dealer_groups(
    session: AsyncSession, program_id: UUID, dealer_group_ids: list[UUID]
) -> None:
    await session.execute(
        delete(SupportProgramDealerGroup).where(
            SupportProgramDealerGroup.support_program_id == program_id
        )
    )
    for dg_id in dealer_group_ids:
        session.add(
            SupportProgramDealerGroup(
                support_program_id=program_id,
                dealer_group_id=dg_id,
            )
        )
    await session.flush()


@timed_repository
async def list_leasing_companies_for_program(
    session: AsyncSession, program_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(LeasingCompany.id, LeasingCompany.company_id)
        .join(
            SupportProgramLeasingCompany,
            SupportProgramLeasingCompany.leasing_company_id == LeasingCompany.id,
        )
        .where(SupportProgramLeasingCompany.support_program_id == program_id)
        .order_by(LeasingCompany.id)
    )
    result = await session.execute(stmt)
    return [{"id": row.id, "company_id": row.company_id} for row in result.all()]


@timed_repository
async def get_existing_leasing_company_ids(
    session: AsyncSession, leasing_company_ids: list[UUID]
) -> set[UUID]:
    if not leasing_company_ids:
        return set()
    stmt = select(LeasingCompany.id).where(LeasingCompany.id.in_(leasing_company_ids))
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


@timed_repository
async def get_program_ids_for_leasing_company(
    session: AsyncSession,
    leasing_company_id: UUID,
    program_ids: list[UUID],
) -> set[UUID]:
    """Return programs explicitly assigned to the leasing company."""
    unique_program_ids = list(dict.fromkeys(program_ids))
    if not unique_program_ids:
        return set()
    stmt = select(SupportProgramLeasingCompany.support_program_id).where(
        SupportProgramLeasingCompany.leasing_company_id == leasing_company_id,
        SupportProgramLeasingCompany.support_program_id.in_(unique_program_ids),
    )
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


@timed_repository
async def distributor_exists(session: AsyncSession, distributor_id: UUID) -> bool:
    stmt = select(Company.id).where(
        Company.id == distributor_id,
        Company.company_type == "distributor",
    )
    result = await session.execute(stmt)
    return result.first() is not None


@timed_repository
async def get_existing_distributor_ids(
    session: AsyncSession, distributor_ids: list[UUID]
) -> set[UUID]:
    if not distributor_ids:
        return set()
    stmt = select(Company.id).where(
        Company.id.in_(distributor_ids),
        Company.company_type == "distributor",
    )
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


@timed_repository
async def insert_bill_of_lading(
    session: AsyncSession,
    *,
    program_id: UUID,
    bill_date: date | None,
    file_name: str | None,
    file_path: str | None,
    file_size: int | None,
    comment: str | None,
) -> dict[str, Any]:
    row = SupportBillOfLading(
        support_program_id=program_id,
        bill_date=bill_date,
        file_name=file_name,
        file_path=file_path,
        file_size=file_size,
        comment=comment,
    )
    session.add(row)
    await session.flush()
    return {
        "id": row.id,
        "support_program_id": row.support_program_id,
        "bill_date": row.bill_date,
        "file_name": row.file_name,
        "file_path": row.file_path,
        "file_size": row.file_size,
        "comment": row.comment,
    }


@timed_repository
async def get_bill_of_lading(
    session: AsyncSession, file_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(SupportBillOfLading, file_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "support_program_id": row.support_program_id,
        "bill_date": row.bill_date,
        "file_name": row.file_name,
        "file_path": row.file_path,
        "file_size": row.file_size,
        "comment": row.comment,
    }


@timed_repository
async def delete_bill_of_lading(
    session: AsyncSession, program_id: UUID, file_id: UUID
) -> bool:
    row = await session.get(SupportBillOfLading, file_id)
    if row is None or row.support_program_id != program_id:
        return False
    await session.delete(row)
    await session.flush()
    return True
