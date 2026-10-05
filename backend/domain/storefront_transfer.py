"""Portable storefront settings: strict JSON syntax and existing domain rules."""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from domain.section_visibility import (
    STOREFRONT_SECTION_VISIBILITY_SCOPES,
    get_section_visibility_defaults,
    validate_section_visibility_key,
)
from domain.storefronts import (
    MAX_STOREFRONT_LOGO_BYTES,
    CurrentHomePageHiddenError,
    DefaultStorefrontMutationError,
    PublicUIConfig,
    StorefrontAppearanceConfig,
    StorefrontError,
    StorefrontWarehouseRequiredError,
    normalize_storefront_slug,
    validate_public_ui_config,
    validate_storefront_appearance,
    validate_storefront_contact_email,
    validate_storefront_contact_phone,
    validate_storefront_logo,
)

MAX_STOREFRONT_TRANSFER_BYTES = 20 * 1024 * 1024
MAX_TRANSFER_STOREFRONTS = 1000


class InvalidStorefrontTransferError(StorefrontError):
    pass


class StaleStorefrontPreviewError(StorefrontError):
    def __init__(self) -> None:
        super().__init__("Файл или настройки изменились. Выполните предпросмотр повторно.")


@dataclass(frozen=True, slots=True)
class TransferLogo:
    content_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class StorefrontSettingsTransfer:
    slug: str
    is_active: bool
    contact_email: str | None
    contact_phone: str | None
    public_ui: PublicUIConfig
    appearance: StorefrontAppearanceConfig
    section_visibility: dict[str, dict[str, bool]]
    logo: TransferLogo | None

    def preview_warnings(self, *, exists: bool, has_active_warehouses: bool) -> list[str]:
        if self.slug == "/":
            if not exists or not self.is_active:
                raise DefaultStorefrontMutationError
            return []
        if not exists:
            return ["Будет создана выключенная витрина без складов с системным шрифтом. Перед публикацией выберите склады."]
        if self.is_active and not has_active_warehouses:
            raise StorefrontWarehouseRequiredError
        return []


def _object(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise InvalidStorefrontTransferError(
            f"{label}: ожидаются ровно поля {', '.join(sorted(keys))}"
        )
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidStorefrontTransferError(f"Повторный ключ JSON: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise InvalidStorefrontTransferError(f"Недопустимое значение JSON: {value}")


def _parse_logo(value: object) -> TransferLogo | None:
    if value is None:
        return None
    raw = _object(value, {"content_type", "data_base64"}, "Логотип")
    content_type, encoded = raw["content_type"], raw["data_base64"]
    if not isinstance(content_type, str) or not isinstance(encoded, str):
        raise InvalidStorefrontTransferError("MIME и base64 логотипа должны быть строками")
    if len(encoded) > 4 * ((MAX_STOREFRONT_LOGO_BYTES + 2) // 3):
        raise InvalidStorefrontTransferError("Логотип превышает 5 MiB")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvalidStorefrontTransferError("Некорректный base64 логотипа") from exc
    validate_storefront_logo(content_type, len(data))
    return TransferLogo(content_type=content_type, data=data)


def _parse_visibility(value: Any) -> dict[str, dict[str, bool]]:
    visibility = _object(value, set(STOREFRONT_SECTION_VISIBILITY_SCOPES), "section_visibility")
    for scope, overrides in visibility.items():
        if not isinstance(overrides, dict):
            raise InvalidStorefrontTransferError(f"Видимость {scope} должна быть словарём")
        for key, visible in overrides.items():
            try:
                validate_section_visibility_key(scope, key)
            except ValueError as exc:
                raise InvalidStorefrontTransferError(str(exc)) from exc
            if not isinstance(visible, bool):
                raise InvalidStorefrontTransferError("Видимость должна быть boolean")
    return visibility


def parse_storefront_settings(data: bytes) -> dict[str, StorefrontSettingsTransfer]:
    if not data or len(data) > MAX_STOREFRONT_TRANSFER_BYTES:
        raise InvalidStorefrontTransferError("JSON-файл должен иметь размер от 1 байта до 20 MiB")
    try:
        raw = json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidStorefrontTransferError("Некорректный JSON UTF-8") from exc
    if not isinstance(raw, dict) or not 1 <= len(raw) <= MAX_TRANSFER_STOREFRONTS:
        raise InvalidStorefrontTransferError("Ожидается непустой словарь не более 1000 витрин")
    result = {}
    for slug, value in sorted(raw.items()):
        if slug != "/" and normalize_storefront_slug(slug) != slug:
            raise InvalidStorefrontTransferError("Ключ витрины должен быть каноническим slug в нижнем регистре")
        block = _object(value, {
            "is_active", "contact_email", "contact_phone", "public_ui",
            "appearance", "section_visibility", "logo",
        }, f"Витрина {slug}")
        if not isinstance(block["is_active"], bool):
            raise InvalidStorefrontTransferError("is_active должен быть boolean")
        for field in ("contact_email", "contact_phone"):
            if block[field] is not None and not isinstance(block[field], str):
                raise InvalidStorefrontTransferError(f"{field} должен быть строкой или null")
        raw_ui = block["public_ui"]
        if not isinstance(raw_ui, dict):
            raise InvalidStorefrontTransferError("public_ui должен быть объектом")
        # Accept legacy "blocks" key silently; strip before validation.
        stripped_ui = {k: v for k, v in raw_ui.items() if k != "blocks"}
        ui = _object(stripped_ui, {"home_page_key", "pages"}, "public_ui")
        public_ui = validate_public_ui_config(ui["home_page_key"], ui["pages"])
        appearance = _object(block["appearance"], {"colors", "border_radius", "color_overrides"}, "appearance")
        validated_appearance = validate_storefront_appearance(
            appearance["colors"], appearance["border_radius"], None, appearance["color_overrides"],
        )
        visibility = _parse_visibility(block["section_visibility"])
        home = public_ui["home_page_key"]
        effective_public = {**get_section_visibility_defaults("public"), **visibility["public"]}
        if home != "home" and not effective_public[home]:
            raise CurrentHomePageHiddenError(home)
        if slug == "/" and not block["is_active"]:
            raise DefaultStorefrontMutationError
        result[slug] = StorefrontSettingsTransfer(
            slug=slug, is_active=block["is_active"],
            contact_email=validate_storefront_contact_email(block["contact_email"]),
            contact_phone=validate_storefront_contact_phone(block["contact_phone"]),
            public_ui=public_ui, appearance=validated_appearance,
            section_visibility=visibility, logo=_parse_logo(block["logo"]),
        )
    return result
