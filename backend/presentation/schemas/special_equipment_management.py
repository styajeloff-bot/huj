"""Private HTTP contracts for special-equipment catalog management."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    WithJsonSchema,
    model_validator,
)

from domain.special_equipment_management import (
    SpecialEquipmentManagementValidationError,
    ensure_product_commercial_terms,
)

PublicationStatus = Literal["draft", "published", "archived"]
SaleStatus = Literal["available", "on_order", "reserved", "sold", "unavailable"]
UsageMetric = Literal["mileage_km", "engine_hours"]
EquipmentCondition = Literal["new", "used"]
AttributeDataType = Literal["number", "text", "boolean", "select"]
AttributeFilterKind = Literal["exact", "range", "search"]

_PRICE_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]{1,2})?$")


def _price(value: object) -> Decimal:
    if not isinstance(value, str) or not _PRICE_PATTERN.fullmatch(value):
        raise ValueError("Цена должна быть decimal-строкой с точностью до 2 знаков")
    return Decimal(value)


PriceInput = Annotated[
    Decimal,
    BeforeValidator(_price),
    Field(gt=0, max_digits=15, decimal_places=2),
    WithJsonSchema({"type": "string", "examples": ["3500000.00"]}),
]

SpecialPriceInput = Annotated[
    Decimal,
    BeforeValidator(_price),
    Field(gt=0, max_digits=15, decimal_places=2),
    WithJsonSchema({"type": "string", "examples": ["3250000.00"]}),
]

RequestPriceInput = Annotated[
    Decimal,
    BeforeValidator(_price),
    Field(gt=0, max_digits=15, decimal_places=2),
    WithJsonSchema({"type": "string", "examples": ["3000000.00"]}),
]


class RegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegistryPagination(RegistryModel):
    page: int
    page_size: int
    total: int
    pages: int


class CatalogSectionCountsResponse(RegistryModel):
    products: Annotated[int, Field(ge=0)]
    categories: Annotated[int, Field(ge=0)]
    marks: Annotated[int, Field(ge=0)]
    models: Annotated[int, Field(ge=0)]
    modifications: Annotated[int, Field(ge=0)]
    trims: Annotated[int, Field(ge=0)]
    attributes: Annotated[int, Field(ge=0)]
    attribute_groups: Annotated[int, Field(ge=0)]
    colors: Annotated[int, Field(ge=0)]
    units: Annotated[int, Field(ge=0)] = 0
    superstructures: Annotated[int, Field(ge=0)] = 0


class VersionedResource(RegistryModel):
    id: UUID
    code: str
    name: str
    slug: str
    is_active: bool
    lock_version: int
    updated_at: datetime


class NamedDirectoryRef(RegistryModel):
    id: UUID
    code: str
    name: str


ColorApplicability = Literal["body", "interior", "both"]


class ColorRef(RegistryModel):
    id: UUID
    name: str
    is_active: bool


class ColorResource(RegistryModel):
    id: UUID
    code: str
    name: str
    applicability: ColorApplicability
    is_active: bool
    lock_version: int
    created_at: datetime
    updated_at: datetime


class ColorSelectItem(RegistryModel):
    id: UUID
    name: str
    applicability: ColorApplicability


class ColorListResponse(RegistryModel):
    items: list[ColorResource]
    pagination: RegistryPagination


class ColorCreateRequest(RegistryModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    code: Annotated[str | None, Field(max_length=100)] = None
    applicability: ColorApplicability
    is_active: bool = True


class ColorPatchRequest(RegistryModel):
    name: Annotated[str | None, Field(max_length=255)] = None
    code: Annotated[str | None, Field(max_length=100)] = None
    applicability: ColorApplicability | None = None
    is_active: bool | None = None


class ColorSelectResponse(RegistryModel):
    items: list[ColorSelectItem]


class DirectoryCreateRequest(RegistryModel):
    code: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1, max_length=255)]
    is_active: bool = True


class DirectoryPatchRequest(RegistryModel):
    name: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    is_active: bool | None = None


class EffectiveCategoryAttributeResource(RegistryModel):
    attribute_id: UUID
    attribute_name: str
    data_type: AttributeDataType
    filter_kind: AttributeFilterKind
    group_id: UUID | None
    group_name: str
    group_sort_order: int
    is_required: bool
    is_filterable: bool
    is_visible: bool
    sort_order: int


class CategoryResource(VersionedResource):
    usage_metric: UsageMetric
    is_attachment_category: bool
    is_visible_in_catalog: bool = True
    sort_order: int
    canonical_path: str
    parent_ids: list[UUID] = Field(default_factory=list)
    child_ids: list[UUID] = Field(default_factory=list)
    parents: list[NamedDirectoryRef] = Field(default_factory=list)
    attribute_links: list[dict] = Field(default_factory=list)
    effective_attribute_links: list[EffectiveCategoryAttributeResource] = Field(
        default_factory=list
    )
    product_count: int = 0
    image_url: str | None = None


class CategoryListResponse(RegistryModel):
    items: list[CategoryResource]
    pagination: RegistryPagination


class CategoryCreateRequest(DirectoryCreateRequest):
    usage_metric: UsageMetric
    is_attachment_category: bool = False
    is_visible_in_catalog: bool = True
    sort_order: Annotated[int, Field(ge=0)] = 0
    parent_ids: Annotated[list[UUID], Field(max_length=20)] = Field(
        default_factory=list
    )
    attribute_links: Annotated[
        list[CategoryAttributeLinkInput], Field(max_length=300)
    ] = Field(default_factory=list)


class CategoryPatchRequest(DirectoryPatchRequest):
    usage_metric: UsageMetric | None = None
    is_attachment_category: bool | None = None
    is_visible_in_catalog: bool | None = None
    sort_order: Annotated[int | None, Field(ge=0)] = None
    parent_ids: Annotated[list[UUID] | None, Field(max_length=20)] = None
    attribute_links: Annotated[
        list[CategoryAttributeLinkInput] | None,
        Field(max_length=300),
    ] = None


class CategoryParentsReplaceRequest(RegistryModel):
    parent_ids: Annotated[list[UUID], Field(max_length=20)]

    @model_validator(mode="after")
    def unique_parents(self) -> CategoryParentsReplaceRequest:
        if len(self.parent_ids) != len(set(self.parent_ids)):
            raise ValueError("Родительскую категорию нельзя передать дважды")
        return self


class MarkResource(VersionedResource):
    model_count: int = 0


class MarkListResponse(RegistryModel):
    items: list[MarkResource]
    pagination: RegistryPagination


class MarkCreateRequest(DirectoryCreateRequest):
    pass


class MarkPatchRequest(DirectoryPatchRequest):
    pass


class ModelResource(VersionedResource):
    mark_id: UUID
    mark_name: str
    mark: NamedDirectoryRef
    category_id: UUID | None = None
    category_name: str | None = None
    category: NamedDirectoryRef | None = None
    modification_count: int = 0


class ModelListResponse(RegistryModel):
    items: list[ModelResource]
    pagination: RegistryPagination


class ModelCreateRequest(DirectoryCreateRequest):
    mark_id: UUID
    category_id: UUID


class ModelPatchRequest(DirectoryPatchRequest):
    mark_id: UUID | None = None
    category_id: UUID | None = None


class ModificationAttributeValueInput(RegistryModel):
    attribute_id: UUID
    option_id: UUID | None = None
    value: StrictBool | Decimal | StrictStr | None = None

    @model_validator(mode="after")
    def one_value(self) -> ModificationAttributeValueInput:
        if (self.option_id is None) == (self.value is None):
            raise ValueError("Укажите ровно option_id или value")
        return self


class ModificationResource(VersionedResource):
    model_id: UUID
    model_name: str
    mark_id: UUID
    mark_name: str
    model: dict
    year_from: int | None
    year_to: int | None
    category_ids: list[UUID] = Field(default_factory=list)
    categories: list[NamedDirectoryRef] = Field(default_factory=list)
    attribute_values: list[dict] = Field(default_factory=list)
    product_count: int = 0


class ModificationListResponse(RegistryModel):
    items: list[ModificationResource]
    pagination: RegistryPagination


class TrimAttributeLinkInput(RegistryModel):
    attribute_id: UUID
    group_id: UUID | None = None
    is_required: bool = False
    is_filterable: bool = False
    sort_order: Annotated[int, Field(ge=0)] = 0


class TrimAttributeValueInput(RegistryModel):
    attribute_id: UUID
    value_number: Decimal | None = None
    value_text: Annotated[str | None, Field(max_length=2000)] = None
    value_boolean: bool | None = None
    option_id: UUID | None = None


class TrimResource(VersionedResource):
    modification_id: UUID
    modification_name: str
    model_id: UUID
    model_name: str
    mark_id: UUID
    mark_name: str
    sort_order: int
    attribute_links: list[dict] = Field(default_factory=list)
    attribute_values: list[dict] = Field(default_factory=list)
    product_count: int = 0


class TrimLifecycleItem(RegistryModel):
    id: UUID
    modification_id: UUID
    name: str
    is_active: bool


class TrimListResponse(RegistryModel):
    items: list[TrimLifecycleItem]


class TrimCreateResponse(TrimLifecycleItem):
    pass


class TrimCreateRequest(RegistryModel):
    modification_id: UUID
    name: Annotated[
        str,
        BeforeValidator(
            lambda value: value.strip() if isinstance(value, str) else value
        ),
        Field(min_length=1, max_length=255),
    ]


class TrimPatchRequest(DirectoryPatchRequest):
    modification_id: UUID | None = None
    sort_order: Annotated[int | None, Field(ge=0)] = None


class TrimAttributeCandidateOption(RegistryModel):
    id: UUID
    code: str
    name: str
    sort_order: int
    is_active: bool


class TrimAttributeCandidate(RegistryModel):
    attribute_id: UUID
    attribute_code: str
    attribute_name: str
    data_type: AttributeDataType
    unit: str | None = None
    group_id: UUID | None = None
    group_name: str | None = None
    options: list[TrimAttributeCandidateOption] = Field(default_factory=list)
    is_required: bool
    is_filterable: bool
    sort_order: int
    modification_value: dict | None = None
    is_available: bool
    block_reason: str | None = None


class TrimAttributeCandidateGroup(RegistryModel):
    group_id: UUID | None = None
    group_name: str
    sort_order: int
    attributes: list[TrimAttributeCandidate] = Field(default_factory=list)


class TrimAttributeCandidatesResponse(RegistryModel):
    candidates: list[TrimAttributeCandidate] = Field(default_factory=list)


class TrimAttributesReplaceRequest(RegistryModel):
    items: Annotated[list[TrimAttributeLinkInput], Field(max_length=300)]


class TrimAttributesResponse(RegistryModel):
    items: list[dict]


class TrimAttributeCreateResponse(RegistryModel):
    item: dict


class TrimAttributeValuesReplaceRequest(RegistryModel):
    values: Annotated[list[TrimAttributeValueInput], Field(max_length=300)]


class TrimAttributeValuesResponse(RegistryModel):
    saved: list[TrimAttributeValueInput]


class TrimAttributeValuesLegacyResponse(RegistryModel):
    items: list[dict]
    lock_version: int


class TrimProblemDetails(RegistryModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    errors: list[dict] | None = None


class ModificationCreateRequest(DirectoryCreateRequest):
    model_id: UUID
    year_from: Annotated[int | None, Field(ge=1900, le=2200)] = None
    year_to: Annotated[int | None, Field(ge=1900, le=2200)] = None
    category_ids: Annotated[list[UUID], Field(min_length=1, max_length=50)]
    attribute_values: Annotated[
        list[ModificationAttributeValueInput], Field(max_length=300)
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_relations(self) -> ModificationCreateRequest:
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("Год начала не может быть больше года окончания")
        if len(self.category_ids) != len(set(self.category_ids)):
            raise ValueError("Категорию нельзя передать дважды")
        ids = [item.attribute_id for item in self.attribute_values]
        if len(ids) != len(set(ids)):
            raise ValueError("Характеристику нельзя передать дважды")
        return self


class ModificationPatchRequest(DirectoryPatchRequest):
    model_id: UUID | None = None
    year_from: Annotated[int | None, Field(ge=1900, le=2200)] = None
    year_to: Annotated[int | None, Field(ge=1900, le=2200)] = None
    category_ids: Annotated[
        list[UUID] | None,
        Field(min_length=1, max_length=50),
    ] = None
    attribute_values: Annotated[
        list[ModificationAttributeValueInput] | None,
        Field(max_length=300),
    ] = None

    @model_validator(mode="after")
    def unique_relations(self) -> ModificationPatchRequest:
        if self.category_ids is not None and len(self.category_ids) != len(
            set(self.category_ids)
        ):
            raise ValueError("Категорию нельзя передать дважды")
        if self.attribute_values is not None:
            ids = [item.attribute_id for item in self.attribute_values]
            if len(ids) != len(set(ids)):
                raise ValueError("Характеристику нельзя передать дважды")
        return self


class AttributeGroupResource(VersionedResource):
    sort_order: int
    category_attribute_count: int = 0
    attribute_ids: list[UUID] = Field(default_factory=list)


class AttributeGroupListResponse(RegistryModel):
    items: list[AttributeGroupResource]
    pagination: RegistryPagination


class AttributeGroupCreateRequest(DirectoryCreateRequest):
    sort_order: Annotated[int, Field(ge=0)] = 0
    attribute_ids: Annotated[list[UUID], Field(max_length=500)] = Field(
        default_factory=list
    )


class AttributeGroupPatchRequest(DirectoryPatchRequest):
    sort_order: Annotated[int | None, Field(ge=0)] = None
    attribute_ids: Annotated[
        list[UUID] | None, Field(max_length=500)
    ] = None


class AttributeOptionResource(RegistryModel):
    id: UUID
    attribute_id: UUID
    code: str
    name: str
    sort_order: int
    is_active: bool
    lock_version: int
    updated_at: datetime


class AttributeOptionListResponse(RegistryModel):
    items: list[AttributeOptionResource]
    pagination: RegistryPagination


class AttributeOptionCreateRequest(RegistryModel):
    code: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1, max_length=255)]
    sort_order: Annotated[int, Field(ge=0)] = 0
    is_active: bool = True


class AttributeOptionPatchRequest(RegistryModel):
    name: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    sort_order: Annotated[int | None, Field(ge=0)] = None
    is_active: bool | None = None


class UnitResource(VersionedResource):
    attribute_count: int = 0


class UnitListResponse(RegistryModel):
    items: list[UnitResource]
    pagination: RegistryPagination


class UnitCreateRequest(RegistryModel):
    code: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1, max_length=50)]
    is_active: bool = True


class UnitPatchRequest(RegistryModel):
    name: Annotated[str | None, Field(min_length=1, max_length=50)] = None
    is_active: bool | None = None


class UnitMergeRequest(RegistryModel):
    target_unit_id: UUID
    target_lock_version: int | None = None


class SuperstructureAttributeLinkInput(RegistryModel):
    attribute_id: UUID
    group_id: UUID
    is_required: bool = False
    is_visible: bool = False
    is_filterable: bool = False
    sort_order: Annotated[int, Field(ge=0)] = 0


class SuperstructureAttributeItem(RegistryModel):
    attribute_id: UUID
    group_id: UUID
    is_required: bool = False
    is_visible: bool = False
    is_filterable: bool = False
    sort_order: int = 0
    attribute_name: str | None = None
    attribute_code: str | None = None
    group_name: str | None = None
    group_code: str | None = None
    data_type: str | None = None
    unit: str | None = None


class SuperstructureResource(VersionedResource):
    attribute_count: int = 0
    product_count: int = 0
    category_ids: list[UUID] = Field(default_factory=list)
    categories: list[NamedDirectoryRef] = Field(default_factory=list)
    attributes: list[SuperstructureAttributeItem] = Field(default_factory=list)


class SuperstructureListResponse(RegistryModel):
    items: list[SuperstructureResource]
    pagination: RegistryPagination


class SuperstructureCreateRequest(DirectoryCreateRequest):
    category_ids: Annotated[list[UUID], Field(max_length=50)] = Field(
        default_factory=list
    )
    attributes: Annotated[
        list[SuperstructureAttributeLinkInput], Field(max_length=300)
    ] = Field(default_factory=list)


class SuperstructurePatchRequest(DirectoryPatchRequest):
    category_ids: Annotated[list[UUID] | None, Field(max_length=50)] = None
    attributes: Annotated[
        list[SuperstructureAttributeLinkInput] | None, Field(max_length=300)
    ] = None


class SuperstructureAttributeCandidate(RegistryModel):
    attribute_id: UUID
    attribute_code: str
    attribute_name: str
    data_type: str
    unit: str | None = None
    group_id: UUID
    group_name: str
    is_active: bool


class SuperstructureAttributeCandidatesResponse(RegistryModel):
    items: list[SuperstructureAttributeCandidate]


class AttributeOptionUpsertInput(RegistryModel):
    id: UUID | None = None
    code: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1, max_length=255)]
    sort_order: Annotated[int, Field(ge=0)] = 0
    is_active: bool = True


class AttributeResource(RegistryModel):
    id: UUID
    code: str
    name: str
    attribute_group_id: UUID | None
    data_type: AttributeDataType
    unit_id: UUID | None = None
    unit: str | None = None
    filter_kind: AttributeFilterKind
    is_active: bool
    options: list[AttributeOptionResource] = Field(default_factory=list)
    category_count: int = 0
    modification_value_count: int = 0
    lock_version: int
    updated_at: datetime


class AttributeListResponse(RegistryModel):
    items: list[AttributeResource]
    pagination: RegistryPagination


class AttributeCreateRequest(RegistryModel):
    code: Annotated[str, Field(min_length=1, max_length=100)]
    name: Annotated[str, Field(min_length=1, max_length=255)]
    attribute_group_id: UUID | None = None
    data_type: AttributeDataType
    unit_id: UUID | None = None
    filter_kind: AttributeFilterKind
    is_active: bool = True
    options: Annotated[
        list[AttributeOptionUpsertInput], Field(max_length=500)
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self) -> AttributeCreateRequest:
        if self.filter_kind == "range" and self.data_type != "number":
            raise ValueError("Диапазон доступен только числовой характеристике")
        if self.filter_kind == "search" and self.data_type != "text":
            raise ValueError(
                "Текстовый поиск доступен только текстовой характеристике"
            )
        return self


class AttributePatchRequest(RegistryModel):
    name: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    attribute_group_id: UUID | None = None
    data_type: AttributeDataType | None = None
    confirm_type_conversion: bool = False
    unit_id: UUID | None = None
    filter_kind: AttributeFilterKind | None = None
    is_active: bool | None = None
    options: Annotated[
        list[AttributeOptionUpsertInput] | None,
        Field(max_length=500),
    ] = None


class CategoryAttributeLinkInput(RegistryModel):
    attribute_id: UUID
    group_id: UUID | None = None
    is_required: bool = False
    is_filterable: bool = False
    is_visible: bool = True
    sort_order: Annotated[int, Field(ge=0)] = 0


class CategoryAttributeLinksReplaceRequest(RegistryModel):
    items: Annotated[list[CategoryAttributeLinkInput], Field(max_length=300)]


class ProductAttributeValueInput(RegistryModel):
    attribute_id: UUID
    option_id: UUID | None = None
    value_number: Decimal | None = None
    value_text: Annotated[str | None, Field(max_length=2000)] = None
    value_boolean: bool | None = None
    value: StrictBool | Decimal | StrictStr | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_value(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("value")
            if (
                val is not None
                and data.get("option_id") is None
                and data.get("value_number") is None
                and data.get("value_text") is None
                and data.get("value_boolean") is None
            ):
                if isinstance(val, bool):
                    data["value_boolean"] = val
                elif isinstance(val, (int, float, Decimal)):
                    data["value_number"] = Decimal(str(val))
                elif isinstance(val, str):
                    data["value_text"] = val
        return data

    @model_validator(mode="after")
    def one_value(self) -> ProductAttributeValueInput:
        non_null = sum(
            x is not None
            for x in (
                self.option_id,
                self.value_number,
                self.value_text,
                self.value_boolean,
            )
        )
        if non_null != 1:
            raise ValueError(
                "Укажите ровно одно значение характеристики (option_id, value_number, value_text или value_boolean)"
            )
        return self


class SpecialEquipmentModelRef(RegistryModel):
    id: UUID
    code: str
    name: str
    mark: NamedDirectoryRef | None = None


class SpecialEquipmentProductRef(RegistryModel):
    id: UUID
    code: str
    name: str
    publication_status: str
    mark: str | NamedDirectoryRef | None = None
    model: str | NamedDirectoryRef | None = None
    modification: str | NamedDirectoryRef | None = None


class ProductResource(RegistryModel):
    id: UUID
    code: str
    slug: str
    title: str | None = None
    modification_id: UUID | None = None
    trim_id: UUID | None = None
    trim_name: str | None = None
    modification_name: str | None = None
    model_name: str
    mark_name: str
    modification: dict | None = None
    model: dict | None = None
    seller_company_id: UUID | None
    seller_company_name: str | None
    warehouse_id: UUID | None = None
    body_color_id: UUID | None = None
    interior_color_id: UUID | None = None
    body_color: ColorRef | None = None
    interior_color: ColorRef | None = None
    description: str | None
    price: str | None
    special_price: str | None = None
    price_on_request: bool = False
    price_from: str | None = None
    currency_code: Literal["RUB"]
    manufacture_year: int | None
    vin: str | None
    chassis_vin: str | None = None
    superstructure_vin: str | None = None
    no_vin: bool
    condition: EquipmentCondition
    owners_count: int | None
    mileage_km: int | None
    engine_hours: int | None
    publication_status: PublicationStatus
    sale_status: SaleStatus
    category_ids: list[UUID] = Field(default_factory=list)
    categories: list[NamedDirectoryRef] = Field(default_factory=list)
    images: list[dict] = Field(default_factory=list)
    lock_version: int
    published_at: datetime | None = None
    updated_at: datetime
    normalization_state: Literal["normalized"] = "normalized"
    is_attachment: bool = False
    is_composite: bool = False
    # Kit fields
    is_kit: bool = False
    model_id: UUID | None = None
    superstructure_id: UUID | None = None
    superstructure_model_id: UUID | None = None
    superstructure_model: SpecialEquipmentModelRef | None = None
    superstructure_modification_id: UUID | None = None
    superstructure_source_product_id: UUID | None = None
    superstructure_source: SpecialEquipmentProductRef | None = None
    superstructure_name: str | None = None
    superstructure_manufacturer: str | None = None
    superstructure: dict | None = None
    chassis_values: list[dict] = Field(default_factory=list)
    superstructure_values: list[dict] = Field(default_factory=list)


class ProductListResponse(RegistryModel):
    items: list[ProductResource]
    pagination: RegistryPagination


class CompatibleAttachmentLinkResource(RegistryModel):
    attachment_product_id: UUID
    position: int
    product: ProductResource


class CompatibleAttachmentsResponse(RegistryModel):
    items: list[CompatibleAttachmentLinkResource]
    pagination: RegistryPagination


class CompatibleAttachmentInput(RegistryModel):
    attachment_product_id: UUID
    position: Annotated[int, Field(ge=0)]


class CompatibleAttachmentCreateRequest(CompatibleAttachmentInput):
    pass


class CompatibleAttachmentPatchRequest(RegistryModel):
    position: Annotated[int, Field(ge=0)]


class CompatibleAttachmentsReplaceRequest(RegistryModel):
    items: Annotated[list[CompatibleAttachmentInput], Field(max_length=500)]

    @model_validator(mode="after")
    def unique_products_and_positions(self) -> CompatibleAttachmentsReplaceRequest:
        product_ids = [item.attachment_product_id for item in self.items]
        positions = [item.position for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Надстройку нельзя добавить дважды")
        if len(positions) != len(set(positions)):
            raise ValueError("Позиции надстроек должны быть уникальными")
        return self


class ProductCommercialInput(RegistryModel):
    code: Annotated[str, Field(min_length=1, max_length=100)]
    seller_company_id: UUID | None = None
    warehouse_id: UUID | None = None
    body_color_id: UUID | None = None
    interior_color_id: UUID | None = None
    description: str | None = None
    price: PriceInput | None = None
    special_price: SpecialPriceInput | None = None
    price_on_request: bool = False
    price_from: RequestPriceInput | None = None
    currency_code: Literal["RUB"] = "RUB"
    manufacture_year: Annotated[int | None, Field(ge=1900, le=2200)] = None
    vin: Annotated[str | None, Field(max_length=17)] = None
    chassis_vin: Annotated[str | None, Field(max_length=32)] = None
    superstructure_vin: Annotated[str | None, Field(max_length=32)] = None
    no_vin: bool = False
    condition: EquipmentCondition
    owners_count: Annotated[int | None, Field(ge=0)] = None
    mileage_km: Annotated[int | None, Field(ge=0)] = None
    engine_hours: Annotated[int | None, Field(ge=0)] = None
    publication_status: PublicationStatus = "draft"
    sale_status: SaleStatus = "unavailable"

    @model_validator(mode="after")
    def strict_identity(self) -> ProductCommercialInput:
        if self.condition == "new" and self.owners_count is not None:
            raise ValueError("Для новой техники владельцы не заполняются")
        if self.condition == "used" and self.owners_count is None:
            raise ValueError(
                "Для техники «С пробегом» требуется количество владельцев "
                "не меньше 0"
            )
        if self.no_vin:
            if self.vin or self.chassis_vin or self.superstructure_vin:
                raise ValueError("При отметке «Нет VIN» все поля VIN должны быть пустыми")
        elif not (self.vin or "").strip():
            raise ValueError("Укажите VIN или отметьте «Нет VIN»")
        if not self.price_on_request:
            self.price_from = None
        try:
            ensure_product_commercial_terms(
                price=self.price,
                special_price=self.special_price,
                price_on_request=self.price_on_request,
                price_from=self.price_from,
            )
        except SpecialEquipmentManagementValidationError as exc:
            raise ValueError(str(exc)) from exc
        return self


class ProductCreateRequest(ProductCommercialInput):
    modification_id: UUID | None = None
    trim_id: UUID | None = None
    category_ids: Annotated[list[UUID], Field(min_length=1, max_length=50)]
    compatible_attachments: Annotated[
        list[CompatibleAttachmentInput],
        Field(max_length=500),
    ] = Field(default_factory=list)

    # Kit fields
    model_id: UUID | None = None
    superstructure_id: UUID | None = None
    superstructure_model_id: UUID | None = None
    superstructure_modification_id: UUID | None = None
    superstructure_source_product_id: UUID | None = None
    superstructure_name: Annotated[str | None, Field(max_length=255)] = None
    superstructure_manufacturer: Annotated[str | None, Field(max_length=255)] = None
    chassis_values: Annotated[
        list[ProductAttributeValueInput], Field(max_length=300)
    ] = Field(default_factory=list)
    superstructure_values: Annotated[
        list[ProductAttributeValueInput], Field(max_length=300)
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_product_kind(self) -> ProductCreateRequest:  # noqa: PLR0912
        is_kit = self.model_id is not None and self.superstructure_id is not None
        if is_kit:
            if self.superstructure_source_product_id is None:
                if not (self.superstructure_name or "").strip():
                    raise ValueError("Для комплекта необходимо указать название надстройки")
                if not (self.superstructure_manufacturer or "").strip():
                    raise ValueError("Для комплекта необходимо указать производителя надстройки")
            if self.trim_id is not None:
                raise ValueError("У комплекта не может быть комплектации")
            if self.compatible_attachments:
                raise ValueError("Комплект не поддерживает совместимые надстройки")
            if not self.no_vin and not (self.chassis_vin or "").strip():
                raise ValueError("Для комплекта техники необходимо указать VIN шасси")
        else:
            if self.modification_id is None:
                raise ValueError("Для обычного объявления необходима модификация")
            if self.model_id is not None:
                raise ValueError("model_id заполняется только для комплекта")
            if (
                self.superstructure_model_id is not None
                or self.superstructure_source_product_id is not None
            ):
                raise ValueError("Поля надстройки заполняются только для комплекта")
            if self.superstructure_name is not None or self.superstructure_manufacturer is not None:
                raise ValueError("Поля надстройки заполняются только для комплекта")
            if self.chassis_values or self.superstructure_values:
                raise ValueError("Характеристики комплекта заполняются только для комплекта")
            if self.chassis_vin is not None or self.superstructure_vin is not None:
                raise ValueError("VIN шасси и надстройки заполняются только для комплекта")
        return self

    @model_validator(mode="after")
    def unique_initial_compatibility(self) -> ProductCreateRequest:
        product_ids = [
            item.attachment_product_id for item in self.compatible_attachments
        ]
        positions = [item.position for item in self.compatible_attachments]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Надстройку нельзя добавить дважды")
        if len(positions) != len(set(positions)):
            raise ValueError("Позиции надстроек должны быть уникальными")
        return self


class ProductPatchRequest(RegistryModel):
    modification_id: UUID | None = None
    trim_id: UUID | None = None
    seller_company_id: UUID | None = None
    warehouse_id: UUID | None = None
    body_color_id: UUID | None = None
    interior_color_id: UUID | None = None
    description: str | None = None
    price: PriceInput | None = None
    special_price: SpecialPriceInput | None = None
    price_on_request: bool | None = None
    price_from: RequestPriceInput | None = None
    manufacture_year: Annotated[int | None, Field(ge=1900, le=2200)] = None
    vin: Annotated[str | None, Field(max_length=17)] = None
    chassis_vin: Annotated[str | None, Field(max_length=32)] = None
    superstructure_vin: Annotated[str | None, Field(max_length=32)] = None
    no_vin: bool | None = None
    condition: EquipmentCondition | None = None
    owners_count: Annotated[int | None, Field(ge=0)] = None
    mileage_km: Annotated[int | None, Field(ge=0)] = None
    engine_hours: Annotated[int | None, Field(ge=0)] = None
    publication_status: PublicationStatus | None = None
    sale_status: SaleStatus | None = None
    category_ids: Annotated[
        list[UUID] | None,
        Field(min_length=1, max_length=50),
    ] = None
    # Kit fields
    model_id: UUID | None = None
    superstructure_id: UUID | None = None
    superstructure_model_id: UUID | None = None
    superstructure_modification_id: UUID | None = None
    superstructure_source_product_id: UUID | None = None
    superstructure_name: Annotated[str | None, Field(max_length=255)] = None
    superstructure_manufacturer: Annotated[str | None, Field(max_length=255)] = None
    chassis_values: Annotated[
        list[ProductAttributeValueInput] | None, Field(max_length=300)
    ] = None
    superstructure_values: Annotated[
        list[ProductAttributeValueInput] | None, Field(max_length=300)
    ] = None

    @model_validator(mode="after")
    def reject_null_price_on_request(self) -> ProductPatchRequest:
        if (
            "price_on_request" in self.model_fields_set
            and self.price_on_request is None
        ):
            raise ValueError(
                "Поле «Цена по запросу» при передаче должно быть boolean"
            )
        return self


class ProductWarehouseReplaceRequest(RegistryModel):
    """Replace only the product's warehouse link."""

    warehouse_id: UUID | None


class AttachmentSourceItem(RegistryModel):
    id: UUID
    code: str
    name: str
    publication_status: str
    mark: NamedDirectoryRef | None = None
    model: NamedDirectoryRef | None = None
    modification: NamedDirectoryRef | None = None
    superstructure_name: str
    superstructure_manufacturer: str
    superstructure_values_by_attribute: dict[str, Any] = Field(default_factory=dict)


class AttachmentSourcesResponse(RegistryModel):
    items: list[AttachmentSourceItem]


class DependencyResource(RegistryModel):
    entity_type: str
    entity_id: UUID
    entity_code: str | None = None
    entity_name: str | None = None
    blockers: dict[str, int]
    can_delete: bool


class DependencyConflictItem(RegistryModel):
    entity: str
    id: UUID
    code: str
    name: str
    count: Annotated[int, Field(gt=0)]


class DependencyConflictDetail(RegistryModel):
    detail: str
    code: Literal["SPECIAL_EQUIPMENT_DEPENDENCY_CONFLICT"]
    entity_type: str
    entity_id: UUID
    entity_code: str | None = None
    entity_name: str | None = None
    dependencies: list[DependencyConflictItem]


class SellerCompanyResource(RegistryModel):
    id: UUID
    name: str
    inn: str | None


class SellerCompaniesResponse(RegistryModel):
    items: list[SellerCompanyResource]


class ManagementImageResource(RegistryModel):
    id: UUID
    content_url: str
    alt_text: str | None
    sort_order: int
    is_primary: bool


class ProductImagePatchRequest(RegistryModel):
    alt_text: Annotated[str | None, Field(default=None, max_length=1000)]
    sort_order: Annotated[int | None, Field(default=None, ge=0)]
    is_primary: bool | None = None


class MediaUploadResponse(RegistryModel):
    image: ManagementImageResource | None = None
    category: CategoryResource | None = None


class CascadeEntityRefSchema(RegistryModel):
    id: UUID
    code: str = ""
    name: str = ""


class CascadeRootEntitySchema(RegistryModel):
    type: str
    id: UUID
    code: str = ""
    name: str = ""


class CascadeDeleteGroupSchema(RegistryModel):
    type: str
    count: int
    items: list[CascadeEntityRefSchema]
    truncated: bool = False


class CascadeUnlinkGroupSchema(RegistryModel):
    type: str
    count: int
    description: str


class CascadeClearGroupSchema(RegistryModel):
    type: str
    field: str
    count: int
    description: str


class CascadeUserImpactSchema(RegistryModel):
    cart_items: int = 0
    favorites: int = 0


class CascadeProductBlockerDocSchema(RegistryModel):
    type: str
    id: UUID
    number: str
    status: str


class CascadeProductBlockerProductSchema(RegistryModel):
    id: UUID
    code: str
    vin: str | None = None
    name: str


class CascadeProductBlockerSchema(RegistryModel):
    product: CascadeProductBlockerProductSchema
    vin: str | None = None
    documents: list[CascadeProductBlockerDocSchema]


class CascadeDistributorCompanySchema(RegistryModel):
    id: UUID
    name: str
    inn: str | None = None


class CascadeDistributorBlockerSchema(RegistryModel):
    company: CascadeDistributorCompanySchema


class CascadeSupportProgramProgramSchema(RegistryModel):
    id: UUID
    name: str
    is_active: bool
    starts_at: str | None = None
    ends_at: str | None = None


class CascadeSupportProgramRefSchema(RegistryModel):
    type: str
    id: UUID
    code: str = ""
    name: str = ""


class CascadeSupportProgramBlockerSchema(RegistryModel):
    program: CascadeSupportProgramProgramSchema
    references: list[CascadeSupportProgramRefSchema]


class CascadeKitSourceProductSchema(RegistryModel):
    id: UUID
    code: str
    title: str = ""


class CascadeKitSourceItemSchema(RegistryModel):
    id: UUID
    code: str
    title: str


class CascadeKitSourceBlockerSchema(RegistryModel):
    product: CascadeKitSourceProductSchema
    kits: list[CascadeKitSourceItemSchema]


class CascadeBlockersSchema(RegistryModel):
    products: list[CascadeProductBlockerSchema] = Field(default_factory=list)
    distributors: list[CascadeDistributorBlockerSchema] = Field(default_factory=list)
    support_programs: list[CascadeSupportProgramBlockerSchema] = Field(default_factory=list)
    kit_sources: list[CascadeKitSourceBlockerSchema] = Field(default_factory=list)


class CascadePreviewResponseSchema(RegistryModel):
    root: CascadeRootEntitySchema
    delete: list[CascadeDeleteGroupSchema]
    unlink: list[CascadeUnlinkGroupSchema]
    clear: list[CascadeClearGroupSchema]
    user_impact: CascadeUserImpactSchema
    blockers: CascadeBlockersSchema
    total: int
    preview_token: str
    catalog_revision: int


class CascadeDeleteRequestSchema(RegistryModel):
    confirmation: StrictStr
    preview_token: StrictStr


class CascadeDeleteResponseSchema(RegistryModel):
    deleted: dict[str, int]
    catalog_revision: int

