"""Persistence operations for the shared storefront font catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import (
    StorefrontFontContentConflictError,
    StorefrontFontNameConflictError,
)
from infrastructure.models.storefronts import Storefront, StorefrontFont
from infrastructure.repository_timing import timed_repository


class StorefrontFontRecord(TypedDict):
    id: UUID
    name: str
    description: str | None
    original_filename: str
    storage_key: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    storefront_usage_count: int
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


def _to_record(row: StorefrontFont, usage_count: int) -> StorefrontFontRecord:
    return StorefrontFontRecord(
        id=row.id,
        name=row.name,
        description=row.description,
        original_filename=row.original_filename,
        storage_key=row.storage_key,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        checksum_sha256=row.checksum_sha256,
        storefront_usage_count=usage_count,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _constraint_name(exc: IntegrityError) -> str | None:
    original = getattr(exc, "orig", None)
    diagnostic = getattr(original, "diag", None)
    value = getattr(original, "constraint_name", None) or getattr(
        diagnostic, "constraint_name", None
    )
    return str(value) if value is not None else None


async def _usage_count(session: AsyncSession, font_id: UUID) -> int:
    return int(
        await session.scalar(
            select(sa.func.count(Storefront.id)).where(Storefront.font_id == font_id)
        )
        or 0
    )


@timed_repository
async def list_storefront_fonts(session: AsyncSession) -> list[StorefrontFontRecord]:
    rows = (
        await session.execute(
            select(StorefrontFont, sa.func.count(Storefront.id))
            .outerjoin(Storefront, Storefront.font_id == StorefrontFont.id)
            .group_by(StorefrontFont.id)
            .order_by(sa.func.lower(StorefrontFont.name), StorefrontFont.id)
        )
    ).all()
    return [_to_record(row, int(usage_count)) for row, usage_count in rows]


@timed_repository
async def get_storefront_font_by_id(
    session: AsyncSession, font_id: UUID
) -> StorefrontFontRecord | None:
    row = await session.get(StorefrontFont, font_id)
    if row is None:
        return None
    return _to_record(row, await _usage_count(session, font_id))


@timed_repository
async def lock_storefront_font_by_id(
    session: AsyncSession, font_id: UUID
) -> StorefrontFontRecord | None:
    row = (
        await session.execute(
            select(StorefrontFont)
            .where(StorefrontFont.id == font_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return _to_record(row, await _usage_count(session, font_id))


@timed_repository
async def get_storefront_font_by_name(
    session: AsyncSession, name: str
) -> StorefrontFontRecord | None:
    row = (
        await session.execute(
            select(StorefrontFont).where(sa.func.lower(StorefrontFont.name) == name.lower())
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return _to_record(row, await _usage_count(session, row.id))


@timed_repository
async def get_storefront_font_by_checksum(
    session: AsyncSession, checksum_sha256: str
) -> StorefrontFontRecord | None:
    row = (
        await session.execute(
            select(StorefrontFont).where(
                StorefrontFont.checksum_sha256 == checksum_sha256
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return _to_record(row, await _usage_count(session, row.id))


@timed_repository
async def create_storefront_font(
    session: AsyncSession,
    *,
    font_id: UUID,
    name: str,
    description: str | None,
    original_filename: str,
    storage_key: str,
    content_type: str,
    size_bytes: int,
    checksum_sha256: str,
    created_by: UUID,
) -> StorefrontFontRecord:
    row = StorefrontFont(
        id=font_id,
        name=name,
        description=description,
        original_filename=original_filename,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256,
        created_by=created_by,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError as exc:
        constraint = _constraint_name(exc)
        if constraint == "uq_catalog_storefront_fonts_name_lower":
            raise StorefrontFontNameConflictError from exc
        if constraint == "uq_catalog_storefront_fonts_checksum_sha256":
            existing_name = await session.scalar(
                select(StorefrontFont.name).where(
                    StorefrontFont.checksum_sha256 == checksum_sha256
                )
            )
            raise StorefrontFontContentConflictError(
                existing_name or "существующий шрифт"
            ) from exc
        raise
    return _to_record(row, 0)


@timed_repository
async def update_storefront_font(
    session: AsyncSession,
    font_id: UUID,
    *,
    name: str | None,
    description: str | None,
    update_description: bool,
) -> StorefrontFontRecord | None:
    row = await session.get(StorefrontFont, font_id)
    if row is None:
        return None
    try:
        async with session.begin_nested():
            if name is not None:
                row.name = name
            if update_description:
                row.description = description
            row.updated_at = datetime.now(UTC)
            await session.flush()
    except IntegrityError as exc:
        if _constraint_name(exc) == "uq_catalog_storefront_fonts_name_lower":
            raise StorefrontFontNameConflictError from exc
        raise
    return _to_record(row, await _usage_count(session, font_id))


@timed_repository
async def delete_storefront_font_and_reset_usage(
    session: AsyncSession, font_id: UUID
) -> int:
    now = datetime.now(UTC)
    usage_count = await _usage_count(session, font_id)
    await session.execute(
        update(Storefront)
        .where(Storefront.font_id == font_id)
        .values(
            font_id=None,
            version=Storefront.version + 1,
            updated_at=now,
        )
    )
    await session.execute(delete(StorefrontFont).where(StorefrontFont.id == font_id))
    await session.flush()
    return usage_count
