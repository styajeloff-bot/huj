"""Read handlers for corrected special-equipment catalog management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.special_equipment_catalog import trim_attribute_group_conflicts
from domain.special_equipment_kits import KitInvariantError
from domain.special_equipment_management import (
    SpecialEquipmentManagementNotFoundError,
    SpecialEquipmentTrimContractError,
)
from infrastructure.repositories import (
    special_equipment_management_repository as repository,
)


@dataclass(frozen=True)
class ListRegistryQuery:
    entity_type: repository.EntityType
    page: int = 1
    page_size: int = 50
    search: str | None = None
    mark_id: UUID | None = None
    model_id: UUID | None = None
    modification_id: UUID | None = None
    category_id: UUID | None = None
    sale_status: repository.ProductSaleStatus | None = None
    attribute_id: UUID | None = None
    category_level_ids: tuple[UUID | None, ...] = ()
    sort: repository.CategorySort | None = None
    attribute_group_id: UUID | None = None
    normalization_state: Literal["normalized", "legacy", "conflict"] | None = None
    role: repository.ProductCandidateRole | None = None
    applicability: str | None = None
    is_active: bool | None = None


@dataclass(frozen=True)
class ListProductRelationsQuery:
    product_id: UUID
    relation: Literal["compatible_attachments"]
    page: int = 1
    page_size: int = 100


@dataclass(frozen=True)
class GetRegistryEntityQuery:
    entity_type: repository.EntityType
    entity_id: UUID


@dataclass(frozen=True)
class GetRegistryDependenciesQuery:
    entity_type: repository.EntityType
    entity_id: UUID


@dataclass(frozen=True)
class SelectColorsQuery:
    applicability: Literal["body", "interior"]
    search: str | None = None
    limit: int = 50


@dataclass(frozen=True)
class ListAttachmentSourcesQuery:
    model_id: UUID
    modification_id: UUID | None = None
    exclude_product_id: UUID | None = None
    search: str | None = None
    limit: int = 50



async def handle_list(query: ListRegistryQuery, session: AsyncSession) -> dict:
    rows, total = await repository.list_entities(
        session,
        query.entity_type,
        offset=(query.page - 1) * query.page_size,
        limit=query.page_size,
        search=query.search,
        mark_id=query.mark_id,
        model_id=query.model_id,
        modification_id=query.modification_id,
        category_id=query.category_id,
        sale_status=query.sale_status,
        attribute_id=query.attribute_id,
        category_level_ids=query.category_level_ids,
        sort=query.sort,
        attribute_group_id=query.attribute_group_id,
        normalization_state=query.normalization_state,
        role=query.role,
        applicability=query.applicability,
        is_active=query.is_active,
    )
    pages = (total + query.page_size - 1) // query.page_size if total else 0
    return {
        "items": rows,
        "pagination": {
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "pages": pages,
        },
    }


async def handle_list_trim_lifecycle_items(
    modification_id: UUID,
    session: AsyncSession,
) -> dict[str, Any]:
    return {
        "items": await repository.list_trim_lifecycle_items(
            session,
            modification_id=modification_id,
        )
    }



async def resolve_trim_attribute_candidates(
    modification_id: UUID,
    session: AsyncSession,
) -> dict[str, Any]:
    """Resolve the canonical trim candidate projection for a modification."""

    modification = await repository.get_entity(
        session, "modification", modification_id
    )
    if modification is None or not modification.get("is_active", True):
        raise SpecialEquipmentTrimContractError(
            "Модификация не найдена",
            code="MODIFICATION_NOT_FOUND",
            kind="not_found",
        )
    modification_values = {
        item["attribute_id"]: item
        for item in modification.get("attribute_values", ())
    }
    candidates_by_attribute: dict[UUID, dict[str, Any]] = {}
    sources_by_attribute: dict[UUID, list[dict[str, Any]]] = {}
    for category_id in modification.get("category_ids", ()):  # hydrated by get_entity
        category = await repository.get_entity(session, "category", category_id)
        if category is None or not category.get("is_active", True):
            continue
        for link in category.get("effective_attribute_links", ()):
            attribute_id = link["attribute_id"]
            source = {
                "category_id": category_id,
                "category_name": category.get("name", ""),
                "group_id": link.get("group_id"),
                "group_name": link.get("group_name"),
            }
            sources = sources_by_attribute.setdefault(attribute_id, [])
            if source not in sources:
                sources.append(source)
            if attribute_id in candidates_by_attribute:
                continue
            attribute = await repository.get_entity(
                session, "attribute", attribute_id
            )
            if attribute is None or not attribute.get("is_active", True):
                continue
            modification_value = modification_values.get(attribute_id)
            candidates_by_attribute[attribute_id] = {
                "attribute_id": attribute_id,
                "attribute_code": attribute["code"],
                "attribute_name": attribute["name"],
                "data_type": attribute["data_type"],
                "unit": attribute.get("unit"),
                "options": [
                    option
                    for option in attribute.get("options", [])
                    if option.get("is_active", True)
                ],
                "is_required": link.get("is_required", False),
                "is_filterable": link.get("is_filterable", False),
                "group_id": link.get("group_id"),
                "group_name": (
                    link.get("group_name")
                    if link.get("group_id") is not None
                    else None
                ),
                "sort_order": link.get("sort_order", 0),
                "modification_value": modification_value,
                "is_available": modification_value is None,
                "block_reason": (
                    None
                    if modification_value is None
                    else "ATTRIBUTE_ALREADY_USED_IN_MODIFICATION"
                ),
            }
    conflicting_attribute_ids = {
        conflict.attribute_id
        for conflict in trim_attribute_group_conflicts(
            (attribute_id, source["group_id"])
            for attribute_id, sources in sources_by_attribute.items()
            for source in sources
        )
    }
    conflicts = [
        {
            "attribute_id": str(attribute_id),
            "sources": sources,
        }
        for attribute_id, sources in sources_by_attribute.items()
        if attribute_id in candidates_by_attribute
        and attribute_id in conflicting_attribute_ids
    ]
    if conflicts:
        raise SpecialEquipmentTrimContractError(
            "Характеристика назначена разным группам в категориях модификации",
            code="CATEGORY_ATTRIBUTE_GROUP_CONFLICT",
            kind="conflict",
            detail={"conflicts": conflicts},
        )
    candidates = sorted(
        candidates_by_attribute.values(),
        key=lambda item: (
            item["sort_order"],
            str(item["attribute_id"]),
        ),
    )
    return {"candidates": candidates}


async def handle_trim_attribute_candidates(
    trim_id: UUID, session: AsyncSession
) -> dict[str, Any]:
    trim = await repository.get_entity(session, "trim", trim_id)
    if trim is None:
        raise SpecialEquipmentTrimContractError(
            "Комплектация не найдена",
            code="TRIM_NOT_FOUND",
            kind="not_found",
        )
    return await resolve_trim_attribute_candidates(trim["modification_id"], session)


async def handle_superstructure_attribute_candidates(
    group_id: UUID, session: AsyncSession
) -> list[dict[str, Any]]:
    return await repository.list_superstructure_attribute_candidates(session, group_id)


async def handle_trim_attributes(
    trim_id: UUID, session: AsyncSession
) -> dict[str, Any]:
    trim = await repository.get_entity(session, "trim", trim_id)
    if trim is None:
        raise SpecialEquipmentTrimContractError(
            "Комплектация не найдена",
            code="TRIM_NOT_FOUND",
            kind="not_found",
        )
    return {
        "trim_id": trim_id,
        "lock_version": trim["lock_version"],
        "items": await repository.trim_attribute_state(session, trim_id),
    }

async def handle_section_counts(session: AsyncSession) -> dict[str, int]:
    """Return global counts for all catalog management sections."""

    return await repository.catalog_section_counts(session)


async def handle_list_product_relations(
    query: ListProductRelationsQuery,
    session: AsyncSession,
) -> dict:
    owner = await repository.get_entity(session, "product", query.product_id)
    if owner is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    if (
        owner.get("superstructure_id") is not None
        and query.relation == "compatible_attachments"
    ):
        raise KitInvariantError(
            "Комплект техники не поддерживает совместимые надстройки",
            code="KIT_COMPATIBILITY_FORBIDDEN",
        )
    offset = (query.page - 1) * query.page_size
    rows, total = await repository.list_product_attachments(
        session,
        product_id=query.product_id,
        offset=offset,
        limit=query.page_size,
    )
    return {
        "data": {
            "items": rows,
            "pagination": {
                "page": query.page,
                "page_size": query.page_size,
                "total": total,
                "pages": (
                    (total + query.page_size - 1) // query.page_size
                    if total
                    else 0
                ),
            },
        },
        "resource": owner,
    }


async def handle_list_attachment_sources(
    query: ListAttachmentSourcesQuery,
    session: AsyncSession,
) -> list[dict[str, Any]]:
    return await repository.list_attachment_sources(
        session,
        model_id=query.model_id,
        modification_id=query.modification_id,
        exclude_product_id=query.exclude_product_id,
        search=query.search,
        limit=query.limit,
    )



async def handle_get(
    query: GetRegistryEntityQuery, session: AsyncSession
) -> dict:
    row = await repository.get_entity(
        session, query.entity_type, query.entity_id
    )
    if row is None:
        raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")
    return row


async def handle_dependencies(
    query: GetRegistryDependenciesQuery, session: AsyncSession
) -> dict:
    entity = await repository.get_entity(
        session, query.entity_type, query.entity_id
    )
    if entity is None:
        raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")
    blockers = await repository.dependencies(
        session, query.entity_type, query.entity_id
    )
    return {
        "entity_type": query.entity_type,
        "entity_id": query.entity_id,
        "entity_code": entity.get("code"),
        "entity_name": entity.get("name") or entity.get("code"),
        "blockers": blockers,
        "can_delete": not any(blockers.values()),
    }


async def handle_seller_companies(session: AsyncSession) -> dict:
    return {"items": await repository.list_seller_companies(session)}


async def handle_select_colors(
    query: SelectColorsQuery, session: AsyncSession
) -> dict:
    return {
        "items": await repository.select_active_colors(
            session,
            applicability=query.applicability,
            search=query.search,
            limit=query.limit,
        )
    }


async def handle_category_image_key(
    category_id: UUID, session: AsyncSession
) -> str:
    storage_key = await repository.get_category_image_key(session, category_id)
    if storage_key is None:
        raise SpecialEquipmentManagementNotFoundError(
            "Изображение не найдено"
        )
    return storage_key


async def handle_product_image_key(
    image_id: UUID, session: AsyncSession
) -> str:
    image = await repository.get_product_image_storage(session, image_id)
    if image is None:
        raise SpecialEquipmentManagementNotFoundError(
            "Изображение не найдено"
        )
    return str(image["storage_key"])
