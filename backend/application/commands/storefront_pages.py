"""Commands and command handlers for storefront constructor pages."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from domain.services.object_storage import ObjectStorage
from domain.storefront_pages import (
    BUILDER_MEDIA_CONTENT_TYPES,
    MAX_BUILDER_MEDIA_BYTES,
    InvalidBuilderMediaError,
    InvalidPagePresetError,
)
from infrastructure.repositories.storefront_page_repository import (
    StorefrontPageRecord,
    create_page,
    get_template_by_code,
    publish_page,
    restore_revision,
    save_draft,
    update_page_metadata,
)


@dataclass(frozen=True)
class CreateStorefrontPageCommand:
    storefront_id: UUID
    title: str
    page_key: str
    slug: str | None
    template_code: str | None
    user_id: UUID | None


@dataclass(frozen=True)
class UpdateStorefrontPageMetadataCommand:
    storefront_id: UUID
    page_id: UUID
    title: str | None = None
    slug: str | None = None


@dataclass(frozen=True)
class SaveStorefrontPageDraftCommand:
    storefront_id: UUID
    page_id: UUID
    expected_version: int
    draft_layout: dict[str, Any]
    summary: str | None
    user_id: UUID | None
    title: str | None = None


@dataclass(frozen=True)
class PublishStorefrontPageCommand:
    storefront_id: UUID
    page_id: UUID
    expected_version: int
    user_id: UUID | None


@dataclass(frozen=True)
class RestoreStorefrontPageRevisionCommand:
    storefront_id: UUID
    page_id: UUID
    revision_id: UUID
    expected_version: int
    user_id: UUID | None


@dataclass(frozen=True)
class ImportStorefrontPagePresetCommand:
    storefront_id: UUID
    page_id: UUID
    preset_data: dict[str, Any]
    expected_version: int
    summary: str | None
    user_id: UUID | None


@dataclass(frozen=True)
class UploadStorefrontBuilderMediaCommand:
    storefront_id: UUID
    filename: str
    content_type: str
    data: bytes


async def handle_create_storefront_page(
    cmd: CreateStorefrontPageCommand, session: AsyncSession
) -> StorefrontPageRecord:
    layout: dict[str, Any]
    if cmd.template_code:
        tmpl = await get_template_by_code(session, cmd.template_code)
        layout = (
            copy.deepcopy(tmpl["layout"])
            if tmpl is not None
            else {"settings": {"title": cmd.title}, "sections": []}
        )
    else:
        layout = {"settings": {"title": cmd.title}, "sections": []}

    return cast(
        "StorefrontPageRecord",
        await create_page(
            session=session,
            storefront_id=cmd.storefront_id,
            title=cmd.title,
            page_key=cmd.page_key,
            slug=cmd.slug,
            layout=layout,
            is_system=False,
            user_id=cmd.user_id,
        ),
    )


async def handle_update_storefront_page_metadata(
    cmd: UpdateStorefrontPageMetadataCommand, session: AsyncSession
) -> StorefrontPageRecord:
    return cast(
        "StorefrontPageRecord",
        await update_page_metadata(
            session=session,
            storefront_id=cmd.storefront_id,
            page_id=cmd.page_id,
            title=cmd.title,
            slug=cmd.slug,
        ),
    )


async def handle_save_storefront_page_draft(
    cmd: SaveStorefrontPageDraftCommand, session: AsyncSession
) -> StorefrontPageRecord:
    return cast(
        "StorefrontPageRecord",
        await save_draft(
            session=session,
            storefront_id=cmd.storefront_id,
            page_id=cmd.page_id,
            expected_version=cmd.expected_version,
            draft_layout=cmd.draft_layout,
            summary=cmd.summary,
            user_id=cmd.user_id,
            title=cmd.title,
        ),
    )


async def handle_publish_storefront_page(
    cmd: PublishStorefrontPageCommand, session: AsyncSession
) -> StorefrontPageRecord:
    return cast(
        "StorefrontPageRecord",
        await publish_page(
            session=session,
            storefront_id=cmd.storefront_id,
            page_id=cmd.page_id,
            expected_version=cmd.expected_version,
            user_id=cmd.user_id,
        ),
    )


async def handle_restore_storefront_page_revision(
    cmd: RestoreStorefrontPageRevisionCommand, session: AsyncSession
) -> StorefrontPageRecord:
    return cast(
        "StorefrontPageRecord",
        await restore_revision(
            session=session,
            storefront_id=cmd.storefront_id,
            page_id=cmd.page_id,
            revision_id=cmd.revision_id,
            expected_version=cmd.expected_version,
            user_id=cmd.user_id,
        ),
    )


async def handle_import_storefront_page_preset(
    cmd: ImportStorefrontPagePresetCommand, session: AsyncSession
) -> StorefrontPageRecord:
    data = cmd.preset_data
    if not isinstance(data, dict):
        raise InvalidPagePresetError("Данные пресета должны быть JSON-объектом")

    layout = data.get("layout", data)
    if not isinstance(layout, dict) or "sections" not in layout:
        raise InvalidPagePresetError("Макет в пресете не содержит секций ('sections')")

    return cast(
        "StorefrontPageRecord",
        await save_draft(
            session=session,
            storefront_id=cmd.storefront_id,
            page_id=cmd.page_id,
            expected_version=cmd.expected_version,
            draft_layout=layout,
            summary=cmd.summary or "Импорт пресета из файла",
            user_id=cmd.user_id,
        ),
    )


async def handle_upload_storefront_builder_media(
    cmd: UploadStorefrontBuilderMediaCommand, storage: ObjectStorage
) -> dict[str, Any]:
    normalized_ct = cmd.content_type.strip().lower()
    if normalized_ct not in BUILDER_MEDIA_CONTENT_TYPES:
        raise InvalidBuilderMediaError(
            f"Неподдерживаемый формат файла: '{cmd.content_type}'. "
            f"Допустимы: {', '.join(sorted(BUILDER_MEDIA_CONTENT_TYPES))}"
        )

    if len(cmd.data) > MAX_BUILDER_MEDIA_BYTES:
        raise InvalidBuilderMediaError(
            f"Превышен максимальный размер файла: {len(cmd.data)} байт "
            f"(максимум {MAX_BUILDER_MEDIA_BYTES // (1024 * 1024)} МБ)"
        )

    clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", cmd.filename) or "image.png"
    storage_key = (
        f"storefronts/{cmd.storefront_id}/builder/{uuid4().hex[:12]}_{clean_name}"
    )

    url = await storage.put(storage_key, cmd.data, normalized_ct)
    if not url:
        url = storage.public_url(storage_key)

    return {
        "url": url,
        "key": storage_key,
        "content_type": normalized_ct,
        "size": len(cmd.data),
    }
