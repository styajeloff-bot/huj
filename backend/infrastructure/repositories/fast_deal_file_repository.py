"""Metadata of private fast deal files: one row per addressee, shared storage object.

The bytes live in the private object storage; here are only the keys and the facts the
ACL needs. Every function returns plain dicts and never commits. A row carries
``lc_company_id``: the leasing company that owns the invitation the file is tied to
(offer PDFs and per-position offers), so the ACL does not depend on the invitation
still belonging to the current review cycle.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.fast_deals import FastDealFile, FastDealLcApplication
from infrastructure.repository_timing import timed_repository

Record = dict[str, Any]


def _select_files() -> sa.Select[Any]:
    return sa.select(
        FastDealFile,
        FastDealLcApplication.leasing_company_id.label("lc_company_id"),
    ).outerjoin(
        FastDealLcApplication, FastDealLcApplication.id == FastDealFile.lc_application_id
    )


def _record(row: Any) -> Record:
    file = row.FastDealFile
    values: Record = {column.name: getattr(file, column.name) for column in file.__table__.columns}
    values["lc_company_id"] = row.lc_company_id
    return values


@timed_repository
async def insert_file(session: AsyncSession, values: Record) -> Record:
    """Insert one metadata row; ``lc_company_id`` is filled by the next read."""
    row = FastDealFile(**values)
    session.add(row)
    await session.flush()
    stored = await get_file(session, row.id)
    assert stored is not None
    return stored


@timed_repository
async def get_file(session: AsyncSession, file_id: UUID) -> Record | None:
    result = await session.execute(_select_files().where(FastDealFile.id == file_id))
    row = result.first()
    return _record(row) if row is not None else None


@timed_repository
async def list_files(session: AsyncSession, deal_id: UUID) -> list[Record]:
    """Every file row of the deal, oldest first; the ACL filters them afterwards."""
    result = await session.execute(
        _select_files()
        .where(FastDealFile.fast_deal_id == deal_id)
        .order_by(FastDealFile.created_at, FastDealFile.id)
    )
    return [_record(row) for row in result.all()]


@timed_repository
async def get_files_by_ids(
    session: AsyncSession, deal_id: UUID, file_ids: list[UUID]
) -> list[Record]:
    """Rows of this deal among ``file_ids``; foreign ids are simply absent."""
    if not file_ids:
        return []
    result = await session.execute(
        _select_files().where(
            FastDealFile.fast_deal_id == deal_id, FastDealFile.id.in_(file_ids)
        )
    )
    return [_record(row) for row in result.all()]
