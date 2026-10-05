"""Persistence and reads for immutable company-card audit snapshots."""
from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, DistributorBrand, LeasingCompany
from infrastructure.models.company_change_history import CompanyChangeHistory
from infrastructure.models.contractors import Contractor, LeasingCompanyContractor
from infrastructure.models.special_equipment import SpecialEquipmentMark
from infrastructure.models.users import User
from infrastructure.repository_timing import timed_repository


class HistoryRecordDict(TypedDict):
    id: UUID
    company_id: UUID
    actor_user_id: UUID
    actor_display_name: str
    action: str
    snapshot: dict[str, object]
    changed_at: datetime


_SNAPSHOT_FIELDS = (
    "name", "company_type", "inn", "kpp", "ogrn", "is_active", "phone", "email",
    "website", "legal_address", "actual_address",
)


def _record(row: CompanyChangeHistory) -> HistoryRecordDict:
    return {"id": row.id, "company_id": row.company_id, "actor_user_id": row.actor_user_id,
            "actor_display_name": row.actor_display_name, "action": row.action,
            "snapshot": row.snapshot, "changed_at": row.changed_at}


@timed_repository
async def build_snapshot(session: AsyncSession, company_id: UUID, *, include_brands: bool = False, include_contractors: bool = False) -> dict[str, object]:
    company = await session.get(Company, company_id)
    if company is None:
        raise RuntimeError("Cannot snapshot a missing company")
    snapshot: dict[str, object] = {field: getattr(company, field) for field in _SNAPSHOT_FIELDS}
    if include_brands:
        brand_rows = (await session.execute(
            sa.select(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
            .join(DistributorBrand, DistributorBrand.brand_id == SpecialEquipmentMark.id)
            .where(DistributorBrand.distributor_company_id == company_id, DistributorBrand.is_active.is_(True))
            .order_by(sa.func.lower(SpecialEquipmentMark.name), SpecialEquipmentMark.id)
        )).all()
        snapshot["distributor_brands"] = [{"id": str(row.id), "name": row.name} for row in brand_rows]
    if include_contractors:
        contractor_rows = (await session.execute(
            sa.select(Contractor.id, Contractor.name, Contractor.inn)
            .join(LeasingCompanyContractor, LeasingCompanyContractor.contractor_id == Contractor.id)
            .join(LeasingCompany, LeasingCompany.id == LeasingCompanyContractor.leasing_company_id)
            .where(LeasingCompany.company_id == company_id)
            .order_by(sa.func.lower(Contractor.name), Contractor.id)
        )).all()
        snapshot["leasing_contractors"] = [
            {"id": str(row.id), "name": row.name, "inn": row.inn} for row in contractor_rows
        ]
    return snapshot


@timed_repository
async def write_snapshot(session: AsyncSession, *, company_id: UUID, actor_user_id: UUID, action: str, include_brands: bool = False, include_contractors: bool = False) -> HistoryRecordDict:
    actor_name = (await session.execute(
        sa.select(sa.func.coalesce(User.name, User.email, User.phone)).where(User.id == actor_user_id)
    )).scalar_one_or_none()
    if actor_name is None:
        raise RuntimeError("Audit actor does not exist")
    row = CompanyChangeHistory(company_id=company_id, actor_user_id=actor_user_id,
        actor_display_name=actor_name, action=action,
        snapshot=await build_snapshot(session, company_id, include_brands=include_brands, include_contractors=include_contractors))
    session.add(row)
    await session.flush()
    return _record(row)


def encode_cursor(changed_at: datetime, record_id: UUID) -> str:
    payload = json.dumps([changed_at.astimezone(UTC).isoformat(), str(record_id)]).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        timestamp, identifier = json.loads(raw)
        value = datetime.fromisoformat(timestamp)
        identifier_uuid = UUID(identifier)
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
        raise ValueError("Invalid history cursor") from exc
    if value.tzinfo is None:
        raise ValueError("Invalid history cursor")
    return value, identifier_uuid


@timed_repository
async def company_exists(session: AsyncSession, company_id: UUID) -> bool:
    return (await session.scalar(sa.select(Company.id).where(Company.id == company_id))) is not None


@timed_repository
async def list_history(session: AsyncSession, company_id: UUID, *, limit: int, cursor: tuple[datetime, UUID] | None) -> list[HistoryRecordDict]:
    stmt = sa.select(CompanyChangeHistory).where(CompanyChangeHistory.company_id == company_id)
    if cursor is not None:
        changed_at, record_id = cursor
        stmt = stmt.where(sa.tuple_(CompanyChangeHistory.changed_at, CompanyChangeHistory.id) < (changed_at, record_id))
    rows = (await session.scalars(stmt.order_by(CompanyChangeHistory.changed_at.desc(), CompanyChangeHistory.id.desc()).limit(limit + 1))).all()
    return [_record(row) for row in rows]


@timed_repository
async def get_history_record(session: AsyncSession, company_id: UUID, record_id: UUID) -> HistoryRecordDict | None:
    row = await session.scalar(sa.select(CompanyChangeHistory).where(CompanyChangeHistory.company_id == company_id, CompanyChangeHistory.id == record_id))
    return _record(row) if row is not None else None
