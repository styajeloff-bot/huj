"""Pydantic schemas for the dealer-options API."""
from __future__ import annotations

import datetime as _dt
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DealerOptionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255)
    sort_order: int = Field(default=0, ge=0)


class DealerOptionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class DealerOptionOut(BaseModel):
    id: UUID
    name: str
    sort_order: int
    is_active: bool = True
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class DealerOptionListResponse(BaseModel):
    options: list[DealerOptionOut]


class DealerOptionResponse(BaseModel):
    option: DealerOptionOut
    message: str | None = None


class MessageResponse(BaseModel):
    message: str
