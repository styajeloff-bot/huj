"""Pydantic schemas for the leasing applications API (Phase 3)."""

from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from domain.application_sources import ApplicationCreationSource
from presentation.schemas.common import NonBlankAddress
from presentation.schemas.companies import SopdSignerCandidate


class ApplicationVehicleRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: UUID | None = None
    modification_id: str | None = None
    allow_overstock: bool = False
    quantity: int = Field(default=1, ge=1, le=2147483647)
    custom_price: Decimal | None = None
    comment: str | None = None
    leasing_purpose: str | None = None
    leasing_purposes: list[Annotated[str, Field(min_length=1, max_length=255)]] | None = None
    regions: list[str] = Field(default_factory=list)
    region: str | None = None
    is_model_order: bool = False
    equipments: list[ApplicationEquipmentOption] = Field(default_factory=list)
    services: list[ApplicationServiceOption] = Field(default_factory=list)


class ApplicationEquipmentOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    equipment_code: str = Field(min_length=1, max_length=64)
    price: Decimal = Field(default=Decimal("0"), ge=0)
    comment: str | None = None


class ApplicationServiceOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    service_code: str = Field(min_length=1, max_length=64)
    price: Decimal = Field(default=Decimal("0"), ge=0)
    comment: str | None = None


class AdditionalOptionsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_vehicle_id: UUID
    equipments: list[ApplicationEquipmentOption] = Field(default_factory=list)
    services: list[ApplicationServiceOption] = Field(default_factory=list)


class AdditionalOptionsUpdatedVehicle(BaseModel):
    model_config = ConfigDict(extra="allow")

    equipments: list[ApplicationEquipmentOption] = Field(default_factory=list)
    services: list[ApplicationServiceOption] = Field(default_factory=list)


class AdditionalOptionsUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str
    application_vehicle: AdditionalOptionsUpdatedVehicle
    application: dict[str, Any]


class DraftCalculationPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: float | None = None
    lease_term_months: int | None = None
    monthly_payment: Decimal | None = None
    total_cost: Decimal | None = None
    markup: Decimal | None = None
    rate: Decimal | None = None
    total_interest: Decimal | None = None
    buyout_amount: Decimal | None = None
    vat_refund: Decimal | None = None
    profit_tax_savings: Decimal | None = None
    total_savings: Decimal | None = None
    selected_support: dict[str, list[str]] | None = None
    support_per_vehicle: list[dict[str, Any]] | None = None
    support_per_program: list[dict[str, Any]] | None = None
    support_program_details: list[dict[str, Any]] | None = None
    calculations_per_vehicle: list[dict[str, Any]] | None = None


class DraftCompanyInfoRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    full_name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: NonBlankAddress | None = None
    actual_address: NonBlankAddress | None = None
    phone: str | None = None
    email: str | None = None
    manager_name: str | None = None
    entity_type: str | None = None


class CreateApplicationInitRequest(BaseModel):
    """POST /applications."""

    model_config = ConfigDict(extra="ignore")

    source_type: ApplicationCreationSource

    company_id: UUID | None = None
    company: DraftCompanyInfoRequest | None = None
    name: str = ""
    email: str = ""
    vehicles: list[ApplicationVehicleRequest] = Field(default_factory=list)
    calculation: DraftCalculationPayload | None = None


class ApplicationItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: UUID
    kind: Literal["vehicle", "special_equipment"]
    leasing_purpose: str | None = None
    leasing_purposes: list[Annotated[str, Field(min_length=1, max_length=255)]] | None = None
    regions: list[str] = Field(default_factory=list)
    region: str | None = None
    comment: str | None = Field(default=None, max_length=2000)


class UpdateApplicationItemsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ApplicationItemUpdateRequest] = Field(default_factory=list)


class UpdateApplicationItemsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    items: list[ApplicationItemUpdateRequest]


class UpdateConditionsRequest(BaseModel):
    """PUT /applications/{id}/conditions."""

    model_config = ConfigDict(extra="ignore")

    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: float | None = None
    lease_term_months: int | None = None
    monthly_payment: Decimal | None = None
    total_cost: Decimal | None = None
    markup: Decimal | None = None
    rate: Decimal | None = None
    total_interest: Decimal | None = None
    buyout_amount: Decimal | None = None
    vat_refund: Decimal | None = None
    profit_tax_savings: Decimal | None = None
    total_savings: Decimal | None = None
    selected_support: dict[str, list[str]] | None = None
    support_per_vehicle: list[dict[str, Any]] | None = None
    support_per_program: list[dict[str, Any]] | None = None
    support_program_details: list[dict[str, Any]] | None = None
    calculations_per_vehicle: list[dict[str, Any]] | None = None


class UpdateCompanyRequest(BaseModel):
    """PUT /applications/{id}/company."""

    model_config = ConfigDict(extra="ignore")

    company_id: UUID


class UpdateVehiclesRequest(BaseModel):
    """PUT /applications/{id}/vehicles."""

    model_config = ConfigDict(extra="ignore")

    vehicles: list[ApplicationVehicleRequest] = Field(default_factory=list)
    vehicle_calculations: list[dict[str, Any]] | None = None


class UpdateLeasingCompaniesRequest(BaseModel):
    """PUT /applications/{id}/leasing-companies."""

    model_config = ConfigDict(extra="ignore")

    leasing_company_ids: list[UUID] = Field(default_factory=list)


class AttachDocumentsRequest(BaseModel):
    """POST /applications/{id}/documents/attach."""

    model_config = ConfigDict(extra="ignore")

    document_ids: list[UUID] = Field(default_factory=list)


class AttachDocumentsResponse(BaseModel):
    application_id: uuid.UUID
    linked_document_ids: list[UUID] = Field(default_factory=list)
    skipped_document_ids: list[UUID] = Field(default_factory=list)


class UpdateQuestionnaireRequest(BaseModel):
    """PUT /applications/{id}/questionnaire."""

    model_config = ConfigDict(extra="allow")


class LeasingPurposeResponse(BaseModel):
    purpose_name: str
    purpose_display_name: str


class LeasingPurposesResponse(BaseModel):
    purposes: list[LeasingPurposeResponse] = Field(default_factory=list)


class LeasingRegionResponse(BaseModel):
    region_name: str
    region_display_name: str
    region_number: str


class LeasingRegionsResponse(BaseModel):
    regions: list[LeasingRegionResponse] = Field(default_factory=list)


class ApplicationSubresourceResponse(BaseModel):
    """Common shape for sub-resource PUTs (conditions/company/vehicles/LCs)."""

    model_config = ConfigDict(extra="allow")

    message: str
    application: dict[str, Any]


class QuestionnaireUpdateResponse(BaseModel):
    """PUT /applications/{id}/questionnaire — returns upserted row."""

    model_config = ConfigDict(extra="allow")

    message: str
    questionnaire: dict[str, Any] | None = None


class StatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["active", "rejected", "issued"] = Field(min_length=1, max_length=50)


class AssignVinRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: UUID


class ApplicationItemBase(BaseModel):
    """Common item projection backed by an FK-correct domain line."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    item_id: UUID | None = None
    title: str
    image_url: str | None = None
    detail_url: str | None = None
    allow_overstock: bool = False
    quantity: int = Field(default=1, ge=1, le=2147483647)
    unit_price: Decimal | None = None
    total_price: Decimal | None = None
    currency_code: str = Field(default="RUB", min_length=3, max_length=3)
    status: str | None = None
    snapshot: dict[str, Any] | None = None
    leasing_purpose: str | None = None
    leasing_purposes: list[str] | None = None
    regions: list[str] = Field(default_factory=list)
    region: str | None = None
    comment: str | None = None


class ApplicationVehicleItem(ApplicationItemBase):
    type: Literal["vehicle"]
    catalog_price: Decimal | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    discount_amount: Decimal | None = None
    markup_type: str | None = None
    markup_value: Decimal | None = None
    markup_amount: Decimal | None = None
    final_price: Decimal | None = None
    show_catalog_price: bool = True
    dealer_comment: str | None = None


class ApplicationSpecialEquipmentItem(ApplicationItemBase):
    type: Literal["special_equipment"]
    item_id: UUID
    item_role: Literal["offer", "attachment", "component"] = "offer"
    seller_company_id: UUID | None = None
    snapshot: dict[str, Any]
    price_on_request: bool = False
    price_status: Literal["none", "pending", "set"] = "none"
    price_set_by: UUID | None = None
    price_set_at: _dt.datetime | None = None
    overstock_requested_quantity: int = 0
    product_ids: list[UUID] = Field(default_factory=list)


class DealerApplicationItemPriceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agreed_price: Decimal | None = None


class DealerApplicationItemPriceResponse(BaseModel):
    item_id: UUID
    application_id: UUID
    agreed_price: Decimal
    currency: str = Field(min_length=3, max_length=3)
    status: Literal["price_set"]
    price_set_by: UUID
    price_set_at: _dt.datetime
    application_total_amount: Decimal


class DealerApplicationItemPriceError(BaseModel):
    error_code: str
    message: str


ApplicationItem = Annotated[
    ApplicationVehicleItem | ApplicationSpecialEquipmentItem,
    Field(discriminator="type"),
]


_COMMERCE_TOTAL_FIELDS = (
    "total_items_price",
    "total_special_equipment_price",
)
_COMMERCE_ITEM_MONEY_FIELDS = ("unit_price", "total_price")


def application_commerce_money_to_wire(
    application: dict[str, Any],
) -> dict[str, Any]:
    """Stringify only newly introduced commerce money fields.

    Existing application endpoints historically encode their legacy Decimal
    fields as JSON numbers. Keeping the conversion narrowly scoped avoids a
    breaking response change while giving ``items`` exact decimal strings.
    """

    payload = dict(application)
    for field_name in _COMMERCE_TOTAL_FIELDS:
        value = payload.get(field_name)
        if isinstance(value, Decimal):
            payload[field_name] = str(value)

    items = payload.get("items")
    if isinstance(items, list):
        wire_items: list[Any] = []
        for item in items:
            if not isinstance(item, dict):
                wire_items.append(item)
                continue
            wire_item = dict(item)
            for field_name in _COMMERCE_ITEM_MONEY_FIELDS:
                value = wire_item.get(field_name)
                if isinstance(value, Decimal):
                    wire_item[field_name] = str(value)
            wire_items.append(wire_item)
        payload["items"] = wire_items
    return payload


class AssignmentAuditActorOut(BaseModel):
    id: UUID
    name: str | None = None


class AssignedDealerOut(BaseModel):
    id: UUID
    name: str | None = None
    inn: str | None = None


class ApplicationDealerAllocationOut(BaseModel):
    dealer: AssignedDealerOut
    quantity: int


class ApplicationDealerDistributionOut(BaseModel):
    application_vehicle_id: UUID
    title: str
    quantity: int
    stock_dealer: AssignedDealerOut | None = None
    dealer_allocations: list[ApplicationDealerAllocationOut] = Field(default_factory=list)
    unassigned_quantity: int
    can_assign_dealer: bool


class AssignedApplicationEmployeeOut(BaseModel):
    id: UUID
    name: str | None = None
    phone: str | None = None
    sub_role: str | None = None


class ApplicationWarehouseOut(BaseModel):
    id: UUID
    address: str | None = None
    brand: str | None = None
    city: str | None = None
    company_id: UUID | None = None
    company_name: str | None = None


class ApplicationVehicleDetailOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID
    can_manage_whole_vehicle: bool = True
    equipments: list[ApplicationEquipmentOption] = Field(default_factory=list)
    services: list[ApplicationServiceOption] = Field(default_factory=list)
    discount_show_catalog_price: bool = True
    markup_show_catalog_price: bool = True
    show_catalog_price: bool = True
    warehouse: ApplicationWarehouseOut | None = None
    dealer_company_id: UUID | None = None
    assigned_dealer: AssignedDealerOut | None = None
    stock_dealer: AssignedDealerOut | None = None
    dealer_assigned_by_id: UUID | None = None
    dealer_assigned_by: AssignmentAuditActorOut | None = None
    dealer_assigned_at: _dt.datetime | None = None
    primary_employee_id: UUID | None = None
    primary_employee: AssignedApplicationEmployeeOut | None = None
    additional_employee_id: UUID | None = None
    additional_employee: AssignedApplicationEmployeeOut | None = None
    employees_assigned_by_id: UUID | None = None
    employees_assigned_by: AssignmentAuditActorOut | None = None
    employees_assigned_at: _dt.datetime | None = None
    vin: str | None = None


class ApplicationSummary(BaseModel):
    """Minimal application summary returned from /applications/."""

    model_config = ConfigDict(extra="allow")

    id: UUID
    source_type: str | None = None
    dealer_distribution: list[ApplicationDealerDistributionOut] = Field(default_factory=list)
    company_id: UUID | None = None
    status: str | None = None
    application_status: str | None = None
    application_status_label: str | None = None
    group_status: str | None = None
    group_status_label: str | None = None
    name: str | None = None
    email: str | None = None
    selected_leasing_companies: list[UUID] = Field(default_factory=list)
    items: list[ApplicationItem] = Field(default_factory=list)
    items_count: int = 0
    special_equipment_count: int = 0
    vehicles_count: int = 0
    total_amount: Decimal | None = None
    total_items_price: Decimal | None = None
    total_special_equipment_price: Decimal | None = None
    total_vehicles_price: Decimal | None = None
    monthly_payment: Decimal | None = None
    created_at: _dt.datetime | None = None
    assigned_dealer_group_id: UUID | None = None
    assigned_dealer: AssignedDealerOut | None = None


class PaginationOut(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class ApplicationListResponse(BaseModel):
    applications: list[ApplicationSummary]
    total: int
    pagination: PaginationOut


class ApplicationCompanyDetailOut(BaseModel):
    """Application-scoped company projection."""

    model_config = ConfigDict(extra="allow")

    id: UUID
    name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    company_type: str | None = None
    phone: str | None = None
    email: str | None = None
    legal_address: str | None = None
    actual_address: str | None = None
    tax_system: str | None = None


class SopdSignerCandidatesResponse(BaseModel):
    candidates: list[SopdSignerCandidate] = Field(default_factory=list)


class ApplicationDetailResponse(BaseModel):
    """Full application detail returned from /applications/{id}."""

    model_config = ConfigDict(extra="allow")

    id: UUID
    source_type: str | None = None
    dealer_distribution: list[ApplicationDealerDistributionOut] = Field(default_factory=list)
    company_id: UUID | None = None
    company: ApplicationCompanyDetailOut | None = None
    status: str | None = None
    application_status: str | None = None
    application_status_label: str | None = None
    group_status: str | None = None
    group_status_label: str | None = None
    can_assign_dealer: bool = False
    assigned_dealer_group_id: UUID | None = None
    assigned_dealer: AssignedDealerOut | None = None
    dealer_assigned_by_id: UUID | None = None
    dealer_assigned_by: AssignmentAuditActorOut | None = None
    dealer_assigned_at: _dt.datetime | None = None
    primary_employee_id: UUID | None = None
    primary_employee: AssignedApplicationEmployeeOut | None = None
    additional_employee_id: UUID | None = None
    additional_employee: AssignedApplicationEmployeeOut | None = None
    employees_assigned_by_id: UUID | None = None
    employees_assigned_by: AssignmentAuditActorOut | None = None
    employees_assigned_at: _dt.datetime | None = None
    vehicles: list[ApplicationVehicleDetailOut] = Field(default_factory=list)
    items: list[ApplicationItem] = Field(default_factory=list)
    items_count: int = 0
    special_equipment_count: int = 0
    vehicles_count: int = 0
    total_items_price: Decimal | None = None
    total_special_equipment_price: Decimal | None = None
    total_vehicles_price: Decimal | None = None
    deal_date: _dt.date | None = None
    deal_documents: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)


class ApplicationEmployeeOut(BaseModel):
    id: UUID
    name: str | None = None
    phone: str | None = None
    sub_role: str | None = None


class ApplicationEmployeeSearchResponse(BaseModel):
    employees: list[ApplicationEmployeeOut] = Field(default_factory=list)


class AssignApplicationEmployeesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_employee_id: UUID | None = None
    additional_employee_id: UUID | None = None


class AssignApplicationEmployeesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    application: dict[str, Any]


class AssignApplicationVehicleEmployeesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    application_vehicle: dict[str, Any]


class CreateApplicationInitResponse(BaseModel):
    source_type: ApplicationCreationSource | None = None
    application_id: uuid.UUID
    status: str


class StatusUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str
    application: dict[str, Any]


class AvailableVinOut(BaseModel):
    id: UUID
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
    success: bool = True
    vehicles: list[AvailableVinOut]
    application_vehicle_id: UUID | None = None
    modification_id: str | None = None


class AssignVinResponse(BaseModel):
    success: bool
    message: str
    application_vehicle_id: UUID
    assigned_vin: str | None = None


class ClientProposalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["accepted", "rejected", "cancelled"] = Field(
        ..., description="Решение клиента по КП"
    )
    comment: str | None = Field(
        default=None,
        description=(
            "Комментарий клиента (опционально). При rejected — причина отказа."
        ),
        max_length=2000,
    )


class ClientProposalDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    proposal_id: UUID
    application_id: uuid.UUID
    leasing_company_application_id: UUID
    client_decision_action: str | None
    lca_status: str
    proposal: dict[str, Any] | None = None


class SelectLeasingCompanyResponse(BaseModel):
    application_id: uuid.UUID
    leasing_company_application_id: uuid.UUID
    status: str


class SopdStatusItem(BaseModel):
    signer_key: str | None = None
    signer_name: str
    signer_inn: str | None = None
    status: str
    signature_request_id: uuid.UUID


class SopdStatusListResponse(BaseModel):
    items: list[SopdStatusItem]
