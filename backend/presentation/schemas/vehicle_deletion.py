"""Administrative deletion API contracts, including optional confirmations."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool


class VehicleDeleteRequest(BaseModel):
    confirmation: str | None = None
    reason: str | None = None


class WarehouseUnbindRequest(BaseModel):
    confirmed: StrictBool = False


class WarehouseBulkDeleteRequest(WarehouseUnbindRequest):
    confirmation: str | None = None


class VehicleBlockingReason(BaseModel):
    type: str
    count: int
    description: str


class VehicleDeletionCheckResponse(BaseModel):
    can_delete: bool
    vin: str
    name: str
    blocking_reasons: list[VehicleBlockingReason] = Field(default_factory=list)


class VehicleDeleteResponse(BaseModel):
    deleted: Literal[True]
    vehicle_id: UUID
    cleaned_relations: dict[str, int]


class WarehouseUnbindResponse(BaseModel):
    warehouse_id: UUID
    unbound_count: int


class WarehouseBlockingReason(VehicleBlockingReason):
    vehicle_count: int


class WarehouseDeletionCheckResponse(BaseModel):
    warehouse_id: UUID
    requested_count: int
    deletable_count: int
    blocked_count: int
    blocking_reasons: list[WarehouseBlockingReason] = Field(default_factory=list)


class SkippedVehicle(BaseModel):
    vehicle_id: UUID
    vin: str
    blocking_reasons: list[VehicleBlockingReason]


class WarehouseBulkDeleteResponse(BaseModel):
    warehouse_id: UUID
    requested_count: int
    deleted_count: int
    skipped_count: int
    skipped: list[SkippedVehicle] = Field(default_factory=list)
