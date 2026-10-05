"""HTTP schemas for car images."""
from __future__ import annotations

from pydantic import BaseModel


class VehicleImageItem(BaseModel):
    filename: str
    url: str
    size: int


class VehicleImagesListResponse(BaseModel):
    images: list[VehicleImageItem]
