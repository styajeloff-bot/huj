"""Mutation handlers for corrected special-equipment catalog management."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from application.special_equipment_management_etag import (
    special_equipment_management_etag,
    special_equipment_trim_attributes_etag,
)
from domain.errors import DomainError
from domain.special_equipment_attachments import (
    AttachmentCategoryInUseError,
    AttachmentClassification,
    AttachmentInvariantError,
    attachment_branch_ids,
    ensure_single_attachment_classification,
    rule_inheritance_graph,
)
from domain.special_equipment_cascade_delete import (
    CascadeBlockers,
    CascadeDeleteBlockedError,
    CascadePlan,
    CascadePreviewStaleError,
    build_cascade_plan,
    compute_preview_token,
    ensure_confirmation,
)
from domain.special_equipment_catalog import (
    CategoryAttributeRule,
    CategoryGraph,
    SpecialEquipmentCatalogError,
    effective_attribute_rules,
    ensure_card_attribute_limit,
    ensure_category_change_card_attribute_limits,
    ensure_condition_owners,
    ensure_condition_usage,
    ensure_single_usage_metric,
    ensure_vin_choice,
    generate_catalog_slug,
    resolve_trim_attribute_contract,
)
from domain.special_equipment_import import validate_entity_code
from domain.special_equipment_kits import (
    ChassisAttributeContract,
    ChassisAttributeRule,
    KitInvariantError,
    SuperstructureAttributeAssignment,
    ensure_kit_categories,
    ensure_kit_chassis_values,
    ensure_kit_superstructure,
    ensure_kit_superstructure_values,
    ensure_kit_vins,
    ensure_standalone_superstructure,
    ensure_superstructure_attribute_groups,
)
from domain.special_equipment_management import (
    AttributeDefinition,
    AttributeTypeConversionBlockedError,
    CatalogDependency,
    ProductWarehouseValidationError,
    SpecialEquipmentColorConflictError,
    SpecialEquipmentColorValidationError,
    SpecialEquipmentManagementConflictError,
    SpecialEquipmentManagementNotFoundError,
    SpecialEquipmentManagementPreconditionError,
    SpecialEquipmentManagementValidationError,
    SpecialEquipmentTrimContractError,
    UnitInactiveError,
    UnitInUseError,
    UnitNotFoundError,
    ensure_color_applicability_change_allowed,
    ensure_deactivation_allowed,
    ensure_delete_allowed,
    ensure_manufacture_year_within_range,
    ensure_price_on_request_mode_change,
    ensure_product_archive_allowed,
    ensure_product_color_assignment_allowed,
    ensure_product_commercial_terms,
    ensure_product_warehouse_assignment,
    ensure_publication_ready,
    ensure_sale_transition,
    ensure_warehouse_owner_matches_seller,
    ensure_year_range,
    normalize_color_applicability,
    normalize_color_code,
    normalize_color_name,
    trim_modification_value_conflicts,
    typed_modification_value,
)
from infrastructure.repositories import (
    special_equipment_cascade_delete_repository as cascade_repository,
)
from infrastructure.repositories import (
    special_equipment_management_repository as repository,
)
from infrastructure.settings import settings

_SLUGGED_ENTITY_TYPES: frozenset[repository.EntityType] = frozenset(
    {
        "category",
        "mark",
        "model",
        "modification",
        "trim",
        "attribute_group",
        "unit",
        "superstructure",
    }
)


_MISSING = object()


async def lock_catalog_for_mutation(session: AsyncSession) -> None:
    await repository.lock_catalog_for_mutation(session)


def product_warehouse_error_from_integrity(
    exc: BaseException,
) -> ProductWarehouseValidationError | None:
    code = repository.product_warehouse_integrity_error_code(exc)
    if code is None:
        return None
    message = {
        "WAREHOUSE_NOT_FOUND": "Склад не найден",
        "WAREHOUSE_INACTIVE": "Склад неактивен",
        "WAREHOUSE_NOT_ALLOWED": "Товар без VIN не может быть привязан к складу",
        "WAREHOUSE_REQUIRED": "Для товара в наличии требуется активный склад",
    }[code]
    return ProductWarehouseValidationError(message, code=code)


def _ensure_precondition(
    current: Mapping[str, Any],
    *,
    expected_version: int,
    expected_etag: str | None,
) -> None:
    if current["lock_version"] != expected_version or (
        expected_etag is not None
        and special_equipment_management_etag(dict(current)) != expected_etag
    ):
        raise SpecialEquipmentManagementPreconditionError("Ресурс уже изменён")


def _rules_by_category(rows: Sequence[Mapping[str, Any]]) -> dict:
    result: dict[UUID, list[CategoryAttributeRule]] = {}
    for row in rows:
        result.setdefault(row["category_id"], []).append(
            CategoryAttributeRule(
                attribute_id=row["attribute_id"],
                group_id=row["group_id"],
                is_required=row["is_required"],
                is_filterable=row["is_filterable"],
                is_visible=row["is_visible"],
                sort_order=row["sort_order"],
            )
        )
    return result


async def _graph(session: AsyncSession) -> CategoryGraph:
    snapshot = await repository.category_graph_snapshot(session)
    return CategoryGraph.from_edges(
        category_ids=snapshot["category_ids"], edges=snapshot["edges"]
    )


async def _attachment_context(
    session: AsyncSession,
) -> tuple[CategoryGraph, frozenset[UUID]]:
    snapshot = await repository.category_graph_snapshot(session)
    graph = CategoryGraph.from_edges(
        category_ids=snapshot["category_ids"], edges=snapshot["edges"]
    )
    return graph, attachment_branch_ids(
        graph=graph,
        attachment_roots=snapshot.get("attachment_root_ids", ()),
    )


async def _rule_graph(session: AsyncSession) -> CategoryGraph:
    """Category graph without boundary edges — for rule inheritance only."""
    full_graph, attachment_ids = await _attachment_context(session)
    return rule_inheritance_graph(graph=full_graph, attachment_ids=attachment_ids)


async def _validate_attachment_category_selection(
    session: AsyncSession,
    category_ids: Sequence[UUID],
) -> AttachmentClassification:
    _graph_snapshot, attachment_ids = await _attachment_context(session)
    return ensure_single_attachment_classification(
        category_ids=category_ids,
        attachment_ids=attachment_ids,
    )


def _validate_compatibility_states(
    *,
    product_id: UUID,
    attachment_product_ids: Sequence[UUID],
    states: Mapping[UUID, Mapping[str, Any]],
    attachment_ids: frozenset[UUID],
) -> None:
    owner = states.get(product_id)
    if owner is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    if owner.get("superstructure_id") is not None:
        raise KitInvariantError(
            "Комплект техники не поддерживает совместимые надстройки",
            code="KIT_COMPATIBILITY_FORBIDDEN",
        )
    owner_classification = ensure_single_attachment_classification(
        category_ids=owner["category_ids"],
        attachment_ids=attachment_ids,
    )
    if owner_classification is not AttachmentClassification.ORDINARY:
        raise AttachmentInvariantError(
            "Владельцем совместимости может быть только обычный товар",
            code="INVALID_COMPATIBILITY_OWNER",
        )
    for attachment_product_id in attachment_product_ids:
        if attachment_product_id == product_id:
            raise AttachmentInvariantError(
                "Товар нельзя связать с самим собой",
                code="SELF_ATTACHMENT_FORBIDDEN",
            )
        attachment = states.get(attachment_product_id)
        if attachment is None:
            raise SpecialEquipmentManagementNotFoundError("Надстройка не найдена")
        if attachment.get("superstructure_id") is not None:
            raise KitInvariantError(
                "Комплект техники не может быть совместимой надстройкой",
                code="KIT_COMPATIBILITY_FORBIDDEN",
            )
        classification = ensure_single_attachment_classification(
            category_ids=attachment["category_ids"],
            attachment_ids=attachment_ids,
        )
        if classification is not AttachmentClassification.ATTACHMENT:
            raise AttachmentInvariantError(
                "Совместимым товаром может быть только надстройка",
                code="PRODUCT_NOT_ATTACHMENT",
            )


async def _validate_attachment_integrity(
    session: AsyncSession,
    *,
    category_mutation: bool = False,
) -> None:
    """Validate every persisted classification-dependent relation in one pass."""

    try:
        _graph_snapshot, attachment_ids = await _attachment_context(session)
        for category_ids in (
            await repository.list_modification_category_sets(session)
        ).values():
            ensure_single_attachment_classification(
                category_ids=category_ids,
                attachment_ids=attachment_ids,
            )
        states = await repository.get_product_offering_states(session)
        _validate_offering_snapshot(
            states=states,
            attachment_links=(
                await repository.list_all_product_attachment_links(session)
            ),
            attachment_ids=attachment_ids,
        )
    except AttachmentInvariantError as exc:
        if category_mutation:
            raise AttachmentCategoryInUseError(
                "Изменение категории нарушает существующие надстройки"
            ) from exc
        raise


def _validate_offering_snapshot(
    *,
    states: Mapping[UUID, Mapping[str, Any]],
    attachment_links: Sequence[Mapping[str, Any]],
    attachment_ids: frozenset[UUID],
) -> None:
    for state in states.values():
        ensure_single_attachment_classification(
            category_ids=state["category_ids"],
            attachment_ids=attachment_ids,
        )
    by_owner: dict[UUID, list[UUID]] = {}
    for link in attachment_links:
        by_owner.setdefault(link["product_id"], []).append(
            link["attachment_product_id"]
        )
    for product_id, target_ids in by_owner.items():
        _validate_compatibility_states(
            product_id=product_id,
            attachment_product_ids=target_ids,
            states=states,
            attachment_ids=attachment_ids,
        )


async def _validate_attachment_neighborhood(
    session: AsyncSession, product_ids: Sequence[UUID]
) -> None:
    neighborhood = await repository.offering_neighborhood(session, product_ids)
    if not neighborhood["product_ids"]:
        return
    _graph_snapshot, attachment_ids = await _attachment_context(session)
    states = await repository.get_product_offering_states(
        session, neighborhood["product_ids"]
    )
    _validate_offering_snapshot(
        states=states,
        attachment_links=neighborhood["attachments"],
        attachment_ids=attachment_ids,
    )


async def _replace_parents(
    session: AsyncSession, category_id: UUID, parent_ids: Sequence[UUID]
) -> None:
    snapshot = await repository.category_graph_snapshot(session)
    edges = {
        edge for edge in snapshot["edges"] if edge[1] != category_id
    }
    graph = CategoryGraph.from_edges(
        category_ids=snapshot["category_ids"], edges=edges
    )
    for parent_id in parent_ids:
        graph = graph.with_edge(parent_id=parent_id, child_id=category_id)
    await repository.replace_category_parents(
        session, category_id=category_id, parent_ids=parent_ids
    )


async def _typed_values(
    session: AsyncSession, values: Sequence[Mapping[str, Any]]
) -> list[dict]:
    attribute_ids = [item["attribute_id"] for item in values]
    if len(attribute_ids) != len(set(attribute_ids)):
        raise SpecialEquipmentManagementValidationError(
            "Характеристику нельзя передать дважды"
        )
    definitions = await repository.get_attribute_definitions(
        session, attribute_ids
    )
    option_ids = [
        item["option_id"] for item in values if item.get("option_id") is not None
    ]
    options = await repository.get_option_definitions(session, option_ids)
    result: list[dict] = []
    for item in values:
        definition = definitions.get(item["attribute_id"])
        if definition is None:
            raise SpecialEquipmentManagementNotFoundError(
                "Характеристика не найдена"
            )
        option_id = item.get("option_id")
        option = options.get(option_id) if option_id is not None else None
        raw = item.get("value")
        if raw is None and option_id is None:
            non_null = [
                item.get("value_number"),
                item.get("value_text"),
                item.get("value_boolean"),
            ]
            provided = [value for value in non_null if value is not None]
            if len(provided) == 1:
                raw = provided[0]
            elif len(provided) > 1:
                raise SpecialEquipmentManagementValidationError(
                    "Для значения можно передать только одно типизированное поле"
                )
        result.append(
            typed_modification_value(
                definition=AttributeDefinition(
                    id=definition["id"],
                    code=definition["code"],
                    data_type=definition["data_type"],
                    is_active=definition["is_active"],
                ),
                raw=raw,
                option_id=option_id,
                option_attribute_id=(
                    option["attribute_id"]
                    if option and option.get("is_active", True)
                    else None
                ),
            )
        )
    return result


def _validate_modification_categories(category_ids: Sequence[UUID]) -> None:
    if not category_ids:
        raise SpecialEquipmentManagementValidationError(
            "У модификации должна быть основная категория"
        )
    if len(category_ids) != len(set(category_ids)):
        raise SpecialEquipmentManagementValidationError(
            "Категорию нельзя передать дважды"
        )


def _validate_attribute_filter_kind(*, data_type: str, filter_kind: str) -> None:
    if filter_kind == "range" and data_type != "number":
        raise SpecialEquipmentManagementValidationError(
            "Диапазон доступен только числовой характеристике"
        )
    if filter_kind == "search" and data_type != "text":
        raise SpecialEquipmentManagementValidationError(
            "Текстовый поиск доступен только текстовой характеристике"
        )


def _text_value_options(
    values: Sequence[str],
    *,
    existing_options: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    normalized = {value.strip() for value in values if value.strip()}
    existing_names = {
        str(option["name"]).strip() for option in existing_options
    }
    used_codes = {str(option["code"]) for option in existing_options}
    next_sort_order = max(
        (int(option["sort_order"]) for option in existing_options),
        default=-1,
    ) + 1
    result: list[dict[str, Any]] = []
    for sort_order, name in enumerate(
        sorted(
            normalized - existing_names,
            key=lambda item: (item.casefold(), item),
        ),
        start=next_sort_order,
    ):
        base = generate_catalog_slug(name)[:100]
        code = base
        suffix = 2
        while code in used_codes:
            marker = f"-{suffix}"
            code = f"{base[: 100 - len(marker)]}{marker}"
            suffix += 1
        used_codes.add(code)
        result.append(
            {
                "code": code,
                "name": name,
                "sort_order": sort_order,
                "is_active": True,
            }
        )
    return result


def _merge_converted_attribute_options(
    persisted_options: Sequence[Mapping[str, Any]],
    requested_options: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    requested_by_id = {
        option_id: dict(option)
        for option in requested_options
        if (option_id := option.get("id")) is not None
    }
    persisted_ids = {option["id"] for option in persisted_options}
    merged = [
        requested_by_id.get(
            option["id"],
            {
                "id": option["id"],
                "code": option["code"],
                "name": option["name"],
                "sort_order": option["sort_order"],
                "is_active": option["is_active"],
            },
        )
        for option in persisted_options
    ]
    merged.extend(
        dict(option)
        for option in requested_options
        if option.get("id") not in persisted_ids
    )
    return merged


async def _validate_modification_attribute_values(
    session: AsyncSession,
    *,
    category_ids: Sequence[UUID],
    attribute_ids: Iterable[UUID],
) -> None:
    try:
        rules_by_category = _rules_by_category(
            await repository.all_category_attribute_rules(session)
        )
        graph = await _rule_graph(session)
        allowed_attribute_ids = {
            rule.attribute_id
            for category_id in category_ids
            for rule in effective_attribute_rules(
                graph=graph,
                category_id=category_id,
                rules_by_category=rules_by_category,
            )
        }
        ensure_card_attribute_limit(
            graph=graph,
            category_ids=category_ids,
            rules_by_category=rules_by_category,
        )
    except SpecialEquipmentCatalogError as exc:
        raise SpecialEquipmentManagementValidationError(str(exc)) from exc
    if not set(attribute_ids).issubset(allowed_attribute_ids):
        raise SpecialEquipmentManagementValidationError(
            "Значения модификации разрешены только для характеристик "
            "выбранных категорий"
        )


async def _ensure_modification_values_not_assigned_in_trims(
    session: AsyncSession,
    *,
    modification_id: UUID,
    attribute_ids: Iterable[UUID],
) -> None:
    await repository.lock_modification_trim_states(session, modification_id)
    conflicts = trim_modification_value_conflicts(
        incoming_modification_values=(
            (modification_id, attribute_id) for attribute_id in attribute_ids
        ),
        incoming_trim_values=(),
        persisted_modification_values=(),
        persisted_trim_values=(
            (modification_id, attribute_id)
            for attribute_id in {
                row["attribute_id"]
                for row in await repository.trim_value_attributes_for_modification(
                    session, modification_id
                )
            }
        ),
    )
    if conflicts:
        conflict = conflicts[0]
        raise SpecialEquipmentTrimContractError(
            conflict.message,
            code=conflict.code,
            kind="conflict",
            detail={
                "attribute_ids": [
                    str(item.attribute_id) for item in conflicts
                ]
            },
        )


async def _validate_trim_attributes(
    session: AsyncSession,
    *,
    modification_id: UUID,
    attribute_links: Sequence[Mapping[str, Any]],
    value_attribute_ids: Iterable[UUID],
) -> None:
    modification = await repository.get_entity(session, "modification", modification_id)
    if modification is None:
        raise SpecialEquipmentManagementNotFoundError("Модификация не найдена")
    link_ids = [item["attribute_id"] for item in attribute_links]
    if len(link_ids) != len(set(link_ids)):
        raise SpecialEquipmentManagementValidationError(
            "Характеристику комплектации нельзя передать дважды"
        )
    value_ids = set(value_attribute_ids)
    if not value_ids.issubset(set(link_ids)):
        raise SpecialEquipmentManagementValidationError(
            "Значения комплектации разрешены только для её характеристик"
        )
    rules_by_category = _rules_by_category(
        [
            row
            for row in await repository.all_category_attribute_rules(session)
            if row["attribute_active"] and row["group_active"]
        ]
    )
    graph = await _rule_graph(session)
    contract = resolve_trim_attribute_contract(
        graph=graph,
        category_ids=modification.get("category_ids", []),
        rules_by_category=rules_by_category,
    )
    if contract.group_conflicts:
        raise SpecialEquipmentTrimContractError(
            "Характеристика назначена разным группам в категориях модификации",
            code="CATEGORY_ATTRIBUTE_GROUP_CONFLICT",
            kind="conflict",
            detail={
                "conflicts": [
                    {
                        "attribute_id": str(conflict.attribute_id),
                        "group_ids": [
                            str(group_id) if group_id is not None else None
                            for group_id in conflict.group_ids
                        ],
                    }
                    for conflict in contract.group_conflicts
                ]
            },
        )
    if any(
        (link["attribute_id"], link.get("group_id")) not in contract.allowed_pairs
        for link in attribute_links
    ):
        raise SpecialEquipmentTrimContractError(
            "Характеристика недоступна для комплектации",
            code="ATTRIBUTE_NOT_AVAILABLE_FOR_TRIM",
            kind="conflict",
        )
    modification_value_ids = {
        item["attribute_id"] for item in modification.get("attribute_values", [])
    }
    value_conflicts = trim_modification_value_conflicts(
        incoming_modification_values=(),
        incoming_trim_values=(
            (modification_id, attribute_id) for attribute_id in link_ids
        ),
        persisted_modification_values=(
            (modification_id, attribute_id)
            for attribute_id in modification_value_ids
        ),
        persisted_trim_values=(),
    )
    if value_conflicts:
        conflict = value_conflicts[0]
        raise SpecialEquipmentTrimContractError(
            conflict.message,
            code=conflict.code,
            kind="conflict",
        )


async def _validate_product_trim(
    session: AsyncSession,
    *,
    modification_id: UUID,
    trim_id: UUID | None,
    allow_inactive: bool = False,
) -> None:
    if trim_id is None:
        return
    if await repository.get_trim_modification_link(
        session,
        trim_id=trim_id,
        modification_id=modification_id,
        require_active=not allow_inactive,
    ) is None:
        raise SpecialEquipmentTrimContractError(
            "Комплектация должна быть активной и принадлежать выбранной модификации",
            code="TRIM_MODIFICATION_MISMATCH",
            kind="conflict",
        )


def _ensure_trim_not_reparented(
    *,
    current_modification_id: UUID,
    requested_modification_id: UUID | None,
) -> None:
    if (
        requested_modification_id is not None
        and requested_modification_id != current_modification_id
    ):
        raise SpecialEquipmentTrimContractError(
            "Нельзя перенести существующую комплектацию в другую модификацию",
            code="TRIM_MODIFICATION_MISMATCH",
            kind="conflict",
        )


async def _validate_category_attributes(
    session: AsyncSession,
    *,
    category_id: UUID,
    replacement: Sequence[Mapping[str, Any]],
) -> None:
    all_rows = [
        row
        for row in await repository.all_category_attribute_rules(session)
        if row["category_id"] != category_id
    ]
    all_rows.extend({"category_id": category_id, **dict(row)} for row in replacement)
    rules = _rules_by_category(all_rows)
    graph = await _rule_graph(session)
    try:
        ensure_category_change_card_attribute_limits(
            graph=graph,
            category_id=category_id,
            modification_category_sets=(
                await repository.list_modification_category_sets(session)
            ).values(),
            rules_by_category=rules,
        )
    except SpecialEquipmentCatalogError as exc:
        raise SpecialEquipmentManagementValidationError(str(exc)) from exc


async def _validate_product_warehouse(
    session: AsyncSession,
    *,
    no_vin: bool,
    sale_status: str,
    warehouse_id: UUID | None,
    seller_company_id: UUID | None,
    warehouse_explicit: bool = True,
) -> None:
    effective_warehouse_id = ensure_product_warehouse_assignment(
        no_vin=no_vin,
        sale_status=sale_status,
        warehouse_id=warehouse_id,
        warehouse_explicit=warehouse_explicit,
    )
    if effective_warehouse_id is None:
        return
    if not await repository.warehouse_exists(session, effective_warehouse_id):
        raise ProductWarehouseValidationError(
            "Склад не найден", code="WAREHOUSE_NOT_FOUND"
        )
    if not await repository.warehouse_is_active(session, effective_warehouse_id):
        raise ProductWarehouseValidationError(
            "Склад неактивен", code="WAREHOUSE_INACTIVE"
        )
    warehouse = await repository.get_warehouse_assignment(
        session, effective_warehouse_id
    )
    if warehouse is None:
        raise ProductWarehouseValidationError(
            "Склад не найден", code="WAREHOUSE_NOT_FOUND"
        )
    if warehouse["status"] != "active":
        raise ProductWarehouseValidationError(
            "Склад неактивен", code="WAREHOUSE_INACTIVE"
        )
    ensure_warehouse_owner_matches_seller(
        company_id=warehouse.get("company_id"),
        dealer_id=warehouse.get("dealer_id"),
        seller_company_id=seller_company_id,
    )


async def _validate_product(  # noqa: PLR0912, PLR0915
    session: AsyncSession,
    *,
    scalar: Mapping[str, Any],
    category_ids: Sequence[UUID],
    current_sale_status: str | None,
    current_color_ids: Mapping[str, UUID | None] | None = None,
    color_fields_present: frozenset[str] | None = None,
    allow_inactive_trim: bool = False,
    validate_warehouse_assignment: bool = True,
    warehouse_explicit: bool = True,
    chassis_values: Sequence[Mapping[str, Any]] | None = None,
    superstructure_values: Sequence[Mapping[str, Any]] | None = None,
    current_product_id: UUID | None = None,
) -> None:
    is_kit = scalar.get("model_id") is not None and scalar.get("superstructure_id") is not None
    if scalar.get("model_id") is not None and scalar.get("superstructure_id") is None:
        raise SpecialEquipmentManagementValidationError(
            "Для комплекта техники необходимо указать тип надстройки"
        )
    if is_kit:
        model_id = scalar.get("model_id")
        if model_id is None:
            raise SpecialEquipmentManagementValidationError(
                "Для комплекта техники необходимо указать модель шасси"
            )
        model = await repository.get_entity(session, "model", model_id)
        if model is None:
            raise SpecialEquipmentManagementNotFoundError("Модель шасси не найдена")
        mark = await repository.get_entity(session, "mark", model["mark_id"])
        if mark is None:
            raise SpecialEquipmentManagementNotFoundError("Марка шасси не найдена")

        modification_id = scalar.get("modification_id")
        chain = None
        if modification_id is not None:
            chain = await repository.get_modification_chain(session, modification_id)
            if chain is None:
                raise SpecialEquipmentManagementNotFoundError("Модификация шасси не найдена")
            if chain["model_id"] != model_id:
                raise KitInvariantError(
                    "Модификация шасси должна принадлежать выбранной модели шасси",
                    code="KIT_CHASSIS_MODIFICATION_MODEL_MISMATCH",
                )

        if scalar.get("trim_id") is not None:
            raise SpecialEquipmentManagementValidationError("У комплекта не может быть комплектации")

        superstructure_id = scalar.get("superstructure_id")
        if superstructure_id is None:
            raise SpecialEquipmentManagementValidationError(
                "Для комплекта техники необходимо указать тип надстройки"
            )
        superstructure = await repository.get_entity(
            session, "superstructure", superstructure_id
        )
        if superstructure is None:
            raise SpecialEquipmentManagementNotFoundError("Тип надстройки не найден")

        effective_category_ids = list(dict.fromkeys(category_ids))
        _graph_snapshot, attachment_ids = await _attachment_context(session)
        type_cat_ids = superstructure.get("category_ids", [])
        allowed_kit_cats = [cid for cid in type_cat_ids if cid not in attachment_ids]
        ensure_kit_categories(
            effective_category_ids,
            attachment_ids,
            allowed_superstructure_category_ids=allowed_kit_cats,
        )
        if await repository.get_active_category_ids(
            session, effective_category_ids
        ) != set(effective_category_ids):
            raise SpecialEquipmentManagementValidationError(
                "Выбрана неактивная категория: объявлению можно назначить "
                "только активные категории"
            )

        metrics = await repository.get_category_metrics(session, effective_category_ids)
        try:
            usage_metric = ensure_single_usage_metric(
                category_ids=effective_category_ids,
                metric_by_category=metrics,
            )
            ensure_condition_usage(
                condition=scalar["condition"],
                usage_metric=usage_metric,
                mileage_km=scalar.get("mileage_km"),
                engine_hours=scalar.get("engine_hours"),
            )
            ensure_condition_owners(
                condition=scalar["condition"],
                owners_count=scalar.get("owners_count"),
            )
            ensure_kit_vins(
                vin=scalar.get("vin"),
                chassis_vin=scalar.get("chassis_vin"),
                superstructure_vin=scalar.get("superstructure_vin"),
                no_vin=bool(scalar.get("no_vin")),
            )
            ensure_vin_choice(
                vin=scalar.get("vin"),
                no_vin=bool(scalar.get("no_vin")),
            )
        except (SpecialEquipmentCatalogError, DomainError) as exc:
            raise SpecialEquipmentManagementValidationError(str(exc)) from exc

        price = scalar.get("price")
        special_price = scalar.get("special_price")
        price_from = scalar.get("price_from")
        effective_price = ensure_product_commercial_terms(
            price=Decimal(str(price)) if price is not None else None,
            special_price=(
                Decimal(str(special_price)) if special_price is not None else None
            ),
            price_on_request=bool(scalar.get("price_on_request")),
            price_from=(
                Decimal(str(price_from)) if price_from is not None else None
            ),
        )
        if (
            scalar["sale_status"] == "on_order"
            and not bool(scalar.get("price_on_request"))
            and (
                effective_price is None or effective_price <= Decimal("0")
            )
        ):
            raise SpecialEquipmentManagementValidationError(
                "Для статуса «Под заказ» требуется положительная цена"
            )

        if validate_warehouse_assignment:
            await _validate_product_warehouse(
                session,
                no_vin=bool(scalar.get("no_vin")),
                sale_status=str(scalar["sale_status"]),
                warehouse_id=scalar.get("warehouse_id"),
                seller_company_id=scalar.get("seller_company_id"),
                warehouse_explicit=warehouse_explicit,
            )

        ensure_sale_transition(
            current=current_sale_status,
            requested=scalar["sale_status"],
            publication_status=scalar["publication_status"],
        )
        await _validate_product_color_assignment(
            session,
            color_id=scalar.get("body_color_id"),
            current_color_id=(current_color_ids or {}).get("body_color_id"),
            field_present=(
                color_fields_present is None or "body_color_id" in color_fields_present
            ),
            applicability="body",
            field="body_color_id",
        )
        await _validate_product_color_assignment(
            session,
            color_id=scalar.get("interior_color_id"),
            current_color_id=(current_color_ids or {}).get("interior_color_id"),
            field_present=(
                color_fields_present is None
                or "interior_color_id" in color_fields_present
            ),
            applicability="interior",
            field="interior_color_id",
        )

        # Chassis values check (Rules Ш4–Ш5)
        if modification_id is not None:
            if chassis_values:
                raise KitInvariantError(
                    "При выбранной модификации шасси собственные характеристики шасси не сохраняются",
                    code="KIT_CHASSIS_VALUES_WITH_MODIFICATION",
                )
        else:
            chassis_category_id = model.get("category_id")
            if chassis_category_id is None:
                raise SpecialEquipmentManagementValidationError(
                    "Для модели шасси не задана категория в справочнике. "
                    "Необходимо исправить модель в справочнике для определения характеристик шасси."
                )
            all_rule_rows = await repository.all_category_attribute_rules(session)
            rules_by_category = _rules_by_category(all_rule_rows)
            graph = await _rule_graph(session)
            rules_by_attr: dict[UUID, ChassisAttributeRule] = {}
            for rule in effective_attribute_rules(
                graph=graph,
                category_id=chassis_category_id,
                rules_by_category=rules_by_category,
            ):
                rules_by_attr[rule.attribute_id] = ChassisAttributeRule(
                    attribute_id=rule.attribute_id,
                    group_id=rule.group_id,
                    is_required=rule.is_required,
                    is_visible=rule.is_visible,
                    is_filterable=rule.is_filterable,
                    sort_order=rule.sort_order,
                )
            contract = ChassisAttributeContract(rules_by_attribute_id=rules_by_attr)
            typed_chassis = await _typed_values(session, chassis_values or ())
            ensure_kit_chassis_values(
                contract=contract,
                provided_attribute_ids=[v["attribute_id"] for v in typed_chassis],
                filled_attribute_ids=[
                    v["attribute_id"]
                    for v in typed_chassis
                    if v.get("option_id") is not None
                    or v.get("value_number") is not None
                    or v.get("value_text") is not None
                    or v.get("value_boolean") is not None
                ],
                has_modification=False,
                require_mandatory=(scalar["publication_status"] == "published"),
            )

        # Superstructure check (Rules Н1–Н5)

        ss_source_id = scalar.get("superstructure_source_product_id")
        source_product = None
        source_is_attachment = False
        if ss_source_id is not None:
            source_product = await repository.get_entity(session, "product", ss_source_id)
            if source_product is not None:
                source_is_attachment = bool(source_product.get("is_attachment"))

        ss_mod_id = scalar.get("superstructure_modification_id")
        ss_mod_model_id = None
        if ss_mod_id is not None:
            ss_mod = await repository.get_entity(session, "modification", ss_mod_id)
            if ss_mod is None:
                raise SpecialEquipmentManagementNotFoundError("Модификация надстройки не найдена")
            ss_mod_model_id = ss_mod.get("model_id")

        if ss_source_id is None and scalar.get("superstructure_model_id") is not None:
            ss_model = await repository.get_entity(
                session, "model", scalar["superstructure_model_id"]
            )
            if ss_model is None:
                raise SpecialEquipmentManagementNotFoundError("Модель надстройки не найдена")

        ensure_kit_superstructure(
            superstructure_is_active=bool(superstructure.get("is_active")),
            superstructure_source_product_id=ss_source_id,
            source_product=source_product,
            current_product_id=current_product_id,
            source_is_attachment=source_is_attachment,
            superstructure_model_id=scalar.get("superstructure_model_id"),
            superstructure_modification_model_id=ss_mod_model_id,
            superstructure_name=scalar.get("superstructure_name"),
            superstructure_manufacturer=scalar.get("superstructure_manufacturer"),
        )

        assignments = [
            SuperstructureAttributeAssignment(
                attribute_id=a["attribute_id"],
                group_id=a["group_id"],
                is_required=bool(a.get("is_required", False)),
                is_visible=bool(a.get("is_visible", False)),
                is_filterable=bool(a.get("is_filterable", False)),
                sort_order=int(a.get("sort_order", 0)),
            )
            for a in superstructure.get("attributes", [])
        ]
        typed_ss = await _typed_values(session, superstructure_values or ())
        ensure_kit_superstructure_values(
            assignments=assignments,
            provided_attribute_ids=[v["attribute_id"] for v in typed_ss],
            filled_attribute_ids=[
                v["attribute_id"]
                for v in typed_ss
                if v.get("option_id") is not None
                or v.get("value_number") is not None
                or v.get("value_text") is not None
                or v.get("value_boolean") is not None
            ],
            require_mandatory=(scalar["publication_status"] == "published"),
        )

        if scalar["publication_status"] == "published":
            seller_exists = await repository.lock_active_seller_company(
                session, scalar.get("seller_company_id")
            )
            if not seller_exists:
                raise SpecialEquipmentManagementValidationError("Продавец не найден или неактивен")
            if modification_id is not None and chain is not None:
                if not all(
                    (
                        chain["modification_active"],
                        chain["model_active"],
                        chain["mark_active"],
                    )
                ):
                    raise SpecialEquipmentManagementValidationError(
                        "Модификация, модель или марка шасси неактивна"
                    )
                ensure_manufacture_year_within_range(
                    manufacture_year=scalar.get("manufacture_year"),
                    year_from=chain["year_from"],
                    year_to=chain["year_to"],
                )
            elif not model.get("is_active") or not mark.get("is_active"):
                raise SpecialEquipmentManagementValidationError(
                    "Модель или марка шасси неактивна"
                )
        return

    modification_id = scalar["modification_id"]
    superstructure_id = scalar.get("superstructure_id")
    if superstructure_id is not None:
        superstructure = await repository.get_entity(session, "superstructure", superstructure_id)
        if superstructure is None:
            raise SpecialEquipmentManagementNotFoundError("Тип надстройки не найден")
        allowed_cats = await repository.get_superstructure_category_ids(session, superstructure_id)
        try:
            ensure_standalone_superstructure(
                superstructure_is_active=bool(superstructure.get("is_active")),
                superstructure_id=superstructure_id,
                allowed_category_ids=allowed_cats,
                category_ids=category_ids,
            )
        except DomainError as exc:
            raise SpecialEquipmentManagementValidationError(str(exc)) from exc

    chain = await repository.get_modification_chain(session, modification_id)
    if chain is None:
        raise SpecialEquipmentManagementNotFoundError("Модификация не найдена")
    modification_category_ids = await repository.get_allowed_modification_categories(
        session, modification_id
    )
    effective_category_ids = list(
        dict.fromkeys(
            [*category_ids, *sorted(modification_category_ids, key=str)]
        )
    )
    await _validate_attachment_category_selection(session, effective_category_ids)
    if await repository.get_active_category_ids(
        session, effective_category_ids
    ) != set(effective_category_ids):
        raise SpecialEquipmentManagementValidationError(
            "Выбрана неактивная категория: объявлению можно назначить "
            "только активные категории"
        )
    metrics = await repository.get_category_metrics(session, effective_category_ids)
    try:
        usage_metric = ensure_single_usage_metric(
            category_ids=effective_category_ids,
            metric_by_category=metrics,
        )
        ensure_condition_usage(
            condition=scalar["condition"],
            usage_metric=usage_metric,
            mileage_km=scalar.get("mileage_km"),
            engine_hours=scalar.get("engine_hours"),
        )
        ensure_condition_owners(
            condition=scalar["condition"],
            owners_count=scalar.get("owners_count"),
        )
        if scalar.get("no_vin"):
            if scalar.get("vin") or scalar.get("chassis_vin") or scalar.get("superstructure_vin"):
                raise SpecialEquipmentManagementValidationError(
                    "При отметке «Нет VIN» все поля VIN должны быть пустыми"
                )
        else:
            ensure_vin_choice(
                vin=scalar.get("vin"),
                no_vin=bool(scalar.get("no_vin")),
            )
            if scalar.get("chassis_vin") or scalar.get("superstructure_vin"):
                raise SpecialEquipmentManagementValidationError(
                    "VIN шасси и VIN надстройки допустимы только для комплекта"
                )
    except SpecialEquipmentCatalogError as exc:
        raise SpecialEquipmentManagementValidationError(str(exc)) from exc
    price = scalar.get("price")
    special_price = scalar.get("special_price")
    price_from = scalar.get("price_from")
    effective_price = ensure_product_commercial_terms(
        price=Decimal(str(price)) if price is not None else None,
        special_price=(
            Decimal(str(special_price)) if special_price is not None else None
        ),
        price_on_request=bool(scalar.get("price_on_request")),
        price_from=(
            Decimal(str(price_from)) if price_from is not None else None
        ),
    )
    if (
        scalar["sale_status"] == "on_order"
        and not bool(scalar.get("price_on_request"))
        and (
            effective_price is None or effective_price <= Decimal("0")
        )
    ):
        raise SpecialEquipmentManagementValidationError(
            "Для статуса «Под заказ» требуется положительная цена"
        )
    if validate_warehouse_assignment:
        await _validate_product_warehouse(
            session,
            no_vin=bool(scalar.get("no_vin")),
            sale_status=str(scalar["sale_status"]),
            warehouse_id=scalar.get("warehouse_id"),
            seller_company_id=scalar.get("seller_company_id"),
            warehouse_explicit=warehouse_explicit,
        )
    await _validate_product_trim(
        session,
        modification_id=modification_id,
        trim_id=scalar.get("trim_id"),
        allow_inactive=allow_inactive_trim,
    )
    ensure_sale_transition(
        current=current_sale_status,
        requested=scalar["sale_status"],
        publication_status=scalar["publication_status"],
    )
    await _validate_product_color_assignment(
        session,
        color_id=scalar.get("body_color_id"),
        current_color_id=(current_color_ids or {}).get("body_color_id"),
        field_present=(
            color_fields_present is None or "body_color_id" in color_fields_present
        ),
        applicability="body",
        field="body_color_id",
    )
    await _validate_product_color_assignment(
        session,
        color_id=scalar.get("interior_color_id"),
        current_color_id=(current_color_ids or {}).get("interior_color_id"),
        field_present=(
            color_fields_present is None or "interior_color_id" in color_fields_present
        ),
        applicability="interior",
        field="interior_color_id",
    )
    try:
        all_rule_rows = await repository.all_category_attribute_rules(session)
        rules_by_category = _rules_by_category(all_rule_rows)
        graph = await _rule_graph(session)
        required: set[UUID] = set()
        effective_rules_by_attribute: dict[UUID, CategoryAttributeRule] = {}
        for category_id in effective_category_ids:
            for rule in effective_attribute_rules(
                graph=graph,
                category_id=category_id,
                rules_by_category=rules_by_category,
            ):
                effective_rules_by_attribute[rule.attribute_id] = rule
                if rule.is_required:
                    required.add(rule.attribute_id)
    except SpecialEquipmentCatalogError as exc:
        raise SpecialEquipmentManagementValidationError(str(exc)) from exc
    (
        attribute_groups_active,
        attributes_active,
        attribute_options_active,
    ) = _publication_attribute_activity(
        rule_rows=all_rule_rows,
        effective_rules=effective_rules_by_attribute.values(),
        value_rows=await repository.get_modification_value_activity(
            session, modification_id
        ),
    )
    modification = await repository.get_entity(
        session, "modification", modification_id
    )
    value_ids = {
        item["attribute_id"]
        for item in (modification or {}).get("attribute_values", [])
    }
    ensure_publication_ready(
        publication_status=scalar["publication_status"],
        directory_chain_active=all(
            (
                chain["modification_active"],
                chain["model_active"],
                chain["mark_active"],
            )
        ),
        seller_exists=await repository.lock_active_seller_company(
            session, scalar.get("seller_company_id")
        ),
        categories_active=(
            await repository.get_active_category_ids(session, effective_category_ids)
            == set(effective_category_ids)
        ),
        attribute_groups_active=attribute_groups_active,
        attributes_active=attributes_active,
        attribute_options_active=attribute_options_active,
        category_ids=effective_category_ids,
        required_attribute_ids=required,
        value_attribute_ids=value_ids,
    )
    if scalar["publication_status"] == "published":
        ensure_manufacture_year_within_range(
            manufacture_year=scalar.get("manufacture_year"),
            year_from=chain["year_from"],
            year_to=chain["year_to"],
        )


async def _validate_product_color_assignment(
    session: AsyncSession,
    *,
    color_id: UUID | None,
    current_color_id: UUID | None = None,
    field_present: bool = True,
    applicability: Literal["body", "interior"],
    field: str,
) -> None:
    if not field_present or color_id is None or color_id == current_color_id:
        return
    color = await repository.get_color(session, color_id)
    if color is None:
        raise SpecialEquipmentColorValidationError(
            "Цвет не найден",
            field=field,
            code="color_not_found",
            field_code="not_found",
        )
    ensure_product_color_assignment_allowed(
        current_color_id=current_color_id,
        field_present=field_present,
        requested_color_id=color_id,
        is_active=bool(color["is_active"]),
        color_applicability=str(color["applicability"]),
        required_applicability=applicability,
        field=field,
    )


async def _ensure_published_dependencies_valid(
    session: AsyncSession,
    *,
    entity_type: repository.EntityType,
    entity_id: UUID,
) -> None:
    """Reject a mutation that invalidates already published products."""

    product_ids = await repository.published_product_ids_for_entity(
        session, entity_type, entity_id
    )
    if not product_ids:
        return
    graph = await _rule_graph(session)
    all_rule_rows = await repository.all_category_attribute_rules(session)
    rules_by_category = _rules_by_category(all_rule_rows)
    invalid: dict[str, dict[str, Any]] = {}
    snapshots = await repository.published_product_validation_snapshots(
        session, product_ids
    )
    for product in snapshots:
        category_ids = [item["id"] for item in product["categories"]]
        metrics = {
            item["id"]: item["usage_metric"]
            for item in product["categories"]
        }
        try:
            usage_metric = ensure_single_usage_metric(
                category_ids=category_ids,
                metric_by_category=metrics,
            )
            ensure_condition_usage(
                condition=product["condition"],
                usage_metric=usage_metric,
                mileage_km=product["mileage_km"],
                engine_hours=product["engine_hours"],
            )
            required: set[UUID] = set()
            effective_rules_by_attribute: dict[
                UUID, CategoryAttributeRule
            ] = {}
            for category_id in category_ids:
                for rule in effective_attribute_rules(
                    graph=graph,
                    category_id=category_id,
                    rules_by_category=rules_by_category,
                ):
                    effective_rules_by_attribute[rule.attribute_id] = rule
                    if rule.is_required:
                        required.add(rule.attribute_id)
            (
                attribute_groups_active,
                attributes_active,
                attribute_options_active,
            ) = _publication_attribute_activity(
                rule_rows=all_rule_rows,
                effective_rules=effective_rules_by_attribute.values(),
                value_rows=product["value_activity"],
            )
            ensure_publication_ready(
                publication_status=product["publication_status"],
                directory_chain_active=all(
                    (
                        product["modification_active"],
                        product["model_active"],
                        product["mark_active"],
                    )
                ),
                seller_exists=product["seller_exists"],
                categories_active=all(
                    item["is_active"] for item in product["categories"]
                ),
                attribute_groups_active=attribute_groups_active,
                attributes_active=attributes_active,
                attribute_options_active=attribute_options_active,
                category_ids=category_ids,
                required_attribute_ids=required,
                value_attribute_ids=product["value_attribute_ids"],
            )
            ensure_manufacture_year_within_range(
                manufacture_year=product["manufacture_year"],
                year_from=product["year_from"],
                year_to=product["year_to"],
            )
        except (
            SpecialEquipmentCatalogError,
            SpecialEquipmentManagementValidationError,
        ) as exc:
            reason = str(exc)
            aggregate = invalid.setdefault(
                reason,
                {
                    "entity_id": product["id"],
                    "code": product["code"],
                    "count": 0,
                },
            )
            aggregate["count"] += 1
    if not invalid:
        return
    subject = await repository.get_entity(session, entity_type, entity_id)
    if subject is None:
        raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")
    dependencies = tuple(
        CatalogDependency(
            entity_type="product",
            entity_id=aggregate["entity_id"],
            code=aggregate["code"],
            name=reason,
            count=aggregate["count"],
        )
        for reason, aggregate in sorted(invalid.items())
    )
    raise SpecialEquipmentManagementConflictError(
        "Изменение сделает опубликованные объявления невалидными",
        entity_type=entity_type,
        entity_id=entity_id,
        entity_code=subject.get("code"),
        entity_name=subject.get("name") or subject.get("code"),
        dependencies=dependencies,
    )


def _publication_attribute_activity(
    *,
    rule_rows: Sequence[Mapping[str, Any]],
    effective_rules: Iterable[CategoryAttributeRule],
    value_rows: Sequence[Mapping[str, Any]],
) -> tuple[bool, bool, bool]:
    """Resolve active-state guards for the attributes visible in a product."""

    effective = tuple(effective_rules)
    relevant_attribute_ids = {rule.attribute_id for rule in effective}
    relevant_group_ids = {
        rule.group_id for rule in effective if rule.group_id is not None
    }
    attribute_activity = {
        row["attribute_id"]: bool(row["attribute_active"])
        for row in rule_rows
    }
    group_activity = {
        row["group_id"]: bool(row["group_active"]) for row in rule_rows
    }
    relevant_values = [
        row
        for row in value_rows
        if row["attribute_id"] in relevant_attribute_ids
    ]
    return (
        all(group_activity.get(group_id, False) for group_id in relevant_group_ids),
        all(
            attribute_activity.get(attribute_id, False)
            for attribute_id in relevant_attribute_ids
        )
        and all(bool(row["attribute_active"]) for row in relevant_values),
        all(
            row["option_id"] is None or bool(row["option_active"])
            for row in relevant_values
        ),
    )


_DEACTIVATION_DEPENDENCIES: dict[
    repository.EntityType, frozenset[str]
] = {
    "attribute_group": frozenset({"attributes", "category_attributes"}),
    "attribute": frozenset(
        {"category_attributes", "modification_values"}
    ),
    "attribute_option": frozenset({"modification_values"}),
}


async def _validate_attribute_group_members(
    session: AsyncSession,
    attribute_ids: Sequence[UUID],
    *,
    group_is_active: bool,
) -> None:
    if attribute_ids and not group_is_active:
        raise SpecialEquipmentManagementValidationError(
            "Нельзя назначить характеристики неактивной группе"
        )
    if len(attribute_ids) != len(set(attribute_ids)):
        raise SpecialEquipmentManagementValidationError(
            "Характеристику нельзя передать дважды"
        )
    definitions = await repository.get_attribute_definitions(
        session, attribute_ids
    )
    if len(definitions) != len(attribute_ids):
        raise SpecialEquipmentManagementNotFoundError(
            "Одна или несколько характеристик не найдены"
        )


async def _require_active_attribute_group(
    session: AsyncSession, group_id: UUID
) -> Mapping[str, Any]:
    group = await repository.get_entity(session, "attribute_group", group_id)
    if group is None:
        raise SpecialEquipmentManagementNotFoundError(
            "Группа характеристик не найдена"
        )
    if not group["is_active"]:
        raise SpecialEquipmentManagementValidationError(
            "Нельзя назначить неактивную группу характеристик"
        )
    return group


async def _ensure_deactivation_allowed(
    session: AsyncSession,
    *,
    entity_type: repository.EntityType,
    entity: Mapping[str, Any],
) -> None:
    dependency_names = _DEACTIVATION_DEPENDENCIES.get(entity_type)
    if dependency_names is None:
        return
    dependencies = await repository.dependencies(
        session, entity_type, entity["id"]
    )
    ensure_deactivation_allowed(
        {
            name: count
            for name, count in dependencies.items()
            if name in dependency_names
        },
        entity_type=entity_type,
        entity_id=entity["id"],
        entity_code=entity.get("code"),
        entity_name=entity.get("name") or entity.get("code"),
    )


async def _replace_attribute_options(
    session: AsyncSession,
    *,
    attribute_id: UUID,
    options: Sequence[Mapping[str, Any]],
) -> None:
    attribute = await repository.get_entity(session, "attribute", attribute_id)
    if attribute is None:
        raise SpecialEquipmentManagementNotFoundError(
            "Характеристика не найдена"
        )
    if attribute["data_type"] != "select" and options:
        raise SpecialEquipmentManagementValidationError(
            "Варианты допустимы только для select-характеристики"
        )
    existing, _ = await repository.list_entities(
        session,
        "attribute_option",
        offset=0,
        limit=1000,
        attribute_id=attribute_id,
    )
    by_id = {item["id"]: item for item in existing}
    retained: set[UUID] = set()
    codes: set[str] = set()
    for raw in options:
        item = dict(raw)
        option_id = item.pop("id", None)
        code = item["code"]
        if code in codes:
            raise SpecialEquipmentManagementValidationError(
                "Код варианта нельзя передать дважды"
            )
        codes.add(code)
        if option_id is None:
            await repository.create_entity(
                session,
                "attribute_option",
                {"attribute_id": attribute_id, **item},
            )
            continue
        current = by_id.get(option_id)
        if current is None:
            raise SpecialEquipmentManagementValidationError(
                "Вариант не принадлежит характеристике"
            )
        if current["code"] != code:
            raise SpecialEquipmentManagementValidationError(
                "Код существующего варианта неизменяем"
            )
        retained.add(option_id)
        if current["is_active"] and not item["is_active"]:
            await _ensure_deactivation_allowed(
                session,
                entity_type="attribute_option",
                entity=current,
            )
        await repository.patch_entity(
            session,
            "attribute_option",
            option_id,
            {
                "name": item["name"],
                "sort_order": item["sort_order"],
                "is_active": item["is_active"],
            },
        )
    for option_id in set(by_id) - retained:
        deleted_option = by_id[option_id]
        blockers = await repository.dependencies(
            session, "attribute_option", option_id
        )
        ensure_delete_allowed(
            blockers,
            entity_type="attribute_option",
            entity_id=option_id,
            entity_code=deleted_option["code"],
            entity_name=deleted_option["name"],
        )
        await repository.delete_entity(session, "attribute_option", option_id)


async def _replay_create(
    session: AsyncSession,
    *,
    actor_id: UUID,
    idempotency_key: str,
    request_hash: str,
    entity_type: repository.EntityType,
) -> dict | None:
    await repository.lock_idempotency_key(
        session, actor_id, idempotency_key
    )
    receipt = await repository.get_mutation_receipt(
        session, actor_id, idempotency_key
    )
    if receipt is None:
        return None
    if (
        receipt["request_hash"] != request_hash
        or receipt["resource_type"] != entity_type
    ):
        if entity_type == "color":
            raise SpecialEquipmentColorConflictError(
                "Этот Idempotency-Key уже использовался с другим телом запроса",
                code="idempotency_payload_mismatch",
                detail={"resource_type": "color"},
            )
        raise SpecialEquipmentManagementConflictError(
            "Idempotency-Key уже использован для другого запроса"
        )
    response_snapshot = receipt.get("response_snapshot")
    if response_snapshot is not None:
        return dict(response_snapshot)
    resource = await repository.get_entity(
        session, entity_type, receipt["resource_id"]
    )
    if resource is None:
        if entity_type == "color":
            raise SpecialEquipmentColorConflictError(
                "Операция с этим Idempotency-Key уже создавала ресурс, "
                "но он был удалён",
                code="idempotency_resource_deleted",
                detail={"resource_type": "color"},
            )
        raise SpecialEquipmentManagementConflictError(
            "Результат идемпотентного запроса больше недоступен"
        )
    return resource


async def _validate_superstructure_create(
    session: AsyncSession,
    payload: dict,
    attributes: list[dict],
    category_ids: Sequence[UUID] | None = None,
) -> None:
    payload["code"] = validate_entity_code(payload["code"])
    name = payload.get("name", "")
    payload["name"] = name.strip()
    if not (1 <= len(payload["name"]) <= 255):
        raise SpecialEquipmentManagementValidationError(
            "Название надстройки должно содержать от 1 до 255 символов"
        )
    if await repository.superstructure_name_exists(session, payload["name"]):
        raise KitInvariantError(
            "Надстройка с таким названием уже существует",
            code="SUPERSTRUCTURE_NAME_CONFLICT",
        )
    await _validate_superstructure_attributes(session, attributes)
    if category_ids:
        active_cats = await repository.get_active_category_ids(session, category_ids)
        if set(active_cats) != set(category_ids):
            raise SpecialEquipmentManagementValidationError(
                "Выбрана неактивная категория для типа надстройки"
            )


async def _validate_superstructure_attributes(
    session: AsyncSession,
    attributes: list[dict],
) -> None:
    if not attributes:
        return
    attr_ids = [a["attribute_id"] for a in attributes]
    if len(attr_ids) != len(set(attr_ids)):
        raise KitInvariantError(
            "Характеристика не может быть назначена повторно",
            code="SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
        )
    attrs_map: dict[UUID, UUID] = {}
    for aid in attr_ids:
        attr = await repository.get_entity(session, "attribute", aid)
        if attr is None or not attr.get("is_active"):
            raise KitInvariantError(
                f"Характеристика {aid} не найдена или неактивна",
                code="SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
            )
        group_id = attr.get("attribute_group_id")
        if group_id is None:
            raise KitInvariantError(
                f"Характеристика {aid} не входит в группу",
                code="SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
            )
        group = await repository.get_entity(session, "attribute_group", group_id)
        if group is None or not group.get("is_active"):
            raise KitInvariantError(
                f"Группа характеристик {group_id} не найдена или неактивна",
                code="SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
            )
        attrs_map[aid] = group_id
    assignments = [
        SuperstructureAttributeAssignment(
            attribute_id=a["attribute_id"],
            group_id=a["group_id"],
            is_required=bool(a.get("is_required", False)),
            is_visible=bool(a.get("is_visible", False)),
            is_filterable=bool(a.get("is_filterable", False)),
            sort_order=int(a.get("sort_order", 0)),
        )
        for a in attributes
    ]
    ensure_superstructure_attribute_groups(assignments, attrs_map)


async def _validate_superstructure_patch(
    session: AsyncSession,
    current: dict,
    payload: dict,
    attributes: list[dict] | None,
    category_ids: Sequence[UUID] | None = None,
) -> None:
    entity_id = current["id"]
    name = payload.get("name")
    if name is not None:
        payload["name"] = name.strip()
        if not (1 <= len(payload["name"]) <= 255):
            raise SpecialEquipmentManagementValidationError(
                "Название надстройки должно содержать от 1 до 255 символов"
            )
        if await repository.superstructure_name_exists(
            session, payload["name"], exclude_id=entity_id
        ):
            raise KitInvariantError(
                "Надстройка с таким названием уже существует",
                code="SUPERSTRUCTURE_NAME_CONFLICT",
            )

    if category_ids is not None and category_ids:
        current_cat_ids = set(current.get("category_ids", []))
        newly_added = set(category_ids) - current_cat_ids
        if newly_added:
            active_cats = await repository.get_active_category_ids(session, list(newly_added))
            if set(active_cats) != newly_added:
                raise SpecialEquipmentManagementValidationError(
                    "Выбрана неактивная категория для типа надстройки"
                )

    if attributes is not None:
        await _validate_superstructure_attributes(session, attributes)
        current_attr_ids = {a["attribute_id"] for a in current.get("attributes", [])}
        new_attr_ids = {a["attribute_id"] for a in attributes}
        removed_attr_ids = current_attr_ids - new_attr_ids
        if removed_attr_ids:
            in_use_count = await repository.count_products_with_superstructure_attribute_values(
                session, entity_id, removed_attr_ids
            )
            if in_use_count > 0:
                raise KitInvariantError(
                    f"Характеристику нельзя убрать из типа, так как в комплектах ({in_use_count}) есть её значения",
                    code="SUPERSTRUCTURE_ATTRIBUTE_IN_USE",
                )
        new_required_ids = {
            a["attribute_id"] for a in attributes if a.get("is_required")
        }
        old_required_ids = {
            a["attribute_id"]
            for a in current.get("attributes", [])
            if a.get("is_required")
        }
        added_required_ids = new_required_ids - old_required_ids
        if added_required_ids:
            missing_count = await repository.count_published_products_missing_superstructure_attributes(
                session, entity_id, added_required_ids
            )
            if missing_count > 0:
                raise KitInvariantError(
                    "Характеристику нельзя сделать обязательной, если есть опубликованные комплекты этого типа без значения",
                    code="SUPERSTRUCTURE_REQUIRED_VALUE_MISSING",
                )


async def create_entity(  # noqa: PLR0912, PLR0915
    session: AsyncSession,
    *,
    entity_type: repository.EntityType,
    values: Mapping[str, Any],
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    payload = dict(values)
    parent_ids = payload.pop("parent_ids", None)
    category_ids = payload.pop("category_ids", None)
    attribute_ids = payload.pop("attribute_ids", None)
    attribute_links = payload.pop("attribute_links", None)
    attribute_values = payload.pop("attribute_values", None)
    options = payload.pop("options", None)
    superstructure_attributes = payload.pop("attributes", None)
    chassis_values = payload.pop("chassis_values", None)
    superstructure_values = payload.pop("superstructure_values", None)
    typed_attribute_values: list[dict] | None = None
    if entity_type == "trim" and "code" not in payload:
        payload["code"] = f"trim-{uuid4().hex}"
    if entity_type in _SLUGGED_ENTITY_TYPES:
        payload["slug"] = generate_catalog_slug(payload["name"])
    elif entity_type == "product":
        payload["slug"] = generate_catalog_slug(payload["code"])
        if not bool(payload.get("price_on_request")):
            payload["price_from"] = None
        if payload.get("no_vin"):
            payload["vin"] = None
            payload["chassis_vin"] = None
            payload["superstructure_vin"] = None
        else:
            if payload.get("vin") is not None:
                payload["vin"] = payload["vin"].strip()
            if payload.get("chassis_vin") is not None:
                payload["chassis_vin"] = payload["chassis_vin"].strip()
            if payload.get("superstructure_vin") is not None:
                payload["superstructure_vin"] = payload["superstructure_vin"].strip()
        if payload.get("publication_status") == "published":
            payload["published_at"] = datetime.now(UTC)

    if entity_type == "model":
        mark = await repository.get_entity(session, "mark", payload["mark_id"])
        if mark is None:
            raise SpecialEquipmentManagementNotFoundError("Марка не найдена")
        if "category_id" in payload and payload["category_id"] is not None:
            category = await repository.get_entity(session, "category", payload["category_id"])
            if category is None:
                raise SpecialEquipmentManagementNotFoundError("Категория не найдена")
            if not category.get("is_active"):
                raise SpecialEquipmentManagementValidationError("Нельзя выбрать неактивную категорию")
        else:
            raise SpecialEquipmentManagementValidationError("Для модели необходимо указать категорию")
    elif entity_type == "modification":
        model = await repository.get_entity(session, "model", payload["model_id"])
        if model is None:
            raise SpecialEquipmentManagementNotFoundError("Модель не найдена")
        ensure_year_range(payload.get("year_from"), payload.get("year_to"))
        _validate_modification_categories(category_ids or ())
        await _validate_attachment_category_selection(
            session, category_ids or ()
        )
        typed_attribute_values = await _typed_values(
            session, attribute_values or ()
        )
        await _validate_modification_attribute_values(
            session,
            category_ids=category_ids or (),
            attribute_ids=(
                item["attribute_id"] for item in typed_attribute_values
            ),
        )
    elif entity_type == "trim":
        modification = await repository.get_entity(
            session, "modification", payload["modification_id"]
        )
        if modification is None or modification.get("is_active") is not True:
            raise SpecialEquipmentTrimContractError(
                "Активная модификация не найдена",
                code="MODIFICATION_NOT_FOUND",
                kind="not_found",
            )
    elif entity_type == "attribute_option":
        attribute = await repository.get_entity(
            session, "attribute", payload["attribute_id"]
        )
        if attribute is None or attribute["data_type"] != "select":
            raise SpecialEquipmentManagementValidationError(
                "Варианты допустимы только для select-характеристики"
            )
    elif entity_type == "unit":
        payload["code"] = validate_entity_code(payload["code"])
        payload["name"] = payload["name"].strip()
        if not (1 <= len(payload["name"]) <= 50):
            raise SpecialEquipmentManagementValidationError(
                "Название единицы измерения должно содержать от 1 до 50 символов"
            )
    elif entity_type == "attribute":
        _validate_attribute_filter_kind(
            data_type=payload["data_type"],
            filter_kind=payload["filter_kind"],
        )
        if payload.get("attribute_group_id") is not None:
            await _require_active_attribute_group(
                session, payload["attribute_group_id"]
            )
        if payload.get("unit_id") is not None:
            unit = await repository.get_entity(session, "unit", payload["unit_id"])
            if unit is None:
                raise UnitNotFoundError("Единица измерения не найдена")
            if not unit.get("is_active"):
                raise UnitInactiveError("Нельзя выбрать неактивную единицу измерения")
    elif entity_type == "superstructure":
        await _validate_superstructure_create(
            session, payload, superstructure_attributes or [], category_ids=category_ids
        )

    if entity_type == "product":
        await _validate_product(
            session,
            scalar=payload,
            category_ids=category_ids or (),
            current_sale_status=None,
            chassis_values=chassis_values,
            superstructure_values=superstructure_values,
        )
    entity_id = await repository.create_entity(
        session, entity_type, payload
    )
    if entity_type == "category":
        await _replace_parents(session, entity_id, parent_ids or ())
        await _validate_category_attributes(
            session,
            category_id=entity_id,
            replacement=attribute_links or (),
        )
        await repository.replace_category_attributes(
            session,
            category_id=entity_id,
            links=attribute_links or (),
        )
    elif entity_type == "superstructure":
        if superstructure_attributes:
            await repository.replace_superstructure_attributes(
                session, superstructure_id=entity_id, attributes=superstructure_attributes
            )
        if category_ids is not None:
            await repository.replace_superstructure_categories(
                session, superstructure_id=entity_id, category_ids=category_ids
            )
    elif entity_type == "modification":
        await repository.replace_modification_categories(
            session,
            modification_id=entity_id,
            category_ids=category_ids or (),
        )
        await repository.replace_modification_values(
            session,
            modification_id=entity_id,
            values=typed_attribute_values or [],
        )
    elif entity_type == "product":
        await repository.replace_product_categories(
            session, product_id=entity_id, category_ids=category_ids or ()
        )
        if payload.get("model_id") is not None and payload.get("superstructure_id") is not None:
            if not payload.get("modification_id") and chassis_values:
                typed_chassis = await _typed_values(session, chassis_values)
                await repository.replace_product_chassis_values(
                    session, product_id=entity_id, values=typed_chassis
                )
            if superstructure_values:
                typed_ss = await _typed_values(session, superstructure_values)
                await repository.replace_product_superstructure_values(
                    session,
                    product_id=entity_id,
                    superstructure_id=payload["superstructure_id"],
                    values=typed_ss,
                )
    elif entity_type == "attribute_group":
        await _validate_attribute_group_members(
            session,
            attribute_ids or (),
            group_is_active=bool(payload.get("is_active", True)),
        )
        await repository.replace_attribute_group_members(
            session,
            group_id=entity_id,
            attribute_ids=attribute_ids or (),
        )
    elif entity_type == "attribute":
        await _replace_attribute_options(
            session,
            attribute_id=entity_id,
            options=options or (),
        )
    if entity_type == "attribute_group" and attribute_ids:
        await _ensure_published_dependencies_valid(
            session,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    row = await repository.get_entity(session, entity_type, entity_id)
    if row is None:
        raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")
    await repository.increment_catalog_revision(session)
    return row


async def create_entity_idempotent(
    session: AsyncSession,
    *,
    actor_id: UUID,
    idempotency_key: str,
    request_hash: str,
    entity_type: repository.EntityType,
    values: Mapping[str, Any],
) -> dict:
    replay = await _replay_create(
        session,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        entity_type=entity_type,
    )
    if replay is not None:
        return replay
    row = await create_entity(
        session,
        entity_type=entity_type,
        values=values,
    )
    await repository.add_mutation_receipt(
        session,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        resource_type=entity_type,
        resource_id=row["id"],
        response_snapshot=row,
    )
    return row


async def create_color_idempotent(
    session: AsyncSession,
    *,
    actor_id: UUID,
    idempotency_key: str,
    request_hash: str,
    values: Mapping[str, Any],
) -> dict:
    replay = await _replay_create(
        session,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        entity_type="color",
    )
    if replay is not None:
        if await repository.get_color(session, replay["id"]) is None:
            raise SpecialEquipmentColorConflictError(
                "Операция с этим Idempotency-Key уже создавала ресурс, "
                "но он был удалён",
                code="idempotency_resource_deleted",
                detail={"resource_type": "color"},
            )
        return replay
    name = normalize_color_name(str(values["name"]))
    payload = {
        "name": name,
        "code": normalize_color_code(values.get("code"), name=name),
        "applicability": normalize_color_applicability(str(values["applicability"])),
        "is_active": bool(values.get("is_active", True)),
    }
    row = await repository.create_color(session, payload)
    await repository.add_mutation_receipt(
        session,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        resource_type="color",
        resource_id=row["id"],
        response_snapshot=row,
    )
    await repository.increment_catalog_revision(session)
    return row


def _trim_link_signature(
    links: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        sorted(
            (
                item["attribute_id"],
                item.get("group_id"),
                bool(item.get("is_required", False)),
                bool(item.get("is_filterable", False)),
                int(item.get("sort_order", 0)),
            )
            for item in links
        )
    )


def _trim_value_signature(
    values: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        sorted(
            (
                item["attribute_id"],
                item.get("value_number"),
                item.get("value_text"),
                item.get("value_boolean"),
                item.get("option_id"),
            )
            for item in values
        )
    )


async def update_color(
    session: AsyncSession,
    *,
    color_id: UUID,
    values: Mapping[str, Any],
    expected_version: int,
    expected_etag: str | None = None,
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    current = await repository.get_color(session, color_id)
    if current is None:
        raise SpecialEquipmentManagementNotFoundError("Цвет не найден")
    _ensure_precondition(
        current,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    payload: dict[str, Any] = {}
    name = normalize_color_name(str(values.get("name", current["name"])))
    if "name" in values:
        payload["name"] = name
    if "code" in values:
        payload["code"] = normalize_color_code(values.get("code"), name=name)
    if "applicability" in values:
        requested = normalize_color_applicability(str(values["applicability"]))
        counts = await repository.color_usage_counts(session, color_id)
        ensure_color_applicability_change_allowed(
            current=current["applicability"],
            requested=requested,
            body_products_count=counts["body"],
            interior_products_count=counts["interior"],
        )
        payload["applicability"] = requested
    if "is_active" in values:
        payload["is_active"] = bool(values["is_active"])
    row = await repository.update_color(
        session, color_id, payload, lock_version=expected_version
    )
    if row is None:
        raise SpecialEquipmentManagementPreconditionError("Ресурс уже изменён")
    await repository.increment_catalog_revision(session)
    return row


async def delete_color(
    session: AsyncSession,
    *,
    color_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
) -> None:
    await repository.lock_catalog_for_mutation(session)
    current = await repository.get_color(session, color_id)
    if current is None:
        raise SpecialEquipmentManagementNotFoundError("Цвет не найден")
    _ensure_precondition(
        current,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    counts = await repository.color_usage_counts(session, color_id)
    if counts["body"] or counts["interior"]:
        raise SpecialEquipmentColorConflictError(
            "Цвет используется в объявлениях и не может быть удалён",
            code="color_in_use",
            detail={
                "used_in_products_count": counts["body"] + counts["interior"],
                "body_products_count": counts["body"],
                "interior_products_count": counts["interior"],
            },
        )
    if not await repository.delete_color(
        session, color_id, lock_version=expected_version
    ):
        raise SpecialEquipmentManagementPreconditionError("Ресурс уже изменён")
    await repository.increment_catalog_revision(session)


async def create_product_idempotent(
    session: AsyncSession,
    *,
    actor_id: UUID,
    idempotency_key: str,
    request_hash: str,
    values: Mapping[str, Any],
) -> dict:
    """Create a product and its initial compatibility graph atomically."""

    replay = await _replay_create(
        session,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        entity_type="product",
    )
    if replay is not None:
        return {"product": replay}
    payload = dict(values)
    links = [dict(item) for item in payload.pop("compatible_attachments", ())]
    row = await create_entity(
        session,
        entity_type="product",
        values=payload,
    )
    if links:
        relation = await _replace_compatible_attachments_locked(
            session,
            product_id=row["id"],
            links=links,
            actor_id=actor_id,
        )
        row = relation["resource"]
    await repository.add_mutation_receipt(
        session,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        resource_type="product",
        resource_id=row["id"],
        response_snapshot=row,
    )
    return {"product": row}


async def patch_entity(  # noqa: PLR0912, PLR0915
    session: AsyncSession,
    *,
    entity_type: repository.EntityType,
    entity_id: UUID,
    values: Mapping[str, Any],
    expected_version: int,
    expected_etag: str | None = None,
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    current: dict[str, Any] | None
    if entity_type == "trim" and expected_etag is not None:
        current, _items = await _locked_trim_contract_state(
            session,
            trim_id=entity_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
        )
    else:
        current = await repository.lock_entity(session, entity_type, entity_id)
        if current is None:
            raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")
        _ensure_precondition(
            current,
            expected_version=expected_version,
            expected_etag=expected_etag,
        )
    assert current is not None
    payload = dict(values)
    if entity_type == "trim":
        _ensure_trim_not_reparented(
            current_modification_id=current["modification_id"],
            requested_modification_id=payload.get("modification_id"),
        )
    parent_ids = payload.pop("parent_ids", None)
    category_ids = payload.pop("category_ids", None)
    attribute_ids = payload.pop("attribute_ids", None)
    attribute_links = payload.pop("attribute_links", None)
    attribute_values = payload.pop("attribute_values", None)
    options = payload.pop("options", None)
    superstructure_attributes = payload.pop("attributes", None)
    chassis_values = payload.pop("chassis_values", None)
    superstructure_values = payload.pop("superstructure_values", None)
    product_fields_present = frozenset(payload)
    warehouse_id = payload.get("warehouse_id", _MISSING)
    confirm_type_conversion = bool(
        payload.pop("confirm_type_conversion", False)
    )
    typed_attribute_values: list[dict] | None = None
    name = payload.get("name")
    if name is not None and entity_type in _SLUGGED_ENTITY_TYPES:
        payload["slug"] = generate_catalog_slug(name)
    if entity_type == "product":
        current_is_kit = bool(
            current.get("model_id") is not None
            and current.get("superstructure_id") is not None
        )
        if "superstructure_id" in payload or "model_id" in payload:
            target_model_id = payload.get("model_id", current.get("model_id"))
            target_superstructure_id = payload.get(
                "superstructure_id", current.get("superstructure_id")
            )
            target_is_kit = bool(
                target_model_id is not None and target_superstructure_id is not None
            )
            if current_is_kit != target_is_kit:
                raise KitInvariantError(
                    "Тип объявления (обычное ↔ комплект) после создания не меняется",
                    code="PRODUCT_KIND_IMMUTABLE",
                )
        if payload.get("no_vin") is True:
            payload["vin"] = None
            payload["chassis_vin"] = None
            payload["superstructure_vin"] = None
        else:
            if payload.get("vin") is not None:
                payload["vin"] = payload["vin"].strip()
            if payload.get("chassis_vin") is not None:
                payload["chassis_vin"] = payload["chassis_vin"].strip()
            if payload.get("superstructure_vin") is not None:
                payload["superstructure_vin"] = payload["superstructure_vin"].strip()
    if entity_type == "model":
        if "mark_id" in payload:
            mark = await repository.get_entity(session, "mark", payload["mark_id"])
            if mark is None:
                raise SpecialEquipmentManagementNotFoundError("Марка не найдена")
        if "category_id" in payload:
            if payload["category_id"] is not None:
                category = await repository.get_entity(
                    session, "category", payload["category_id"]
                )
                if category is None:
                    raise SpecialEquipmentManagementNotFoundError("Категория не найдена")
                if not category.get("is_active"):
                    raise SpecialEquipmentManagementValidationError(
                        "Нельзя выбрать неактивную категорию"
                    )
            else:
                raise SpecialEquipmentManagementValidationError(
                    "Для модели необходимо указать категорию"
                )
    if entity_type == "superstructure":
        await _validate_superstructure_patch(
            session, current, payload, superstructure_attributes, category_ids=category_ids
        )
    if entity_type == "unit" and payload.get("name") is not None:
        payload["name"] = payload["name"].strip()
        if not (1 <= len(payload["name"]) <= 50):
            raise SpecialEquipmentManagementValidationError(
                "Название единицы измерения должно содержать от 1 до 50 символов"
            )
    if entity_type == "attribute" and "attribute_group_id" in payload:
        group_id = payload["attribute_group_id"]
        if group_id is not None:
            await _require_active_attribute_group(session, group_id)
    if entity_type == "attribute" and "unit_id" in payload:
        new_unit_id = payload["unit_id"]
        if new_unit_id is not None:
            if new_unit_id != current.get("unit_id"):
                unit = await repository.get_entity(session, "unit", new_unit_id)
                if unit is None:
                    raise UnitNotFoundError("Единица измерения не найдена")
                if not unit.get("is_active"):
                    raise UnitInactiveError(
                        "Нельзя выбрать неактивную единицу измерения"
                    )
            else:
                unit = await repository.get_entity(session, "unit", new_unit_id)
                if unit is None:
                    raise UnitNotFoundError("Единица измерения не найдена")
    if entity_type == "attribute" and (
        "data_type" in payload or "filter_kind" in payload
    ):
        target_data_type = payload.get("data_type", current["data_type"])
        target_filter_kind = payload.get(
            "filter_kind", current.get("filter_kind", "exact")
        )
        if (
            target_data_type != current["data_type"]
            and "filter_kind" not in payload
            and (
                (target_filter_kind == "range" and target_data_type != "number")
                or (target_filter_kind == "search" and target_data_type != "text")
            )
        ):
            target_filter_kind = "exact"
            payload["filter_kind"] = target_filter_kind
        _validate_attribute_filter_kind(
            data_type=target_data_type,
            filter_kind=target_filter_kind,
        )
        if target_data_type != current["data_type"]:
            stored_values = (
                await repository.list_attribute_values_for_type_conversion(
                    session, entity_id
                )
            )
            if stored_values:
                can_convert_text_values = (
                    current["data_type"] == "text"
                    and target_data_type == "select"
                    and all(
                        item["value_text"] is not None
                        and item["option_id"] is None
                        and item["value_number"] is None
                        and item["value_boolean"] is None
                        for item in stored_values
                    )
                )
                if not can_convert_text_values or not confirm_type_conversion:
                    raise AttributeTypeConversionBlockedError(
                        "Смена типа заблокирована сохранёнными значениями; "
                        "подтвердите безопасное преобразование text → select",
                        value_count=len(stored_values),
                    )
                existing_options, _ = await repository.list_entities(
                    session,
                    "attribute_option",
                    offset=0,
                    limit=1000,
                    attribute_id=entity_id,
                )
                generated_options = _text_value_options(
                    [str(item["value_text"]) for item in stored_values],
                    existing_options=existing_options,
                )
                await repository.convert_text_attribute_values_to_options(
                    session,
                    attribute_id=entity_id,
                    options=generated_options,
                )
                if options is not None:
                    persisted_options, _ = await repository.list_entities(
                        session,
                        "attribute_option",
                        offset=0,
                        limit=1000,
                        attribute_id=entity_id,
                    )
                    options = _merge_converted_attribute_options(
                        persisted_options,
                        options,
                    )
            elif current["data_type"] == "select" and target_data_type != "select":
                await repository.delete_attribute_options(session, entity_id)
    if entity_type == "modification":
        if "model_id" in payload:
            model = await repository.get_entity(
                session, "model", payload["model_id"]
            )
            if model is None:
                raise SpecialEquipmentManagementNotFoundError("Модель не найдена")
        ensure_year_range(
            payload.get("year_from", current["year_from"]),
            payload.get("year_to", current["year_to"]),
        )
        if category_ids is not None:
            _validate_modification_categories(category_ids)
            await _validate_attachment_category_selection(
                session, category_ids
            )
        target_category_ids = (
            category_ids if category_ids is not None else current["category_ids"]
        )
        if attribute_values is not None:
            typed_attribute_values = await _typed_values(
                session, attribute_values
            )
            target_attribute_ids = (
                item["attribute_id"] for item in typed_attribute_values
            )
        else:
            target_attribute_ids = (
                item["attribute_id"] for item in current["attribute_values"]
            )
        await _validate_modification_attribute_values(
            session,
            category_ids=target_category_ids,
            attribute_ids=target_attribute_ids,
        )
        if typed_attribute_values is not None:
            await _ensure_modification_values_not_assigned_in_trims(
                session,
                modification_id=entity_id,
                attribute_ids=(
                    item["attribute_id"] for item in typed_attribute_values
                ),
            )
    if entity_type == "trim" and (
        "modification_id" in payload
        or attribute_links is not None
        or attribute_values is not None
    ):
        target_modification_id = payload.get(
            "modification_id", current["modification_id"]
        )
        modification = await repository.get_entity(
            session, "modification", target_modification_id
        )
        if modification is None:
            raise SpecialEquipmentManagementNotFoundError("Модификация не найдена")
        if attribute_values is not None:
            typed_attribute_values = await _typed_values(
                session, attribute_values
            )
            value_attribute_ids = (
                item["attribute_id"] for item in typed_attribute_values
            )
        else:
            value_attribute_ids = (
                item["attribute_id"] for item in current["attribute_values"]
            )
        await _validate_trim_attributes(
            session,
            modification_id=target_modification_id,
            attribute_links=(
                attribute_links
                if attribute_links is not None
                else current["attribute_links"]
            ),
            value_attribute_ids=value_attribute_ids,
        )
    if entity_type == "product":
        requested_price_on_request = bool(
            payload.get("price_on_request", current.get("price_on_request", False))
        )
        if "price_on_request" in payload:
            ensure_price_on_request_mode_change(
                current=bool(current.get("price_on_request", False)),
                requested=requested_price_on_request,
                published_at=current.get("published_at"),
            )
        if not requested_price_on_request and (
            "price_on_request" in payload or "price_from" in payload
        ):
            payload["price_from"] = None
        requested_publication_status = payload.get(
            "publication_status", current["publication_status"]
        )
        if (
            requested_publication_status == "archived"
            and current["publication_status"] != "archived"
        ):
            ensure_product_archive_allowed(
                dependencies=await repository.product_archive_dependencies(
                    session, entity_id
                ),
                sale_status=current["sale_status"],
                entity_id=entity_id,
                entity_code=current["code"],
                entity_name=current["code"],
            )
        if (
            requested_publication_status == "published"
            and current["publication_status"] != "published"
        ):
            payload["published_at"] = datetime.now(UTC)
        target_no_vin = payload.get("no_vin", current["no_vin"])
        target_warehouse_id = (
            current.get("warehouse_id") if warehouse_id is _MISSING else warehouse_id
        )
        warehouse_invariant_touched = (
            warehouse_id is not _MISSING
            or "vin" in payload
            or "no_vin" in payload
            or "sale_status" in payload
            or "seller_company_id" in payload
            or (
                requested_publication_status == "published"
                and current["publication_status"] != "published"
            )
        )
        if target_no_vin:
            target_warehouse_id = ensure_product_warehouse_assignment(
                no_vin=True,
                sale_status=str(payload.get("sale_status", current["sale_status"])),
                warehouse_id=target_warehouse_id,
                warehouse_explicit=warehouse_id is not _MISSING,
            )
            payload["vin"] = None
            payload["chassis_vin"] = None
            payload["superstructure_vin"] = None
            payload["warehouse_id"] = None
        elif warehouse_invariant_touched:
            target_warehouse_id = ensure_product_warehouse_assignment(
                no_vin=False,
                sale_status=str(payload.get("sale_status", current["sale_status"])),
                warehouse_id=target_warehouse_id,
                warehouse_explicit=warehouse_id is not _MISSING,
            )
            payload["warehouse_id"] = target_warehouse_id
        scalar = {
            key: payload[key] if key in payload else current.get(key)
            for key in (
                "modification_id",
                "model_id",
                "superstructure_id",
                "superstructure_model_id",
                "superstructure_modification_id",
                "superstructure_source_product_id",
                "superstructure_name",
                "superstructure_manufacturer",
                "trim_id",
                "seller_company_id",
                "warehouse_id",
                "body_color_id",
                "interior_color_id",
                "price",
                "special_price",
                "price_on_request",
                "price_from",
                "vin",
                "chassis_vin",
                "superstructure_vin",
                "no_vin",
                "condition",
                "owners_count",
                "mileage_km",
                "engine_hours",
                "manufacture_year",
                "publication_status",
                "sale_status",
            )
        }
        await _validate_product(
            session,
            scalar=scalar,
            category_ids=(
                category_ids
                if category_ids is not None
                else current["category_ids"]
            ),
            current_sale_status=current["sale_status"],
            current_color_ids={
                "body_color_id": current.get("body_color_id"),
                "interior_color_id": current.get("interior_color_id"),
            },
            color_fields_present=product_fields_present,
            allow_inactive_trim=(
                scalar.get("trim_id") is not None
                and scalar.get("trim_id") == current.get("trim_id")
                and scalar.get("modification_id") == current.get("modification_id")
            ),
            validate_warehouse_assignment=warehouse_invariant_touched,
            warehouse_explicit=warehouse_id is not _MISSING,
            chassis_values=chassis_values,
            superstructure_values=superstructure_values,
            current_product_id=entity_id,
        )
    if (
        current.get("is_active")
        and payload.get("is_active") is False
        and entity_type in _DEACTIVATION_DEPENDENCIES
    ):
        await _ensure_deactivation_allowed(
            session,
            entity_type=entity_type,
            entity=current,
        )
    if entity_type == "trim":
        scalar_changed = any(current.get(key) != value for key, value in payload.items())
        link_changed = attribute_links is not None and _trim_link_signature(
            attribute_links
        ) != _trim_link_signature(current.get("attribute_links") or ())
        value_changed = typed_attribute_values is not None and _trim_value_signature(
            typed_attribute_values
        ) != _trim_value_signature(current.get("attribute_values") or ())
        if not scalar_changed and not link_changed and not value_changed:
            return current
    await repository.patch_entity(session, entity_type, entity_id, payload)
    if entity_type == "superstructure":
        if superstructure_attributes is not None:
            await repository.replace_superstructure_attributes(
                session, superstructure_id=entity_id, attributes=superstructure_attributes
            )
        if category_ids is not None:
            await repository.replace_superstructure_categories(
                session, superstructure_id=entity_id, category_ids=category_ids
            )
    if entity_type == "category" and parent_ids is not None:
        await _replace_parents(session, entity_id, parent_ids)
    if entity_type == "category" and (
        parent_ids is not None or attribute_links is not None
    ):
        await _validate_category_attributes(
            session,
            category_id=entity_id,
            replacement=(
                attribute_links
                if attribute_links is not None
                else current["attribute_links"]
            ),
        )
    if entity_type == "category" and attribute_links is not None:
        await repository.replace_category_attributes(
            session,
            category_id=entity_id,
            links=attribute_links,
        )
    elif entity_type == "modification":
        if category_ids is not None:
            await repository.replace_modification_categories(
                session,
                modification_id=entity_id,
                category_ids=category_ids,
            )
        if attribute_values is not None:
            await repository.replace_modification_values(
                session,
                modification_id=entity_id,
                values=typed_attribute_values or [],
            )
    elif entity_type == "trim":
        if attribute_links is not None:
            await repository.replace_trim_attributes(
                session,
                trim_id=entity_id,
                links=attribute_links,
            )
        if attribute_values is not None:
            await repository.replace_trim_values(
                session,
                trim_id=entity_id,
                values=typed_attribute_values or [],
            )
    elif entity_type == "product":
        if category_ids is not None:
            await repository.replace_product_categories(
                session, product_id=entity_id, category_ids=category_ids
            )
        effective_superstructure_id = scalar.get("superstructure_id")
        if effective_superstructure_id is not None and scalar.get("model_id") is not None:
            if scalar.get("modification_id") is not None:
                await repository.replace_product_chassis_values(
                    session, product_id=entity_id, values=[]
                )
            elif chassis_values is not None:
                typed_chassis = await _typed_values(session, chassis_values)
                await repository.replace_product_chassis_values(
                    session, product_id=entity_id, values=typed_chassis
                )
            if superstructure_values is not None:
                typed_ss = await _typed_values(session, superstructure_values)
                await repository.replace_product_superstructure_values(
                    session,
                    product_id=entity_id,
                    superstructure_id=effective_superstructure_id,
                    values=typed_ss,
                )
    elif entity_type == "attribute" and options is not None:
        await _replace_attribute_options(
            session,
            attribute_id=entity_id,
            options=options,
        )
    elif entity_type == "attribute_group" and attribute_ids is not None:
        await _validate_attribute_group_members(
            session,
            attribute_ids,
            group_is_active=bool(payload.get("is_active", current["is_active"])),
        )
        await repository.replace_attribute_group_members(
            session,
            group_id=entity_id,
            attribute_ids=attribute_ids,
        )
    if entity_type == "category" and (
        parent_ids is not None or "is_attachment_category" in payload
    ):
        await _validate_attachment_integrity(
            session,
            category_mutation=True,
        )
    elif entity_type == "modification" and category_ids is not None:
        await _validate_attachment_neighborhood(
            session,
            tuple(await repository.product_ids_for_modification(session, entity_id)),
        )
    elif entity_type == "product" and (
        category_ids is not None or "modification_id" in payload
    ):
        await _validate_attachment_neighborhood(session, [entity_id])
    if entity_type in {
        "category",
        "mark",
        "model",
        "modification",
        "attribute_group",
        "attribute",
    }:
        await _ensure_published_dependencies_valid(
            session,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    row = await repository.get_entity(session, entity_type, entity_id)
    if row is None:
        raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")
    await repository.increment_catalog_revision(session)
    return row


async def replace_product_warehouse(
    session: AsyncSession,
    *,
    product_id: UUID,
    warehouse_id: UUID | None,
    expected_version: int,
    expected_etag: str | None = None,
) -> dict:
    """Replace a product warehouse without changing any other product field."""

    await repository.lock_catalog_for_mutation(session)
    current = await repository.lock_entity(session, "product", product_id)
    if current is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    _ensure_precondition(
        current,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    await _validate_product_warehouse(
        session,
        no_vin=bool(current["no_vin"]),
        sale_status=str(current["sale_status"]),
        warehouse_id=warehouse_id,
        seller_company_id=current.get("seller_company_id"),
    )

    await repository.replace_product_warehouse(
        session, product_id=product_id, warehouse_id=warehouse_id
    )
    row = await repository.get_entity(session, "product", product_id)
    if row is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    await repository.increment_catalog_revision(session)
    return row


async def replace_category_attributes(
    session: AsyncSession,
    *,
    category_id: UUID,
    links: Sequence[Mapping[str, Any]],
    expected_version: int,
    expected_etag: str | None = None,
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    category = await repository.lock_entity(
        session, "category", category_id
    )
    if category is None:
        raise SpecialEquipmentManagementNotFoundError("Категория не найдена")
    _ensure_precondition(
        category,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    await _validate_category_attributes(
        session, category_id=category_id, replacement=links
    )
    await repository.replace_category_attributes(
        session, category_id=category_id, links=links
    )
    await repository.patch_entity(session, "category", category_id, {})
    await _ensure_published_dependencies_valid(
        session,
        entity_type="category",
        entity_id=category_id,
    )
    result = await repository.get_entity(session, "category", category_id)
    if result is None:
        raise SpecialEquipmentManagementNotFoundError("Категория не найдена")
    await repository.increment_catalog_revision(session)
    return result


async def replace_trim_attributes(
    session: AsyncSession,
    *,
    trim_id: UUID,
    links: Sequence[Mapping[str, Any]],
    expected_version: int,
    expected_etag: str | None = None,
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    trim = await repository.lock_entity(session, "trim", trim_id)
    if trim is None:
        raise SpecialEquipmentManagementNotFoundError("Комплектация не найдена")
    _ensure_precondition(
        trim, expected_version=expected_version, expected_etag=expected_etag
    )
    await _validate_trim_attributes(
        session,
        modification_id=trim["modification_id"],
        attribute_links=links,
        value_attribute_ids=(
            row["attribute_id"]
            for row in await repository.trim_attributes(session, trim_id)
        ),
    )
    await repository.replace_trim_attributes(session, trim_id=trim_id, links=links)
    await repository.patch_entity(session, "trim", trim_id, {})
    result = await repository.get_entity(session, "trim", trim_id)
    if result is None:
        raise SpecialEquipmentManagementNotFoundError("Комплектация не найдена")
    await repository.increment_catalog_revision(session)
    return result


async def replace_trim_attribute_values(
    session: AsyncSession,
    *,
    trim_id: UUID,
    values: Sequence[Mapping[str, Any]],
    expected_version: int,
    expected_etag: str | None = None,
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    trim = await repository.lock_entity(session, "trim", trim_id)
    if trim is None:
        raise SpecialEquipmentManagementNotFoundError("Комплектация не найдена")
    _ensure_precondition(
        trim, expected_version=expected_version, expected_etag=expected_etag
    )
    current = await repository.get_entity(session, "trim", trim_id)
    if current is None:
        raise SpecialEquipmentManagementNotFoundError("Комплектация не найдена")
    typed_values = await _typed_values(session, values)
    await _validate_trim_attributes(
        session,
        modification_id=trim["modification_id"],
        attribute_links=current.get("attribute_links") or (),
        value_attribute_ids=(item["attribute_id"] for item in typed_values),
    )
    await repository.replace_trim_values(
        session, trim_id=trim_id, values=typed_values
    )
    await repository.patch_entity(session, "trim", trim_id, {})
    result = await repository.get_entity(session, "trim", trim_id)
    if result is None:
        raise SpecialEquipmentManagementNotFoundError("Комплектация не найдена")
    await repository.increment_catalog_revision(session)
    return result


async def _locked_trim_contract_state(
    session: AsyncSession,
    *,
    trim_id: UUID,
    expected_version: int,
    expected_etag: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trim = await repository.lock_trim_state(session, trim_id)
    if trim is None:
        raise SpecialEquipmentTrimContractError(
            "Комплектация не найдена",
            code="TRIM_NOT_FOUND",
            kind="not_found",
        )
    items = await repository.trim_attribute_state(session, trim_id)
    current_etag = special_equipment_trim_attributes_etag(
        trim_id=trim_id,
        lock_version=trim["lock_version"],
        items=items,
    )
    if trim["lock_version"] != expected_version or current_etag != expected_etag:
        raise SpecialEquipmentTrimContractError(
            "Комплектация уже изменена",
            code="PRECONDITION_FAILED",
            kind="precondition",
        )
    return trim, items


async def add_trim_attribute(
    session: AsyncSession,
    *,
    trim_id: UUID,
    link: Mapping[str, Any],
    expected_version: int,
    expected_etag: str,
) -> dict[str, Any]:
    """Add exactly one effective category assignment to a trim."""

    await repository.lock_catalog_for_mutation(session)
    trim, items = await _locked_trim_contract_state(
        session,
        trim_id=trim_id,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    assigned_attribute_ids = {
        row["attribute_id"]
        for row in await repository.trim_attributes(session, trim_id)
    }
    if link["attribute_id"] in assigned_attribute_ids:
        raise SpecialEquipmentTrimContractError(
            "Характеристика уже назначена комплектации",
            code="ATTRIBUTE_ALREADY_ASSIGNED",
            kind="conflict",
        )
    persisted = {
        "attribute_id": link["attribute_id"],
        "group_id": link.get("group_id"),
        "is_required": bool(link.get("is_required", False)),
        "is_filterable": bool(link.get("is_filterable", False)),
        "sort_order": int(link.get("sort_order", 0)),
    }
    await _validate_trim_attributes(
        session,
        modification_id=trim["modification_id"],
        attribute_links=[*items, persisted],
        value_attribute_ids=(
            item["attribute_id"]
            for item in items
            if any(
                item.get(column) is not None
                for column in (
                    "value_number",
                    "value_text",
                    "value_boolean",
                    "option_id",
                )
            )
        ),
    )
    await repository.add_trim_attribute(session, trim_id=trim_id, link=persisted)
    await repository.patch_entity(session, "trim", trim_id, {})
    await repository.increment_catalog_revision(session)
    updated = await repository.get_entity(session, "trim", trim_id)
    if updated is None:
        raise SpecialEquipmentTrimContractError(
            "Комплектация не найдена",
            code="TRIM_NOT_FOUND",
            kind="not_found",
        )
    return {
        "trim": updated,
        "items": await repository.trim_attribute_state(session, trim_id),
        "item": next(
            item
            for item in await repository.trim_attribute_state(session, trim_id)
            if item["attribute_id"] == link["attribute_id"]
        ),
    }


async def delete_trim_attribute_assignment(
    session: AsyncSession,
    *,
    trim_id: UUID,
    attribute_id: UUID,
    expected_version: int,
    expected_etag: str,
) -> dict[str, Any]:
    """Delete one assignment and its value; absent assignment is a no-op."""

    await repository.lock_catalog_for_mutation(session)
    trim, items = await _locked_trim_contract_state(
        session,
        trim_id=trim_id,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    changed = await repository.delete_trim_attribute(
        session, trim_id=trim_id, attribute_id=attribute_id
    )
    if changed:
        await repository.patch_entity(session, "trim", trim_id, {})
        await repository.increment_catalog_revision(session)
        trim = await repository.get_entity(session, "trim", trim_id) or trim
        items = await repository.trim_attribute_state(session, trim_id)
    return {"trim": trim, "items": items, "changed": changed}


def _value_columns(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "attribute_id": item["attribute_id"],
        "value_number": item.get("value_number"),
        "value_text": item.get("value_text"),
        "value_boolean": item.get("value_boolean"),
        "option_id": item.get("option_id"),
    }


async def patch_trim_attribute_values(
    session: AsyncSession,
    *,
    trim_id: UUID,
    values: Sequence[Mapping[str, Any]],
    expected_version: int,
    expected_etag: str,
) -> dict[str, Any]:
    """Atomically patch supplied trim values and return only actual changes."""

    await repository.lock_catalog_for_mutation(session)
    trim, current_items = await _locked_trim_contract_state(
        session,
        trim_id=trim_id,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    ids = [item["attribute_id"] for item in values]
    if len(ids) != len(set(ids)):
        raise SpecialEquipmentTrimContractError(
            "Характеристика передана в пачке более одного раза",
            code="ATTRIBUTE_VALUES_BATCH_FAILED",
            kind="validation",
            errors=[
                {
                    "code": "ATTRIBUTE_VALUE_DUPLICATE",
                    "attribute_id": str(attribute_id),
                    "detail": "Характеристика передана более одного раза",
                }
                for attribute_id in sorted(set(ids), key=str)
                if ids.count(attribute_id) > 1
            ],
        )
    assigned_ids = {item["attribute_id"] for item in current_items}
    modification_values = await repository.modification_attribute_values(
        session, trim["modification_id"]
    )
    value_conflicts = {
        conflict.attribute_id: conflict
        for conflict in trim_modification_value_conflicts(
            incoming_modification_values=(),
            incoming_trim_values=(
                (trim["modification_id"], item["attribute_id"])
                for item in values
            ),
            persisted_modification_values=(
                (trim["modification_id"], attribute_id)
                for attribute_id in modification_values
            ),
            persisted_trim_values=(),
        )
    }
    errors: list[dict[str, Any]] = []
    delete_ids: list[UUID] = []
    candidates: list[Mapping[str, Any]] = []
    for item in values:
        attribute_id = item["attribute_id"]
        if attribute_id not in assigned_ids:
            errors.append(
                {
                    "code": "ATTRIBUTE_NOT_ASSIGNED",
                    "attribute_id": str(attribute_id),
                    "detail": "Характеристика не назначена комплектации",
                    "kind": "conflict",
                }
            )
            continue
        if attribute_id in value_conflicts:
            conflict = value_conflicts[attribute_id]
            errors.append(
                {
                    "code": conflict.code,
                    "attribute_id": str(attribute_id),
                    "detail": conflict.message,
                    "kind": "conflict",
                }
            )
            continue
        non_null = [
            item.get("value_number"),
            item.get("value_text"),
            item.get("value_boolean"),
            item.get("option_id"),
        ]
        value_text = item.get("value_text")
        if (
            isinstance(value_text, str)
            and not value_text.strip()
            and sum(v is not None for v in non_null) == 1
        ):
            delete_ids.append(attribute_id)
            continue
        candidates.append(item)
    typed_values: list[dict[str, Any]] = []
    for item in candidates:
        try:
            typed_values.extend(await _typed_values(session, [item]))
        except SpecialEquipmentManagementNotFoundError:
            errors.append(
                {
                    "code": "ATTRIBUTE_NOT_FOUND",
                    "attribute_id": str(item["attribute_id"]),
                    "detail": "Характеристика не найдена",
                    "kind": "validation",
                }
            )
        except SpecialEquipmentManagementValidationError as exc:
            code = (
                "INVALID_OPTION"
                if item.get("option_id") is not None
                else "VALIDATION_ERROR"
            )
            errors.append(
                {
                    "code": code,
                    "attribute_id": str(item["attribute_id"]),
                    "detail": str(exc),
                    "kind": "validation",
                }
            )
    if errors:
        kind: Literal["validation", "conflict"] = (
            "validation"
            if any(error.get("kind") == "validation" for error in errors)
            else "conflict"
        )
        raise SpecialEquipmentTrimContractError(
            "Не удалось сохранить значения характеристик",
            code="ATTRIBUTE_VALUES_BATCH_FAILED",
            kind=kind,
            errors=errors,
        )
    current_by_id = {
        item["attribute_id"]: _value_columns(item) for item in current_items
    }
    changed_values = [
        value
        for value in typed_values
        if _value_columns(value) != current_by_id.get(value["attribute_id"])
    ]
    effective_delete_ids = [
        attribute_id
        for attribute_id in delete_ids
        if any(
            current_by_id[attribute_id].get(key) is not None
            for key in ("value_number", "value_text", "value_boolean", "option_id")
        )
    ]
    if changed_values or effective_delete_ids:
        await repository.upsert_trim_attribute_values(
            session,
            trim_id=trim_id,
            values=changed_values,
            delete_attribute_ids=effective_delete_ids,
        )
        await repository.patch_entity(session, "trim", trim_id, {})
        await repository.increment_catalog_revision(session)
        trim = await repository.get_entity(session, "trim", trim_id) or trim
    saved = [_value_columns(item) for item in changed_values]
    saved.extend(
        {
            "attribute_id": attribute_id,
            "value_number": None,
            "value_text": None,
            "value_boolean": None,
            "option_id": None,
        }
        for attribute_id in effective_delete_ids
    )
    return {
        "trim": trim,
        "items": await repository.trim_attribute_state(session, trim_id),
        "saved": saved,
    }


def _ensure_unique_ordered_links(
    links: Sequence[Mapping[str, Any]],
    *,
    id_key: str,
    duplicate_message: str,
) -> None:
    product_ids = [link[id_key] for link in links]
    positions = [link["position"] for link in links]
    if len(product_ids) != len(set(product_ids)):
        raise AttachmentInvariantError(
            duplicate_message,
            code="DUPLICATE_PRODUCT_RELATION",
        )
    if len(positions) != len(set(positions)) or any(
        position < 0 for position in positions
    ):
        raise AttachmentInvariantError(
            "Позиции должны быть уникальными и неотрицательными",
            code="INVALID_PRODUCT_RELATION_POSITION",
        )


async def _relation_result(
    session: AsyncSession,
    *,
    product_id: UUID,
) -> dict[str, Any]:
    resource = await repository.get_entity(session, "product", product_id)
    if resource is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    items, total = await repository.list_product_attachments(
        session,
        product_id=product_id,
        offset=0,
        limit=500,
    )
    return {
        "data": {
            "items": items,
            "pagination": {
                "page": 1,
                "page_size": 500,
                "total": total,
                "pages": 1 if total else 0,
            },
        },
        "resource": resource,
    }


async def replace_compatible_attachments(
    session: AsyncSession,
    *,
    product_id: UUID,
    links: Sequence[Mapping[str, Any]],
    actor_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
) -> dict[str, Any]:
    await repository.lock_catalog_for_mutation(session)
    owner = await repository.lock_entity(session, "product", product_id)
    if owner is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    _ensure_precondition(
        owner,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    return await _replace_compatible_attachments_locked(
        session,
        product_id=product_id,
        links=links,
        actor_id=actor_id,
    )


async def _replace_compatible_attachments_locked(
    session: AsyncSession,
    *,
    product_id: UUID,
    links: Sequence[Mapping[str, Any]],
    actor_id: UUID,
) -> dict[str, Any]:
    _ensure_unique_ordered_links(
        links,
        id_key="attachment_product_id",
        duplicate_message="Надстройку нельзя добавить дважды",
    )
    attachment_product_ids = [
        link["attachment_product_id"] for link in links
    ]
    states = await repository.get_product_offering_states(
        session,
        [product_id, *attachment_product_ids],
    )
    _graph_snapshot, attachment_ids = await _attachment_context(session)
    _validate_compatibility_states(
        product_id=product_id,
        attachment_product_ids=attachment_product_ids,
        states=states,
        attachment_ids=attachment_ids,
    )
    await repository.replace_product_attachments(
        session,
        product_id=product_id,
        links=links,
        actor_id=actor_id,
    )
    await repository.patch_entity(session, "product", product_id, {})
    await repository.increment_catalog_revision(session)
    return await _relation_result(
        session,
        product_id=product_id,
    )


async def create_compatible_attachment(
    session: AsyncSession,
    *,
    product_id: UUID,
    attachment_product_id: UUID,
    position: int,
    actor_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
) -> dict[str, Any]:
    await repository.lock_catalog_for_mutation(session)
    owner = await repository.lock_entity(session, "product", product_id)
    if owner is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    _ensure_precondition(
        owner,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    links = await repository.get_product_attachment_links(session, product_id)
    if any(
        link["attachment_product_id"] == attachment_product_id for link in links
    ):
        raise SpecialEquipmentManagementConflictError(
            "Совместимость уже существует"
        )
    return await _replace_compatible_attachments_locked(
        session,
        product_id=product_id,
        links=[
            *links,
            {
                "attachment_product_id": attachment_product_id,
                "position": position,
            },
        ],
        actor_id=actor_id,
    )


async def patch_compatible_attachment(
    session: AsyncSession,
    *,
    product_id: UUID,
    attachment_product_id: UUID,
    position: int,
    actor_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
) -> dict[str, Any]:
    await repository.lock_catalog_for_mutation(session)
    owner = await repository.lock_entity(session, "product", product_id)
    if owner is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    _ensure_precondition(
        owner,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    links = await repository.get_product_attachment_links(session, product_id)
    found = False
    replacement: list[dict[str, Any]] = []
    for link in links:
        item = dict(link)
        if item["attachment_product_id"] == attachment_product_id:
            item["position"] = position
            found = True
        replacement.append(item)
    if not found:
        raise SpecialEquipmentManagementNotFoundError("Совместимость не найдена")
    return await _replace_compatible_attachments_locked(
        session,
        product_id=product_id,
        links=replacement,
        actor_id=actor_id,
    )


async def delete_compatible_attachment(
    session: AsyncSession,
    *,
    product_id: UUID,
    attachment_product_id: UUID,
    actor_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
) -> dict[str, Any]:
    await repository.lock_catalog_for_mutation(session)
    owner = await repository.lock_entity(session, "product", product_id)
    if owner is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    _ensure_precondition(
        owner,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    links = await repository.get_product_attachment_links(session, product_id)
    replacement = [
        link
        for link in links
        if link["attachment_product_id"] != attachment_product_id
    ]
    if len(replacement) == len(links):
        raise SpecialEquipmentManagementNotFoundError("Совместимость не найдена")
    return await _replace_compatible_attachments_locked(
        session,
        product_id=product_id,
        links=replacement,
        actor_id=actor_id,
    )


async def delete_entity(
    session: AsyncSession,
    *,
    entity_type: repository.EntityType,
    entity_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
    user_id: UUID | None = None,
) -> None:
    await repository.lock_catalog_for_mutation(session)
    row: dict[str, Any] | None
    if entity_type == "trim" and expected_etag is not None:
        row, _items = await _locked_trim_contract_state(
            session,
            trim_id=entity_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
        )
    else:
        row = await repository.lock_entity(session, entity_type, entity_id)
        if row is None:
            raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")
        _ensure_precondition(
            row,
            expected_version=expected_version,
            expected_etag=expected_etag,
        )
    dependencies = await repository.dependencies(session, entity_type, entity_id)
    if entity_type == "unit" and dependencies.get("attributes", 0) > 0:
        raise UnitInUseError(
            "Единица измерения используется в характеристиках",
            attribute_count=dependencies["attributes"],
        )
    ensure_delete_allowed(
        dependencies,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_code=row.get("code"),
        entity_name=row.get("name") or row.get("code"),
    )
    await repository.delete_mutation_receipts_for_resource(
        session,
        resource_type=entity_type,
        resource_id=entity_id,
    )
    if not await repository.delete_entity(session, entity_type, entity_id):
        raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")
    catalog_revision = await repository.increment_catalog_revision(session)
    if entity_type == "unit":
        await repository.record_catalog_deletion(
            session,
            user_id=user_id,
            root_type="unit",
            root_id=entity_id,
            root_code=row.get("code"),
            root_name=row.get("name"),
            catalog_revision=catalog_revision,
            counts={"units": 1},
            items=[
                {
                    "type": "unit",
                    "id": str(entity_id),
                    "code": row.get("code"),
                    "name": row.get("name"),
                    "action": "delete",
                }
            ],
        )


async def merge_unit(
    session: AsyncSession,
    *,
    source_unit_id: UUID,
    target_unit_id: UUID,
    expected_version: int,
    target_expected_version: int | None = None,
    expected_etag: str | None = None,
    user_id: UUID | None = None,
) -> dict:
    if source_unit_id == target_unit_id:
        raise SpecialEquipmentManagementValidationError(
            "Нельзя объединить единицу измерения с самой собой"
        )
    await repository.lock_catalog_for_mutation(session)
    source = await repository.lock_entity(session, "unit", source_unit_id)
    if source is None:
        raise SpecialEquipmentManagementNotFoundError(
            "Исходная единица измерения не найдена"
        )
    _ensure_precondition(
        source, expected_version=expected_version, expected_etag=expected_etag
    )

    target = await repository.lock_entity(session, "unit", target_unit_id)
    if target is None:
        raise SpecialEquipmentManagementNotFoundError(
            "Целевая единица измерения не найдена"
        )
    if (
        target_expected_version is not None
        and target.get("lock_version") != target_expected_version
    ):
        raise SpecialEquipmentManagementPreconditionError(
            "Целевая единица измерения была изменена"
        )
    if not target.get("is_active"):
        raise UnitInactiveError("Целевая единица измерения должна быть активна")

    rebound_count = await repository.rebind_unit_attributes(
        session, source_unit_id=source_unit_id, target_unit_id=target_unit_id
    )

    await repository.delete_mutation_receipts_for_resource(
        session, resource_type="unit", resource_id=source_unit_id
    )

    if not await repository.delete_entity(session, "unit", source_unit_id):
        raise SpecialEquipmentManagementNotFoundError(
            "Исходная единица измерения не найдена"
        )

    catalog_revision = await repository.increment_catalog_revision(session)
    await repository.record_catalog_deletion(
        session,
        user_id=user_id,
        root_type="unit",
        root_id=source_unit_id,
        root_code=source.get("code"),
        root_name=source.get("name"),
        catalog_revision=catalog_revision,
        counts={"attributes_rebound": rebound_count, "units": 1},
        items=[
            {
                "type": "unit",
                "id": str(source_unit_id),
                "code": source.get("code"),
                "name": source.get("name"),
                "action": "merged",
                "target_unit_id": str(target_unit_id),
                "reason": "unit_merged",
                "rebound_attributes_count": rebound_count,
            }
        ],
    )

    refreshed = await repository.get_entity(session, "unit", target_unit_id)
    assert refreshed is not None
    return refreshed


async def reserve_media_upload(
    session: AsyncSession, storage_key: str
) -> None:
    await repository.reserve_media_upload(session, storage_key)


async def cancel_media_upload(
    session: AsyncSession, storage_key: str
) -> None:
    await repository.cancel_media_cleanup(session, storage_key)


async def set_category_image(
    session: AsyncSession,
    *,
    category_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
    storage_key: str,
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    category = await repository.lock_entity(session, "category", category_id)
    if category is None:
        raise SpecialEquipmentManagementNotFoundError("Категория не найдена")
    _ensure_precondition(
        category,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    if not await repository.cancel_media_cleanup(session, storage_key):
        raise SpecialEquipmentManagementConflictError(
            "Не удалось закрепить загруженное изображение"
        )
    previous = await repository.get_category_image_key(session, category_id)
    await repository.set_category_image_key(session, category_id, storage_key)
    if previous and previous != storage_key:
        await repository.enqueue_media_cleanup(session, previous)
    result = await repository.get_entity(session, "category", category_id)
    if result is None:
        raise SpecialEquipmentManagementNotFoundError("Категория не найдена")
    await repository.increment_catalog_revision(session)
    return result


async def delete_category_image(
    session: AsyncSession,
    *,
    category_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    category = await repository.lock_entity(session, "category", category_id)
    if category is None:
        raise SpecialEquipmentManagementNotFoundError("Категория не найдена")
    _ensure_precondition(
        category,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    storage_key = await repository.get_category_image_key(session, category_id)
    if storage_key is None:
        raise SpecialEquipmentManagementNotFoundError("Изображение не найдено")
    await repository.set_category_image_key(session, category_id, None)
    await repository.enqueue_media_cleanup(session, storage_key)
    result = await repository.get_entity(session, "category", category_id)
    if result is None:
        raise SpecialEquipmentManagementNotFoundError("Категория не найдена")
    await repository.increment_catalog_revision(session)
    return result


async def add_product_image(
    session: AsyncSession,
    *,
    product_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
    storage_key: str,
    alt_text: str | None,
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    product = await repository.lock_entity(session, "product", product_id)
    if product is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    _ensure_precondition(
        product,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    if len(product["images"]) >= 50:
        raise SpecialEquipmentManagementValidationError(
            "В галерее может быть не более 50 изображений"
        )
    if not await repository.cancel_media_cleanup(session, storage_key):
        raise SpecialEquipmentManagementConflictError(
            "Не удалось закрепить загруженное изображение"
        )
    image_id = await repository.create_product_image(
        session,
        product_id=product_id,
        storage_key=storage_key,
        alt_text=alt_text,
    )
    updated = await repository.get_entity(session, "product", product_id)
    if updated is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    image = next(item for item in updated["images"] if item["id"] == image_id)
    await repository.increment_catalog_revision(session)
    return {"image": image, "product": updated}


async def update_product_image(
    session: AsyncSession,
    *,
    product_id: UUID,
    image_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
    values: Mapping[str, Any],
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    product = await repository.lock_entity(session, "product", product_id)
    if product is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    _ensure_precondition(
        product,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    changed = await repository.patch_product_image(
        session,
        product_id=product_id,
        image_id=image_id,
        values=values,
    )
    if not changed:
        raise SpecialEquipmentManagementNotFoundError("Изображение не найдено")
    updated = await repository.get_entity(session, "product", product_id)
    if updated is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    image = next(item for item in updated["images"] if item["id"] == image_id)
    await repository.increment_catalog_revision(session)
    return {"image": image, "product": updated}


async def remove_product_image(
    session: AsyncSession,
    *,
    product_id: UUID,
    image_id: UUID,
    expected_version: int,
    expected_etag: str | None = None,
) -> dict:
    await repository.lock_catalog_for_mutation(session)
    product = await repository.lock_entity(session, "product", product_id)
    if product is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    _ensure_precondition(
        product,
        expected_version=expected_version,
        expected_etag=expected_etag,
    )
    storage_key = await repository.delete_product_image(
        session, product_id=product_id, image_id=image_id
    )
    if storage_key is None:
        raise SpecialEquipmentManagementNotFoundError("Изображение не найдено")
    await repository.enqueue_media_cleanup(session, storage_key)
    updated = await repository.get_entity(session, "product", product_id)
    if updated is None:
        raise SpecialEquipmentManagementNotFoundError("Товар не найден")
    await repository.increment_catalog_revision(session)
    return updated


_RESOURCE_TO_ENTITY_TYPE: dict[str, str] = {
    "categories": "category",
    "marks": "mark",
    "models": "model",
    "modifications": "modification",
    "trims": "trim",
    "attribute-groups": "attribute_group",
    "attribute_groups": "attribute_group",
    "attributes": "attribute",
    "attribute-options": "attribute_option",
    "attribute_options": "attribute_option",
    "products": "product",
    "colors": "color",
    "units": "unit",
    "superstructures": "superstructure",
}


def _resolve_cascade_entity_type(resource_or_type: str) -> str:
    key = resource_or_type.strip().lower()
    return _RESOURCE_TO_ENTITY_TYPE.get(key, key)


async def preview_cascade_delete(
    session: AsyncSession,
    resource: str,
    entity_id: UUID,
) -> CascadePlan:
    """Build a cascade delete plan and check blockers without taking locks."""
    root_type = _resolve_cascade_entity_type(resource)
    root_ref, graph = await cascade_repository.load_cascade_graph(
        session, root_type, entity_id
    )
    max_rows = getattr(settings, "special_equipment_cascade_delete_max_rows", 5000)
    plan = build_cascade_plan(
        root=root_ref,
        graph=graph,
        max_rows=max_rows,
        raise_on_too_large=True,
    )

    product_ids = {p.id for p in plan.delete.get("products", [])}
    product_blockers = await cascade_repository.load_product_blockers(
        session, product_ids, lock=False
    )
    kit_source_blockers = await cascade_repository.load_kit_source_blockers(
        session, product_ids, lock=False
    )

    distributor_blockers = []
    if root_type == "mark":
        distributor_blockers = await cascade_repository.load_mark_distributor_blockers(
            session, entity_id, lock=False
        )

    mark_ids = {m.id for m in plan.delete.get("marks", [])}
    model_ids = {m.id for m in plan.delete.get("models", [])}
    trim_ids = {t.id for t in plan.delete.get("trims", [])}
    support_program_blockers = await cascade_repository.load_support_program_blockers(
        session,
        mark_ids=mark_ids,
        model_ids=model_ids,
        trim_ids=trim_ids,
        lock=False,
    )

    plan.blockers = CascadeBlockers(
        products=product_blockers,
        distributors=distributor_blockers,
        support_programs=support_program_blockers,
        kit_sources=kit_source_blockers,
    )

    catalog_revision = await cascade_repository.get_catalog_revision(session)
    plan.catalog_revision = catalog_revision
    plan.preview_token = compute_preview_token(plan, catalog_revision)
    return plan


async def cascade_delete_entity(
    session: AsyncSession,
    resource: str,
    entity_id: UUID,
    confirmation: str,
    preview_token: str,
    if_match: str | None = None,
    user_id: UUID | None = None,
    *,
    expected_version: int | None = None,
    expected_etag: str | None = None,
) -> dict[str, Any]:
    """Execute cascade delete under exclusive mutation lock, verifying confirmation and preview token."""
    ensure_confirmation(confirmation)
    root_type = _resolve_cascade_entity_type(resource)

    if if_match is not None and expected_version is None and expected_etag is None:
        raw_etag = if_match.strip()
        if raw_etag.startswith('"') and raw_etag.endswith('"'):
            parts = raw_etag[1:-1].split(":")
            if len(parts) == 3:
                try:
                    expected_version = int(parts[1])
                    expected_etag = raw_etag
                except ValueError:
                    pass
        elif raw_etag.isdigit():
            expected_version = int(raw_etag)

    # Acquire lock for catalog mutation
    await cascade_repository.lock_catalog_for_mutation(session)

    # Check root entity existence and precondition
    current_root = await repository.lock_entity(
        session, cast("repository.EntityType", root_type), entity_id
    )
    if current_root is None:
        raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")

    if expected_version is not None or expected_etag is not None:
        _ensure_precondition(
            current_root,
            expected_version=(
                expected_version
                if expected_version is not None
                else current_root["lock_version"]
            ),
            expected_etag=expected_etag,
        )

    # Re-build cascade plan under mutation lock
    root_ref, graph = await cascade_repository.load_cascade_graph(
        session, root_type, entity_id
    )
    max_rows = getattr(settings, "special_equipment_cascade_delete_max_rows", 5000)
    plan = build_cascade_plan(
        root=root_ref,
        graph=graph,
        max_rows=max_rows,
        raise_on_too_large=True,
    )

    # Lock candidate products and check blockers under lock
    product_ids = {p.id for p in plan.delete.get("products", [])}
    product_blockers = await cascade_repository.load_product_blockers(
        session, product_ids, lock=True
    )
    kit_source_blockers = await cascade_repository.load_kit_source_blockers(
        session, product_ids, lock=True
    )

    distributor_blockers = []
    if root_type == "mark":
        distributor_blockers = await cascade_repository.load_mark_distributor_blockers(
            session, entity_id, lock=True
        )

    mark_ids = {m.id for m in plan.delete.get("marks", [])}
    model_ids = {m.id for m in plan.delete.get("models", [])}
    trim_ids = {t.id for t in plan.delete.get("trims", [])}
    support_program_blockers = await cascade_repository.load_support_program_blockers(
        session,
        mark_ids=mark_ids,
        model_ids=model_ids,
        trim_ids=trim_ids,
        lock=True,
    )

    plan.blockers = CascadeBlockers(
        products=product_blockers,
        distributors=distributor_blockers,
        support_programs=support_program_blockers,
        kit_sources=kit_source_blockers,
    )

    if not plan.blockers.is_empty:
        raise CascadeDeleteBlockedError(blockers=plan.blockers)

    current_revision = await cascade_repository.get_catalog_revision(session)
    plan.catalog_revision = current_revision
    new_token = compute_preview_token(plan, current_revision)
    plan.preview_token = new_token

    if new_token != preview_token:
        raise CascadePreviewStaleError(plan=plan)

    deleted_counts = await cascade_repository.apply_cascade_plan(
        session, plan, user_id=user_id, catalog_revision=current_revision
    )
    new_revision = await cascade_repository.get_catalog_revision(session)

    return {
        "deleted": deleted_counts,
        "catalog_revision": new_revision,
    }
