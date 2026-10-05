"""Pydantic schemas for the Positions catalog API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PositionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(description="Уникальный идентификатор должности")
    name: str = Field(description="Название должности")
    code: str = Field(description="Системный код должности")
    is_active: bool = Field(description="Флаг активности должности")
    created_at: datetime = Field(description="Дата и время создания")
    updated_at: datetime = Field(description="Дата и время последнего обновления")


class PositionsListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[PositionOut] = Field(description="Список должностей")


class CreatePositionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=255, description="Название должности")
    code: str = Field(min_length=1, max_length=100, description="Системный код должности")
    is_active: bool = Field(default=True, description="Флаг активности должности")


class UpdatePositionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=255, description="Название должности")
    code: str = Field(min_length=1, max_length=100, description="Системный код должности")
    is_active: bool = Field(description="Флаг активности должности")
