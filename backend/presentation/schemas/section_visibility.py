"""HTTP schemas for section visibility settings."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from domain.section_visibility import SectionVisibilityScope


class SectionVisibilityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(
        min_length=1,
        max_length=64,
        description="Стабильный ключ раздела навигации.",
    )
    is_visible: bool = Field(
        description="Показывать ли раздел пользователям выбранной области."
    )


class SectionVisibilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: SectionVisibilityScope
    storefront_id: UUID | None
    sections: list[SectionVisibilityItem]


class SectionVisibilityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SectionVisibilityResponse]


class UpdateSectionVisibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[SectionVisibilityItem] = Field(
        min_length=1,
        description="Непустой частичный список изменяемых разделов.",
    )
