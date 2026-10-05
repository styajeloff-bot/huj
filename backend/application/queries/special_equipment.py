"""Public query handlers for the corrected special-equipment catalog."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application import special_equipment_offerings as offerings
from application.errors import ServiceError
from application.special_equipment_urls import special_equipment_detail_url
from domain.special_equipment_catalog import (
    CategoryGraph,
    CategoryPathError,
    format_attribute_display_value,
    resolve_terminal_category,
)
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import special_equipment_repository as repository


class SpecialEquipmentResourceNotFoundError(ServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)


class SpecialEquipmentQueryValidationError(ServiceError):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message, status_code=422, code=code)


class SpecialEquipmentIncompatibleFiltersError(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            "city_id и warehouse_id несовместимы",
            status_code=400,
            code="incompatible-filters",
        )


@dataclass(frozen=True)
class ListSpecialEquipmentProductsQuery:
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE
    category_path: str | None = None
    mark_ids: tuple[UUID, ...] = ()
    model_ids: tuple[UUID, ...] = ()
    modification_ids: tuple[UUID, ...] = ()
    trim_ids: tuple[UUID, ...] = ()
    superstructure_ids: tuple[UUID, ...] = ()
    body_color_ids: tuple[UUID, ...] = ()
    interior_color_ids: tuple[UUID, ...] = ()
    availability: tuple[Literal["available", "on_order"], ...] = ()
    condition: Literal["new", "used"] | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    mileage_min: int | None = None
    mileage_max: int | None = None
    engine_hours_min: int | None = None
    engine_hours_max: int | None = None
    city_id: UUID | None = None
    warehouse_id: UUID | None = None
    min_in_stock: int | None = None
    search: str | None = None
    description_include: str | None = None
    description_exclude: str | None = None
    sort: repository.Sort = "published_desc"
    page: int = 1
    page_size: int = 24
    attribute_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class GetSpecialEquipmentProductQuery:
    product_id: UUID
    category_path: str | None = None
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


@dataclass(frozen=True)
class ListSpecialEquipmentProductImagesQuery:
    product_id: UUID


@dataclass(frozen=True)
class ListCompatibleAttachmentsQuery:
    product_id: UUID
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


@dataclass(frozen=True)
class GetSpecialEquipmentMediaQuery:
    media_type: Literal["category", "image"]
    media_id: UUID


@dataclass(frozen=True)
class _CategoryContext:
    category_id: UUID
    usage_metric: str | None


async def _resolve_filter_category_context(
    query: ListSpecialEquipmentProductsQuery,
    session: AsyncSession,
) -> _CategoryContext | None:
    """Resolve the one category that owns dynamic and usage filters.

    An explicit path is authoritative.  Without one, exactly one selected
    modification may supply its active public primary category.
    """

    if query.category_path:
        context = await handle_resolve_category_path(query.category_path, session)
        return _CategoryContext(
            category_id=context["category"]["id"],
            usage_metric=context["category"]["usage_metric"],
        )
    modification_ids = tuple(dict.fromkeys(query.modification_ids))
    if len(modification_ids) != 1:
        return None
    primary_category = await repository.get_modification_primary_category(
        session, modification_ids[0]
    )
    if primary_category is None:
        return None
    return _CategoryContext(
        category_id=primary_category["id"],
        usage_metric=primary_category["usage_metric"],
    )


def _category_context_required() -> SpecialEquipmentQueryValidationError:
    return SpecialEquipmentQueryValidationError(
        "Категориальные фильтры требуют category_path или ровно одну "
        "modification_id с активной основной категорией",
        code="CATEGORY_CONTEXT_REQUIRED",
    )


def _graph_resources(snapshot: dict[str, list[dict]]) -> list[dict]:
    parents: dict[UUID, list[UUID]] = {}
    children: dict[UUID, list[UUID]] = {}
    for relation in snapshot["relations"]:
        parents.setdefault(relation["child_id"], []).append(relation["parent_id"])
        children.setdefault(relation["parent_id"], []).append(relation["child_id"])
    return [
        {
            **category,
            "parent_ids": parents.get(category["id"], []),
            "child_ids": children.get(category["id"], []),
            "image_url": (
                f"/api/v1/special-equipment/categories/{category['id']}/image/content"
                if category["image_key"]
                else None
            ),
        }
        for category in snapshot["categories"]
    ]


async def handle_list_categories(session: AsyncSession) -> dict:
    snapshot = await repository.list_category_graph(session)
    resources = _graph_resources(snapshot)
    resources_by_id = {item["id"]: item for item in resources}
    return {
        "items": resources,
        "root_items": [
            resources_by_id[category["id"]]
            for category in snapshot["root_categories"]
        ],
        "placements": [
            {
                "parent_id": relation["parent_id"],
                "category_id": relation["child_id"],
                "sort_order": relation["sort_order"],
            }
            for relation in snapshot["relations"]
        ],
    }


async def handle_resolve_category_path(path: str, session: AsyncSession) -> dict:
    snapshot = await repository.list_category_graph(session)
    categories = {item["id"]: item for item in snapshot["categories"]}
    by_slug = {item["slug"]: item["id"] for item in snapshot["categories"]}
    slugs = tuple(part for part in path.strip("/").split("/") if part)
    if not slugs:
        raise SpecialEquipmentQueryValidationError("Путь категории не задан")
    try:
        ids = tuple(by_slug[slug] for slug in slugs)
    except KeyError as exc:
        raise SpecialEquipmentResourceNotFoundError(
            "Путь категории не найден"
        ) from exc
    graph = CategoryGraph.from_edges(
        category_ids=categories,
        edges=(
            (item["parent_id"], item["child_id"])
            for item in snapshot["relations"]
        ),
    )
    try:
        graph.resolve_context_path(category_id=ids[-1], path=ids)
    except CategoryPathError as exc:
        raise SpecialEquipmentResourceNotFoundError(str(exc)) from exc
    resources = {item["id"]: item for item in _graph_resources(snapshot)}
    return {
        "items": [
            {
                "id": categories[category_id]["id"],
                "code": categories[category_id]["code"],
                "name": categories[category_id]["name"],
                "slug": categories[category_id]["slug"],
            }
            for category_id in ids
        ],
        "category": resources[ids[-1]],
    }


async def handle_list_marks(session: AsyncSession) -> dict:
    return {"items": await repository.list_marks(session)}


async def _filters(  # noqa: PLR0912
    query: ListSpecialEquipmentProductsQuery,
    session: AsyncSession,
) -> repository.SpecialEquipmentFilters:
    category_context = await _resolve_filter_category_context(query, session)
    category_id = (
        category_context.category_id if category_context is not None else None
    )
    usage_metric = (
        category_context.usage_metric if category_context is not None else None
    )
    if (
        query.price_min is not None
        and query.price_max is not None
        and query.price_min > query.price_max
    ):
        raise SpecialEquipmentQueryValidationError(
            "price_min не может быть больше price_max"
        )
    if (
        query.mileage_min is not None
        and query.mileage_max is not None
        and query.mileage_min > query.mileage_max
    ):
        raise SpecialEquipmentQueryValidationError(
            "mileage_min не может быть больше mileage_max"
        )
    if (
        query.engine_hours_min is not None
        and query.engine_hours_max is not None
        and query.engine_hours_min > query.engine_hours_max
    ):
        raise SpecialEquipmentQueryValidationError(
            "engine_hours_min не может быть больше engine_hours_max"
        )
    has_mileage = query.mileage_min is not None or query.mileage_max is not None
    has_hours = (
        query.engine_hours_min is not None or query.engine_hours_max is not None
    )
    category_specific_filter = bool(query.attribute_tokens) or has_mileage or has_hours
    if category_specific_filter and category_context is None:
        raise _category_context_required()
    if has_mileage and has_hours:
        raise SpecialEquipmentQueryValidationError(
            "Пробег и моточасы нельзя фильтровать одновременно"
        )
    if usage_metric == "mileage_km" and has_hours:
        raise SpecialEquipmentQueryValidationError(
            "В выбранной категории разрешён только пробег"
        )
    if usage_metric == "engine_hours" and has_mileage:
        raise SpecialEquipmentQueryValidationError(
            "В выбранной категории разрешены только моточасы"
        )
    if usage_metric is None and (has_mileage or has_hours):
        raise SpecialEquipmentQueryValidationError(
            "Для фильтра эксплуатации сначала выберите категорию"
        )
    if (
        query.city_id is not None
        and query.warehouse_id is not None
        and not await repository.warehouse_matches_city(
            session, warehouse_id=query.warehouse_id, city_id=query.city_id
        )
    ):
        raise SpecialEquipmentIncompatibleFiltersError()
    attribute_predicates: list[repository.AttributePredicate] = []
    for token in query.attribute_tokens:
        raw_id, separator, remainder = token.partition(":")
        operator, value_separator, value = remainder.partition(":")
        if (
            separator != ":"
            or value_separator != ":"
            or operator not in {"eq", "gte", "lte", "search"}
            or not value.strip()
        ):
            raise SpecialEquipmentQueryValidationError(
                "Характеристика задаётся как UUID:eq|gte|lte|search:значение"
            )
        try:
            attribute_id = UUID(raw_id)
        except ValueError as exc:
            raise SpecialEquipmentQueryValidationError(
                "Некорректный UUID характеристики"
            ) from exc
        attribute_predicates.append(
            repository.AttributePredicate(
                attribute_id,
                cast("Literal['eq', 'gte', 'lte', 'search']", operator),
                value,
            )
        )
    if category_id is not None and attribute_predicates:
        branch_metadata = await repository.list_branch_attribute_metadata(
            session, category_id
        )
        definitions = {
            item["id"]: (item["data_type"], item["filter_kind"])
            for item in branch_metadata
            if item["is_filterable"]
        }
        allowed_ids = set(definitions)
        if any(
            predicate.attribute_id not in allowed_ids
            for predicate in attribute_predicates
        ):
            raise SpecialEquipmentQueryValidationError(
                "Характеристика не является фильтром выбранной категории"
            )
        for predicate in attribute_predicates:
            data_type, filter_kind = definitions[predicate.attribute_id]
            if predicate.operator == "search" and (
                data_type != "text" or filter_kind != "search"
            ):
                raise SpecialEquipmentQueryValidationError(
                    "Оператор search разрешён только для текстового search-фильтра"
                )
            if predicate.operator in {"gte", "lte"} and (
                data_type != "number" or filter_kind != "range"
            ):
                raise SpecialEquipmentQueryValidationError(
                    "Операторы gte/lte разрешены только для числового диапазона"
                )
            if predicate.operator == "eq" and filter_kind != "exact":
                raise SpecialEquipmentQueryValidationError(
                    "Оператор eq разрешён только для точного фильтра"
                )
    return repository.SpecialEquipmentFilters(
        scope=query.scope,
        category_id=category_id,
        mark_ids=tuple(dict.fromkeys(query.mark_ids)),
        model_ids=tuple(dict.fromkeys(query.model_ids)),
        modification_ids=tuple(dict.fromkeys(query.modification_ids)),
        trim_ids=tuple(dict.fromkeys(query.trim_ids)),
        superstructure_ids=tuple(dict.fromkeys(query.superstructure_ids)),
        body_color_ids=tuple(dict.fromkeys(query.body_color_ids)),
        interior_color_ids=tuple(dict.fromkeys(query.interior_color_ids)),
        availability=tuple(dict.fromkeys(query.availability)) or (
            "available",
            "on_order",
        ),
        condition=query.condition,
        price_min=query.price_min,
        price_max=query.price_max,
        mileage_min=query.mileage_min,
        mileage_max=query.mileage_max,
        engine_hours_min=query.engine_hours_min,
        engine_hours_max=query.engine_hours_max,
        city_id=query.city_id,
        warehouse_id=query.warehouse_id,
        min_in_stock=query.min_in_stock,
        search=query.search.strip() if query.search else None,
        description_include=(
            query.description_include.strip()
            if query.description_include
            else None
        ),
        description_exclude=(
            query.description_exclude.strip()
            if query.description_exclude
            else None
        ),
        attributes=tuple(attribute_predicates),
    )


def _capabilities(row: dict) -> dict[str, bool]:
    published = row.get("publication_status", "published") == "published"
    available = published and row["sale_status"] == "available"
    on_order = published and row["sale_status"] == "on_order"
    priced = (
        not bool(row.get("price_on_request"))
        and row["price"] is not None
        and row["price"] > 0
    )
    return {
        "can_favorite": True,
        "can_add_to_cart": available or on_order,
        "can_lease": available or on_order,
        "can_buy": available and priced,
        "can_preorder": (available or on_order) and priced,
    }


def _card_attribute_rows(rows: list[dict] | tuple[dict, ...]) -> list[dict]:
    """Keep repository order while applying the public visibility boundary."""

    return [row for row in rows if row.get("is_visible") is True][:6]


def _product_resource(row: dict, *, detail_url_allowed: bool = True) -> dict:
    primary_image = row.get("primary_image")
    card_attributes: list[dict] = []
    for item in _card_attribute_rows(tuple(row.get("card_attributes", ()))):
        resource = _attribute_resource(item)
        if resource is not None:
            resource.pop("source_product", None)
            card_attributes.append(resource)
    model_resource = {
        "id": row["model_id"],
        "code": row["model_code"],
        "name": row["model_name"],
        "slug": row["model_slug"],
        "mark": {
            "id": row["mark_id"],
            "code": row["mark_code"],
            "name": row["mark_name"],
            "slug": row["mark_slug"],
        },
    }
    modification_resource = (
        {
            "id": row["modification_id"],
            "code": row["modification_code"],
            "name": row["modification_name"],
            "slug": row["modification_slug"],
            "year_from": row["year_from"],
            "year_to": row["year_to"],
            "model": model_resource,
        }
        if row.get("modification_id") is not None
        else None
    )
    if row.get("superstructure_id") is not None:
        from domain.special_equipment_kits import kit_title

        title = kit_title(
            superstructure_name=str(row.get("superstructure_name") or ""),
            chassis_mark_name=str(row.get("mark_name") or ""),
            chassis_model_name=str(row.get("model_name") or ""),
        )
        superstructure_resource: dict | None = {
            "type": {
                "id": row["superstructure_id"],
                "code": row.get("superstructure_type_code"),
                "name": row.get("superstructure_type_name"),
            },
            "mark": {
                "id": row.get("superstructure_mark_id"),
                "code": row.get("superstructure_mark_code"),
                "name": row.get("superstructure_mark_name"),
                "slug": row.get("superstructure_mark_slug"),
            },
            "model": {
                "id": row.get("superstructure_model_id"),
                "code": row.get("superstructure_model_code"),
                "name": row.get("superstructure_model_name"),
                "slug": row.get("superstructure_model_slug"),
            },
            "modification": (
                {
                    "id": row.get("superstructure_mod_id"),
                    "code": row.get("superstructure_mod_code"),
                    "name": row.get("superstructure_mod_name"),
                    "slug": row.get("superstructure_mod_slug"),
                }
                if row.get("superstructure_mod_id")
                else None
            ),
            "name": row.get("superstructure_name"),
            "manufacturer": row.get("superstructure_manufacturer"),
        }
    else:
        title = f"{row.get('mark_name', '')} {row.get('model_name', '')}".strip() or "Спецтехника"
        superstructure_resource = None

    return {
        "id": row["id"],
        "code": row["code"],
        "slug": row["slug"],
        "detail_url": (
            special_equipment_detail_url(row["id"], row["slug"])
            if detail_url_allowed
            else None
        ),
        "title": title,
        "model": model_resource,
        "modification": modification_resource,
        "superstructure": superstructure_resource,
        "trim": (
            {"id": row["trim_id"], "name": row["trim_name"]}
            if row.get("trim_id") and row.get("trim_name")
            else None
        ),
        "condition": row["condition"],
        "owners_count": row["owners_count"],
        "mileage_km": row["mileage_km"],
        "engine_hours": row["engine_hours"],
        "price": f"{row['price']:.2f}" if row["price"] is not None else None,
        "base_price": (
            f"{row['base_price']:.2f}" if row.get("base_price") is not None else None
        ),
        "special_price": (
            f"{row['special_price']:.2f}"
            if row.get("special_price") is not None
            else None
        ),
        "price_on_request": bool(row.get("price_on_request")),
        "price_from": (
            f"{row['price_from']:.2f}"
            if row.get("price_on_request") and row.get("price_from") is not None
            else None
        ),
        "currency_code": row["currency_code"],
        "manufacture_year": row["manufacture_year"],
        "sale_status": row["sale_status"],
        "body_color": (
            {"id": row["body_color_id"], "name": row["body_color_name"]}
            if row.get("body_color_id") and row.get("body_color_name")
            else None
        ),
        "interior_color": (
            {"id": row["interior_color_id"], "name": row["interior_color_name"]}
            if row.get("interior_color_id") and row.get("interior_color_name")
            else None
        ),
        "available_count": int(row.get("available_count", 1)),
        "warehouse_city_name": row.get("warehouse_city_name"),
        "warehouse_stock": row.get("warehouse_stock", []),
        "categories": row["categories"],
        "terminal_category": row.get("terminal_category")
        or row.get("primary_category"),
        "card_attributes": card_attributes,
        "primary_image": (
            {
                **primary_image,
                "content_url": (
                    f"/api/v1/special-equipment/images/{primary_image['id']}/content"
                ),
            }
            if primary_image
            else None
        ),
        "capabilities": _capabilities(row),
        "normalization_state": "normalized",
    }


def _facets_resource(facets: dict) -> dict:
    groups: dict[UUID | None, dict] = {}
    for item in facets["attributes"]:
        group = groups.setdefault(
            item["group_id"],
            {
                "id": item["group_id"],
                "name": item["group_name"],
                "sort_order": item["group_sort_order"],
                "attributes": [],
            },
        )
        group["attributes"].append(
            {
                key: value
                for key, value in item.items()
                if key not in {"group_sort_order"}
            }
            | {
                "min": str(item["min"]) if item["min"] is not None else None,
                "max": str(item["max"]) if item["max"] is not None else None,
            }
        )
    return {
        "marks": facets["marks"],
        "models": facets["models"],
        "modifications": facets["modifications"],
        "trims": facets["trims"],
        "body_colors": facets["body_colors"],
        "interior_colors": facets["interior_colors"],
        "availability": facets["availability"],
        "conditions": facets["conditions"],
        "price": {
            "min": (
                f"{facets['price']['min']:.2f}"
                if facets["price"]["min"] is not None
                else None
            ),
            "max": (
                f"{facets['price']['max']:.2f}"
                if facets["price"]["max"] is not None
                else None
            ),
        },
        "usage": facets["usage"],
        "cities": facets["cities"],
        "warehouses": facets["warehouses"],
        "attribute_groups": sorted(
            (group for group in groups.values() if group["attributes"]),
            key=lambda item: (item["sort_order"], str(item["id"])),
        ),
        "superstructures": facets.get("superstructures", []),
    }


async def handle_list_products(
    query: ListSpecialEquipmentProductsQuery, session: AsyncSession
) -> dict:
    filters = await _filters(query, session)
    rows, total = await offerings.list_public_offerings(
        session,
        filters=filters,
        sort=query.sort,
        offset=(query.page - 1) * query.page_size,
        limit=query.page_size,
    )
    edges = await repository.list_active_category_edges(session)
    attributes_by_product = await repository.list_product_attributes_batch(
        session, rows
    )
    for row in rows:
        row["terminal_category"] = resolve_terminal_category(
            edges=edges,
            product_categories=row.get("categories", ()),
            context_category_id=filters.category_id,
            primary_category=row.get("primary_category"),
        )
        row["card_attributes"] = _card_attribute_rows(
            tuple(attributes_by_product.get(row["id"], ()))
        )
    facets = await repository.get_facets(session, filters)
    pages = (total + query.page_size - 1) // query.page_size if total else 0
    return {
        "items": [_product_resource(row) for row in rows],
        "pagination": {
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "pages": pages,
        },
        "facets": _facets_resource(facets),
    }


async def handle_list_facets(
    query: ListSpecialEquipmentProductsQuery, session: AsyncSession
) -> dict:
    return _facets_resource(
        await repository.get_facets(session, await _filters(query, session))
    )


def _attribute_resource(row: dict) -> dict | None:
    is_select = row["data_type"] == "select"
    if row.get("option_code") is not None:
        value: str | bool | None = row["option_code"]
        display = format_attribute_display_value(row["option_name"])
    elif row["value_number"] is not None:
        value = format_attribute_display_value(row["value_number"])
        display = format_attribute_display_value(
            row["value_number"], row["unit"]
        )
    elif row["value_boolean"] is not None:
        value = row["value_boolean"]
        display = format_attribute_display_value(value, row["unit"])
    else:
        value = str(row["value_text"] or "").strip()
        display = format_attribute_display_value(value, row["unit"])
    if value is None or display is None:
        return None
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "data_type": row["data_type"],
        "unit": row["unit"],
        "group_id": row["group_id"],
        "group_name": row["group_name"],
        "section": row.get("section") or "chassis",
        "value": value,
        "display_value": display,
        # Retain display_value for legacy clients, but expose the selected
        # option explicitly. Non-select attributes must contain explicit nulls.
        "option_id": row.get("option_id") if is_select else None,
        "option_label": row.get("option_name") if is_select else None,
        "source_product": row.get("source_product"),
    }


def _attribute_groups_resource(attribute_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    groups: dict[tuple[str, UUID | None], dict] = {}
    flat_attributes: list[dict] = []
    for item in attribute_rows:
        resource = _attribute_resource(item)
        if resource is None:
            continue
        flat_attributes.append(resource)
        section = item.get("section") or "chassis"
        group_key = (section, item.get("group_id"))
        group = groups.setdefault(
            group_key,
            {
                "id": item.get("group_id"),
                "name": item.get("group_name"),
                "section": section,
                "sort_order": item.get("group_sort_order", 0) or 0,
                "attributes": [],
            },
        )
        group["attributes"].append(resource)
    return flat_attributes, [
        {
            "id": item["id"],
            "name": item["name"],
            "section": item["section"],
            "attributes": item["attributes"],
        }
        for item in sorted(
            groups.values(),
            key=lambda value: (
                0 if value["section"] == "chassis" else 1,
                value["sort_order"],
                str(value["id"]),
            ),
        )
    ]



async def handle_get_product(
    query: GetSpecialEquipmentProductQuery, session: AsyncSession
) -> dict:
    category_id: UUID | None = None
    if query.category_path is not None:
        context = await handle_resolve_category_path(query.category_path, session)
        category_id = context["category"]["id"]
    row = await repository.get_product(
        session,
        product_id=query.product_id,
        category_id=None,
    )
    if row is None:
        raise SpecialEquipmentResourceNotFoundError("Товар не найден")
    physical_ids, available_count = (
        await offerings.grouped_product_inventory_for_product(
            session,
            row,
            category_id=category_id,
            scope=query.scope,
        )
    )
    if not physical_ids:
        raise SpecialEquipmentResourceNotFoundError("Товар не найден")
    row["warehouse_stock"] = await repository.list_warehouse_stock(
        session,
        physical_ids,
        maximum_count=available_count,
    )
    attributes_by_product = await repository.list_product_attributes_batch(
        session,
        [row],
        include_hidden=True,
    )
    attribute_rows = list(attributes_by_product.get(row["id"], ()))
    edges = await repository.list_active_category_edges(session)
    row["terminal_category"] = resolve_terminal_category(
        edges=edges,
        product_categories=row.get("categories", ()),
        context_category_id=category_id,
        primary_category=row.get("primary_category"),
    )
    row["card_attributes"] = _card_attribute_rows(tuple(attribute_rows))
    visible_rows = (
        attribute_rows
        if row.get("superstructure_id") is not None
        else [item for item in attribute_rows if item.get("is_visible") is True]
    )
    flat_attributes, attribute_groups = _attribute_groups_resource(visible_rows)
    trim_attribute_rows = await repository.list_trim_attributes(
        session, trim_id=row.get("trim_id")
    )
    _, trim_attribute_groups = _attribute_groups_resource(trim_attribute_rows)
    return {
        **_product_resource(row),
        "description": row["description"],
        "available_count": available_count,
        "attributes": flat_attributes,
        "attribute_groups": attribute_groups,
        "trim_attribute_groups": trim_attribute_groups,
        "images": [
            {
                **item,
                "content_url": (
                    f"/api/v1/special-equipment/images/{item['id']}/content"
                ),
            }
            for item in row["images"]
        ],
    }


async def handle_list_compatible_attachments(
    query: ListCompatibleAttachmentsQuery,
    session: AsyncSession,
) -> dict:
    rows = await offerings.list_compatible_attachments(
        session, query.product_id, scope=query.scope
    )
    if rows is None:
        raise SpecialEquipmentResourceNotFoundError("Товар не найден")
    category_ids = tuple(
        category["id"]
        for row in rows
        for category in row["categories"]
    )
    non_leaf_ids = await repository.list_non_leaf_category_ids(
        session, category_ids
    )

    def primary_leaf_category(row: dict) -> dict | None:
        candidates = [
            category
            for category in row["categories"]
            if category["id"] not in non_leaf_ids
        ]
        if not candidates:
            return None
        # Product categories are already ordered by category sort/name/id in
        # the batched public product projection.
        return cast("dict", candidates[0])

    return {
        "items": [
            {
                "position": row["position"],
                "primary_category": primary_leaf_category(row),
                "product": _product_resource(row),
            }
            for row in rows
        ]
    }


async def handle_list_product_images(
    query: ListSpecialEquipmentProductImagesQuery, session: AsyncSession
) -> dict:
    items = await repository.list_product_images(session, query.product_id)
    return {
        "items": [
            {
                **item,
                "content_url": (
                    f"/api/v1/special-equipment/images/{item['id']}/content"
                ),
            }
            for item in items
        ]
    }


async def handle_get_media(
    query: GetSpecialEquipmentMediaQuery, session: AsyncSession
) -> str:
    if query.media_type == "category":
        storage_key = await repository.get_category_image_key(
            session, query.media_id
        )
    else:
        storage_key = await repository.get_image_storage_key(session, query.media_id)
    if storage_key is None:
        raise SpecialEquipmentResourceNotFoundError("Изображение не найдено")
    return storage_key
