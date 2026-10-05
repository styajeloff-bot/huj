"""Coherent snapshots and locking for a whole storefront settings package."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from domain.section_visibility import STOREFRONT_SECTION_VISIBILITY_SCOPES
from infrastructure.models.section_visibility import SectionVisibility
from infrastructure.models.storefronts import StorefrontFont
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories.section_visibility_repository import (
    upsert_visibility_overrides,
)


async def read_transfer_state(
    session: AsyncSession, slugs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """One statement: settings, visibility, preserved bindings/font and revisions.

    Role visibility writers do not bump storefront.version. Include their
    actual rows and timestamps instead of relying on that counter alone.
    Warehouse status is derived from is_active.
    """
    rows = await session.execute(sa.text("""
        SELECT s.*,
            COALESCE((SELECT jsonb_agg(to_jsonb(v) ORDER BY v.scope, v.section_key)
                FROM section_visibility v WHERE v.storefront_id = s.id), '[]'::jsonb) AS visibility,
            COALESCE((SELECT jsonb_agg(jsonb_build_object(
                                      'id', w.id,
                                      'status', CASE WHEN w.is_active THEN 'active' ELSE 'inactive' END
                                  )
                                  ORDER BY w.id)
                FROM catalog_storefront_warehouses sw JOIN warehouses w ON w.id = sw.warehouse_id
                WHERE sw.storefront_id = s.id), '[]'::jsonb) AS warehouse_state,
            (SELECT to_jsonb(f) FROM catalog_storefront_fonts f WHERE f.id = s.font_id) AS font_state
        FROM catalog_storefronts s
        WHERE CAST(:slugs AS text[]) IS NULL OR COALESCE(s.slug, '/') = ANY(CAST(:slugs AS text[]))
        ORDER BY COALESCE(s.slug, '/') COLLATE "C"
    """), {"slugs": slugs})
    return [dict(row) for row in rows.mappings()]


async def lock_transfer_state(session: AsyncSession, state: list[dict[str, Any]]) -> None:
    """Finish staging before entering this short, DB-only critical section.

    Lock referenced fonts/warehouses first, matching delete-and-reset/cascade
    paths. KEY SHARE/SHARE remains compatible with normal FK checks. EXCLUSIVE
    on storefronts also conflicts with manual SELECT FOR UPDATE (ROW SHARE),
    preventing the row-lock/table-lock upgrade deadlock that SHARE ROW EXCLUSIVE
    would permit. Visibility and binding tables prevent inserts/updates by
    writers that do not participate in a storefront advisory-lock protocol.
    """
    font_ids = sorted({row["font_id"] for row in state if row["font_id"] is not None})
    warehouse_ids = sorted({UUID(w["id"]) for row in state for w in row["warehouse_state"]})
    if font_ids:
        await session.execute(sa.select(StorefrontFont.id).where(StorefrontFont.id.in_(font_ids))
                              .order_by(StorefrontFont.id).with_for_update(read=True, key_share=True))
    if warehouse_ids:
        await session.execute(sa.select(Warehouse.id).where(Warehouse.id.in_(warehouse_ids))
                              .order_by(Warehouse.id).with_for_update(read=True))
    await session.execute(sa.text("LOCK TABLE catalog_storefronts IN EXCLUSIVE MODE"))
    await session.execute(sa.text("LOCK TABLE catalog_storefront_warehouses IN EXCLUSIVE MODE"))
    await session.execute(sa.text("LOCK TABLE section_visibility IN EXCLUSIVE MODE"))


async def replace_transfer_visibility(
    session: AsyncSession, storefront_id: UUID,
    visibility: dict[str, dict[str, bool]], actor_id: UUID,
) -> None:
    await session.execute(sa.delete(SectionVisibility).where(
        SectionVisibility.storefront_id == storefront_id,
        SectionVisibility.scope.in_(STOREFRONT_SECTION_VISIBILITY_SCOPES),
    ))
    for scope, overrides in visibility.items():
        await upsert_visibility_overrides(session, scope, overrides, actor_id, storefront_id=storefront_id)
