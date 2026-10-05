"""Pydantic schemas for storefront constructor (Page Builder)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class PageStyles(BaseModel):
    model_config = ConfigDict(extra="allow")

    primary_color: str | None = None
    background_color: str | None = None
    surface_color: str | None = None
    text_color: str | None = None
    border_radius: str | None = None
    font_family: str | None = None
    custom_css: str | None = None


class PageSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = ""
    meta_description: str | None = None
    styles: PageStyles = Field(default_factory=PageStyles)


class WidgetStyles(BaseModel):
    model_config = ConfigDict(extra="allow")

    padding_top: str | None = None
    padding_bottom: str | None = None
    padding_left: str | None = None
    padding_right: str | None = None
    margin_top: str | None = None
    margin_bottom: str | None = None
    align: str | None = None
    background_color: str | None = None
    custom_classes: str | None = None


class Widget(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID = Field(default_factory=uuid4)
    type: str
    is_hidden: bool = False
    props: dict[str, Any] = Field(default_factory=dict)
    styles: WidgetStyles = Field(default_factory=WidgetStyles)


class Column(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID = Field(default_factory=uuid4)
    width: int = Field(default=12, ge=1, le=12)
    widgets: list[Widget] = Field(default_factory=list)


class SectionStyles(BaseModel):
    model_config = ConfigDict(extra="allow")

    padding_top: str | None = None
    padding_bottom: str | None = None
    background_color: str | None = None
    background_image: str | None = None
    border_bottom: str | None = None


class Section(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID = Field(default_factory=uuid4)
    name: str = "Секция"
    layout_type: str = "container"
    styles: SectionStyles = Field(default_factory=SectionStyles)
    columns: list[Column] = Field(default_factory=list)


class PageLayout(BaseModel):
    model_config = ConfigDict(extra="allow")

    settings: PageSettings = Field(default_factory=PageSettings)
    sections: list[Section] = Field(default_factory=list)


class StorefrontPageResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    storefront_id: UUID
    page_key: str
    title: str
    slug: str | None
    is_system: bool
    status: str
    version: int
    has_unpublished_draft: bool
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StorefrontPageRevisionResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    page_id: UUID
    version: int
    summary: str | None
    created_by: UUID | None
    created_by_name: str | None = None
    created_at: datetime


class StorefrontPageRevisionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StorefrontPageRevisionResource]


class StorefrontPageDetailResponse(StorefrontPageResource):
    model_config = ConfigDict(extra="forbid")

    draft_layout: dict[str, Any]
    published_layout: dict[str, Any] | None
    revisions: list[StorefrontPageRevisionResource] = Field(default_factory=list)


class StorefrontPageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StorefrontPageResource]


class StorefrontPageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    page_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    slug: str | None = Field(default=None, max_length=120)
    template_code: str | None = None


class StorefrontPageUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)
    slug: str | None = Field(default=None, max_length=120)


class StorefrontPageDraftSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)
    expected_version: int = Field(ge=1)
    summary: str | None = Field(default=None, max_length=255)
    draft_layout: dict[str, Any]


class StorefrontPagePublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class StorefrontTemplateResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str
    description: str | None
    category: str
    preview_image_url: str | None
    layout: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StorefrontTemplateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StorefrontTemplateResource]


class StorefrontPresetExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    page_key: str
    title: str
    layout: dict[str, Any]
    exported_at: datetime


class StorefrontPresetPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    schema_version: str
    sections_count: int
    widgets_count: int
    widget_types: list[str]
    warnings: list[str] = Field(default_factory=list)


class StorefrontPresetImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset_data: dict[str, Any]
    expected_version: int = Field(ge=1)
    summary: str | None = Field(
        default="Импорт пресета из файла", max_length=255
    )


class StorefrontPublicPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_key: str
    title: str
    fallback_layout: bool = False
    layout: dict[str, Any] | None = None
    published_at: datetime | None = None
    version: int = 1


class StorefrontBuilderMediaUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    key: str
    content_type: str
    size: int
