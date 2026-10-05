"""Public HTTP contracts for the corrected special-equipment catalog."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

UsageMetric = Literal["mileage_km", "engine_hours"]
EquipmentCondition = Literal["new", "used"]


class SpecialEquipmentCategoryLink(BaseModel):
    id: UUID
    code: str
    name: str
    slug: str


class SpecialEquipmentCategoryResource(SpecialEquipmentCategoryLink):
    usage_metric: UsageMetric
    is_attachment_category: bool
    sort_order: int
    product_count: int = Field(ge=0)
    image_url: str | None
    parent_ids: list[UUID] = Field(default_factory=list)
    child_ids: list[UUID] = Field(default_factory=list)


class SpecialEquipmentCategoryPlacement(BaseModel):
    parent_id: UUID
    category_id: UUID
    sort_order: int = Field(ge=0)


class SpecialEquipmentCategoriesResponse(BaseModel):
    items: list[SpecialEquipmentCategoryResource]
    placements: list[SpecialEquipmentCategoryPlacement]
    root_items: list[SpecialEquipmentCategoryResource]


class SpecialEquipmentCategoryPathResponse(BaseModel):
    items: list[SpecialEquipmentCategoryLink]
    category: SpecialEquipmentCategoryResource


class SpecialEquipmentMarkResource(BaseModel):
    id: UUID
    code: str
    name: str
    slug: str


class SpecialEquipmentMarksResponse(BaseModel):
    items: list[SpecialEquipmentMarkResource]


class SpecialEquipmentModelLink(BaseModel):
    id: UUID
    code: str
    name: str
    slug: str
    mark: SpecialEquipmentMarkResource


class SpecialEquipmentModificationLink(BaseModel):
    id: UUID
    code: str
    name: str
    slug: str
    year_from: int | None
    year_to: int | None
    model: SpecialEquipmentModelLink


class SpecialEquipmentCapabilities(BaseModel):
    can_favorite: bool
    can_add_to_cart: bool
    can_lease: bool
    can_buy: bool
    can_preorder: bool


class SpecialEquipmentImageResource(BaseModel):
    id: UUID
    content_url: str
    alt_text: str | None


class SpecialEquipmentGalleryImageResource(SpecialEquipmentImageResource):
    sort_order: int
    is_primary: bool


class SpecialEquipmentColorRef(BaseModel):
    id: UUID
    name: str


class SpecialEquipmentTrimRef(BaseModel):
    id: UUID
    name: str


class SpecialEquipmentWarehouseStock(BaseModel):
    warehouse_id: UUID
    address: str
    brand: str
    owner_company_name: str
    count: int = Field(ge=1)


class SpecialEquipmentCardAttributeResource(BaseModel):
    id: UUID
    code: str
    name: str
    data_type: Literal["number", "text", "boolean", "select"]
    unit: str | None
    group_id: UUID | None
    group_name: str
    value: str | bool | None
    display_value: str
    option_id: UUID | None
    option_label: str | None


class SpecialEquipmentSuperstructureRef(BaseModel):
    id: UUID
    name: str
    type_name: str | None = None
    manufacturer: str | None = None


class SpecialEquipmentProductCard(BaseModel):
    id: UUID
    code: str
    slug: str
    detail_url: str | None = None
    title: str | None = None
    model: SpecialEquipmentModelLink | None = None
    modification: SpecialEquipmentModificationLink | None = None
    superstructure: SpecialEquipmentSuperstructureRef | None = None
    condition: EquipmentCondition
    owners_count: int | None
    mileage_km: int | None
    engine_hours: int | None
    price: str | None
    base_price: str | None
    special_price: str | None
    price_on_request: bool = False
    price_from: str | None = None
    currency_code: Literal["RUB"]
    manufacture_year: int | None
    sale_status: Literal["available", "on_order", "reserved", "sold", "unavailable"]
    trim: SpecialEquipmentTrimRef | None = None
    body_color: SpecialEquipmentColorRef | None = None
    interior_color: SpecialEquipmentColorRef | None = None
    available_count: int = Field(ge=1)
    warehouse_city_name: str | None = None
    warehouse_stock: list[SpecialEquipmentWarehouseStock] = Field(
        default_factory=list
    )
    categories: list[SpecialEquipmentCategoryLink]
    terminal_category: SpecialEquipmentCategoryLink | None = None
    card_attributes: list[SpecialEquipmentCardAttributeResource] = Field(
        default_factory=list,
        max_length=6,
    )
    primary_image: SpecialEquipmentImageResource | None
    capabilities: SpecialEquipmentCapabilities
    normalization_state: Literal["normalized"] = "normalized"


class SpecialEquipmentFacetMark(BaseModel):
    id: UUID
    name: str
    count: int


class SpecialEquipmentFacetModel(BaseModel):
    id: UUID
    name: str
    mark_id: UUID
    count: int


class SpecialEquipmentFacetModification(BaseModel):
    id: UUID
    name: str
    model_id: UUID
    count: int


class SpecialEquipmentFacetTrim(BaseModel):
    id: UUID
    name: str
    modification_id: UUID
    count: int


class SpecialEquipmentColorFacet(BaseModel):
    id: UUID
    name: str
    count: int


class SpecialEquipmentFacetSuperstructure(BaseModel):
    id: UUID
    name: str
    count: int


class SpecialEquipmentAvailabilityFacets(BaseModel):
    available: int
    on_order: int


class SpecialEquipmentFacetPrice(BaseModel):
    min: str | None
    max: str | None


class SpecialEquipmentFacetOption(BaseModel):
    value: str
    label: str
    count: int


class SpecialEquipmentAttributeFacet(BaseModel):
    id: UUID
    code: str
    name: str
    data_type: Literal["number", "text", "boolean", "select"]
    filter_kind: Literal["exact", "range", "search"]
    unit: str | None
    group_id: UUID | None
    group_name: str
    min: str | None
    max: str | None
    options: list[SpecialEquipmentFacetOption]


class SpecialEquipmentAttributeFacetGroup(BaseModel):
    id: UUID | None
    name: str
    sort_order: int
    attributes: list[SpecialEquipmentAttributeFacet]


class SpecialEquipmentConditionFacets(BaseModel):
    new: int
    used: int


class SpecialEquipmentUsageFacet(BaseModel):
    metric: UsageMetric | None
    min: int | None
    max: int | None


class SpecialEquipmentCityFacet(BaseModel):
    id: UUID
    name: str
    count: int


class SpecialEquipmentWarehouseFacet(BaseModel):
    id: UUID
    city_id: UUID | None
    city_name: str | None
    address: str
    brand: str | None
    count: int


class SpecialEquipmentFacets(BaseModel):
    marks: list[SpecialEquipmentFacetMark]
    models: list[SpecialEquipmentFacetModel]
    modifications: list[SpecialEquipmentFacetModification]
    trims: list[SpecialEquipmentFacetTrim]
    superstructures: list[SpecialEquipmentFacetSuperstructure] = Field(
        default_factory=list
    )
    body_colors: list[SpecialEquipmentColorFacet]
    interior_colors: list[SpecialEquipmentColorFacet]
    availability: SpecialEquipmentAvailabilityFacets
    conditions: SpecialEquipmentConditionFacets
    price: SpecialEquipmentFacetPrice
    usage: SpecialEquipmentUsageFacet
    attribute_groups: list[SpecialEquipmentAttributeFacetGroup]
    cities: list[SpecialEquipmentCityFacet]
    warehouses: list[SpecialEquipmentWarehouseFacet]


class SpecialEquipmentPagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class SpecialEquipmentProductsResponse(BaseModel):
    items: list[SpecialEquipmentProductCard]
    pagination: SpecialEquipmentPagination
    facets: SpecialEquipmentFacets


class SpecialEquipmentAttributeSourceResource(BaseModel):
    id: UUID
    code: str
    display_name: str


class SpecialEquipmentAttributeResource(BaseModel):
    id: UUID
    code: str
    name: str
    data_type: Literal["number", "text", "boolean", "select"]
    unit: str | None
    group_id: UUID | None
    group_name: str
    value: str | bool | None
    display_value: str
    option_id: UUID | None
    option_label: str | None
    source_product: SpecialEquipmentAttributeSourceResource | None = None


class SpecialEquipmentAttributeResourceGroup(BaseModel):
    id: UUID | None
    name: str
    section: Literal["chassis", "superstructure"] | None = None
    attributes: list[SpecialEquipmentAttributeResource]


class SpecialEquipmentProductDetail(SpecialEquipmentProductCard):
    description: str | None
    attributes: list[SpecialEquipmentAttributeResource]
    attribute_groups: list[SpecialEquipmentAttributeResourceGroup]
    trim_attribute_groups: list[SpecialEquipmentAttributeResourceGroup] = Field(
        default_factory=list
    )
    images: list[SpecialEquipmentGalleryImageResource]


class SpecialEquipmentProductImagesResponse(BaseModel):
    items: list[SpecialEquipmentGalleryImageResource]


class SpecialEquipmentCompatibleAttachmentResource(BaseModel):
    position: int = Field(ge=0)
    primary_category: SpecialEquipmentCategoryLink | None
    product: SpecialEquipmentProductCard


class SpecialEquipmentCompatibleAttachmentsResponse(BaseModel):
    items: list[SpecialEquipmentCompatibleAttachmentResource]


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
