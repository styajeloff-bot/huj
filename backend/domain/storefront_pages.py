"""Domain types, constants, and errors for storefront constructor pages."""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from domain.errors import DomainError

MAX_PAGE_TITLE_LENGTH = 120
MAX_PAGE_KEY_LENGTH = 64
MAX_PAGE_SLUG_LENGTH = 120
MAX_BUILDER_MEDIA_BYTES = 10 * 1024 * 1024
BUILDER_MEDIA_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/svg+xml"}
)

PAGE_KEY_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
PAGE_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,118}[a-z0-9])?$")

PageStatus = Literal["draft", "published"]


class StorefrontPageNotFoundError(DomainError):
    """Storefront page was not found."""

    def __init__(self, identifier: UUID | str = ""):
        super().__init__(f"Страница витрины не найдена: {identifier}")
        self.identifier = identifier


class StorefrontPageAlreadyExistsError(DomainError):
    """Storefront page key already exists for this storefront."""

    def __init__(self, page_key: str):
        super().__init__(f"Страница с ключом '{page_key}' уже существует для данной витрины")
        self.page_key = page_key


class StorefrontPageVersionConflictError(DomainError):
    """Page version does not match expected version (optimistic lock failed)."""

    def __init__(self, current_version: int, expected_version: int):
        super().__init__(
            f"Версия страницы ({current_version}) не совпадает с ожидаемой ({expected_version}). "
            f"Обновите страницу перед сохранением."
        )
        self.current_version = current_version
        self.expected_version = expected_version
        self.code = "VERSION_CONFLICT"


class StorefrontPageRevisionNotFoundError(DomainError):
    """Revision was not found for this page."""

    def __init__(self, revision_id: UUID | str = ""):
        super().__init__(f"Ревизия страницы не найдена: {revision_id}")
        self.revision_id = revision_id


class StorefrontTemplateNotFoundError(DomainError):
    """Storefront template was not found."""

    def __init__(self, code: str = ""):
        super().__init__(f"Шаблон витрины не найден: {code}")
        self.code = code


class InvalidPageLayoutError(DomainError):
    """Page layout structure is invalid."""

    def __init__(self, reason: str):
        super().__init__(f"Некорректная структура макета страницы: {reason}")
        self.reason = reason


class InvalidPagePresetError(DomainError):
    """Page preset payload is invalid."""

    def __init__(self, reason: str):
        super().__init__(f"Некорректный пресет страницы: {reason}")
        self.reason = reason


class InvalidBuilderMediaError(DomainError):
    """Uploaded builder media file is invalid."""

    def __init__(self, reason: str):
        super().__init__(f"Некорректный медиа-файл: {reason}")
        self.reason = reason
