"""HTTP schemas for catalog storefront configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel

from domain.section_visibility import StorefrontSectionVisibilityScope
from domain.storefronts import (
    MAX_PUBLIC_UI_TITLE_LENGTH,
    PublicPageKey,
    StorefrontBorderRadius,
)


class StorefrontColors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    background: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    surface: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    text: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class StorefrontAdminAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    colors: StorefrontColors
    border_radius: StorefrontBorderRadius
    font_id: UUID | None
    color_overrides: dict[
        str, Annotated[str, Field(strict=True, pattern=r"^#[0-9A-Fa-f]{6}$")]
    ] = Field(default_factory=dict)


class StorefrontPublicFont(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None
    family: str
    url: str | None


class StorefrontPublicAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    colors: StorefrontColors
    border_radius: StorefrontBorderRadius
    font: StorefrontPublicFont
    color_overrides: dict[str, str]


class PublicUIPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_PUBLIC_UI_TITLE_LENGTH)


class PublicUIPages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    home: PublicUIPage
    about: PublicUIPage
    special_equipment_catalog: PublicUIPage


class StorefrontPublicUI(BaseModel):
    model_config = ConfigDict(extra="forbid")

    home_page_key: PublicPageKey
    pages: PublicUIPages


class StorefrontPublicResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    slug: str | None
    version: int
    is_default: bool
    logo_url: str
    contact_email: str
    contact_phone: str
    contact_phone_href: str
    is_active: bool
    public_ui: StorefrontPublicUI
    appearance: StorefrontPublicAppearance


class StorefrontAdminResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    slug: str | None
    version: int
    is_default: bool
    logo_url: str | None
    contact_email: str | None
    contact_phone: str | None
    effective_contact_email: str
    effective_contact_phone: str
    effective_contact_phone_href: str
    effective_logo_url: str
    is_active: bool
    warehouse_ids: list[UUID]
    created_at: datetime
    updated_at: datetime
    public_ui: StorefrontPublicUI
    appearance: StorefrontAdminAppearance


class StorefrontListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StorefrontAdminResponse]


class StorefrontCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=63)
    warehouse_ids: list[UUID] = Field(min_length=1)
    is_active: bool = True
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)


class StorefrontPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str | None = Field(default=None, min_length=1, max_length=63)
    warehouse_ids: list[UUID] | None = Field(default=None, min_length=1)
    is_active: bool | None = None
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    public_ui: StorefrontPublicUI | None = None
    appearance: StorefrontAdminAppearance | None = None


class StorefrontSettingsAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    colors: StorefrontColors
    border_radius: StorefrontBorderRadius
    color_overrides: dict[
        str, Annotated[str, Field(strict=True, pattern=r"^#[0-9A-Fa-f]{6}$")]
    ]


class StorefrontSettingsLogo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    data_base64: str


class StorefrontSettingsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool
    contact_email: str | None
    contact_phone: str | None
    public_ui: StorefrontPublicUI
    appearance: StorefrontSettingsAppearance
    section_visibility: dict[StorefrontSectionVisibilityScope, dict[str, bool]]
    logo: StorefrontSettingsLogo | None


class StorefrontSettingsExportResponse(RootModel[dict[str, StorefrontSettingsBlock]]):
    """Portable settings keyed directly by slug, without an envelope."""


class StorefrontSettingsPreviewItem(BaseModel):
    slug: str
    action: Literal["create", "update"]
    warnings: list[str]


class StorefrontSettingsPreviewResponse(BaseModel):
    items: list[StorefrontSettingsPreviewItem]
    preview_token: str


class StorefrontSettingsImportResponse(BaseModel):
    created: list[str]
    updated: list[str]
