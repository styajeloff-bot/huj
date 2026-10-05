"""Read-only storefront settings export and import preview."""
from __future__ import annotations

import base64
import json
from typing import Any
from uuid import UUID

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.section_visibility import (
    STOREFRONT_SECTION_VISIBILITY_SCOPES,
    get_section_visibility_defaults,
)
from domain.services.object_storage import ObjectStorage
from domain.storefront_transfer import (
    MAX_STOREFRONT_TRANSFER_BYTES,
    MAX_TRANSFER_STOREFRONTS,
    InvalidStorefrontTransferError,
    StorefrontSettingsTransfer,
    parse_storefront_settings,
)
from domain.storefronts import InvalidStorefrontLogoError, validate_storefront_logo
from infrastructure.repositories.storefront_transfer_repository import (
    read_transfer_state,
)
from infrastructure.services.image_optimizer import validate_storefront_logo_image
from infrastructure.services.storefront_import_token import issue_preview_token


async def validate_transfer_logos(items: dict[str, StorefrontSettingsTransfer]) -> None:
    for item in items.values():
        if item.logo is not None:
            await validate_transfer_logo(item.logo.data, item.logo.content_type)


async def validate_transfer_logo(data: bytes, content_type: str) -> None:
    validate_storefront_logo(content_type, len(data))
    try:
        actual_type = await validate_storefront_logo_image(data)
    except (Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        raise InvalidStorefrontLogoError from exc
    if actual_type != content_type:
        raise InvalidStorefrontLogoError


def transfer_preview_items(
    items: dict[str, StorefrontSettingsTransfer], state: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current = {row["slug"] or "/": row for row in state}
    result = []
    for slug, item in items.items():
        existing = current.get(slug)
        warehouses = existing["warehouse_state"] if existing else []
        warnings = item.preview_warnings(
            exists=existing is not None,
            has_active_warehouses=bool(warehouses) and all(w["status"] == "active" for w in warehouses),
        )
        result.append({"slug": slug, "action": "update" if existing else "create", "warnings": warnings})
    return result


async def handle_preview_storefront_settings(
    data: bytes, actor_id: UUID, session: AsyncSession,
) -> dict[str, Any]:
    items = parse_storefront_settings(data)
    await validate_transfer_logos(items)
    state = await read_transfer_state(session, list(items))
    return {
        "items": transfer_preview_items(items, state),
        "preview_token": issue_preview_token(actor_id, data, state),
    }


async def handle_export_storefront_settings(
    session: AsyncSession, storage: ObjectStorage,
) -> bytes:
    state = await read_transfer_state(session)
    if len(state) > MAX_TRANSFER_STOREFRONTS:
        raise ServiceError("Экспорт содержит более 1000 витрин и не может быть импортирован", 413)
    chunks: list[bytes] = []
    serialized_size = 5  # Opening brace/newline and final newline/brace/newline.
    allowed_visibility = {
        scope: get_section_visibility_defaults(scope)
        for scope in STOREFRONT_SECTION_VISIBILITY_SCOPES
    }
    for row in state:
        visibility: dict[str, dict[str, bool]] = {
            scope: {} for scope in STOREFRONT_SECTION_VISIBILITY_SCOPES
        }
        for override in row["visibility"]:
            scope, key = override["scope"], override["section_key"]
            # Match effective visibility reads: retired keys may remain in DB,
            # but are not portable settings. Keep actual overrides, not defaults.
            if key in allowed_visibility.get(scope, {}):
                visibility[scope][key] = override["is_visible"]
        logo = None
        if row["logo_storage_key"] is not None:
            stored = await storage.get(row["logo_storage_key"])
            if stored is None:
                raise ServiceError("Не удалось прочитать собственный логотип витрины", 409)
            content_type = row["logo_content_type"]
            await validate_transfer_logo(stored.data, content_type)
            logo = {"content_type": content_type, "data_base64": base64.b64encode(stored.data).decode("ascii")}
        block = {
            "is_active": row["is_active"],
            "contact_email": row["contact_email"], "contact_phone": row["contact_phone"],
            "public_ui": {
                "home_page_key": row["home_page_key"],
                "pages": {key: {"title": value} for key, value in row["public_page_titles"].items()},
            },
            "appearance": {
                "colors": {key: row[f"appearance_{key}_color"] for key in ("primary", "background", "surface", "text")},
                "border_radius": row["appearance_border_radius"],
                "color_overrides": row["appearance_color_overrides"],
            },
            "section_visibility": visibility, "logo": logo,
        }
        entry = json.dumps(row["slug"] or "/", ensure_ascii=False) + ": " + json.dumps(
            block, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False,
        )
        chunk = "\n".join("  " + line for line in entry.splitlines()).encode("utf-8")
        serialized_size += len(chunk) + (2 if chunks else 0)
        if serialized_size > MAX_STOREFRONT_TRANSFER_BYTES:
            raise ServiceError("Экспорт превышает 20 MiB и не может быть импортирован", 413)
        chunks.append(chunk)
    data = b"{\n" + b",\n".join(chunks) + b"\n}\n"
    # Never return a document that fails our own syntax/domain import contract.
    try:
        parse_storefront_settings(data)
    except InvalidStorefrontTransferError as exc:
        raise ServiceError(f"Невозможно экспортировать настройки: {exc}", 409) from exc
    return data
