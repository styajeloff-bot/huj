"""Configurable navigation section visibility by application scope."""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

SectionVisibilityScope = Literal[
    "public",
    "carcraft_employee",
    "leasing_company",
    "dealer",
    "distributor",
]
StorefrontSectionVisibilityScope = Literal[
    "public",
    "leasing_company",
    "dealer",
    "distributor",
]
GlobalSectionVisibilityScope = Literal["carcraft_employee"]

TARGET_SECTION_VISIBILITY_SCOPES: tuple[SectionVisibilityScope, ...] = (
    "public",
    "carcraft_employee",
    "leasing_company",
    "dealer",
    "distributor",
)

STOREFRONT_SECTION_VISIBILITY_SCOPES: tuple[
    StorefrontSectionVisibilityScope, ...
] = (
    "public",
    "leasing_company",
    "dealer",
    "distributor",
)

GLOBAL_SECTION_VISIBILITY_SCOPES: tuple[GlobalSectionVisibilityScope, ...] = (
    "carcraft_employee",
)

SECTION_DEFAULTS_BY_SCOPE: dict[SectionVisibilityScope, dict[str, bool]] = {
    "public": {
        "about": True,
        "special_equipment_catalog": True,
    },
    "carcraft_employee": {
        "monetization": True,
        "document_registry": True,
        "special_equipment_import": True,
        "special_equipment_catalog": True,
    },
    "leasing_company": {
        "monetization": True,
        "document_registry": True,
        "leasing_applications": True,
        "documents": True,
        "document_requirements": True,
        "support": True,
        "exchange": True,
        "leasing_analytics": True,
        "security": True,
        "employees": True,
    },
    "dealer": {
        "monetization": True,
        "document_registry": True,
        "applications": True,
        "clients": True,
        "inventory": True,
        "reports": True,
        "distributor_analytics": True,
        "exchange": True,
        "support": True,
        "employees": True,
    },
    "distributor": {
        "monetization": True,
        "document_registry": True,
        "exchange": True,
        "applications": True,
        "warehouses": True,
        "distributor_analytics": True,
        "dealers": True,
        "companies": True,
        "support": True,
        "employees": True,
    },
}


class InvalidSectionVisibilityScopeError(ValueError):
    """Raised when a scope has no configurable section catalog."""


class InvalidSectionVisibilityKeyError(ValueError):
    """Raised when a section key does not belong to the scope catalog."""


class InvalidSectionVisibilityTargetError(ValueError):
    """Raised when storefront identity does not match the selected scope."""


def validate_section_visibility_scope(scope: str) -> SectionVisibilityScope:
    """Return a typed visibility scope or reject unsupported scopes."""
    if scope not in TARGET_SECTION_VISIBILITY_SCOPES:
        raise InvalidSectionVisibilityScopeError(
            f"Область {scope!r} не поддерживает настройку видимости разделов"
        )
    return cast("SectionVisibilityScope", scope)


def get_section_visibility_defaults(scope: str) -> dict[str, bool]:
    """Return defaults in their stable display order for one scope."""
    validated_scope = validate_section_visibility_scope(scope)
    return dict(SECTION_DEFAULTS_BY_SCOPE[validated_scope])


def validate_section_visibility_key(
    scope: str,
    section_key: str,
    allowed_custom_keys: set[str] | None = None,
) -> str:
    """Return a key when it is configurable for the requested scope."""
    defaults = get_section_visibility_defaults(scope)
    if section_key in defaults:
        return section_key
    if allowed_custom_keys is not None and section_key in allowed_custom_keys:
        return section_key
    raise InvalidSectionVisibilityKeyError(
        f"Раздел {section_key!r} нельзя настроить для области {scope!r}"
    )


def validate_section_visibility_target(
    scope: str,
    storefront_id: UUID | None,
) -> tuple[SectionVisibilityScope, UUID | None]:
    """Require a storefront for scoped visibility and forbid it for global."""
    validated_scope = validate_section_visibility_scope(scope)
    if (validated_scope in STOREFRONT_SECTION_VISIBILITY_SCOPES) != (
        storefront_id is not None
    ):
        raise InvalidSectionVisibilityTargetError(
            "Видимость public и бизнес-ролей требует витрину, "
            "а область сотрудника Carcraft является глобальной"
        )
    return validated_scope, storefront_id
