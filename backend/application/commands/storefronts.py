"""Commands for storefront configuration and logo branding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.section_visibility import (
    InitializeStorefrontSectionVisibilityCommand,
    handle_initialize_storefront_section_visibility,
)
from domain.services.object_storage import ObjectStorage
from domain.storefronts import (
    DefaultStorefrontMutationError,
    InvalidStorefrontLogoError,
    PublicUIConfig,
    StorefrontAppearancePatch,
    StorefrontFontNotFoundError,
    StorefrontNotFoundError,
    StorefrontSlugConflictError,
    StorefrontWarehouseRequiredError,
    normalize_storefront_slug,
    validate_public_ui_config,
    validate_storefront_appearance,
    validate_storefront_contact_email,
    validate_storefront_contact_phone,
    validate_storefront_logo,
)
from infrastructure.repositories.section_visibility_repository import (
    upsert_visibility_overrides,
)
from infrastructure.repositories.storefront_font_repository import (
    get_storefront_font_by_id,
)
from infrastructure.repositories.storefront_repository import (
    StorefrontRecord,
    clear_storefront_logo,
    count_active_warehouses,
    create_storefront,
    get_default_storefront,
    get_storefront_by_id,
    get_storefront_by_slug,
    lock_storefront_by_id,
    set_storefront_logo,
    update_storefront,
)
from infrastructure.services.image_optimizer import (
    extension_for_content_type,
    validate_storefront_logo_image,
)


@dataclass(frozen=True, slots=True)
class CreateStorefrontCommand:
    slug: str
    warehouse_ids: tuple[UUID, ...]
    created_by: UUID
    is_active: bool = True
    contact_email: str | None = None
    contact_phone: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateStorefrontCommand:
    storefront_id: UUID
    updated_by: UUID
    slug: str | None = None
    warehouse_ids: tuple[UUID, ...] | None = None
    is_active: bool | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    update_contact_email: bool = False
    update_contact_phone: bool = False
    public_ui: PublicUIConfig | None = None
    appearance: StorefrontAppearancePatch | None = None


@dataclass(frozen=True, slots=True)
class UploadStorefrontLogoCommand:
    storefront_id: UUID
    content_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class ClearStorefrontLogoCommand:
    storefront_id: UUID


async def _validate_warehouses(
    session: AsyncSession, warehouse_ids: tuple[UUID, ...]
) -> tuple[UUID, ...]:
    unique_ids = tuple(dict.fromkeys(warehouse_ids))
    if not unique_ids or await count_active_warehouses(session, unique_ids) != len(
        unique_ids
    ):
        raise StorefrontWarehouseRequiredError
    return unique_ids


async def handle_create_storefront(
    command: CreateStorefrontCommand, session: AsyncSession
) -> StorefrontRecord:
    slug = normalize_storefront_slug(command.slug)
    if await get_storefront_by_slug(session, slug) is not None:
        raise StorefrontSlugConflictError
    warehouse_ids = await _validate_warehouses(session, command.warehouse_ids)
    contact_email = validate_storefront_contact_email(command.contact_email)
    contact_phone = validate_storefront_contact_phone(command.contact_phone)
    default = await get_default_storefront(session)
    if default is None:
        raise StorefrontNotFoundError
    created = cast(
        "StorefrontRecord",
        await create_storefront(
            session,
            slug=slug,
            warehouse_ids=warehouse_ids,
            created_by=command.created_by,
            is_active=command.is_active,
            contact_email=contact_email,
            contact_phone=contact_phone,
            public_ui=default["public_ui"],
            appearance=default["appearance"],
        ),
    )
    await handle_initialize_storefront_section_visibility(
        InitializeStorefrontSectionVisibilityCommand(
            storefront_id=created["id"],
            updated_by=command.created_by,
        ),
        session,
    )
    return created


async def handle_update_storefront(
    command: UpdateStorefrontCommand, session: AsyncSession
) -> StorefrontRecord:
    current = await lock_storefront_by_id(session, command.storefront_id)
    if current is None:
        raise StorefrontNotFoundError
    if current["is_default"]:
        if command.slug is not None or command.is_active is not None:
            raise DefaultStorefrontMutationError
        if command.warehouse_ids is not None:
            raise DefaultStorefrontMutationError

    slug = None
    if command.slug is not None:
        slug = normalize_storefront_slug(command.slug)
        existing = await get_storefront_by_slug(session, slug)
        if existing is not None and existing["id"] != command.storefront_id:
            raise StorefrontSlugConflictError

    warehouse_ids = command.warehouse_ids
    if warehouse_ids is not None or (command.is_active is True and not current["is_default"]):
        # Imported drafts have no bindings; ordinary activation must satisfy
        # the same warehouse contract as ordinary creation.
        validated_ids = await _validate_warehouses(
            session, warehouse_ids if warehouse_ids is not None else tuple(current["warehouse_ids"]),
        )
        warehouse_ids = validated_ids if warehouse_ids is not None else None
    contact_email = (
        validate_storefront_contact_email(command.contact_email)
        if command.update_contact_email
        else None
    )
    contact_phone = (
        validate_storefront_contact_phone(command.contact_phone)
        if command.update_contact_phone
        else None
    )
    appearance = None
    if command.appearance is not None:
        appearance = validate_storefront_appearance(
            command.appearance["colors"],
            command.appearance["border_radius"],
            command.appearance["font_id"],
            command.appearance.get(
                "color_overrides", current["appearance"]["color_overrides"]
            ),
        )
        font_id = appearance["font_id"]
        if (
            font_id is not None
            and await get_storefront_font_by_id(session, font_id) is None
        ):
            raise StorefrontFontNotFoundError
    public_ui = None
    if command.public_ui is not None:
        public_ui = validate_public_ui_config(
            command.public_ui["home_page_key"],
            command.public_ui["pages"],
        )
        home_page_key = public_ui["home_page_key"]
        if home_page_key != "home":
            await upsert_visibility_overrides(
                session,
                "public",
                {home_page_key: True},
                command.updated_by,
                storefront_id=command.storefront_id,
            )
    record = await update_storefront(
        session,
        command.storefront_id,
        slug=slug,
        is_active=command.is_active,
        warehouse_ids=warehouse_ids,
        contact_email=contact_email,
        contact_phone=contact_phone,
        update_contact_email=command.update_contact_email,
        update_contact_phone=command.update_contact_phone,
        public_ui=public_ui,
        public_ui_updated_by=command.updated_by if public_ui is not None else None,
        appearance=appearance,
    )
    if record is None:
        raise StorefrontNotFoundError
    return cast("StorefrontRecord", record)


async def handle_upload_storefront_logo(
    command: UploadStorefrontLogoCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> StorefrontRecord:
    validate_storefront_logo(command.content_type, len(command.data))
    current = await get_storefront_by_id(session, command.storefront_id)
    if current is None:
        raise StorefrontNotFoundError
    try:
        content_type = await validate_storefront_logo_image(command.data)
    except (Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        raise InvalidStorefrontLogoError from exc
    if content_type != command.content_type.split(";", 1)[0].strip().lower():
        raise InvalidStorefrontLogoError
    extension = extension_for_content_type(content_type)
    storage_key = f"storefronts/{command.storefront_id}/logo{extension}"
    await storage.put(storage_key, command.data, content_type)
    record = await set_storefront_logo(
        session,
        command.storefront_id,
        storage_key=storage_key,
        content_type=content_type,
    )
    if record is None:
        await storage.delete(storage_key)
        raise StorefrontNotFoundError
    old_storage_key = current["logo_storage_key"]
    if old_storage_key is not None and old_storage_key != storage_key:
        await storage.delete(old_storage_key)
    return cast("StorefrontRecord", record)


async def handle_clear_storefront_logo(
    command: ClearStorefrontLogoCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> StorefrontRecord:
    current = await get_storefront_by_id(session, command.storefront_id)
    if current is None:
        raise StorefrontNotFoundError
    record = await clear_storefront_logo(session, command.storefront_id)
    if record is None:
        raise StorefrontNotFoundError
    if current["logo_storage_key"] is not None:
        await storage.delete(current["logo_storage_key"])
    return cast("StorefrontRecord", record)
