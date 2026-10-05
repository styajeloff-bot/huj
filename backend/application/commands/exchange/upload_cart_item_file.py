"""Attach a single file (PDF / image / КП) to an exchange cart item.

The blob lands under the LC user's object-storage prefix; we keep only
``file_url`` + ``file_name`` on the cart row itself so that the submit
handler can copy them onto each ``exchange_request`` unchanged.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import exchange_cart_repository as cart_repo
from infrastructure.services import document_storage

logger = logging.getLogger("carcraft-backend")

_MAX_BYTES = 10 * 1024 * 1024


@dataclass
class UploadCartItemFileCommand:
    item_id: UUID
    user_id: UUID
    filename: str
    content_type: str
    data: bytes


async def handle_upload_cart_item_file(
    cmd: UploadCartItemFileCommand, session: AsyncSession
) -> dict[str, Any]:
    if not cmd.data:
        raise ServiceError("Пустой файл", 400)
    if len(cmd.data) > _MAX_BYTES:
        raise ServiceError("Файл слишком большой (макс. 10 МБ)", 413)

    existing = await cart_repo.get_by_id(session, cmd.item_id)
    if existing is None or existing["user_id"] != cmd.user_id:
        raise ServiceError("Элемент корзины не найден", 404)

    safe_name = cmd.filename.strip() or "file"
    key = document_storage.build_user_key(
        cmd.user_id,
        f"exchange-cart/{cmd.item_id}/{uuid.uuid4().hex[:8]}_{safe_name}",
    )
    stored = await document_storage.put_document(
        key, cmd.data, cmd.content_type or "application/octet-stream"
    )

    # Store the bare S3 key (not the direct `storage.yandexcloud.net` URL)
    # — the bucket is private, so callers resolve the key through the
    # backend proxy (see infrastructure.services.file_proxy).
    updated = await cart_repo.set_item_file(
        session,
        cmd.item_id,
        user_id=cmd.user_id,
        file_url=stored.key,
        file_name=safe_name,
    )
    if updated is None:
        # Item vanished between the read and the write (unlikely, but keep
        # a precise error instead of a KeyError downstream).
        raise ServiceError("Элемент корзины не найден", 404)

    logger.info(
        "exchange_cart_file_uploaded item_id=%s user_id=%s size=%s key=%s",
        cmd.item_id, cmd.user_id, len(cmd.data), stored.key,
    )
    return {
        "message": "Файл загружен",
        "cart_item": updated,
    }
