"""Pydantic HTTP contracts for warehouse vehicle transfers."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from presentation.schemas.admin_warehouses import PaginationOut


class TransferWarehouseOut(BaseModel):
    id: UUID
    address: str
    brand: str
    city_name: str | None = None
    vehicles_count: int = 0


class AvailableWarehousesResponse(BaseModel):
    warehouses: list[TransferWarehouseOut]


class TransferVehicleOut(BaseModel):
    id: UUID
    vin: str | None = None
    mark_id: str | None = None
    mark_name: str | None = None
    model_id: str | None = None
    model_name: str | None = None
    year: int | None = None
    color: str | None = None
    source_warehouse_id: UUID


class TransferMarkFacetOut(BaseModel):
    id: str
    name: str


class TransferModelFacetOut(TransferMarkFacetOut):
    mark_id: str


class TransferVehicleFacetsOut(BaseModel):
    marks: list[TransferMarkFacetOut]
    models: list[TransferModelFacetOut]
    years: list[int]
    colors: list[str]


class SourceVehiclesResponse(BaseModel):
    vehicles: list[TransferVehicleOut]
    facets: TransferVehicleFacetsOut
    pagination: PaginationOut


class TransferVehiclesRequest(BaseModel):
    """Selection-mode rules are business validation and therefore return 400."""

    model_config = ConfigDict(extra="ignore")

    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    vehicle_ids: list[UUID] = Field(default_factory=list)
    all_filtered: bool = False
    vin: str | None = Field(default=None, max_length=100)
    mark_ids: list[str] | None = None
    model_ids: list[str] | None = None
    years: list[int] | None = None
    colors: list[str] | None = None


class TransferItemResultOut(BaseModel):
    vehicle_id: UUID
    status: str


class TransferVehiclesResponse(BaseModel):
    transferred_count: int
    failed_count: int
    results: list[TransferItemResultOut]
    message: str
