"""Queries for storefront font metadata and immutable public content."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import ObjectStorageUnavailableError
from domain.services.object_storage import ObjectStorage, StoredObject
from domain.storefronts import StorefrontFontNotFoundError
from infrastructure.repositories.storefront_font_repository import (
    StorefrontFontRecord,
    get_storefront_font_by_id,
    list_storefront_fonts,
)

logger = logging.getLogger("carcraft-backend")


@dataclass(frozen=True, slots=True)
class ListStorefrontFontsQuery:
    """Marker query for the administrator font list."""


@dataclass(frozen=True, slots=True)
class GetStorefrontFontContentQuery:
    font_id: UUID


class StorefrontFontContentRecord(TypedDict):
    stored: StoredObject
    checksum_sha256: str


async def handle_list_storefront_fonts(
    _query: ListStorefrontFontsQuery,
    session: AsyncSession,
) -> dict[str, list[StorefrontFontRecord]]:
    return {"items": await list_storefront_fonts(session)}


async def handle_get_storefront_font_content(
    query: GetStorefrontFontContentQuery,
    session: AsyncSession,
    storage: ObjectStorage,
) -> StorefrontFontContentRecord:
    font = await get_storefront_font_by_id(session, query.font_id)
    if font is None:
        raise StorefrontFontNotFoundError
    try:
        stored = await storage.get(font["storage_key"])
    except Exception as exc:
        logger.error(
            "storefront_font_storage_get_failed font_id=%s",
            query.font_id,
            exc_info=exc,
        )
        raise ObjectStorageUnavailableError from exc
    if stored is None:
        raise StorefrontFontNotFoundError
    return {
        "stored": stored,
        "checksum_sha256": font["checksum_sha256"],
    }
