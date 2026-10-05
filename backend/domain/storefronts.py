"""Storefront identity and branding invariants."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict, cast
from uuid import UUID

from domain.errors import DomainError
from domain.storefront_color_keys import STOREFRONT_COLOR_OVERRIDE_KEYS

DEFAULT_STOREFRONT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_STOREFRONT_CONTACT_EMAIL = "info@multileasing.ru"
DEFAULT_STOREFRONT_CONTACT_PHONE = "+7 (930) 999-03-65"
MAX_STOREFRONT_LOGO_BYTES = 5 * 1024 * 1024
STOREFRONT_LOGO_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_PUBLIC_UI_TITLE_LENGTH = 120
MAX_STOREFRONT_FONT_NAME_LENGTH = 120
MAX_STOREFRONT_FONT_DESCRIPTION_LENGTH = 500
MAX_STOREFRONT_FONT_BYTES = 5 * 1024 * 1024

DEFAULT_STOREFRONT_PRIMARY_COLOR = "#3367BD"
DEFAULT_STOREFRONT_BACKGROUND_COLOR = "#F9FAFB"
DEFAULT_STOREFRONT_SURFACE_COLOR = "#FFFFFF"
DEFAULT_STOREFRONT_TEXT_COLOR = "#111827"
DEFAULT_STOREFRONT_BORDER_RADIUS = "medium"
DEFAULT_STOREFRONT_FONT_FAMILY = "Mulish"

StorefrontBorderRadius = Literal["none", "small", "medium", "large"]
STOREFRONT_BORDER_RADII: tuple[StorefrontBorderRadius, ...] = (
    "none",
    "small",
    "medium",
    "large",
)
STOREFRONT_FONT_EXTENSIONS = frozenset({".woff2", ".woff", ".ttf", ".otf"})

PublicPageKey = Literal[
    "home",
    "about",
    "special_equipment_catalog",
]
PUBLIC_PAGE_KEYS: tuple[PublicPageKey, ...] = (
    "home",
    "about",
    "special_equipment_catalog",
)

DEFAULT_PUBLIC_PAGE_TITLES: dict[PublicPageKey, str] = {
    "home": "Главная",
    "about": "О нас",
    "special_equipment_catalog": "Спецтехника",
}


class PublicPageConfig(TypedDict):
    title: str


class PublicUIConfig(TypedDict):
    home_page_key: PublicPageKey
    pages: dict[PublicPageKey, PublicPageConfig]


class StorefrontColors(TypedDict):
    primary: str
    background: str
    surface: str
    text: str


class StorefrontAppearanceConfig(TypedDict):
    colors: StorefrontColors
    border_radius: StorefrontBorderRadius
    font_id: UUID | None
    color_overrides: dict[str, str]


class StorefrontAppearancePatch(TypedDict):
    colors: StorefrontColors
    border_radius: StorefrontBorderRadius
    font_id: UUID | None
    color_overrides: NotRequired[dict[str, str]]


_UNSET_COLOR_OVERRIDES = object()

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_RE = re.compile(r"^[0-9() -]{1,32}$")
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_RESERVED_SLUGS = frozenset(
    {
        "401",
        "404",
        "500",
        "_nuxt",
        "about",
        "admin",
        "api",
        "application",
        "auth",
        "cabinet",
        "cars",
        "cart",
        "catalog",
        "favicon.ico",
        "favorites",
        "images",
        "models",
        "notifications",
        "orders",
        "privacy-policy",
        "s",
        "settings",
        "special-equipment",
        "storefront",
        "storefronts",
        "terms-of-service",
        "workspace",
    }
)


@dataclass(frozen=True, slots=True)
class CatalogScope:
    """Opaque catalog scope used by public application queries."""

    id: UUID
    slug: str | None
    version: int
    is_default: bool


DEFAULT_CATALOG_SCOPE = CatalogScope(
    id=DEFAULT_STOREFRONT_ID,
    slug=None,
    version=1,
    is_default=True,
)


class StorefrontError(DomainError):
    """Base storefront domain error."""


class InvalidStorefrontSlugError(StorefrontError):
    def __init__(self) -> None:
        super().__init__(
            "Адрес витрины должен содержать от 1 до 63 латинских букв, цифр или дефисов"
        )


class ReservedStorefrontSlugError(StorefrontError):
    def __init__(self, slug: str) -> None:
        super().__init__(f"Адрес витрины '{slug}' занят системным разделом")


class StorefrontNotFoundError(StorefrontError):
    def __init__(self) -> None:
        super().__init__("Витрина не найдена")


class StorefrontSlugConflictError(StorefrontError):
    def __init__(self) -> None:
        super().__init__("Витрина с таким адресом уже существует")


class DefaultStorefrontMutationError(StorefrontError):
    def __init__(self) -> None:
        super().__init__("Основную витрину нельзя удалить или отключить")


class StorefrontWarehouseRequiredError(StorefrontError):
    def __init__(self) -> None:
        super().__init__("Выберите хотя бы один существующий активный склад")


class InvalidStorefrontLogoError(StorefrontError):
    def __init__(self) -> None:
        super().__init__(
            "Логотип должен быть статичным JPEG, PNG или WebP размером до 5 МиБ"
        )


class InvalidStorefrontContactError(StorefrontError):
    def __init__(self) -> None:
        super().__init__("Некорректные контактные данные витрины")


class StorefrontLogoNotFoundError(StorefrontError):
    def __init__(self) -> None:
        super().__init__("Логотип витрины не найден")


class InvalidPublicUIConfigError(StorefrontError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class CurrentHomePageHiddenError(StorefrontError):
    def __init__(self, page_key: PublicPageKey) -> None:
        super().__init__(
            f"Нельзя скрыть текущую главную страницу {page_key!r}; "
            "сначала выберите другую главную страницу"
        )


class InvalidStorefrontAppearanceError(StorefrontError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidStorefrontFontError(StorefrontError):
    def __init__(self, message: str = "Некорректный файл шрифта") -> None:
        super().__init__(message)


class StorefrontFontNotFoundError(StorefrontError):
    def __init__(self) -> None:
        super().__init__("Шрифт не найден")


class StorefrontFontNameConflictError(StorefrontError):
    def __init__(self) -> None:
        super().__init__("Шрифт с таким названием уже существует")


class StorefrontFontContentConflictError(StorefrontError):
    def __init__(self, existing_name: str) -> None:
        super().__init__(f"Такой файл уже загружен как шрифт «{existing_name}»")


def default_public_ui_config() -> PublicUIConfig:
    """Return an independent default public UI configuration snapshot."""
    return PublicUIConfig(
        home_page_key="home",
        pages={
            key: PublicPageConfig(title=title)
            for key, title in DEFAULT_PUBLIC_PAGE_TITLES.items()
        },
    )


def default_storefront_appearance() -> StorefrontAppearanceConfig:
    """Return an independent snapshot of the existing storefront theme."""
    return StorefrontAppearanceConfig(
        colors=StorefrontColors(
            primary=DEFAULT_STOREFRONT_PRIMARY_COLOR,
            background=DEFAULT_STOREFRONT_BACKGROUND_COLOR,
            surface=DEFAULT_STOREFRONT_SURFACE_COLOR,
            text=DEFAULT_STOREFRONT_TEXT_COLOR,
        ),
        border_radius=cast(
            "StorefrontBorderRadius", DEFAULT_STOREFRONT_BORDER_RADIUS
        ),
        font_id=None,
        color_overrides={},
    )


def normalize_storefront_hex_color(value: object) -> str:
    if not isinstance(value, str) or not _HEX_COLOR_RE.fullmatch(value):
        raise InvalidStorefrontAppearanceError(
            "Цвет должен быть указан в формате #RRGGBB без прозрачности"
        )
    return value.upper()


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def storefront_contrast_ratio(first: str, second: str) -> float:
    first_luminance = _relative_luminance(normalize_storefront_hex_color(first))
    second_luminance = _relative_luminance(normalize_storefront_hex_color(second))
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def validate_storefront_appearance(
    colors: object,
    border_radius: object,
    font_id: object,
    color_overrides: object = _UNSET_COLOR_OVERRIDES,
) -> StorefrontAppearanceConfig:
    """Validate the complete, atomically persisted appearance contract."""
    if not isinstance(colors, Mapping):
        raise InvalidStorefrontAppearanceError("Цвета оформления должны быть объектом")
    expected_colors = ("primary", "background", "surface", "text")
    if set(colors) != set(expected_colors):
        raise InvalidStorefrontAppearanceError(
            "Цвета должны содержать ровно primary, background, surface и text"
        )
    normalized = StorefrontColors(
        primary=normalize_storefront_hex_color(colors["primary"]),
        background=normalize_storefront_hex_color(colors["background"]),
        surface=normalize_storefront_hex_color(colors["surface"]),
        text=normalize_storefront_hex_color(colors["text"]),
    )
    if border_radius not in STOREFRONT_BORDER_RADII:
        raise InvalidStorefrontAppearanceError("Неизвестный вариант скругления")
    if font_id is not None and not isinstance(font_id, UUID):
        raise InvalidStorefrontAppearanceError("Идентификатор шрифта должен быть UUID")

    return StorefrontAppearanceConfig(
        colors=normalized,
        border_radius=cast("StorefrontBorderRadius", border_radius),
        font_id=font_id,
        color_overrides=validate_storefront_color_overrides(
            {} if color_overrides is _UNSET_COLOR_OVERRIDES else color_overrides
        ),
    )


def validate_storefront_color_overrides(value: object) -> dict[str, str]:
    """Accept only registered semantic colors, without contrast restrictions."""
    if not isinstance(value, Mapping):
        raise InvalidStorefrontAppearanceError(
            "Переопределения цветов должны быть объектом"
        )
    normalized: dict[str, str] = {}
    for key, color in value.items():
        if not isinstance(key, str) or key not in STOREFRONT_COLOR_OVERRIDE_KEYS:
            raise InvalidStorefrontAppearanceError("Неизвестное назначение цвета")
        normalized[key] = normalize_storefront_hex_color(color)
    return normalized


def storefront_primary_text_color(primary: str) -> str:
    """Choose the accessible black/white text token for the primary color."""
    normalized = normalize_storefront_hex_color(primary)
    white_ratio = storefront_contrast_ratio(normalized, "#FFFFFF")
    black_ratio = storefront_contrast_ratio(normalized, "#000000")
    return "#FFFFFF" if white_ratio >= black_ratio else "#000000"


def storefront_font_family(font_id: UUID) -> str:
    return f"storefront-font-{font_id.hex}"


def storefront_font_storage_key(font_id: UUID) -> str:
    return f"storefront-fonts/{font_id}/font.woff2"


def normalize_storefront_font_name(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidStorefrontFontError("Название шрифта должно быть строкой")
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_STOREFRONT_FONT_NAME_LENGTH:
        raise InvalidStorefrontFontError(
            "Название шрифта должно содержать от 1 до 120 символов"
        )
    return normalized


def normalize_storefront_font_description(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidStorefrontFontError("Описание шрифта должно быть строкой")
    normalized = value.strip()
    if len(normalized) > MAX_STOREFRONT_FONT_DESCRIPTION_LENGTH:
        raise InvalidStorefrontFontError(
            "Описание шрифта не должно превышать 500 символов"
        )
    return normalized or None


def validate_storefront_font_upload(filename: str | None, size: int) -> str:
    if filename is None:
        raise InvalidStorefrontFontError("У файла шрифта должно быть имя")
    normalized_filename = filename.strip()
    if not normalized_filename or len(normalized_filename) > 255:
        raise InvalidStorefrontFontError("Некорректное имя файла шрифта")
    dot = normalized_filename.rfind(".")
    extension = normalized_filename[dot:].lower() if dot >= 0 else ""
    if extension not in STOREFRONT_FONT_EXTENSIONS:
        raise InvalidStorefrontFontError(
            "Поддерживаются только файлы WOFF2, WOFF, TTF и OTF"
        )
    if size <= 0 or size > MAX_STOREFRONT_FONT_BYTES:
        raise InvalidStorefrontFontError("Размер файла шрифта должен быть от 1 байта до 5 МБ")
    return normalized_filename


def _validate_exact_keys(
    actual: Mapping[str, object], expected: tuple[str, ...], label: str
) -> None:
    if set(actual) != set(expected):
        raise InvalidPublicUIConfigError(
            f"{label} должны содержать ровно ключи: {', '.join(expected)}"
        )


def _normalize_public_ui_title(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidPublicUIConfigError("Название публичного элемента должно быть строкой")
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_PUBLIC_UI_TITLE_LENGTH:
        raise InvalidPublicUIConfigError(
            "Название публичного элемента должно содержать от 1 до "
            f"{MAX_PUBLIC_UI_TITLE_LENGTH} символов"
        )
    return normalized


def validate_public_ui_config(
    home_page_key: object,
    pages: object,
) -> PublicUIConfig:
    """Validate and normalize the complete storefront public UI contract."""
    if home_page_key not in PUBLIC_PAGE_KEYS:
        raise InvalidPublicUIConfigError("Неизвестная главная публичная страница")
    if not isinstance(pages, Mapping):
        raise InvalidPublicUIConfigError("Страницы должны быть объектом")
    _validate_exact_keys(pages, cast("tuple[str, ...]", PUBLIC_PAGE_KEYS), "Страницы")

    normalized_pages: dict[PublicPageKey, PublicPageConfig] = {}
    for page_key in PUBLIC_PAGE_KEYS:
        raw = pages[page_key]
        if not isinstance(raw, Mapping) or set(raw) != {"title"}:
            raise InvalidPublicUIConfigError(
                f"Страница {page_key!r} должна содержать только название"
            )
        normalized_pages[page_key] = PublicPageConfig(
            title=_normalize_public_ui_title(raw["title"])
        )

    return PublicUIConfig(
        home_page_key=cast("PublicPageKey", home_page_key),
        pages=normalized_pages,
    )


def normalize_storefront_slug(value: str) -> str:
    """Normalize and validate a custom top-level storefront path segment."""
    slug = value.strip().lower()
    if not _SLUG_RE.fullmatch(slug):
        raise InvalidStorefrontSlugError
    if slug in _RESERVED_SLUGS:
        raise ReservedStorefrontSlugError(slug)
    return slug


def validate_storefront_logo(content_type: str, size: int) -> None:
    """Validate upload metadata before attempting an image decode."""
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if (
        normalized_type not in STOREFRONT_LOGO_CONTENT_TYPES
        or size <= 0
        or size > MAX_STOREFRONT_LOGO_BYTES
    ):
        raise InvalidStorefrontLogoError


def validate_storefront_contact_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if len(normalized) > 255 or not _EMAIL_RE.fullmatch(normalized):
        raise InvalidStorefrontContactError
    return normalized


def validate_storefront_contact_phone(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    body = normalized[1:] if normalized.startswith("+") else normalized
    digits = "".join(character for character in normalized if character.isdigit())
    if not _PHONE_RE.fullmatch(body) or "+" in body or not 5 <= len(digits) <= 15:
        raise InvalidStorefrontContactError
    return normalized


def storefront_phone_href(value: str) -> str:
    normalized = validate_storefront_contact_phone(value)
    if normalized is None:
        raise InvalidStorefrontContactError
    digits = "".join(character for character in normalized if character.isdigit())
    prefix = "+" if normalized.startswith("+") else ""
    return f"{prefix}{digits}"
