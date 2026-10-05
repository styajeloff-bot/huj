"""Pydantic schemas for the featured-vehicles admin API."""
from __future__ import annotations

import datetime as _dt
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FeaturedCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model_id: str = Field(min_length=1, max_length=255)


class FeaturedReorderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ordered_ids: list[UUID] = Field(min_length=1)


class FeaturedPatchRequest(BaseModel):
    """Partial update: currently only supports flipping `active` flag."""

    model_config = ConfigDict(extra="ignore")

    active: bool | None = None
    is_active: bool | None = None


class FeaturedOut(BaseModel):
    id: UUID
    model_id: str
    model_name: str | None = None
    mark_id: str | None = None
    mark_name: str | None = None
    position: int
    is_active: bool | None = None
    is_eligible: bool
    created_by: UUID | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class FeaturedListResponse(BaseModel):
    featured: list[FeaturedOut]


class FeaturedResponse(BaseModel):
    featured: FeaturedOut
    message: str | None = None


class FeaturedReorderResponse(BaseModel):
    message: str
    updated_count: int


class FeaturedDeleteResponse(BaseModel):
    message: str
    id: UUID


class FeaturedModelOut(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_id: str
    model_name: str | None = None
    mark_id: str | None = None
    mark_name: str | None = None
    is_featured: bool


class PaginationOut(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class FeaturedModelsListResponse(BaseModel):
    models: list[FeaturedModelOut]
    pagination: PaginationOut


class FeaturedMarkOut(BaseModel):
    id: str
    name: str | None = None


class FeaturedMarksListResponse(BaseModel):
    marks: list[FeaturedMarkOut]
