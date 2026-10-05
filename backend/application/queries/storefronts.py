"""Queries for public and administrative storefront context."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TypedDict
from uuid import UUID

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from domain.services.object_storage import ObjectStorage, StoredObject
from domain.storefronts import (
    DEFAULT_STOREFRONT_CONTACT_EMAIL,
    DEFAULT_STOREFRONT_CONTACT_PHONE,
    CatalogScope,
    InvalidStorefrontSlugError,
    PublicUIConfig,
    ReservedStorefrontSlugError,
    StorefrontAppearanceConfig,
    StorefrontLogoNotFoundError,
    StorefrontNotFoundError,
    normalize_storefront_slug,
    storefront_font_family,
    storefront_phone_href,
)
from infrastructure.repositories.storefront_font_repository import (
    get_storefront_font_by_id,
)
from infrastructure.repositories.storefront_repository import (
    StorefrontRecord,
    get_default_storefront,
    get_storefront_by_id,
    get_storefront_by_slug,
    list_storefronts,
)
from infrastructure.services.image_optimizer import validate_storefront_logo_image


@dataclass(frozen=True, slots=True)
class ResolveStorefrontQuery:
    slug: str | None


@dataclass(frozen=True, slots=True)
class GetStorefrontQuery:
    storefront_id: UUID


@dataclass(frozen=True, slots=True)
class ListStorefrontsQuery:
    """Marker query for the administrator list."""


@dataclass(frozen=True, slots=True)
class GetStorefrontLogoQuery:
    storefront_id: UUID


class PublicStorefrontRecord(TypedDict):
    scope: CatalogScope
    logo_storage_key: str | None
    contact_email: str
    contact_phone: str
    contact_phone_href: str
    is_active: bool
    public_ui: PublicUIConfig
    appearance: StorefrontAppearanceConfig
    font_family: str


class AdminStorefrontRecord(StorefrontRecord):
    effective_contact_email: str
    effective_contact_phone: str
    effective_contact_phone_href: str
    has_effective_logo: bool


def _effective_admin_record(
    record: StorefrontRecord, default: StorefrontRecord
) -> AdminStorefrontRecord:
    email = (
        record["contact_email"]
        or default["contact_email"]
        or DEFAULT_STOREFRONT_CONTACT_EMAIL
    )
    phone = (
        record["contact_phone"]
        or default["contact_phone"]
        or DEFAULT_STOREFRONT_CONTACT_PHONE
    )
    return AdminStorefrontRecord(
        **record,
        effective_contact_email=email,
        effective_contact_phone=phone,
        effective_contact_phone_href=storefront_phone_href(phone),
        has_effective_logo=(
            record["logo_storage_key"] is not None
            or default["logo_storage_key"] is not None
        ),
    )


async def handle_resolve_storefront(
    query: ResolveStorefrontQuery, session: AsyncSession
) -> CatalogScope:
    if query.slug is None:
        record = await get_default_storefront(session, active_only=True)
    else:
        try:
            slug = normalize_storefront_slug(query.slug)
        except (InvalidStorefrontSlugError, ReservedStorefrontSlugError) as exc:
            raise StorefrontNotFoundError from exc
        record = await get_storefront_by_slug(session, slug, active_only=True)
    if record is None:
        raise StorefrontNotFoundError
    return CatalogScope(
        id=record["id"],
        slug=record["slug"],
        version=record["version"],
        is_default=record["is_default"],
    )


async def handle_get_public_storefront(
    query: ResolveStorefrontQuery, session: AsyncSession
) -> PublicStorefrontRecord:
    scope = await handle_resolve_storefront(query, session)
    record = await get_storefront_by_id(session, scope.id)
    if record is None:
        raise StorefrontNotFoundError
    default = record if scope.is_default else await get_default_storefront(session)
    if default is None:
        raise StorefrontNotFoundError
    appearance = record["appearance"]
    font_id = appearance["font_id"]
    if font_id is not None and await get_storefront_font_by_id(session, font_id) is None:
        appearance = StorefrontAppearanceConfig(
            colors=appearance["colors"],
            border_radius=appearance["border_radius"],
            font_id=None,
            color_overrides=appearance["color_overrides"],
        )
        font_id = None
    return PublicStorefrontRecord(
        scope=scope,
        logo_storage_key=(record["logo_storage_key"] or default["logo_storage_key"]),
        contact_email=(
            record["contact_email"]
            or default["contact_email"]
            or DEFAULT_STOREFRONT_CONTACT_EMAIL
        ),
        contact_phone=(
            record["contact_phone"]
            or default["contact_phone"]
            or DEFAULT_STOREFRONT_CONTACT_PHONE
        ),
        contact_phone_href=storefront_phone_href(
            record["contact_phone"]
            or default["contact_phone"]
            or DEFAULT_STOREFRONT_CONTACT_PHONE
        ),
        is_active=True,
        public_ui=record["public_ui"],
        appearance=appearance,
        font_family=(storefront_font_family(font_id) if font_id else "Mulish"),
    )


async def handle_get_storefront(
    query: GetStorefrontQuery, session: AsyncSession
) -> AdminStorefrontRecord:
    record = await get_storefront_by_id(session, query.storefront_id)
    if record is None:
        raise StorefrontNotFoundError
    default = record if record["is_default"] else await get_default_storefront(session)
    if default is None:
        raise StorefrontNotFoundError
    return _effective_admin_record(record, default)


async def handle_list_storefronts(
    _query: ListStorefrontsQuery, session: AsyncSession
) -> dict[str, list[AdminStorefrontRecord]]:
    records = await list_storefronts(session)
    default = next((item for item in records if item["is_default"]), None)
    if default is None:
        raise StorefrontNotFoundError
    return {"items": [_effective_admin_record(record, default) for record in records]}


async def handle_get_storefront_logo(
    query: GetStorefrontLogoQuery,
    session: AsyncSession,
    storage: ObjectStorage,
) -> StoredObject:
    record = await get_storefront_by_id(session, query.storefront_id)
    if record is None:
        raise StorefrontLogoNotFoundError
    if record["logo_storage_key"] is None and not record["is_default"]:
        default = await get_default_storefront(session, active_only=True)
        if default is not None:
            record = default
    if record["logo_storage_key"] is None:
        raise StorefrontLogoNotFoundError
    stored = await storage.get(record["logo_storage_key"])
    if stored is None:
        raise StorefrontLogoNotFoundError
    try:
        content_type = await validate_storefront_logo_image(stored.data)
    except (Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        raise StorefrontLogoNotFoundError from exc
    return StoredObject(
        key=stored.key,
        content_type=content_type,
        size=len(stored.data),
        etag=f'"{sha256(stored.data).hexdigest()}"',
        data=stored.data,
    )
