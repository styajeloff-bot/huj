"""Pydantic schemas for the admin warehouses + cities API."""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Cities
# ---------------------------------------------------------------------------


class CityCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255)


class CityOut(BaseModel):
    id: str
    name: str
    created_at: _dt.datetime | None = None


class CityListResponse(BaseModel):
    cities: list[CityOut]


class CityResponse(BaseModel):
    city: CityOut
    message: str | None = None


# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------


class WarehouseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255)
    owner_company_id: UUID
    owner_company_type: str = Field(default="dealer", pattern="^(dealer|distributor)$")
    address: str = Field(min_length=1, max_length=500)
    city_id: UUID | None = None
    brand_ids: list[UUID] = Field(default_factory=list)
    category_id: UUID | None = None
    is_active: bool = True


class WarehouseUpdateRequest(BaseModel):
    """All fields optional. Use Pydantic's `model_fields_set` semantics
    to differentiate 'missing' from 'explicit null'."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    owner_company_id: UUID | None = None
    owner_company_type: str | None = Field(default=None, pattern="^(dealer|distributor)$")
    address: str | None = Field(default=None, min_length=1, max_length=500)
    city_id: UUID | None = None
    brand_ids: list[UUID] = Field(default_factory=list)
    category_id: UUID | None = None
    is_active: bool | None = None


class WarehouseDirectoryOption(BaseModel):
    id: UUID
    name: str


class WarehouseOut(BaseModel):
    id: str
    name: str
    owner_company_id: str
    owner_company_type: str
    owner_company_name: str | None = None
    address: str
    city_id: str | None = None
    city_name: str | None = None
    brand_ids: list[UUID] = Field(default_factory=list)
    selected_brands: list[WarehouseDirectoryOption] = Field(default_factory=list)
    category_id: UUID | None = None
    category_name: str | None = None
    brand_name: str | None = None
    brands: list[str] = Field(default_factory=list)
    vehicle_marks: list[str] = Field(default_factory=list)
    is_active: bool
    warehouse_access_type: str = "A"
    groups: list[str] = Field(default_factory=list)
    vehicles_count: int = 0
    vehicle_types: list[str] = Field(default_factory=list)
    sites: list[str] = Field(default_factory=list)
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class PaginationOut(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class WarehouseCategoriesResponse(BaseModel):
    categories: list[WarehouseDirectoryOption]
    pagination: PaginationOut


class WarehouseMarksResponse(BaseModel):
    marks: list[WarehouseDirectoryOption]
    pagination: PaginationOut


class WarehouseListResponse(BaseModel):
    warehouses: list[WarehouseOut]
    pagination: PaginationOut


class WarehouseResponse(BaseModel):
    warehouse: WarehouseOut
    message: str | None = None


# ---------------------------------------------------------------------------
# Warehouse Access Rules
# ---------------------------------------------------------------------------


class DealerAccessItem(BaseModel):
    dealer_id: UUID
    access_type: str = Field(default="B", pattern="^(B|C)$")


class CreateWarehouseAccessRulesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    warehouse_id: UUID
    mode: str = Field(default="dealers", pattern="^(dealers|dealer_group)$")
    dealer_group_id: UUID | None = None
    group_access_type: str | None = Field(default="B", pattern="^(B|C)$")
    dealers: list[DealerAccessItem] = Field(default_factory=list)
    site_id: UUID | None = None
    brand_id: UUID | None = None


class UpdateWarehouseAccessRuleRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    warehouse_access_type: str | None = Field(default=None, pattern="^(A|B|C)$")
    is_active: bool | None = None


class WarehouseAccessRuleOut(BaseModel):
    id: str
    warehouse_id: str
    warehouse_name: str
    owner_company_id: str | None = None
    owner_company_name: str | None = None
    owner_company_type: str | None = None
    warehouse_brand_names: list[str] = Field(default_factory=list)
    target_type: str
    target_id: str
    target_name: str
    warehouse_access_type: str
    site_id: str | None = None
    site_name: str | None = None
    brand_id: str | None = None
    brand_name: str | None = None
    source_group_id: str | None = None
    source_group_name: str | None = None
    is_visible: bool
    can_create_application: bool
    is_active: bool
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class WarehouseAccessRuleListResponse(BaseModel):
    rules: list[WarehouseAccessRuleOut]
    pagination: PaginationOut


class WarehouseAccessRuleResponse(BaseModel):
    rule: WarehouseAccessRuleOut
    message: str | None = None



# ---------------------------------------------------------------------------
# Vehicle ↔ warehouse bindings
# ---------------------------------------------------------------------------


class WarehouseVehicleOut(BaseModel):
    id: str
    vin: str | None = None
    mark_id: str | None = None
    mark_name: str | None = None
    model_id: str | None = None
    model_name: str | None = None
    year: int | None = None
    base_price: Decimal | None = None
    discount_price: Decimal | None = None
    color: str | None = None
    status: str | None = None
    purchase_pending: bool = False
    sale_completed: bool = False
    reserved_until: _dt.datetime | None = None
    bound_at: _dt.datetime | None = None


class WarehouseVehiclesListResponse(BaseModel):
    vehicles: list[WarehouseVehicleOut]
    pagination: PaginationOut


class AddVehicleToWarehouseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vehicle_id: UUID


class AddVehicleResponse(BaseModel):
    message: str
    vehicle_id: str
    warehouse_id: str


class BulkAddVehiclesToWarehouseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vehicle_ids: list[UUID] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def vehicle_ids_must_be_unique(self) -> BulkAddVehiclesToWarehouseRequest:
        if len(set(self.vehicle_ids)) != len(self.vehicle_ids):
            raise ValueError("vehicle_ids must not contain duplicates")
        return self


class BulkAddVehiclesToWarehouseResponse(BaseModel):
    bound: int
    skipped: int


class BindByMarkRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mark_id: str = Field(min_length=1, max_length=50)


class BindByMarkResponse(BaseModel):
    message: str
    bound_count: int
    total: int


class MessageResponse(BaseModel):
    message: str


class WarehouseDeleteProblem(BaseModel):
    """RFC 9457 response when a warehouse still has dependent records."""

    type: str
    title: str
    status: int
    detail: str
    blocking_dependencies: dict[str, int] = Field(alias="blockingDependencies")


class WarehouseProblem(BaseModel):
    """RFC 9457 response for ordinary warehouse endpoint failures."""

    type: str
    title: str
    status: int
    detail: str


# ---------------------------------------------------------------------------
# Cascade Delete Schemas
# ---------------------------------------------------------------------------


class WarehouseDeletePreviewWarehouse(BaseModel):
    id: UUID
    name: str
    address: str
    owner_company_id: UUID | None = None
    owner_company_name: str | None = None
    owner_company_type: str | None = None


class WarehouseCascadeCounts(BaseModel):
    products: int = 0
    marks: int = 0
    models: int = 0
    modifications: int = 0
    characteristics: int = 0
    characteristic_groups: int = 0
    trims: int = 0
    characteristic_values: int = 0
    images: int = 0
    cart_items: int = 0
    favorites: int = 0
    access_rules: int = 0
    storefront_bindings: int = 0


class WarehouseCascadeRetainedItem(BaseModel):
    type: str
    name: str
    reason: str


class WarehouseCascadeBlockerItem(BaseModel):
    type: str
    title: str
    detail: str
    count: int = 0


class WarehouseDeletePreviewResponse(BaseModel):
    warehouse: WarehouseDeletePreviewWarehouse
    counts: WarehouseCascadeCounts
    retained: list[WarehouseCascadeRetainedItem] = Field(default_factory=list)
    blockers: list[WarehouseCascadeBlockerItem] = Field(default_factory=list)
    can_delete: bool
    catalog_revision: int
    preview_token: str


class WarehouseCascadeDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmation: str
    preview_token: str

    @model_validator(mode="after")
    def validate_confirmation_word(self) -> WarehouseCascadeDeleteRequest:
        if self.confirmation != "УДАЛИТЬ":
            raise ValueError('Для подтверждения каскадного удаления необходимо ввести "УДАЛИТЬ"')
        return self


class WarehouseCascadeDeleteResponse(BaseModel):
    warehouse_id: UUID
    deleted: dict[str, int]
    retained: list[WarehouseCascadeRetainedItem] = Field(default_factory=list)
    catalog_revision: int
    media_cleanup: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None

