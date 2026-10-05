"""Commands for the administrator-managed storefront font catalog."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import ObjectStorageUnavailableError
from domain.services.object_storage import ObjectStorage
from domain.storefronts import (
    InvalidStorefrontFontError,
    StorefrontFontContentConflictError,
    StorefrontFontNameConflictError,
    StorefrontFontNotFoundError,
    normalize_storefront_font_description,
    normalize_storefront_font_name,
    storefront_font_storage_key,
    validate_storefront_font_upload,
)
from infrastructure.repositories.storefront_font_repository import (
    StorefrontFontRecord,
    create_storefront_font,
    delete_storefront_font_and_reset_usage,
    get_storefront_font_by_checksum,
    get_storefront_font_by_name,
    lock_storefront_font_by_id,
    update_storefront_font,
)
from infrastructure.services.font_normalizer import (
    FontNormalizationError,
    normalize_font_to_woff2,
)

logger = logging.getLogger("carcraft-backend")


@dataclass(frozen=True, slots=True)
class UploadStorefrontFontCommand:
    name: str
    description: str | None
    original_filename: str | None
    data: bytes
    created_by: UUID


@dataclass(frozen=True, slots=True)
class UpdateStorefrontFontCommand:
    font_id: UUID
    name: str | None = None
    description: str | None = None
    update_name: bool = False
    update_description: bool = False


@dataclass(frozen=True, slots=True)
class DeleteStorefrontFontCommand:
    font_id: UUID


async def handle_upload_storefront_font(
    command: UploadStorefrontFontCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict[str, StorefrontFontRecord]:
    name = normalize_storefront_font_name(command.name)
    description = normalize_storefront_font_description(command.description)
    original_filename = validate_storefront_font_upload(
        command.original_filename, len(command.data)
    )
    if await get_storefront_font_by_name(session, name) is not None:
        raise StorefrontFontNameConflictError
    try:
        normalized = await normalize_font_to_woff2(command.data)
    except FontNormalizationError as exc:
        raise InvalidStorefrontFontError from exc

    checksum_sha256 = hashlib.sha256(normalized).hexdigest()
    duplicate = await get_storefront_font_by_checksum(session, checksum_sha256)
    if duplicate is not None:
        raise StorefrontFontContentConflictError(duplicate["name"])

    font_id = uuid4()
    storage_key = storefront_font_storage_key(font_id)
    try:
        await storage.put(storage_key, normalized, "font/woff2")
    except Exception as exc:
        logger.error(
            "storefront_font_storage_put_failed font_id=%s",
            font_id,
            exc_info=exc,
        )
        raise ObjectStorageUnavailableError from exc

    try:
        font = await create_storefront_font(
            session,
            font_id=font_id,
            name=name,
            description=description,
            original_filename=original_filename,
            storage_key=storage_key,
            content_type="font/woff2",
            size_bytes=len(normalized),
            checksum_sha256=checksum_sha256,
            created_by=command.created_by,
        )
    except Exception:
        try:
            await storage.delete(storage_key)
        except Exception as cleanup_exc:
            logger.error(
                "storefront_font_storage_compensation_failed font_id=%s",
                font_id,
                exc_info=cleanup_exc,
            )
        raise
    return {"font": font}


async def compensate_storefront_font_upload(
    font_id: UUID, storage: ObjectStorage
) -> None:
    """Best-effort removal when the router cannot commit the created DB row."""
    try:
        await storage.delete(storefront_font_storage_key(font_id))
    except Exception as exc:
        logger.error(
            "storefront_font_storage_compensation_failed font_id=%s",
            font_id,
            exc_info=exc,
        )


async def handle_update_storefront_font(
    command: UpdateStorefrontFontCommand,
    session: AsyncSession,
) -> dict[str, StorefrontFontRecord]:
    if not command.update_name and not command.update_description:
        raise InvalidStorefrontFontError("Укажите название или описание шрифта")
    current = await lock_storefront_font_by_id(session, command.font_id)
    if current is None:
        raise StorefrontFontNotFoundError

    name = None
    if command.update_name:
        name = normalize_storefront_font_name(command.name)
        duplicate = await get_storefront_font_by_name(session, name)
        if duplicate is not None and duplicate["id"] != command.font_id:
            raise StorefrontFontNameConflictError
    description = (
        normalize_storefront_font_description(command.description)
        if command.update_description
        else None
    )
    updated = await update_storefront_font(
        session,
        command.font_id,
        name=name,
        description=description,
        update_description=command.update_description,
    )
    if updated is None:
        raise StorefrontFontNotFoundError
    return {"font": updated}


async def handle_delete_storefront_font(
    command: DeleteStorefrontFontCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict[str, int]:
    current = await lock_storefront_font_by_id(session, command.font_id)
    if current is None:
        raise StorefrontFontNotFoundError
    async with session.begin_nested():
        usage_count = await delete_storefront_font_and_reset_usage(
            session, command.font_id
        )
        try:
            await storage.delete(current["storage_key"])
        except Exception as exc:
            logger.error(
                "storefront_font_storage_delete_failed font_id=%s",
                command.font_id,
                exc_info=exc,
            )
            raise ObjectStorageUnavailableError(
                "Не удалось удалить файл шрифта; повторите операцию"
            ) from exc
    return {"storefront_usage_count": usage_count}
