"""Public grouped offerings for physical special-equipment inventory."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.special_equipment_attachments import (
    attachment_branch_ids,
    commercial_fingerprint,
    rule_inheritance_graph,
)
from domain.special_equipment_catalog import (
    CategoryAttributeRule,
    CategoryGraph,
    effective_attribute_rules,
)
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import (
    special_equipment_offerings_repository as offerings_repository,
)
from infrastructure.repositories import special_equipment_repository as repository


def _attribute_value(row: Mapping[str, object]) -> object | None:
    if row["option_code"] is not None:
        return row["option_code"]
    for key in ("value_number", "value_boolean", "value_text"):
        if row[key] is not None:
            return row[key]
    return None


def _visible_attributes(
    *,
    rows: Sequence[dict],
    inputs: Mapping[str, list[dict]],
) -> dict[UUID, dict[str | UUID, object]]:
    category_ids = tuple(row["id"] for row in inputs["categories"])
    graph = CategoryGraph.from_edges(
        category_ids=category_ids,
        edges=(
            (row["parent_id"], row["child_id"])
            for row in inputs["relations"]
            if row["parent_id"] in category_ids and row["child_id"] in category_ids
        ),
    )
    attachment_roots = [
        row["id"]
        for row in inputs["categories"]
        if row.get("is_attachment_category") and row["id"] in graph.category_ids
    ]
    attachment_ids = attachment_branch_ids(
        graph=graph,
        attachment_roots=attachment_roots,
    )
    rule_graph = rule_inheritance_graph(
        graph=graph,
        attachment_ids=attachment_ids,
    )
    rules_by_category: dict[UUID, list[CategoryAttributeRule]] = {}
    for row in inputs["rules"]:
        rules_by_category.setdefault(row["category_id"], []).append(
            CategoryAttributeRule(
                attribute_id=row["attribute_id"],
                group_id=row["group_id"],
                is_required=row["is_required"],
                is_filterable=row["is_filterable"],
                is_visible=row["is_visible"],
                sort_order=row["sort_order"],
            )
        )
    visible_by_category: dict[UUID, set[UUID]] = {}
    for product in rows:
        for category in product["categories"]:
            category_id = category["id"]
            if category_id in visible_by_category:
                continue
            visible_by_category[category_id] = {
                rule.attribute_id
                for rule in effective_attribute_rules(
                    graph=rule_graph,
                    category_id=category_id,
                    rules_by_category=rules_by_category,
                )
                if rule.is_visible
            }
    values_by_modification: dict[UUID, dict[UUID, object]] = {}
    for value_row in inputs["attributes"]:
        value = _attribute_value(value_row)
        if value is not None:
            values_by_modification.setdefault(
                value_row["modification_id"], {}
            )[value_row["attribute_id"]] = value

    result: dict[UUID, dict[str | UUID, object]] = {}
    for product in rows:
        visible_ids: set[UUID] = set()
        for category in product["categories"]:
            visible_ids.update(visible_by_category.get(category["id"], ()))
        values = values_by_modification.get(product["modification_id"], {})
        product_values: dict[str | UUID, object] = {
            str(attribute_id): values[attribute_id]
            for attribute_id in sorted(visible_ids, key=str)
            if attribute_id in values
        }
        result[product["id"]] = product_values
    return result


def _grouping_collections(
    inputs: Mapping[str, list[dict]],
) -> dict[UUID, tuple[UUID, ...]]:
    attachments: dict[UUID, list[tuple[int, UUID]]] = {}
    for row in inputs.get("attachments", ()):
        attachments.setdefault(row["product_id"], []).append(
            (row["position"], row["attachment_product_id"])
        )
    return {
        product_id: tuple(
            attachment_id
            for _position, attachment_id in sorted(
                items, key=lambda item: (item[0], str(item[1]))
            )
        )
        for product_id, items in attachments.items()
    }


def _fingerprint(
    row: Mapping[str, Any],
    *,
    attributes: Mapping[str | UUID, object],
    attachment_ids: Sequence[UUID],
    component_fingerprints: Sequence[str] = (),
) -> str:
    return commercial_fingerprint(
        modification_id=row["modification_id"],
        category_ids=tuple(category["id"] for category in row["categories"]),
        seller_company_id=row["seller_company_id"],
        condition=row["condition"],
        manufacture_year=row["manufacture_year"],
        price=row["price"],
        currency_code=row["currency_code"],
        mileage_km=row["mileage_km"],
        engine_hours=row["engine_hours"],
        owners_count=row["owners_count"],
        sale_status=row["sale_status"],
        description=row["description"],
        attributes=attributes,
        compatible_attachment_ids=attachment_ids,
        component_fingerprints=component_fingerprints,
    )


def aggregate_product_rows(
    rows: Sequence[dict],
    inputs: Mapping[str, list[dict]],
    *,
    group_product_ids: frozenset[UUID] | None = None,
) -> list[dict]:
    """Collapse physical products behind deterministic public representatives."""

    if not rows:
        return []
    attributes = _visible_attributes(rows=rows, inputs=inputs)
    attachments = _grouping_collections(inputs)
    final_fingerprints = {
        row["id"]: _fingerprint(
            row,
            attributes=attributes[row["id"]],
            attachment_ids=attachments.get(row["id"], ()),
        )
        for row in rows
    }

    selected_ids = (
        frozenset(row["id"] for row in rows)
        if group_product_ids is None
        else group_product_ids
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if row["id"] not in selected_ids:
            continue
        grouped.setdefault(final_fingerprints[row["id"]], []).append(row)
    result: list[dict] = []
    for fingerprint, physical_rows in grouped.items():
        representative = min(physical_rows, key=lambda item: str(item["id"]))
        published_values = [
            item["published_at"]
            for item in physical_rows
            if item["published_at"] is not None
        ]
        result.append(
            {
                **representative,
                "available_count": len(physical_rows),
                "_fingerprint": fingerprint,
                "_physical_ids": tuple(item["id"] for item in physical_rows),
                "_group_published_at": max(published_values)
                if published_values
                else None,
            }
        )
    return result


def sort_grouped_rows(rows: Sequence[dict], sort: repository.Sort) -> list[dict]:
    """Sort groups with deterministic ties and NULL usage values last."""

    ordered = sorted(rows, key=lambda item: (item["_fingerprint"], str(item["id"])))
    if sort == "name_asc":
        return sorted(
            ordered,
            key=lambda item: (
                item["mark_name"].casefold(),
                item["model_name"].casefold(),
                item["modification_name"].casefold(),
            ),
        )
    field, descending = {
        "published_desc": ("_group_published_at", True),
        "published_asc": ("_group_published_at", False),
        "price_asc": ("price", False),
        "price_desc": ("price", True),
        "mileage_asc": ("mileage_km", False),
        "mileage_desc": ("mileage_km", True),
        "engine_hours_asc": ("engine_hours", False),
        "engine_hours_desc": ("engine_hours", True),
    }[sort]
    populated = [item for item in ordered if item[field] is not None]
    empty = [item for item in ordered if item[field] is None]
    return sorted(populated, key=lambda item: item[field], reverse=descending) + empty


async def _aggregate_candidates(
    session: AsyncSession,
    rows: Sequence[dict],
) -> list[dict]:
    candidate_ids = frozenset(row["id"] for row in rows)
    inputs = await offerings_repository.load_fingerprint_inputs(
        session, rows
    )
    return aggregate_product_rows(
        rows,
        inputs,
        group_product_ids=candidate_ids,
    )


async def list_public_offerings(
    session: AsyncSession,
    *,
    filters: repository.SpecialEquipmentFilters,
    sort: repository.Sort,
    offset: int,
    limit: int,
) -> tuple[list[dict], int]:
    return await repository.list_grouped_product_page(
        session,
        filters=filters,
        sort=sort,
        offset=offset,
        limit=limit,
    )


async def available_count_for_product(
    session: AsyncSession,
    product: Mapping[str, Any],
    *,
    category_id: UUID | None = None,
) -> int:
    _physical_ids, available_count = await grouped_product_inventory_for_product(
        session,
        product,
        category_id=category_id,
    )
    return available_count


async def grouped_product_inventory_for_product(
    session: AsyncSession,
    product: Mapping[str, Any],
    *,
    category_id: UUID | None = None,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> tuple[tuple[UUID, ...], int]:
    """Resolve alternatives and bundle-safe capacity behind one offering."""

    return await repository.get_grouped_product_inventory_for_member(
        session,
        UUID(str(product["id"])),
        category_id=category_id,
        scope=scope,
    )


async def equivalent_product_ids_for_product(
    session: AsyncSession,
    product: Mapping[str, Any],
    *,
    category_id: UUID | None = None,
) -> tuple[UUID, ...]:
    """Resolve concrete physical UUIDs behind one representative offering.

    Checkout callers can lock the returned UUIDs in this deterministic order
    and repeat the fingerprint check in their transaction before allocation.
    """

    physical_ids, _available_count = await grouped_product_inventory_for_product(
        session,
        product,
        category_id=category_id,
    )
    return physical_ids


async def list_compatible_attachments(
    session: AsyncSession,
    product_id: UUID,
    *,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> list[dict] | None:
    if not await repository.list_products_by_ids(
        session, (product_id,), scope=scope
    ):
        return None
    links = await offerings_repository.list_attachment_links(session, product_id)
    rows = await repository.list_products_by_ids(
        session,
        tuple(link["attachment_product_id"] for link in links),
        scope=scope,
    )
    groups = await _aggregate_candidates(session, rows)
    position_by_id = {
        link["attachment_product_id"]: link["position"] for link in links
    }
    return sorted(
        (
            {
                **group,
                "position": min(
                    position_by_id[physical_id]
                    for physical_id in group["_physical_ids"]
                ),
            }
            for group in groups
        ),
        key=lambda item: (item["position"], str(item["id"])),
    )
