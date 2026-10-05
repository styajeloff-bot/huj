"""Schemas for additional equipment and service catalogs."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EquipmentOut(BaseModel):
    equipment_code: str
    equipment_display_name: str


class EquipmentListResponse(BaseModel):
    items: list[EquipmentOut] = Field(default_factory=list)


class ServiceOut(BaseModel):
    service_code: str
    service_display_name: str


class ServiceListResponse(BaseModel):
    items: list[ServiceOut] = Field(default_factory=list)
