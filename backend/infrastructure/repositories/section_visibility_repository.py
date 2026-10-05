"""Persistence for explicit section visibility overrides."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TypedDict

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.section_visibility import SectionVisibility
from infrastructure.repository_timing import timed_repository


class SectionVisibilityOverride(TypedDict):
    scope: str
    storefront_id: uuid.UUID | None
    section_key: str
    is_visible: bool


def _to_dict(row: SectionVisibility) -> SectionVisibilityOverride:
    return SectionVisibilityOverride(
        scope=row.scope,
        storefront_id=row.storefront_id,
        section_key=row.section_key,
        is_visible=row.is_visible,
    )


@timed_repository
async def list_visibility_overrides(
    session: AsyncSession,
    scopes: Sequence[str],
    *,
    storefront_id: uuid.UUID | None = None,
) -> list[SectionVisibilityOverride]:
    """Return stored overrides for the requested scopes."""
    if not scopes:
        return []
    result = await session.execute(
        select(SectionVisibility)
        .where(
            SectionVisibility.scope.in_(scopes),
            SectionVisibility.storefront_id == storefront_id,
        )
        .order_by(SectionVisibility.scope, SectionVisibility.section_key)
    )
    return [_to_dict(row) for row in result.scalars().all()]


@timed_repository
async def upsert_visibility_overrides(
    session: AsyncSession,
    scope: str,
    updates: dict[str, bool],
    updated_by: uuid.UUID,
    *,
    storefront_id: uuid.UUID | None = None,
) -> None:
    """Persist a partial batch without committing the caller's transaction."""
    if not updates:
        return

    values = [
        {
            "id": uuid.uuid4(),
            "scope": scope,
            "storefront_id": storefront_id,
            "section_key": section_key,
            "is_visible": is_visible,
            "updated_by": updated_by,
        }
        for section_key, is_visible in updates.items()
    ]
    insert_stmt = pg_insert(SectionVisibility).values(values)
    if storefront_id is not None:
        index_elements = [
            SectionVisibility.storefront_id,
            SectionVisibility.scope,
            SectionVisibility.section_key,
        ]
        index_where = sa.text(
            "scope IN ('public', 'leasing_company', 'dealer', 'distributor') "
            "AND storefront_id IS NOT NULL"
        )
    else:
        index_elements = [SectionVisibility.scope, SectionVisibility.section_key]
        index_where = sa.text(
            "scope = 'carcraft_employee' AND storefront_id IS NULL"
        )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=index_elements,
        index_where=index_where,
        set_={
            "is_visible": insert_stmt.excluded.is_visible,
            "updated_by": insert_stmt.excluded.updated_by,
            "updated_at": func.current_timestamp(),
        },
    )
    await session.execute(upsert_stmt)
