"""Persistence operations for catalog storefronts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import (
    PUBLIC_PAGE_KEYS,
    PublicUIConfig,
    StorefrontAppearanceConfig,
    validate_public_ui_config,
    validate_storefront_appearance,
)
from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
from infrastructure.models.vehicles import Warehouse
from infrastructure.repository_timing import timed_repository


class StorefrontRecord(TypedDict):
    id: UUID
    slug: str | None
    is_default: bool
    is_active: bool
    version: int
    logo_storage_key: str | None
    logo_content_type: str | None
    contact_email: str | None
    contact_phone: str | None
    public_ui: PublicUIConfig
    public_ui_updated_by: UUID | None
    public_ui_updated_at: datetime
    appearance: StorefrontAppearanceConfig
    warehouse_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


async def _to_record(session: AsyncSession, row: Storefront) -> StorefrontRecord:
    warehouse_ids = list(
        (
            await session.execute(
                select(StorefrontWarehouse.warehouse_id)
                .where(StorefrontWarehouse.storefront_id == row.id)
                .order_by(StorefrontWarehouse.warehouse_id)
            )
        ).scalars()
    )
    public_ui = validate_public_ui_config(
        row.home_page_key,
        {
            key: {"title": row.public_page_titles[key]}
            for key in PUBLIC_PAGE_KEYS
        },
    )
    appearance = validate_storefront_appearance(
        {
            "primary": row.appearance_primary_color,
            "background": row.appearance_background_color,
            "surface": row.appearance_surface_color,
            "text": row.appearance_text_color,
        },
        row.appearance_border_radius,
        row.font_id,
        row.appearance_color_overrides,
    )
    return StorefrontRecord(
        id=row.id,
        slug=row.slug,
        is_default=row.is_default,
        is_active=row.is_active,
        version=row.version,
        logo_storage_key=row.logo_storage_key,
        logo_content_type=row.logo_content_type,
        contact_email=row.contact_email,
        contact_phone=row.contact_phone,
        public_ui=public_ui,
        public_ui_updated_by=row.public_ui_updated_by,
        public_ui_updated_at=row.public_ui_updated_at,
        appearance=appearance,
        warehouse_ids=warehouse_ids,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@timed_repository
async def get_storefront_by_id(
    session: AsyncSession, storefront_id: UUID
) -> StorefrontRecord | None:
    row = await session.get(Storefront, storefront_id)
    return await _to_record(session, row) if row is not None else None


@timed_repository
async def lock_storefront_by_id(
    session: AsyncSession, storefront_id: UUID
) -> StorefrontRecord | None:
    row = (
        await session.execute(
            select(Storefront)
            .where(Storefront.id == storefront_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    return await _to_record(session, row) if row is not None else None


@timed_repository
async def get_storefront_by_slug(
    session: AsyncSession, slug: str, *, active_only: bool = False
) -> StorefrontRecord | None:
    query = select(Storefront).where(sa.func.lower(Storefront.slug) == slug)
    if active_only:
        query = query.where(Storefront.is_active.is_(True))
    row = (await session.execute(query)).scalar_one_or_none()
    return await _to_record(session, row) if row is not None else None


@timed_repository
async def get_default_storefront(
    session: AsyncSession, *, active_only: bool = False
) -> StorefrontRecord | None:
    query = select(Storefront).where(Storefront.is_default.is_(True))
    if active_only:
        query = query.where(Storefront.is_active.is_(True))
    row = (await session.execute(query)).scalar_one_or_none()
    return await _to_record(session, row) if row is not None else None


@timed_repository
async def list_storefronts(session: AsyncSession) -> list[StorefrontRecord]:
    rows = (
        await session.execute(
            select(Storefront).order_by(Storefront.is_default.desc(), Storefront.slug)
        )
    ).scalars()
    return [await _to_record(session, row) for row in rows]


@timed_repository
async def count_active_warehouses(
    session: AsyncSession, warehouse_ids: Sequence[UUID]
) -> int:
    if not warehouse_ids:
        return 0
    return int(
        (
            await session.execute(
                select(sa.func.count(Warehouse.id)).where(
                    Warehouse.id.in_(warehouse_ids), Warehouse.status == "active"
                )
            )
        ).scalar_one()
    )


@timed_repository
async def create_storefront(
    session: AsyncSession,
    *,
    slug: str,
    warehouse_ids: Sequence[UUID],
    created_by: UUID,
    is_active: bool,
    contact_email: str | None,
    contact_phone: str | None,
    public_ui: PublicUIConfig,
    appearance: StorefrontAppearanceConfig,
) -> StorefrontRecord:
    row = Storefront(
        id=uuid4(),
        slug=slug,
        is_default=False,
        is_active=is_active,
        version=1,
        created_by=created_by,
        contact_email=contact_email,
        contact_phone=contact_phone,
        home_page_key=public_ui["home_page_key"],
        public_page_titles={
            key: page["title"] for key, page in public_ui["pages"].items()
        },
        public_ui_updated_by=created_by,
        appearance_primary_color=appearance["colors"]["primary"],
        appearance_background_color=appearance["colors"]["background"],
        appearance_surface_color=appearance["colors"]["surface"],
        appearance_text_color=appearance["colors"]["text"],
        appearance_border_radius=appearance["border_radius"],
        font_id=appearance["font_id"],
        appearance_color_overrides=dict(appearance["color_overrides"]),
    )
    session.add(row)
    await session.flush()
    session.add_all(
        StorefrontWarehouse(storefront_id=row.id, warehouse_id=warehouse_id)
        for warehouse_id in sorted(set(warehouse_ids))
    )
    await session.flush()
    return await _to_record(session, row)


@timed_repository
async def update_storefront(
    session: AsyncSession,
    storefront_id: UUID,
    *,
    slug: str | None = None,
    is_active: bool | None = None,
    warehouse_ids: Sequence[UUID] | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    update_contact_email: bool = False,
    update_contact_phone: bool = False,
    public_ui: PublicUIConfig | None = None,
    public_ui_updated_by: UUID | None = None,
    appearance: StorefrontAppearanceConfig | None = None,
) -> StorefrontRecord | None:
    row = await session.get(Storefront, storefront_id)
    if row is None:
        return None
    if slug is not None:
        row.slug = slug
    if is_active is not None:
        row.is_active = is_active
    if warehouse_ids is not None:
        await session.execute(
            delete(StorefrontWarehouse).where(
                StorefrontWarehouse.storefront_id == storefront_id
            )
        )
        session.add_all(
            StorefrontWarehouse(storefront_id=storefront_id, warehouse_id=warehouse_id)
            for warehouse_id in sorted(set(warehouse_ids))
        )
    if update_contact_email:
        row.contact_email = contact_email
    if update_contact_phone:
        row.contact_phone = contact_phone
    if public_ui is not None:
        row.home_page_key = public_ui["home_page_key"]
        row.public_page_titles = {
            key: page["title"] for key, page in public_ui["pages"].items()
        }
        row.public_ui_updated_by = public_ui_updated_by
        row.public_ui_updated_at = datetime.now(UTC)
    if appearance is not None:
        row.appearance_primary_color = appearance["colors"]["primary"]
        row.appearance_background_color = appearance["colors"]["background"]
        row.appearance_surface_color = appearance["colors"]["surface"]
        row.appearance_text_color = appearance["colors"]["text"]
        row.appearance_border_radius = appearance["border_radius"]
        row.font_id = appearance["font_id"]
        row.appearance_color_overrides = dict(appearance["color_overrides"])
    row.version += 1
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return await _to_record(session, row)


@timed_repository
async def set_storefront_logo(
    session: AsyncSession,
    storefront_id: UUID,
    *,
    storage_key: str,
    content_type: str,
) -> StorefrontRecord | None:
    row = await session.get(Storefront, storefront_id)
    if row is None:
        return None
    row.logo_storage_key = storage_key
    row.logo_content_type = content_type
    row.version += 1
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return await _to_record(session, row)


@timed_repository
async def clear_storefront_logo(
    session: AsyncSession, storefront_id: UUID
) -> StorefrontRecord | None:
    row = await session.get(Storefront, storefront_id)
    if row is None:
        return None
    row.logo_storage_key = None
    row.logo_content_type = None
    row.version += 1
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return await _to_record(session, row)
