"""Validation and encoding for direct registry image uploads."""

from __future__ import annotations

import asyncio
from pathlib import PurePath
from uuid import UUID, uuid4

from PIL import Image

from domain.special_equipment_import import ImportContractError
from infrastructure.services.special_equipment_import_images import (
    _decode_and_reencode,
)

MAX_REGISTRY_IMAGE_BYTES = 15 * 1024 * 1024
ALLOWED_REGISTRY_IMAGE_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)


class RegistryImageValidationError(ValueError):
    """Safe validation failure; never includes storage identifiers."""


async def encode_registry_image(
    *, filename: str | None, content_type: str | None, data: bytes
) -> bytes:
    if not filename or PurePath(filename).name != filename:
        raise RegistryImageValidationError("Некорректное имя файла")
    if content_type not in ALLOWED_REGISTRY_IMAGE_TYPES:
        raise RegistryImageValidationError(
            "Поддерживаются только JPEG, PNG и WebP"
        )
    if not data:
        raise RegistryImageValidationError("Файл пуст")
    if len(data) > MAX_REGISTRY_IMAGE_BYTES:
        raise RegistryImageValidationError("Изображение превышает 15 МБ")
    try:
        return await asyncio.to_thread(_decode_and_reencode, data)
    except (Image.DecompressionBombError, ImportContractError) as exc:
        raise RegistryImageValidationError(
            "Файл не является допустимым изображением"
        ) from exc


def registry_image_storage_key(owner: str, owner_id: UUID) -> str:
    if owner not in {"category", "product"}:
        raise ValueError("unsupported registry image owner")
    plural = "categories" if owner == "category" else "products"
    return (
        f"special-equipment/registry/{plural}/{owner_id}/"
        f"{uuid4().hex}.webp"
    )
