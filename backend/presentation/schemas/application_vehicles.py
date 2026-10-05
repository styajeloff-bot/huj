"""Pydantic schemas for admin application_vehicles API."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssignVehicleRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dealer_id: UUID | None = None
    distributor_id: UUID | None = None  # accepted for parity, currently no-op


class AssignVinRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vin: str | None = Field(default=None, max_length=20)
    product_id: UUID | None = None
    vehicle_id: UUID | None = None


class DealerVehicleActionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal[
        "reject",
        "replace",
        "reserve",
        "discount",
        "markup",
        "contact_client",
        "replace_vin",
    ]
    comment: str | None = None
    reserve_expires_at: dt.date | None = None
    discount_type: Literal["rubles_off", "percent_off", "fixed_price"] | None = None
    discount_value: Decimal | None = None
    markup_type: Literal["rubles_up", "percent_up"] | None = None
    markup_value: Decimal | None = None
    final_price: Decimal | None = None
    show_catalog_price: bool | None = None
    vin: str | None = Field(default=None, max_length=20)


class AvailableVinOut(BaseModel):
    id: str
    vin: str | None = None
    color: str | None = None
    year: int | None = None
    base_price: Decimal | None = None
    discount_price: Decimal | None = None
    status: str | None = None
    complectation_id: str | None = None
    model_id: str | None = None
    mark_id: str | None = None


class AvailableVinsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    vehicles: list[AvailableVinOut]
    success: bool = True
    application_vehicle_id: str | None = None
    modification_id: str | None = None


class AssignVehicleResponse(BaseModel):
    success: bool
    message: str
    application_vehicle_id: str


class AssignVinResponse(BaseModel):
    """Unified VIN-assign response.

    Carries role-specific extras on top-level — ``assigned_vin`` mirrors
    the legacy self-owner shape, ``order`` carries the updated model-order
    payload for the distributor flow. Extra fields are allowed to avoid
    breaking existing response bodies.
    """

    model_config = ConfigDict(extra="allow")

    success: bool
    message: str
    vin: str | None = None
    assigned_vin: str | None = None
    application_vehicle_id: str | None = None
    order: dict | None = None


class DealerVehicleActionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool
    status: str
    application_vehicle: dict


class FulfillmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
    confirmed_quantity: int = Field(ge=1, le=2147483647)
    vehicle_ids: list[UUID] = Field(default_factory=list)
    reserve_expires_at: dt.date
    comment: str | None = Field(default=None, max_length=2000)


class FulfillmentAllocationResponse(BaseModel):
    id: UUID
    application_vehicle_id: UUID
    vehicle_id: UUID
    vin: str | None
    unit_price: float
    reserved_until: dt.datetime | None
    created_at: dt.datetime | None
    released_at: dt.datetime | None
    completed_at: dt.datetime | None = None
    reservation_fixed: bool = False
    created_by: UUID | None
    legacy: bool = False
    release_reason: str | None


class FulfillmentStockResponse(BaseModel):
    id: UUID
    vin: str | None
    base_price: float | None
    discount_price: float | None
    mark_id: str | None
    model_id: str | None
    complectation_id: str | None
    color: str | None
    year: int | None
    status: str | None


class FulfillmentHistoryResponse(BaseModel):
    id: UUID
    application_vehicle_id: UUID
    actor_id: UUID
    created_at: dt.datetime
    previous_values: dict[str, Any]
    new_values: dict[str, Any]
    comment: str | None


class FulfillmentResponse(BaseModel):
    application_vehicle_id: UUID
    requested_quantity: int | None
    confirmed_quantity: int | None
    quantity: int
    version: int
    editable: bool
    reservation_fixed: bool = False
    allocated_quantity: int
    remaining_quantity: int
    allocations: list[FulfillmentAllocationResponse]
    available_vehicles: list[FulfillmentStockResponse]
    history: list[FulfillmentHistoryResponse]
    calculation: dict[str, Any]
    application_totals: dict[str, float | None]
