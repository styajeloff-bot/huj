"""Stage immutable logos, then apply all selected settings in one DB transaction."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.storefront_transfer import (
    transfer_preview_items,
    validate_transfer_logos,
)
from domain.services.object_storage import ObjectStorage
from domain.storefront_transfer import parse_storefront_settings
from domain.storefronts import StorefrontAppearanceConfig, StorefrontNotFoundError
from infrastructure.repositories import storefront_repository as repo
from infrastructure.repositories.storefront_transfer_repository import (
    lock_transfer_state,
    read_transfer_state,
    replace_transfer_visibility,
)
from infrastructure.services.image_optimizer import extension_for_content_type
from infrastructure.services.storefront_import_token import verify_preview_token


@dataclass(frozen=True, slots=True)
class ImportStorefrontSettingsCommand:
    data: bytes
    preview_token: str
    confirmed: bool
    actor_id: UUID


async def handle_import_storefront_settings(
    command: ImportStorefrontSettingsCommand, session: AsyncSession, storage: ObjectStorage,
) -> dict[str, list[str]]:
    if command.confirmed is not True:
        raise ServiceError("Подтвердите импорт настроек", 400, code="confirmation_required")
    items = parse_storefront_settings(command.data)
    await validate_transfer_logos(items)
    initial = await read_transfer_state(session, list(items))
    verify_preview_token(command.preview_token, command.actor_id, command.data, initial)
    transfer_preview_items(items, initial)

    staged: dict[str, str] = {}
    for slug, item in items.items():
        if item.logo is not None:
            key = f"storefronts/imports/{uuid4()}/logo{extension_for_content_type(item.logo.content_type)}"
            await storage.put(key, item.logo.data, item.logo.content_type)
            staged[slug] = key
    # No overwrite/delete of old keys, including on rollback or uncertain commit.
    # Failed imports may leave unreferenced immutable objects; deleting them
    # blindly after a lost commit acknowledgement could break a published logo.
    await lock_transfer_state(session, initial)
    current_state = await read_transfer_state(session, list(items))
    verify_preview_token(command.preview_token, command.actor_id, command.data, current_state)
    transfer_preview_items(items, current_state)
    current = {row["slug"] or "/": row for row in current_state}
    result: dict[str, list[str]] = {"created": [], "updated": []}
    for slug, item in items.items():
        existing = current.get(slug)
        appearance: StorefrontAppearanceConfig = {
            **item.appearance,
            "font_id": existing["font_id"] if existing else None,
        }
        if existing is None:
            record = await repo.create_storefront(
                session, slug=slug, warehouse_ids=(), created_by=command.actor_id,
                is_active=False, contact_email=item.contact_email, contact_phone=item.contact_phone,
                public_ui=item.public_ui, appearance=appearance,
            )
            result["created"].append(slug)
        else:
            record = await repo.update_storefront(
                session, existing["id"], is_active=item.is_active,
                contact_email=item.contact_email, contact_phone=item.contact_phone,
                update_contact_email=True, update_contact_phone=True,
                public_ui=item.public_ui, public_ui_updated_by=command.actor_id,
                appearance=appearance,
            )
            if record is None:
                raise StorefrontNotFoundError
            result["updated"].append(slug)
        await replace_transfer_visibility(session, record["id"], item.section_visibility, command.actor_id)
        if item.logo is None:
            await repo.clear_storefront_logo(session, record["id"])
        else:
            await repo.set_storefront_logo(
                session, record["id"], storage_key=staged[slug], content_type=item.logo.content_type,
            )
    return result
