"""HTTP schemas for the administrator storefront font catalog."""

from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class StorefrontFontResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    description: str | None
    original_filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    storefront_usage_count: int
    created_at: datetime
    updated_at: datetime


class StorefrontFontListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StorefrontFontResource]


class StorefrontFontPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Укажите название или описание шрифта")
        return self
