"""Pydantic schemas for the distributor admin API (B3)."""

from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Vehicle IO (subset of the admin schemas — distributors get a narrower
# field set than full admins).
# ---------------------------------------------------------------------------


class DistributorVehicleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vin: str | None = Field(default=None, max_length=20)
    dealer_id: UUID | None = None
    mark_id: str = Field(min_length=1, max_length=50)
    model_id: str = Field(min_length=1, max_length=50)
    generation_id: str | None = Field(default=None, max_length=50)
    configuration_id: str | None = Field(default=None, max_length=50)
    complectation_id: str | None = Field(default=None, max_length=50)
    year: int | None = Field(default=None, ge=1950, le=2100)
    base_price: Decimal | None = None
    special_price: Decimal | None = None
    discount_price: Decimal | None = None
    color: str | None = Field(default=None, max_length=100)
    color_inter: str | None = Field(default=None, max_length=100)
    status: str | None = "available"
    is_available: bool | None = True
    images: list[str] | None = None


class DistributorVehicleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vin: str | None = Field(default=None, max_length=20)
    dealer_id: UUID | None = None
    mark_id: str | None = Field(default=None, max_length=50)
    model_id: str | None = Field(default=None, max_length=50)
    generation_id: str | None = Field(default=None, max_length=50)
    configuration_id: str | None = Field(default=None, max_length=50)
    complectation_id: str | None = Field(default=None, max_length=50)
    year: int | None = Field(default=None, ge=1950, le=2100)
    base_price: Decimal | None = None
    special_price: Decimal | None = None
    discount_price: Decimal | None = None
    color: str | None = Field(default=None, max_length=100)
    color_inter: str | None = Field(default=None, max_length=100)
    status: str | None = None
    is_available: bool | None = None
    images: list[str] | None = None


class DistributorVehicleOut(BaseModel):
    id: str
    vin: str | None = None
    dealer_id: str | None = None
    mark_id: str | None = None
    mark_name: str | None = None
    model_id: str | None = None
    model_name: str | None = None
    generation_id: str | None = None
    configuration_id: str | None = None
    complectation_id: str | None = None
    year: int | None = None
    base_price: Decimal | None = None
    special_price: Decimal | None = None
    discount_price: Decimal | None = None
    color: str | None = None
    color_inter: str | None = None
    status: str | None = None
    purchase_pending: bool = False
    sale_completed: bool = False
    reserved_until: _dt.datetime | None = None
    is_available: bool | None = None
    images: list[str] | dict | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class PaginationOut(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class DistributorVehicleListResponse(BaseModel):
    vehicles: list[DistributorVehicleOut]
    pagination: PaginationOut


class DistributorVehicleResponse(BaseModel):
    vehicle: DistributorVehicleOut
    message: str | None = None


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------


class DistributorBulkUpdateFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str | None = None
    base_price: Decimal | None = None
    special_price: Decimal | None = None
    discount_price: Decimal | None = None
    is_available: bool | None = None


class DistributorVehiclesPatchRequest(BaseModel):
    """Bulk-update body: `{ids, patch}` per REST conventions §5."""

    model_config = ConfigDict(extra="ignore")

    ids: list[UUID] = Field(min_length=1)
    patch: DistributorBulkUpdateFields


class DistributorVehiclesDeleteRequest(BaseModel):
    """Bulk-delete body: `{ids}` for `DELETE /distributor/vehicles` with body."""

    model_config = ConfigDict(extra="forbid")

    ids: list[UUID] = Field(min_length=1)


class DistributorBulkUpdateResponse(BaseModel):
    message: str
    updated_count: int
    vehicles: list[DistributorVehicleOut] = []


class DistributorBulkDeleteResponse(BaseModel):
    message: str
    deleted_count: int
    ids: list[UUID] = []


class BulkImportRowErrorOut(BaseModel):
    row: int
    reason: str
    vin: str | None = None


class DistributorBulkImportResponse(BaseModel):
    imported: int
    total_rows: int
    errors: list[BulkImportRowErrorOut] = []


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


class DistributorApplicationOut(BaseModel):
    id: str
    status: str | None = None
    total_amount: float | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None
    company_id: str | None = None
    vehicles_count: int


class DistributorApplicationsListResponse(BaseModel):
    applications: list[DistributorApplicationOut]
    pagination: PaginationOut


# ---------------------------------------------------------------------------
# Profile + analytics
# ---------------------------------------------------------------------------


class DistributorProfileUserBlock(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    phone: str | None = None
    role: str | None = None
    company_id: str | None = None


class DistributorProfileCompanyBlock(BaseModel):
    id: str
    name: str
    inn: str | None = None
    company_type: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    is_active: bool | None = None


class DistributorProfileBlock(BaseModel):
    id: str
    company_id: str | None = None
    regions: list | dict | None = None
    brands: list | dict | None = None
    is_active: bool | None = None


class DistributorProfileBody(BaseModel):
    user: DistributorProfileUserBlock
    company: DistributorProfileCompanyBlock | None = None
    distributor: DistributorProfileBlock | None = None


class DistributorProfileResponse(BaseModel):
    profile: DistributorProfileBody


class DistributorAnalyticsByMarkItem(BaseModel):
    mark: str
    count: int


class DistributorAnalyticsTimelineItem(BaseModel):
    period: str | None = None
    count: int


class DistributorAnalyticsBody(BaseModel):
    by_status: dict[str, int] = Field(default_factory=dict)
    by_mark: list[DistributorAnalyticsByMarkItem] = Field(default_factory=list)
    timeline: list[DistributorAnalyticsTimelineItem] = Field(default_factory=list)


class DistributorAnalyticsResponse(BaseModel):
    analytics: DistributorAnalyticsBody


class WarehouseAnalyticsStatusItem(BaseModel):
    status: str
    count: int
    value: float


class WarehouseAnalyticsMarkItem(BaseModel):
    mark: str
    count: int
    value: float


class WarehouseAnalyticsDealerItem(BaseModel):
    dealer_id: str
    dealer_name: str
    count: int
    value: float


class WarehouseAnalyticsCityItem(BaseModel):
    city: str
    count: int
    value: float


class WarehouseAnalyticsTimelineItem(BaseModel):
    period: str | None = None
    status: str
    count: int


class WarehouseAnalyticsBody(BaseModel):
    total_vehicles: int
    total_value: float
    total_dealers: int
    by_status: list[WarehouseAnalyticsStatusItem] = Field(default_factory=list)
    by_mark: list[WarehouseAnalyticsMarkItem] = Field(default_factory=list)
    by_dealer: list[WarehouseAnalyticsDealerItem] = Field(default_factory=list)
    by_city: list[WarehouseAnalyticsCityItem] = Field(default_factory=list)
    timeline: list[WarehouseAnalyticsTimelineItem] = Field(default_factory=list)


class DistributorWarehouseAnalyticsResponse(BaseModel):
    analytics: WarehouseAnalyticsBody


# ---------------------------------------------------------------------------
# Dealers, support programs
# ---------------------------------------------------------------------------


class DistributorDealerOut(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    phone: str | None = None
    role: str | None = None
    company_id: str | None = None


class DistributorDealersListResponse(BaseModel):
    dealers: list[DistributorDealerOut]
    pagination: PaginationOut


class DistributorDealerPatchRequest(BaseModel):
    """Partial update of a dealer within the distributor scope."""

    model_config = ConfigDict(extra="ignore")

    status: str | None = Field(default=None)


class DistributorDealerPatchResponse(BaseModel):
    id: str
    status: str
    is_active: bool


class AssignableDealerOut(BaseModel):
    id: UUID
    name: str
    inn: str | None = None
    brands: list[str] = Field(default_factory=list)


class AssignableDealerGroupOut(BaseModel):
    id: UUID
    name: str
    dealers: list[AssignableDealerOut] = Field(default_factory=list)


class AssignableDealerGroupsResponse(BaseModel):
    groups: list[AssignableDealerGroupOut] = Field(default_factory=list)


class AssignDealerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dealer_group_id: UUID
    dealer_company_id: UUID


class AssignDealerResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    application: dict


class DistributorSupportProgramOut(BaseModel):
    id: str
    name: str
    mark_id: str | None = None
    mark_ids: list[str] = Field(default_factory=list)
    mark_name: str | None = None
    model_id: str | None = None
    model_ids: list[str] = Field(default_factory=list)
    model_name: str | None = None
    complectation_ids: list[str] = Field(default_factory=list)
    vin: str | None = None
    vins: list[str] = Field(default_factory=list)
    distributor_id: str | None = None
    distributor_ids: list[UUID] = Field(default_factory=list)
    distributor_name: str | None = None
    distributors: list[dict] = Field(default_factory=list)
    leasing_company_ids: list[UUID] = Field(default_factory=list)
    leasing_companies: list[dict] = Field(default_factory=list)
    support_type: str | None = None
    support_params: dict = Field(default_factory=dict)
    compensation_templates: list[dict] = Field(default_factory=list)
    is_active: bool | None = None
    status: str | None = None
    show_to_leasing_company: bool | None = None
    show_to_client: bool | None = None
    comment: str | None = None
    production_date_from: _dt.date | None = None
    production_date_to: _dt.date | None = None
    delivery_date_from: _dt.date | None = None
    delivery_date_to: _dt.date | None = None
    starts_at: _dt.date | None = None
    ends_at: _dt.date | None = None


class DistributorSupportProgramsListResponse(BaseModel):
    items: list[DistributorSupportProgramOut]
    pagination: PaginationOut


# ---------------------------------------------------------------------------
# Applications grouped / application vehicles / available vehicles
# ---------------------------------------------------------------------------


class DistributorApplicationsGroupedResponse(BaseModel):
    applications: dict[str, list[DistributorApplicationOut]] = Field(
        default_factory=dict
    )


class ApplicationVehicleInner(BaseModel):
    id: UUID | None = None
    vin: str | None = None
    status: str | None = None
    dealer_id: UUID | None = None
    base_price: float | None = None
    discount_price: float | None = None
    mark_id: str | None = None
    model_id: str | None = None
    mark_name: str | None = None
    model_name: str | None = None


class DistributorApplicationVehicleOut(BaseModel):
    id: str
    application_id: uuid.UUID
    vehicle_id: str | None = None
    quantity: int | None = None
    total_price: float | None = None
    unit_price: float | None = None
    vin: str | None = None
    is_model_order: bool | None = None
    vehicle: ApplicationVehicleInner | None = None


class DistributorApplicationVehiclesResponse(BaseModel):
    vehicles: list[DistributorApplicationVehicleOut]


class AddApplicationVehicleRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vehicle_id: UUID
    quantity: int = Field(default=1, ge=1, le=1000)


class ReplaceApplicationVehicleRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    new_vehicle_id: UUID


class AvailableVehiclesForAppResponse(BaseModel):
    vehicles: list[DistributorVehicleOut]


# ---------------------------------------------------------------------------
# Model orders
# ---------------------------------------------------------------------------


class ModelOrdersStatsBody(BaseModel):
    pending: int
    assigned: int
    total: int


class ModelOrdersStatsResponse(BaseModel):
    stats: ModelOrdersStatsBody


# ---------------------------------------------------------------------------
# Import preview (dry-run)
# ---------------------------------------------------------------------------


class ImportPreviewSampleItem(BaseModel):
    vin: str
    mark: str | None = None
    model: str | None = None
    generation: str | None = None
    price: float
    has_vin: bool


class ImportPreviewResponse(BaseModel):
    total_rows: int
    vehicles_count: int
    rows_without_vin: int
    unique_marks: int
    unique_models: int
    sample_data: list[ImportPreviewSampleItem] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Simple messages
# ---------------------------------------------------------------------------


class DistributorMessageResponse(BaseModel):
    message: str
    id: str | None = None
    vehicle_id: str | None = None
    application_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Brands / vehicle history
# ---------------------------------------------------------------------------


class DistributorBrandsResponse(BaseModel):
    """Flat list of distinct mark display names in the distributor scope."""

    brands: list[str] = Field(default_factory=list)


class DistributorVehicleHistoryEntry(BaseModel):
    action: str
    status: str | None = None
    timestamp: _dt.datetime | None = None
    user_id: str | None = None


class DistributorVehicleHistoryResponse(BaseModel):
    """Change history for a distributor-scoped vehicle.

    Currently derived from ``vehicles.created_at`` / ``updated_at``. Schema
    is forward-compatible with a future dedicated status-history table.
    """

    history: list[DistributorVehicleHistoryEntry] = Field(default_factory=list)
