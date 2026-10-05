"""PostgreSQL reads for the public special-equipment catalog."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, aggregate_order_by
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from domain.special_equipment_attachments import is_boundary_edge
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentAttribute,
    SpecialEquipmentAttributeGroup,
    SpecialEquipmentAttributeOption,
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryAttribute,
    SpecialEquipmentCategoryRelation,
    SpecialEquipmentColor,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationAttributeValue,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
    SpecialEquipmentProductAttachment,
    SpecialEquipmentProductCategory,
    SpecialEquipmentProductChassisValue,
    SpecialEquipmentProductImage,
    SpecialEquipmentProductSuperstructureValue,
    SpecialEquipmentSuperstructure,
    SpecialEquipmentSuperstructureAttribute,
    SpecialEquipmentTrim,
    SpecialEquipmentTrimAttribute,
    SpecialEquipmentTrimAttributeValue,
    SpecialEquipmentUnit,
)
from infrastructure.models.vehicles import City, Warehouse
from infrastructure.repositories.catalog_scope import special_equipment_visible_in

Sort = Literal[
    "published_desc",
    "published_asc",
    "price_asc",
    "price_desc",
    "name_asc",
    "mileage_asc",
    "mileage_desc",
    "engine_hours_asc",
    "engine_hours_desc",
]


@dataclass(frozen=True)
class AttributePredicate:
    attribute_id: UUID
    operator: Literal["eq", "gte", "lte", "search"]
    value: str


@dataclass(frozen=True)
class SpecialEquipmentFilters:
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE
    category_id: UUID | None = None
    mark_ids: tuple[UUID, ...] = ()
    model_ids: tuple[UUID, ...] = ()
    modification_ids: tuple[UUID, ...] = ()
    trim_ids: tuple[UUID, ...] = ()
    body_color_ids: tuple[UUID, ...] = ()
    interior_color_ids: tuple[UUID, ...] = ()
    availability: tuple[Literal["available", "on_order"], ...] = (
        "available",
        "on_order",
    )
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
    superstructure_ids: tuple[UUID, ...] = ()
    attributes: tuple[AttributePredicate, ...] = ()


def effective_product_price(product: Any = SpecialEquipmentProduct) -> Any:
    """Return the canonical SQL expression used by every catalog price read."""

    return sa.case(
        (product.price_on_request.is_(True), product.price_from),
        else_=sa.func.coalesce(product.special_price, product.price),
    )


def _public_fixed_price(column: Any, product: Any = SpecialEquipmentProduct) -> Any:
    """Hide persisted fixed-price fields while request pricing is active."""

    return sa.case(
        (product.price_on_request.is_(True), sa.null()),
        else_=column,
    )


def _warehouse_filter_clause(
    product_id: Any, filters: SpecialEquipmentFilters
) -> Any:
    if filters.city_id is None and filters.warehouse_id is None:
        return sa.true()
    match = (
        sa.select(sa.literal(1))
        .select_from(SpecialEquipmentProduct)
        .join(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .where(
            SpecialEquipmentProduct.id == product_id,
            Warehouse.status == "active",
        )
    )
    if filters.city_id is not None:
        match = match.where(Warehouse.city_id == filters.city_id)
    if filters.warehouse_id is not None:
        match = match.where(Warehouse.id == filters.warehouse_id)
    return sa.exists(match)


def _product_counts_by_category(
    *,
    active_ids: set[UUID],
    children: dict[UUID, set[UUID]],
    products_by_category: dict[UUID, set[UUID]],
) -> dict[UUID, int]:
    counts: dict[UUID, int] = {}
    for category_id in active_ids:
        descendants: set[UUID] = set()
        pending = [category_id]
        while pending:
            descendant_id = pending.pop()
            if descendant_id in descendants or descendant_id not in active_ids:
                continue
            descendants.add(descendant_id)
            pending.extend(children.get(descendant_id, ()))

        product_ids: set[UUID] = set()
        for descendant_id in descendants:
            product_ids.update(products_by_category.get(descendant_id, ()))
        counts[category_id] = len(product_ids)
    return counts


async def warehouse_matches_city(
    session: AsyncSession, *, warehouse_id: UUID, city_id: UUID
) -> bool:
    return bool(
        await session.scalar(
            sa.select(sa.literal(True)).where(
                Warehouse.id == warehouse_id,
                Warehouse.city_id == city_id,
                Warehouse.status == "active",
            )
        )
    )


def _public_product_category_links(active_ids: set[UUID]) -> sa.Select:
    return (
        sa.select(
            SpecialEquipmentProductCategory.category_id,
            SpecialEquipmentProductCategory.product_id,
        )
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id
            == SpecialEquipmentProductCategory.product_id,
        )
        .where(
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status.in_(("available", "on_order")),
            SpecialEquipmentProductCategory.category_id.in_(active_ids),
        )
    )


async def list_category_graph(session: AsyncSession) -> dict[str, list[dict]]:
    categories = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentCategory.id,
                    SpecialEquipmentCategory.code,
                    SpecialEquipmentCategory.name,
                    SpecialEquipmentCategory.slug,
                    SpecialEquipmentCategory.usage_metric,
                    SpecialEquipmentCategory.is_attachment_category,
                    SpecialEquipmentCategory.sort_order,
                    SpecialEquipmentCategory.image_key,
                )
                .where(
                    SpecialEquipmentCategory.is_active.is_(True),
                    SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
                )
                .order_by(
                    SpecialEquipmentCategory.sort_order,
                    SpecialEquipmentCategory.name,
                    SpecialEquipmentCategory.id,
                )
            )
        )
        .mappings()
        .all()
    )
    active_ids = {row["id"] for row in categories}
    active_parent = aliased(SpecialEquipmentCategory)
    root_categories = [
        {"id": category_id}
        for category_id in (
            await session.scalars(
                sa.select(SpecialEquipmentCategory.id)
                .where(
                    SpecialEquipmentCategory.is_active.is_(True),
                    SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
                    ~sa.exists(
                        sa.select(SpecialEquipmentCategoryRelation.child_id)
                        .join(
                            active_parent,
                            active_parent.id
                            == SpecialEquipmentCategoryRelation.parent_id,
                        )
                        .where(
                            SpecialEquipmentCategoryRelation.child_id
                            == SpecialEquipmentCategory.id,
                            active_parent.is_active.is_(True),
                            active_parent.is_visible_in_catalog.is_(True),
                        )
                    ),
                )
                .order_by(
                    sa.func.lower(SpecialEquipmentCategory.name).collate("ru-x-icu"),
                    SpecialEquipmentCategory.id,
                )
            )
        ).all()
    ]
    relations = [
        row
        for row in (
            await session.execute(
                sa.select(
                    SpecialEquipmentCategoryRelation.parent_id,
                    SpecialEquipmentCategoryRelation.child_id,
                    SpecialEquipmentCategoryRelation.sort_order,
                ).order_by(
                    SpecialEquipmentCategoryRelation.parent_id,
                    SpecialEquipmentCategoryRelation.sort_order,
                    SpecialEquipmentCategoryRelation.child_id,
                )
            )
        )
        .mappings()
        .all()
        if row["parent_id"] in active_ids and row["child_id"] in active_ids
    ]
    product_links = (
        await session.execute(
            _public_product_category_links(active_ids)
        )
    ).all()
    products_by_category: dict[UUID, set[UUID]] = {}
    for category_id, product_id in product_links:
        products_by_category.setdefault(category_id, set()).add(product_id)
    attachment_category_ids = _attachment_category_ids_from_mappings(
        categories=categories,
        relations=relations,
    )
    rule_children: dict[UUID, set[UUID]] = {}
    for relation in relations:
        parent_id = relation["parent_id"]
        child_id = relation["child_id"]
        if not is_boundary_edge(
            parent_id=parent_id,
            child_id=child_id,
            attachment_ids=attachment_category_ids,
        ):
            rule_children.setdefault(parent_id, set()).add(child_id)
    product_counts = _product_counts_by_category(
        active_ids=active_ids,
        children=rule_children,
        products_by_category=products_by_category,
    )

    category_rows: list[dict] = []
    for raw in categories:
        item = dict(raw)
        item["is_attachment_category"] = item["id"] in attachment_category_ids
        item["product_count"] = product_counts[item["id"]]
        category_rows.append(item)
    return {
        "categories": category_rows,
        "relations": [dict(row) for row in relations],
        "root_categories": root_categories,
    }


def _attachment_category_ids_from_mappings(
    *,
    categories: Iterable[Mapping[str, Any] | Any],
    relations: Iterable[Mapping[str, Any] | tuple[UUID, UUID] | Any],
) -> frozenset[UUID]:
    children: dict[UUID, set[UUID]] = {}
    for rel in relations:
        if isinstance(rel, tuple):
            parent_id, child_id = rel[0], rel[1]
        else:
            parent_id, child_id = rel["parent_id"], rel["child_id"]
        children.setdefault(parent_id, set()).add(child_id)
    attachment_ids = {
        row["id"] for row in categories if row["is_attachment_category"]
    }
    pending = list(attachment_ids)
    while pending:
        parent_id = pending.pop()
        for child_id in children.get(parent_id, ()):
            if child_id in attachment_ids:
                continue
            attachment_ids.add(child_id)
            pending.append(child_id)
    return frozenset(attachment_ids)


async def _active_attachment_branch_category_ids(
    session: AsyncSession,
) -> frozenset[UUID]:
    categories = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategory.id,
                SpecialEquipmentCategory.is_attachment_category,
            ).where(
                SpecialEquipmentCategory.is_active.is_(True),
                SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
            )
        )
    ).mappings()
    relations = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategoryRelation.parent_id,
                SpecialEquipmentCategoryRelation.child_id,
            )
        )
    ).mappings()
    return _attachment_category_ids_from_mappings(
        categories=categories,
        relations=relations,
    )


def _rule_edges(
    edges: Iterable[Sequence[Any] | tuple[UUID, UUID]],
    attachment_ids: frozenset[UUID],
) -> list[tuple[UUID, UUID]]:
    return [
        (UUID(str(edge[0])), UUID(str(edge[1])))
        for edge in edges
        if not is_boundary_edge(
            parent_id=UUID(str(edge[0])),
            child_id=UUID(str(edge[1])),
            attachment_ids=attachment_ids,
        )
    ]


async def list_marks(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentMark.id,
                SpecialEquipmentMark.code,
                SpecialEquipmentMark.name,
                SpecialEquipmentMark.slug,
            )
            .where(SpecialEquipmentMark.is_active.is_(True))
            .order_by(SpecialEquipmentMark.name, SpecialEquipmentMark.id)
        )
    ).mappings()
    return [dict(row) for row in rows]


async def list_non_leaf_category_ids(
    session: AsyncSession,
    category_ids: Sequence[UUID],
) -> set[UUID]:
    """Return candidate categories that have at least one active child."""

    unique_ids = tuple(dict.fromkeys(category_ids))
    if not unique_ids:
        return set()
    active_child = aliased(SpecialEquipmentCategory)
    return set(
        (
            await session.execute(
                sa.select(SpecialEquipmentCategoryRelation.parent_id)
                .join(
                    active_child,
                    active_child.id
                    == SpecialEquipmentCategoryRelation.child_id,
                )
                .where(
                    SpecialEquipmentCategoryRelation.parent_id.in_(unique_ids),
                    active_child.is_active.is_(True),
                    active_child.is_visible_in_catalog.is_(True),
                )
                .distinct()
            )
        ).scalars()
    )


def _attachment_branch_cte(
    name: str = "special_equipment_attachment_branch",
) -> sa.CTE:
    attachment_categories = (
        sa.select(SpecialEquipmentCategory.id.label("id"))
        .where(
            SpecialEquipmentCategory.is_attachment_category.is_(True),
            SpecialEquipmentCategory.is_active.is_(True),
            SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
        )
        .cte(name, recursive=True)
    )
    return attachment_categories.union(
        sa.select(SpecialEquipmentCategoryRelation.child_id.label("id"))
        .join(
            attachment_categories,
            SpecialEquipmentCategoryRelation.parent_id
            == attachment_categories.c.id,
        )
        .join(
            SpecialEquipmentCategory,
            SpecialEquipmentCategory.id
            == SpecialEquipmentCategoryRelation.child_id,
        )
        .where(
            SpecialEquipmentCategory.is_active.is_(True),
            SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
        )
    )


def _descendant_ids(
    category_id: UUID,
    *,
    name: str = "special_equipment_descendants",
) -> sa.CTE:
    att_cte = _attachment_branch_cte(f"{name}_att")
    descendants = sa.select(
        sa.literal(
            category_id,
            type_=PGUUID(as_uuid=True),
        ).label("id")
    ).cte(name, recursive=True)
    return descendants.union(
        sa.select(SpecialEquipmentCategoryRelation.child_id)
        .join(
            descendants,
            SpecialEquipmentCategoryRelation.parent_id == descendants.c.id,
        )
        .join(
            SpecialEquipmentCategory,
            SpecialEquipmentCategory.id
            == SpecialEquipmentCategoryRelation.child_id,
        )
        .where(
            SpecialEquipmentCategory.is_active.is_(True),
            SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
            sa.not_(
                sa.and_(
                    SpecialEquipmentCategoryRelation.child_id.in_(
                        sa.select(att_cte.c.id)
                    ),
                    SpecialEquipmentCategoryRelation.parent_id.not_in(
                        sa.select(att_cte.c.id)
                    ),
                )
            ),
        )
    )


def _ancestor_ids(category_ids: tuple[UUID, ...]) -> sa.CTE:
    name = "special_equipment_ancestors"
    att_cte = _attachment_branch_cte(f"{name}_att")
    ancestors = (
        sa.select(SpecialEquipmentCategory.id.label("id"))
        .where(SpecialEquipmentCategory.id.in_(category_ids))
        .cte(name, recursive=True)
    )
    return ancestors.union(
        sa.select(SpecialEquipmentCategoryRelation.parent_id).join(
            ancestors,
            SpecialEquipmentCategoryRelation.child_id == ancestors.c.id,
        )
        .where(
            sa.not_(
                sa.and_(
                    SpecialEquipmentCategoryRelation.child_id.in_(
                        sa.select(att_cte.c.id)
                    ),
                    SpecialEquipmentCategoryRelation.parent_id.not_in(
                        sa.select(att_cte.c.id)
                    ),
                )
            )
        )
    )


def _category_context_ranks(
    *,
    anchor_ids: Sequence[UUID],
    edges: Sequence[tuple[UUID, UUID]],
) -> dict[UUID, tuple[int, int]]:
    """Rank an ancestor by selected-category priority, then nearest depth."""

    parents: dict[UUID, set[UUID]] = {}
    for parent_id, child_id in edges:
        parents.setdefault(child_id, set()).add(parent_id)
    ranks: dict[UUID, tuple[int, int]] = {}
    for anchor_priority, anchor_id in enumerate(anchor_ids):
        pending = [(anchor_id, 0)]
        visited: dict[UUID, int] = {}
        while pending:
            category_id, distance = pending.pop()
            if distance >= visited.get(category_id, 2**31 - 1):
                continue
            visited[category_id] = distance
            candidate = (anchor_priority, distance)
            if candidate < ranks.get(category_id, (2**31 - 1, 2**31 - 1)):
                ranks[category_id] = candidate
            pending.extend(
                (parent_id, distance + 1)
                for parent_id in parents.get(category_id, ())
            )
    return ranks


def _resolve_attribute_metadata(
    *,
    rows: Sequence[Mapping[str, Any]],
    category_ranks: Mapping[UUID, tuple[int, int]],
    groups: Mapping[UUID, Mapping[str, Any]],
    override_category_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Resolve deepest explicit override, then attribute default, then Other."""

    by_attribute: dict[UUID, list[Mapping[str, Any]]] = {}
    for row in rows:
        if row["category_id"] not in category_ranks:
            continue
        row_group_id = row["override_group_id"] or row["default_group_id"]
        row_group = groups.get(row_group_id) if row_group_id is not None else None
        if row_group is not None and not row_group["is_active"]:
            continue
        by_attribute.setdefault(row["id"], []).append(row)
    result: list[dict[str, Any]] = []
    for attribute_rows in by_attribute.values():
        ordered = sorted(
            attribute_rows,
            key=lambda row: (
                category_ranks[row["category_id"]],
                row["sort_order"],
                str(row["category_id"]),
            ),
        )
        first = ordered[0]
        override = next(
            (
                row
                for row in ordered
                if row["override_group_id"] is not None
                and (
                    override_category_id is None
                    or row["category_id"] == override_category_id
                )
            ),
            None,
        )
        group_id = (
            override["override_group_id"]
            if override is not None
            else first["default_group_id"]
        )
        group = groups.get(group_id) if group_id is not None else None
        if group is not None and not group["is_active"]:
            continue
        result.append(
            {
                "id": first["id"],
                "code": first["code"],
                "name": first["name"],
                "data_type": first["data_type"],
                "filter_kind": first["filter_kind"],
                "unit": first["unit"],
                "group_id": group_id,
                "group_name": group["name"] if group else "Прочие",
                "group_sort_order": (
                    group["sort_order"] if group else 2**31 - 1
                ),
                "is_visible": any(row["is_visible"] for row in ordered),
                "is_filterable": any(row["is_filterable"] for row in ordered),
                "sort_order": min(row["sort_order"] for row in ordered),
            }
        )
    return sorted(
        result,
        key=lambda row: (
            row["group_sort_order"],
            row["sort_order"],
            row["name"],
            str(row["id"]),
        ),
    )


async def _effective_attribute_metadata(
    session: AsyncSession,
    *,
    category_ids: tuple[UUID, ...],
    modification_id: UUID | None = None,
    override_category_id: UUID | None = None,
) -> list[dict[str, Any]]:
    if not category_ids:
        return []
    anchors = list(category_ids)
    if modification_id is not None:
        ordered = list(
            (
                await session.execute(
                    sa.select(SpecialEquipmentModificationCategory.category_id)
                    .where(
                        SpecialEquipmentModificationCategory.modification_id
                        == modification_id,
                        SpecialEquipmentModificationCategory.category_id.in_(
                            category_ids
                        ),
                    )
                    .order_by(
                        SpecialEquipmentModificationCategory.is_primary.desc(),
                        SpecialEquipmentModificationCategory.sort_order,
                        SpecialEquipmentModificationCategory.category_id,
                    )
                )
            ).scalars()
        )
        anchors = ordered + sorted(
            set(category_ids) - set(ordered), key=str
        )
    edges = list(
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentCategoryRelation.parent_id,
                    SpecialEquipmentCategoryRelation.child_id,
                )
            )
        ).tuples()
    )
    attachment_ids = await _active_attachment_branch_category_ids(session)
    rule_edges = _rule_edges(edges, attachment_ids)
    ranks = _category_context_ranks(anchor_ids=anchors, edges=rule_edges)
    rows = list(
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentCategoryAttribute.category_id,
                    SpecialEquipmentAttribute.id,
                    SpecialEquipmentAttribute.code,
                    SpecialEquipmentAttribute.name,
                    SpecialEquipmentAttribute.data_type,
                    SpecialEquipmentAttribute.filter_kind,
                    SpecialEquipmentUnit.name.label("unit"),
                    SpecialEquipmentAttribute.attribute_group_id.label(
                        "default_group_id"
                    ),
                    SpecialEquipmentCategoryAttribute.group_id.label(
                        "override_group_id"
                    ),
                    SpecialEquipmentCategoryAttribute.is_filterable,
                    SpecialEquipmentCategoryAttribute.is_visible,
                    SpecialEquipmentCategoryAttribute.sort_order,
                )
                .join(
                    SpecialEquipmentAttribute,
                    SpecialEquipmentAttribute.id
                    == SpecialEquipmentCategoryAttribute.attribute_id,
                )
                .outerjoin(
                    SpecialEquipmentUnit,
                    SpecialEquipmentUnit.id == SpecialEquipmentAttribute.unit_id,
                )
                .where(
                    SpecialEquipmentCategoryAttribute.category_id.in_(ranks),
                    SpecialEquipmentAttribute.is_active.is_(True),
                )
            )
        ).mappings()
    )
    group_ids = {
        group_id
        for row in rows
        for group_id in (
            row["override_group_id"],
            row["default_group_id"],
        )
        if group_id is not None
    }
    groups = {
        row["id"]: dict(row)
        for row in (
            await session.execute(
                sa.select(
                    SpecialEquipmentAttributeGroup.id,
                    SpecialEquipmentAttributeGroup.name,
                    SpecialEquipmentAttributeGroup.sort_order,
                    SpecialEquipmentAttributeGroup.is_active,
                ).where(SpecialEquipmentAttributeGroup.id.in_(group_ids))
            )
        ).mappings()
    }
    return _resolve_attribute_metadata(
        rows=[dict(row) for row in rows],
        category_ranks=ranks,
        groups=groups,
        override_category_id=override_category_id,
    )


async def list_branch_attribute_metadata(
    session: AsyncSession,
    category_id: UUID,
) -> list[dict[str, Any]]:
    """Return deduplicated effective metadata for one active category branch."""

    descendants = _descendant_ids(
        category_id,
        name="special_equipment_facet_descendants",
    )
    descendant_ids = tuple(
        (
            await session.execute(
                sa.select(SpecialEquipmentCategory.id)
                .where(
                    SpecialEquipmentCategory.id.in_(
                        sa.select(descendants.c.id)
                    ),
                    SpecialEquipmentCategory.is_active.is_(True),
                    SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
                )
                .order_by(
                    SpecialEquipmentCategory.sort_order,
                    SpecialEquipmentCategory.name,
                    SpecialEquipmentCategory.id,
                )
            )
        ).scalars()
    )
    if category_id not in descendant_ids:
        return []
    ordered_ids = (
        category_id,
        *(item for item in descendant_ids if item != category_id),
    )
    return await _effective_attribute_metadata(
        session,
        category_ids=ordered_ids,
        override_category_id=category_id,
    )


async def get_modification_primary_category(
    session: AsyncSession, modification_id: UUID
) -> dict[str, Any] | None:
    """Return the active primary category that defines modification context."""

    row = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategory.id,
                SpecialEquipmentCategory.usage_metric,
            )
            .join(
                SpecialEquipmentModificationCategory,
                SpecialEquipmentModificationCategory.category_id
                == SpecialEquipmentCategory.id,
            )
            .where(
                SpecialEquipmentModificationCategory.modification_id == modification_id,
                SpecialEquipmentModificationCategory.is_primary.is_(True),
                SpecialEquipmentCategory.is_active.is_(True),
                SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
            )
            .order_by(
                SpecialEquipmentModificationCategory.sort_order,
                SpecialEquipmentCategory.id,
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


def _case_insensitive_contains(column: Any, value: str) -> Any:
    """Match a literal substring through the lower(...) trigram indexes."""

    escaped = (
        value.replace("/", "//")
        .replace("%", "/%")
        .replace("_", "/_")
    )
    return sa.func.lower(column).like(
        sa.func.lower(f"%{escaped}%"), escape="/"
    )


def _description_filter_clauses(
    column: Any, filters: SpecialEquipmentFilters
) -> tuple[Any, ...]:
    clauses: list[Any] = []
    if filters.description_include:
        clauses.append(
            _case_insensitive_contains(column, filters.description_include.strip())
        )
    if filters.description_exclude:
        excluded = _case_insensitive_contains(
            column, filters.description_exclude.strip()
        )
        clauses.append(sa.or_(column.is_(None), sa.not_(excluded)))
    return tuple(clauses)


def _attribute_filter_clauses(
    predicates: Sequence[AttributePredicate],
    *,
    modification_id: Any,
    trim_id: Any,
    product_id: Any = None,
) -> list[Any]:
    """Build AND clauses from modification, trim, chassis, or superstructure values.

    Exact predicates for one attribute are alternatives, while every attribute
    itself remains an independent EXISTS condition.  A product can satisfy an
    attribute through either its modification, its effective trim, its product-level
    chassis values, or its superstructure values.
    """

    exact_values: dict[UUID, list[str]] = {}
    clauses: list[Any] = []
    option = SpecialEquipmentAttributeOption

    def _value_exists(
        attribute_id: UUID, condition: Any, *, exact: bool = False
    ) -> Any:
        def _match(value: Any, owner_id: Any, owner_column: Any) -> Any:
            query = sa.select(sa.literal(1)).select_from(value)
            if exact:
                query = query.outerjoin(option, option.id == value.option_id)
            return query.where(
                owner_column == owner_id,
                value.attribute_id == attribute_id,
                condition(value),
            )

        match_options = []
        if modification_id is not None:
            match_options.append(
                sa.and_(
                    modification_id.is_not(None),
                    sa.exists(
                        _match(
                            SpecialEquipmentModificationAttributeValue,
                            modification_id,
                            SpecialEquipmentModificationAttributeValue.modification_id,
                        )
                    ),
                )
            )
        if trim_id is not None:
            match_options.append(
                sa.and_(
                    trim_id.is_not(None),
                    sa.exists(
                        _match(
                            SpecialEquipmentTrimAttributeValue,
                            trim_id,
                            SpecialEquipmentTrimAttributeValue.trim_id,
                        )
                    ),
                )
            )
        if product_id is not None:
            match_options.append(
                sa.and_(
                    product_id.is_not(None),
                    sa.exists(
                        _match(
                            SpecialEquipmentProductChassisValue,
                            product_id,
                            SpecialEquipmentProductChassisValue.product_id,
                        )
                    ),
                )
            )
            match_options.append(
                sa.and_(
                    product_id.is_not(None),
                    sa.exists(
                        _match(
                            SpecialEquipmentProductSuperstructureValue,
                            product_id,
                            SpecialEquipmentProductSuperstructureValue.product_id,
                        )
                    ),
                )
            )
        if not match_options:
            return sa.false()
        return sa.or_(*match_options)

    for predicate in predicates:
        if predicate.operator == "eq":
            values = exact_values.setdefault(predicate.attribute_id, [])
            if predicate.value not in values:
                values.append(predicate.value)
            continue

        if predicate.operator == "search":
            term = predicate.value.strip()
            clauses.append(
                _value_exists(
                    predicate.attribute_id,
                    lambda value, term=term: _case_insensitive_contains(
                        value.value_text, term
                    ),
                )
            )
        else:
            try:
                numeric = Decimal(predicate.value)
            except (InvalidOperation, ValueError):
                clauses.append(sa.false())
                continue
            clauses.append(
                _value_exists(
                    predicate.attribute_id,
                    lambda value, numeric=numeric, operator=predicate.operator: (
                        value.value_number >= numeric
                        if operator == "gte"
                        else value.value_number <= numeric
                    ),
                )
            )

    for attribute_id, raw_values in exact_values.items():
        def _exact_match(value: Any, raw_values: Sequence[str] = raw_values) -> Any:
            comparisons: list[Any] = []
            for raw_value in raw_values:
                lowered = raw_value.casefold()
                boolean_value = (
                    True if lowered == "true" else False if lowered == "false" else None
                )
                try:
                    numeric_value: Decimal | None = Decimal(raw_value)
                except (InvalidOperation, ValueError):
                    numeric_value = None
                comparisons.extend(
                    (
                        option.code == raw_value,
                        value.value_text == raw_value,
                        value.value_boolean == boolean_value
                        if boolean_value is not None
                        else sa.false(),
                        value.value_number == numeric_value
                        if numeric_value is not None
                        else sa.false(),
                    )
                )
            return sa.or_(*comparisons)

        clauses.append(_value_exists(attribute_id, _exact_match, exact=True))

    return clauses


def _product_model_join(
    query: Any,
    product: Any = SpecialEquipmentProduct,
    modification: Any = SpecialEquipmentModification,
    model: Any = SpecialEquipmentModel,
) -> Any:
    """Join modification (outer) and model (coalescing modification and product model_id)."""
    return query.outerjoin(
        modification,
        modification.id == product.modification_id,
    ).join(
        model,
        model.id == sa.func.coalesce(modification.model_id, product.model_id),
    )


def _filtered_product_ids(  # noqa: PLR0912
    filters: SpecialEquipmentFilters,
) -> sa.Select:
    super_model = aliased(SpecialEquipmentModel, name="se_filter_super_model")
    super_mark = aliased(SpecialEquipmentMark, name="se_filter_super_mark")
    query = (
        _product_model_join(
            sa.select(SpecialEquipmentProduct.id),
            product=SpecialEquipmentProduct,
            modification=SpecialEquipmentModification,
            model=SpecialEquipmentModel,
        )
        .join(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .outerjoin(
            SpecialEquipmentSuperstructure,
            SpecialEquipmentSuperstructure.id
            == SpecialEquipmentProduct.superstructure_id,
        )
        .outerjoin(
            super_model,
            super_model.id == SpecialEquipmentProduct.superstructure_model_id,
        )
        .outerjoin(
            super_mark,
            super_mark.id == super_model.mark_id,
        )
        .where(
            SpecialEquipmentProduct.publication_status == "published",
            sa.or_(
                SpecialEquipmentModification.id.is_(None),
                SpecialEquipmentModification.is_active.is_(True),
            ),
            SpecialEquipmentModel.is_active.is_(True),
            SpecialEquipmentMark.is_active.is_(True),
            sa.or_(
                SpecialEquipmentProduct.superstructure_id.is_(None),
                SpecialEquipmentSuperstructure.is_active.is_(True),
            ),
            special_equipment_visible_in(filters.scope),
        )
    )
    if filters.category_id is not None:
        descendants = _descendant_ids(filters.category_id)
        query = query.where(
            SpecialEquipmentProduct.id.in_(
                sa.select(SpecialEquipmentProductCategory.product_id).where(
                    SpecialEquipmentProductCategory.category_id.in_(
                        sa.select(descendants.c.id)
                    )
                )
            )
        )
    if filters.mark_ids:
        query = query.where(SpecialEquipmentMark.id.in_(filters.mark_ids))
    if filters.model_ids:
        query = query.where(SpecialEquipmentModel.id.in_(filters.model_ids))
    if filters.modification_ids:
        query = query.where(
            SpecialEquipmentModification.id.in_(filters.modification_ids)
        )
    if filters.trim_ids:
        query = query.where(SpecialEquipmentProduct.trim_id.in_(filters.trim_ids))
    if filters.body_color_ids:
        query = query.where(SpecialEquipmentProduct.body_color_id.in_(filters.body_color_ids))
    if filters.interior_color_ids:
        query = query.where(
            SpecialEquipmentProduct.interior_color_id.in_(filters.interior_color_ids)
        )
    query = query.where(SpecialEquipmentProduct.sale_status.in_(filters.availability))
    query = query.where(_warehouse_filter_clause(SpecialEquipmentProduct.id, filters))
    if filters.condition is not None:
        query = query.where(SpecialEquipmentProduct.condition == filters.condition)
    for column, minimum, maximum in (
        (
            effective_product_price(),
            filters.price_min,
            filters.price_max,
        ),
        (
            SpecialEquipmentProduct.mileage_km,
            filters.mileage_min,
            filters.mileage_max,
        ),
        (
            SpecialEquipmentProduct.engine_hours,
            filters.engine_hours_min,
            filters.engine_hours_max,
        ),
    ):
        if minimum is not None:
            query = query.where(column >= minimum)
        if maximum is not None:
            query = query.where(column <= maximum)
    if filters.search:
        term = filters.search.strip()
        query = query.where(
            sa.or_(
                _case_insensitive_contains(SpecialEquipmentProduct.code, term),
                _case_insensitive_contains(
                    SpecialEquipmentProduct.description, term
                ),
                _case_insensitive_contains(SpecialEquipmentMark.name, term),
                _case_insensitive_contains(SpecialEquipmentModel.name, term),
                _case_insensitive_contains(
                    SpecialEquipmentModification.name, term
                ),
                _case_insensitive_contains(
                    SpecialEquipmentProduct.superstructure_name, term
                ),
                _case_insensitive_contains(
                    SpecialEquipmentProduct.superstructure_manufacturer, term
                ),
                _case_insensitive_contains(
                    SpecialEquipmentSuperstructure.name, term
                ),
                _case_insensitive_contains(super_model.name, term),
                _case_insensitive_contains(super_mark.name, term),
            )
        )
    if filters.superstructure_ids:
        query = query.where(
            SpecialEquipmentProduct.superstructure_id.in_(filters.superstructure_ids)
        )
    query = query.where(
        *_description_filter_clauses(
            SpecialEquipmentProduct.description,
            filters,
        )
    )
    query = query.where(
        *_attribute_filter_clauses(
            filters.attributes,
            modification_id=SpecialEquipmentProduct.modification_id,
            trim_id=SpecialEquipmentProduct.trim_id,
            product_id=SpecialEquipmentProduct.id,
        )
    )
    return query.distinct()


def _product_projection() -> sa.Select:
    trim = aliased(SpecialEquipmentTrim, name="se_product_trim")
    body_color = aliased(SpecialEquipmentColor, name="se_product_body_color")
    interior_color = aliased(
        SpecialEquipmentColor, name="se_product_interior_color"
    )
    super_type = aliased(
        SpecialEquipmentSuperstructure, name="se_product_super_type"
    )
    super_model = aliased(
        SpecialEquipmentModel, name="se_product_super_model"
    )
    super_mark = aliased(
        SpecialEquipmentMark, name="se_product_super_mark"
    )
    super_mod = aliased(
        SpecialEquipmentModification, name="se_product_super_mod"
    )
    return (
        _product_model_join(
            sa.select(
                SpecialEquipmentProduct.id,
                SpecialEquipmentProduct.code,
                SpecialEquipmentProduct.slug,
                SpecialEquipmentProduct.description,
                _public_fixed_price(SpecialEquipmentProduct.price).label("base_price"),
                _public_fixed_price(SpecialEquipmentProduct.special_price).label(
                    "special_price"
                ),
                SpecialEquipmentProduct.price_on_request,
                SpecialEquipmentProduct.price_from,
                effective_product_price().label("price"),
                SpecialEquipmentProduct.warehouse_id,
                SpecialEquipmentProduct.currency_code,
                SpecialEquipmentProduct.manufacture_year,
                SpecialEquipmentProduct.condition,
                SpecialEquipmentProduct.owners_count,
                SpecialEquipmentProduct.mileage_km,
                SpecialEquipmentProduct.engine_hours,
                SpecialEquipmentProduct.sale_status,
                SpecialEquipmentProduct.modification_id,
                SpecialEquipmentProduct.superstructure_id,
                SpecialEquipmentProduct.superstructure_modification_id,
                SpecialEquipmentProduct.superstructure_name,
                SpecialEquipmentProduct.superstructure_manufacturer,
                super_type.code.label("superstructure_type_code"),
                super_type.name.label("superstructure_type_name"),
                super_model.id.label("superstructure_model_id"),
                super_model.code.label("superstructure_model_code"),
                super_model.name.label("superstructure_model_name"),
                super_model.slug.label("superstructure_model_slug"),
                super_mark.id.label("superstructure_mark_id"),
                super_mark.code.label("superstructure_mark_code"),
                super_mark.name.label("superstructure_mark_name"),
                super_mark.slug.label("superstructure_mark_slug"),
                super_mod.id.label("superstructure_mod_id"),
                super_mod.code.label("superstructure_mod_code"),
                super_mod.name.label("superstructure_mod_name"),
                super_mod.slug.label("superstructure_mod_slug"),
                SpecialEquipmentProduct.trim_id,
                SpecialEquipmentProduct.seller_company_id,
                SpecialEquipmentProduct.body_color_id,
                SpecialEquipmentProduct.interior_color_id,
                body_color.name.label("body_color_name"),
                interior_color.name.label("interior_color_name"),
                trim.name.label("trim_name"),
                SpecialEquipmentModification.code.label("modification_code"),
                SpecialEquipmentModification.name.label("modification_name"),
                SpecialEquipmentModification.slug.label("modification_slug"),
                SpecialEquipmentModification.year_from,
                SpecialEquipmentModification.year_to,
                SpecialEquipmentModel.id.label("model_id"),
                SpecialEquipmentModel.code.label("model_code"),
                SpecialEquipmentModel.name.label("model_name"),
                SpecialEquipmentModel.slug.label("model_slug"),
                SpecialEquipmentMark.id.label("mark_id"),
                SpecialEquipmentMark.code.label("mark_code"),
                SpecialEquipmentMark.name.label("mark_name"),
                SpecialEquipmentMark.slug.label("mark_slug"),
                SpecialEquipmentProduct.published_at,
                (
                    sa.select(City.name)
                    .select_from(Warehouse)
                    .join(City, City.id == Warehouse.city_id)
                    .where(
                        Warehouse.id == SpecialEquipmentProduct.warehouse_id,
                        Warehouse.status == "active",
                    )
                    .scalar_subquery()
                    .label("warehouse_city_name")
                ),
            ),
            product=SpecialEquipmentProduct,
            modification=SpecialEquipmentModification,
            model=SpecialEquipmentModel,
        )
        .join(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .outerjoin(
            super_type,
            super_type.id == SpecialEquipmentProduct.superstructure_id,
        )
        .outerjoin(
            super_model,
            super_model.id == SpecialEquipmentProduct.superstructure_model_id,
        )
        .outerjoin(
            super_mark,
            super_mark.id == super_model.mark_id,
        )
        .outerjoin(
            super_mod,
            super_mod.id == SpecialEquipmentProduct.superstructure_modification_id,
        )
        .outerjoin(trim, trim.id == SpecialEquipmentProduct.trim_id)
        .outerjoin(body_color, body_color.id == SpecialEquipmentProduct.body_color_id)
        .outerjoin(
            interior_color,
            interior_color.id == SpecialEquipmentProduct.interior_color_id,
        )
    )


async def list_product_candidates(
    session: AsyncSession,
    *,
    filters: SpecialEquipmentFilters,
) -> list[dict]:
    """Load every matching physical product for application-level grouping."""

    ids = _filtered_product_ids(filters).subquery()
    rows = (
        (
            await session.execute(
                _product_projection()
                .where(SpecialEquipmentProduct.id.in_(sa.select(ids.c.id)))
            )
        )
        .mappings()
        .all()
    )
    result = [dict(row) for row in rows]
    await _attach_product_collections(session, result)
    return result


def _empty_jsonb_array() -> Any:
    return sa.cast(sa.literal("[]"), JSONB)


def _effective_filtered_product_ids(  # noqa: PLR0912
    filters: SpecialEquipmentFilters,
) -> sa.Select:
    """Filter an offering by public fields."""

    effective_modification = aliased(
        SpecialEquipmentModification, name="se_filter_modification"
    )
    effective_model = aliased(SpecialEquipmentModel, name="se_filter_model")
    effective_mark = aliased(SpecialEquipmentMark, name="se_filter_mark")
    query = (
        sa.select(
            SpecialEquipmentProduct.id,
            SpecialEquipmentProduct.warehouse_id.label("warehouse_id"),
        )
        .outerjoin(
            effective_modification,
            effective_modification.id == SpecialEquipmentProduct.modification_id,
        )
        .join(
            effective_model,
            effective_model.id
            == sa.func.coalesce(
                effective_modification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .join(
            effective_mark,
            effective_mark.id == effective_model.mark_id,
        )
        .where(
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status.in_(filters.availability),
            sa.or_(
                effective_modification.id.is_(None),
                effective_modification.is_active.is_(True),
            ),
            effective_model.is_active.is_(True),
            effective_mark.is_active.is_(True),
            special_equipment_visible_in(filters.scope, product=SpecialEquipmentProduct),
        )
    )
    query = query.where(_warehouse_filter_clause(SpecialEquipmentProduct.id, filters))
    if filters.category_id is not None:
        descendants = _descendant_ids(filters.category_id)
        query = query.where(
            SpecialEquipmentProduct.id.in_(
                sa.select(SpecialEquipmentProductCategory.product_id).where(
                    SpecialEquipmentProductCategory.category_id.in_(
                        sa.select(descendants.c.id)
                    )
                )
            )
        )
    if filters.mark_ids:
        query = query.where(effective_mark.id.in_(filters.mark_ids))
    if filters.model_ids:
        query = query.where(effective_model.id.in_(filters.model_ids))
    if filters.modification_ids:
        query = query.where(effective_modification.id.in_(filters.modification_ids))
    if filters.trim_ids:
        query = query.where(SpecialEquipmentProduct.trim_id.in_(filters.trim_ids))
    if filters.superstructure_ids:
        query = query.where(
            SpecialEquipmentProduct.superstructure_id.in_(filters.superstructure_ids)
        )
    if filters.body_color_ids:
        query = query.where(SpecialEquipmentProduct.body_color_id.in_(filters.body_color_ids))
    if filters.interior_color_ids:
        query = query.where(SpecialEquipmentProduct.interior_color_id.in_(filters.interior_color_ids))
    if filters.condition is not None:
        query = query.where(SpecialEquipmentProduct.condition == filters.condition)
    for column, minimum, maximum in (
        (
            effective_product_price(),
            filters.price_min,
            filters.price_max,
        ),
        (SpecialEquipmentProduct.mileage_km, filters.mileage_min, filters.mileage_max),
        (
            SpecialEquipmentProduct.engine_hours,
            filters.engine_hours_min,
            filters.engine_hours_max,
        ),
    ):
        if minimum is not None:
            query = query.where(column >= minimum)
        if maximum is not None:
            query = query.where(column <= maximum)
    if filters.search:
        term = filters.search.strip()
        query = query.where(
            sa.or_(
                _case_insensitive_contains(SpecialEquipmentProduct.code, term),
                _case_insensitive_contains(SpecialEquipmentProduct.description, term),
                _case_insensitive_contains(effective_mark.name, term),
                _case_insensitive_contains(effective_model.name, term),
                _case_insensitive_contains(effective_modification.name, term),
                _case_insensitive_contains(SpecialEquipmentProduct.superstructure_name, term),
                _case_insensitive_contains(SpecialEquipmentProduct.superstructure_manufacturer, term),
            )
        )
    query = query.where(
        *_description_filter_clauses(SpecialEquipmentProduct.description, filters)
    )
    query = query.where(
        *_attribute_filter_clauses(
            filters.attributes,
            modification_id=effective_modification.id,
            trim_id=SpecialEquipmentProduct.trim_id,
            product_id=SpecialEquipmentProduct.id,
        )
    )
    return query.distinct()


def _public_offering_group_rows(
    filters: SpecialEquipmentFilters,
) -> tuple[sa.CTE, sa.CTE]:
    """Return eligible rows and deterministic disjoint physical bundles."""

    filtered_ids = _effective_filtered_product_ids(filters).cte(
        "se_offering_filtered_ids"
    )
    context_ids = filtered_ids

    category_sets = (
        sa.select(
            SpecialEquipmentProductCategory.product_id,
            sa.func.jsonb_agg(
                aggregate_order_by(
                    sa.cast(SpecialEquipmentProductCategory.category_id, sa.Text),
                    SpecialEquipmentProductCategory.category_id,
                )
            ).label("category_ids"),
        )
        .join(
            SpecialEquipmentCategory,
            SpecialEquipmentCategory.id == SpecialEquipmentProductCategory.category_id,
        )
        .where(
            SpecialEquipmentProductCategory.product_id.in_(
                sa.select(context_ids.c.id)
            ),
            SpecialEquipmentCategory.is_active.is_(True),
            SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
        )
        .group_by(SpecialEquipmentProductCategory.product_id)
        .cte("se_offering_category_sets")
    )
    attachment_sets = (
        sa.select(
            SpecialEquipmentProductAttachment.product_id,
            sa.func.jsonb_agg(
                aggregate_order_by(
                    sa.cast(
                        SpecialEquipmentProductAttachment.attachment_product_id,
                        sa.Text,
                    ),
                    SpecialEquipmentProductAttachment.attachment_product_id,
                )
            ).label("attachment_ids"),
        )
        .where(
            SpecialEquipmentProductAttachment.product_id.in_(
                sa.select(context_ids.c.id)
            )
        )
        .group_by(SpecialEquipmentProductAttachment.product_id)
        .cte("se_offering_attachment_sets")
    )

    chassis_value_sets = (
        sa.select(
            SpecialEquipmentProductChassisValue.product_id,
            sa.func.jsonb_agg(
                aggregate_order_by(
                    sa.func.jsonb_build_array(
                        sa.cast(
                            SpecialEquipmentProductChassisValue.attribute_id,
                            sa.Text,
                        ),
                        SpecialEquipmentProductChassisValue.value_number,
                        SpecialEquipmentProductChassisValue.value_text,
                        SpecialEquipmentProductChassisValue.value_boolean,
                        sa.cast(
                            SpecialEquipmentProductChassisValue.option_id,
                            sa.Text,
                        ),
                    ),
                    SpecialEquipmentProductChassisValue.attribute_id,
                )
            ).label("chassis_values"),
        )
        .where(
            SpecialEquipmentProductChassisValue.product_id.in_(
                sa.select(context_ids.c.id)
            )
        )
        .group_by(SpecialEquipmentProductChassisValue.product_id)
        .cte("se_offering_chassis_value_sets")
    )
    superstructure_value_sets = (
        sa.select(
            SpecialEquipmentProductSuperstructureValue.product_id,
            sa.func.jsonb_agg(
                aggregate_order_by(
                    sa.func.jsonb_build_array(
                        sa.cast(
                            SpecialEquipmentProductSuperstructureValue.attribute_id,
                            sa.Text,
                        ),
                        SpecialEquipmentProductSuperstructureValue.value_number,
                        SpecialEquipmentProductSuperstructureValue.value_text,
                        SpecialEquipmentProductSuperstructureValue.value_boolean,
                        sa.cast(
                            SpecialEquipmentProductSuperstructureValue.option_id,
                            sa.Text,
                        ),
                    ),
                    SpecialEquipmentProductSuperstructureValue.attribute_id,
                )
            ).label("superstructure_values"),
        )
        .where(
            SpecialEquipmentProductSuperstructureValue.product_id.in_(
                sa.select(context_ids.c.id)
            )
        )
        .group_by(SpecialEquipmentProductSuperstructureValue.product_id)
        .cte("se_offering_superstructure_value_sets")
    )

    effective_modification = aliased(
        SpecialEquipmentModification, name="se_effective_modification"
    )
    effective_model = aliased(SpecialEquipmentModel, name="se_effective_model")
    effective_mark = aliased(SpecialEquipmentMark, name="se_effective_mark")
    trim = aliased(SpecialEquipmentTrim, name="se_effective_trim")
    body_color = aliased(SpecialEquipmentColor, name="se_effective_body_color")
    interior_color = aliased(SpecialEquipmentColor, name="se_effective_interior_color")
    eff_super_type = aliased(
        SpecialEquipmentSuperstructure, name="se_eff_super_type"
    )
    eff_super_model = aliased(
        SpecialEquipmentModel, name="se_eff_super_model"
    )
    eff_super_mark = aliased(
        SpecialEquipmentMark, name="se_eff_super_mark"
    )
    eff_super_mod = aliased(
        SpecialEquipmentModification, name="se_eff_super_mod"
    )
    categories = sa.func.coalesce(category_sets.c.category_ids, _empty_jsonb_array())
    attachments = sa.func.coalesce(
        attachment_sets.c.attachment_ids, _empty_jsonb_array()
    )
    chassis_values = sa.func.coalesce(
        chassis_value_sets.c.chassis_values, _empty_jsonb_array()
    )
    super_values = sa.func.coalesce(
        superstructure_value_sets.c.superstructure_values, _empty_jsonb_array()
    )
    base_key = sa.func.jsonb_build_array(
        sa.cast(SpecialEquipmentProduct.modification_id, sa.Text),
        sa.cast(SpecialEquipmentProduct.trim_id, sa.Text),
        sa.cast(SpecialEquipmentProduct.superstructure_id, sa.Text),
        sa.cast(SpecialEquipmentProduct.superstructure_model_id, sa.Text),
        sa.cast(SpecialEquipmentProduct.superstructure_modification_id, sa.Text),
        SpecialEquipmentProduct.superstructure_name,
        sa.cast(effective_model.id, sa.Text),
        categories,
        sa.cast(SpecialEquipmentProduct.seller_company_id, sa.Text),
        sa.cast(SpecialEquipmentProduct.body_color_id, sa.Text),
        sa.cast(SpecialEquipmentProduct.interior_color_id, sa.Text),
        SpecialEquipmentProduct.condition,
        SpecialEquipmentProduct.manufacture_year,
        SpecialEquipmentProduct.price_on_request,
        effective_product_price(),
        SpecialEquipmentProduct.currency_code,
        SpecialEquipmentProduct.mileage_km,
        SpecialEquipmentProduct.engine_hours,
        SpecialEquipmentProduct.owners_count,
        SpecialEquipmentProduct.sale_status,
        SpecialEquipmentProduct.description,
        attachments,
        chassis_values,
        super_values,
    ).label("base_key")
    category_source_id = SpecialEquipmentProduct.id.label("_category_source_id")
    base_rows = (
        sa.select(
            SpecialEquipmentProduct.id,
            SpecialEquipmentProduct.code,
            SpecialEquipmentProduct.slug,
            SpecialEquipmentProduct.description,
            _public_fixed_price(SpecialEquipmentProduct.price).label("base_price"),
            _public_fixed_price(SpecialEquipmentProduct.special_price).label(
                "special_price"
            ),
            SpecialEquipmentProduct.price_on_request,
            SpecialEquipmentProduct.price_from,
            effective_product_price().label("price"),
            SpecialEquipmentProduct.currency_code,
            SpecialEquipmentProduct.manufacture_year,
            SpecialEquipmentProduct.condition.label("condition"),
            SpecialEquipmentProduct.owners_count.label("owners_count"),
            SpecialEquipmentProduct.mileage_km.label("mileage_km"),
            SpecialEquipmentProduct.engine_hours.label("engine_hours"),
            SpecialEquipmentProduct.seller_company_id,
            SpecialEquipmentProduct.sale_status,
            SpecialEquipmentProduct.modification_id.label("modification_id"),
            SpecialEquipmentProduct.superstructure_id.label("superstructure_id"),
            SpecialEquipmentProduct.superstructure_modification_id.label(
                "superstructure_modification_id"
            ),
            SpecialEquipmentProduct.superstructure_name.label("superstructure_name"),
            SpecialEquipmentProduct.superstructure_manufacturer.label(
                "superstructure_manufacturer"
            ),
            effective_modification.name.label("modification_name"),
            effective_modification.slug.label("modification_slug"),
            effective_modification.code.label("modification_code"),
            effective_modification.year_from,
            effective_modification.year_to,
            effective_model.id.label("model_id"),
            effective_model.name.label("model_name"),
            effective_model.slug.label("model_slug"),
            effective_model.code.label("model_code"),
            effective_mark.id.label("mark_id"),
            effective_mark.name.label("mark_name"),
            effective_mark.slug.label("mark_slug"),
            effective_mark.code.label("mark_code"),
            eff_super_type.code.label("superstructure_type_code"),
            eff_super_type.name.label("superstructure_type_name"),
            eff_super_model.id.label("superstructure_model_id"),
            eff_super_model.code.label("superstructure_model_code"),
            eff_super_model.name.label("superstructure_model_name"),
            eff_super_model.slug.label("superstructure_model_slug"),
            eff_super_mark.id.label("superstructure_mark_id"),
            eff_super_mark.code.label("superstructure_mark_code"),
            eff_super_mark.name.label("superstructure_mark_name"),
            eff_super_mark.slug.label("superstructure_mark_slug"),
            eff_super_mod.id.label("superstructure_mod_id"),
            eff_super_mod.code.label("superstructure_mod_code"),
            eff_super_mod.name.label("superstructure_mod_name"),
            eff_super_mod.slug.label("superstructure_mod_slug"),
            eff_super_mod.name.label("superstructure_modification_name"),
            SpecialEquipmentProduct.trim_id.label("trim_id"),
            trim.name.label("trim_name"),
            SpecialEquipmentProduct.warehouse_id.label("warehouse_id"),
            SpecialEquipmentProduct.body_color_id.label("body_color_id"),
            SpecialEquipmentProduct.interior_color_id.label("interior_color_id"),
            body_color.name.label("body_color_name"),
            interior_color.name.label("interior_color_name"),
            categories.label("categories"),
            attachments.label("attachments"),
            chassis_values.label("chassis_values"),
            super_values.label("superstructure_values"),
            SpecialEquipmentProduct.publication_status,
            sa.or_(
                effective_modification.id.is_(None),
                effective_modification.is_active.is_(True),
            ).label("modification_is_active"),
            effective_model.is_active.label("model_is_active"),
            effective_mark.is_active.label("mark_is_active"),
            SpecialEquipmentProduct.published_at,
            (
                sa.select(City.name)
                .select_from(Warehouse)
                .join(City, City.id == Warehouse.city_id)
                .where(
                    Warehouse.id == SpecialEquipmentProduct.warehouse_id,
                    Warehouse.status == "active",
                )
                .scalar_subquery()
                .label("warehouse_city_name")
            ),
            sa.exists(
                sa.select(SpecialEquipmentProduct.id)
                .select_from(Warehouse)
                .join(Company, Company.id == Warehouse.owner_company_id)
                .where(
                    Warehouse.id == SpecialEquipmentProduct.warehouse_id,
                    Warehouse.is_active.is_(True),
                    Company.is_active.is_(True),
                )
            ).label("warehouse_available"),
            category_source_id,
            base_key,
        )
        .outerjoin(
            effective_modification,
            effective_modification.id == SpecialEquipmentProduct.modification_id,
        )
        .join(
            effective_model,
            effective_model.id
            == sa.func.coalesce(
                effective_modification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .join(effective_mark, effective_mark.id == effective_model.mark_id)
        .outerjoin(
            eff_super_type,
            eff_super_type.id == SpecialEquipmentProduct.superstructure_id,
        )
        .outerjoin(
            eff_super_model,
            eff_super_model.id == SpecialEquipmentProduct.superstructure_model_id,
        )
        .outerjoin(
            eff_super_mark,
            eff_super_mark.id == eff_super_model.mark_id,
        )
        .outerjoin(
            eff_super_mod,
            eff_super_mod.id == SpecialEquipmentProduct.superstructure_modification_id,
        )
        .outerjoin(trim, trim.id == SpecialEquipmentProduct.trim_id)
        .outerjoin(
            body_color,
            body_color.id == SpecialEquipmentProduct.body_color_id,
        )
        .outerjoin(
            interior_color,
            interior_color.id == SpecialEquipmentProduct.interior_color_id,
        )
        .outerjoin(
            category_sets,
            category_sets.c.product_id == SpecialEquipmentProduct.id,
        )
        .outerjoin(
            attachment_sets,
            attachment_sets.c.product_id == SpecialEquipmentProduct.id,
        )
        .outerjoin(
            chassis_value_sets,
            chassis_value_sets.c.product_id == SpecialEquipmentProduct.id,
        )
        .outerjoin(
            superstructure_value_sets,
            superstructure_value_sets.c.product_id == SpecialEquipmentProduct.id,
        )
        .where(SpecialEquipmentProduct.id.in_(sa.select(context_ids.c.id)))
        .cte("se_offering_base_rows")
    )

    final_key = sa.func.jsonb_build_array(
        base_rows.c.base_key,
    ).label("commercial_key")
    empty_uuid_array = sa.cast(
        sa.literal("{}"),
        ARRAY(PGUUID(as_uuid=True)),
    )
    bundle_ids = sa.func.array_append(empty_uuid_array, base_rows.c.id).label("bundle_ids")
    eligible = (
        sa.select(*base_rows.c, final_key, bundle_ids)
        .where(base_rows.c.id.in_(sa.select(filtered_ids.c.id)))
        .cte("se_offering_eligible")
    )
    return eligible, eligible


def _min_in_stock_physical_product_ids(
    filters: SpecialEquipmentFilters,
) -> sa.CTE:
    """Physical public stock matching every filter except availability/min stock.

    min_in_stock is an inventory threshold, not an availability facet.
    A physical on_order product with a warehouse is part of the threshold
    population; an on_order product without a warehouse naturally drops
    out when a warehouse or city filter is active.
    """

    threshold_filters = replace(
        filters,
        availability=("available", "on_order"),
        min_in_stock=None,
    )
    return (
        _effective_filtered_product_ids(threshold_filters)
        .where(SpecialEquipmentProduct.no_vin.is_(False))
        .cte("se_min_in_stock_physical_ids")
    )


def _min_in_stock_qualifying_warehouse_ids(
    physical_ids: sa.CTE,
    *,
    threshold: int,
) -> sa.CTE:
    """Warehouses whose filtered physical inventory reaches the threshold."""

    return (
        sa.select(physical_ids.c.warehouse_id)
        .join(Warehouse, Warehouse.id == physical_ids.c.warehouse_id)
        .where(Warehouse.status == "active")
        .group_by(physical_ids.c.warehouse_id)
        .having(sa.func.count(sa.distinct(physical_ids.c.id)) >= threshold)
        .cte("se_min_in_stock_warehouse_ids")
    )


def _public_eligible_product_ids(
    filters: SpecialEquipmentFilters,
) -> sa.Select:
    """Return public IDs stocked in a warehouse that reaches the threshold."""

    if not filters.min_in_stock:
        eligible, _fulfillable = _public_offering_group_rows(
            filters,
        )
        return sa.select(eligible.c.id)

    eligible, _fulfillable = _public_offering_group_rows(
        filters,
    )
    physical_ids = _min_in_stock_physical_product_ids(
        filters,
    )
    qualifying_warehouses = _min_in_stock_qualifying_warehouse_ids(
        physical_ids,
        threshold=filters.min_in_stock,
    )
    return sa.select(eligible.c.id).where(
        eligible.c.warehouse_id.in_(
            sa.select(qualifying_warehouses.c.warehouse_id)
        )
    )


def _deterministic_disjoint_bundle_counts(fulfillable: sa.CTE) -> sa.CTE:
    """Count UUID-ordered, mutually disjoint bundles per commercial group."""

    candidates = (
        sa.select(
            fulfillable.c.commercial_key,
            fulfillable.c.id,
            fulfillable.c.bundle_ids,
            sa.func.row_number()
            .over(
                partition_by=fulfillable.c.commercial_key,
                order_by=fulfillable.c.id,
            )
            .label("bundle_rank"),
        )
        .cte("se_offering_bundle_candidates")
    )
    walk = (
        sa.select(
            candidates.c.commercial_key,
            candidates.c.bundle_rank,
            candidates.c.bundle_ids.label("claimed_ids"),
            sa.literal(1, type_=sa.Integer).label("available_count"),
        )
        .where(candidates.c.bundle_rank == 1)
        .cte("se_offering_bundle_walk", recursive=True)
    )
    state = walk.alias("se_offering_bundle_state")
    next_candidate = candidates.alias("se_offering_next_bundle")
    overlaps = state.c.claimed_ids.op("&&")(next_candidate.c.bundle_ids)
    walk = walk.union_all(
        sa.select(
            next_candidate.c.commercial_key,
            next_candidate.c.bundle_rank,
            sa.case(
                (overlaps, state.c.claimed_ids),
                else_=sa.func.array_cat(
                    state.c.claimed_ids, next_candidate.c.bundle_ids
                ),
            ).label("claimed_ids"),
            (
                state.c.available_count + sa.case((overlaps, 0), else_=1)
            ).label("available_count"),
        ).select_from(
            state.join(
                next_candidate,
                sa.and_(
                    next_candidate.c.commercial_key == state.c.commercial_key,
                    next_candidate.c.bundle_rank == state.c.bundle_rank + 1,
                ),
            )
        )
    )
    return (
        sa.select(
            walk.c.commercial_key,
            sa.func.max(walk.c.available_count).label("available_count"),
        )
        .group_by(walk.c.commercial_key)
        .cte("se_offering_bundle_counts")
    )


def _public_offering_representatives(filters: SpecialEquipmentFilters) -> sa.CTE:
    """Build one public representative per exact commercial group."""

    _, fulfillable = _public_offering_group_rows(
        filters,
    )
    if filters.min_in_stock:
        physical_ids = _min_in_stock_physical_product_ids(
            filters,
        )
        qualifying_warehouses = _min_in_stock_qualifying_warehouse_ids(
            physical_ids,
            threshold=filters.min_in_stock,
        )
        fulfillable = (
            sa.select(*fulfillable.c)
            .where(
                fulfillable.c.warehouse_id.in_(
                    sa.select(qualifying_warehouses.c.warehouse_id)
                )
            )
            .cte("se_offering_min_stock_fulfillable")
        )
    bundle_counts = _deterministic_disjoint_bundle_counts(fulfillable)
    ranked = (
        sa.select(
            *fulfillable.c,
            bundle_counts.c.available_count,
            sa.func.array_agg(fulfillable.c.warehouse_id)
            .filter(fulfillable.c.warehouse_id.is_not(None))
            .over(partition_by=fulfillable.c.commercial_key)
            .label("_warehouse_ids"),
            sa.func.max(fulfillable.c.published_at)
            .over(partition_by=fulfillable.c.commercial_key)
            .label("group_published_at"),
            sa.func.row_number()
            .over(
                partition_by=fulfillable.c.commercial_key,
                order_by=fulfillable.c.id,
            )
            .label("representative_rank"),
        )
        .join(
            bundle_counts,
            bundle_counts.c.commercial_key == fulfillable.c.commercial_key,
        )
        .cte("se_offering_ranked")
    )
    representative_rows = sa.select(*ranked.c).where(ranked.c.representative_rank == 1)
    return representative_rows.cte("se_offering_representatives")


def _grouped_offering_order(representatives: sa.CTE, sort: Sort) -> tuple[Any, ...]:
    tie = representatives.c.id.asc()
    if sort == "name_asc":
        return (
            representatives.c.mark_name.asc(),
            representatives.c.model_name.asc(),
            representatives.c.modification_name.asc(),
            tie,
        )
    field_name, descending = {
        "published_desc": ("group_published_at", True),
        "published_asc": ("group_published_at", False),
        "price_asc": ("price", False),
        "price_desc": ("price", True),
        "mileage_asc": ("mileage_km", False),
        "mileage_desc": ("mileage_km", True),
        "engine_hours_asc": ("engine_hours", False),
        "engine_hours_desc": ("engine_hours", True),
    }[sort]
    field = getattr(representatives.c, field_name)
    ordered = field.desc() if descending else field.asc()
    return (ordered.nullslast(), tie)


async def list_grouped_product_page(
    session: AsyncSession,
    *,
    filters: SpecialEquipmentFilters,
    sort: Sort,
    offset: int,
    limit: int,
) -> tuple[list[dict], int]:
    """Return one bounded page and a same-snapshot total in one statement."""

    representatives = _public_offering_representatives(filters)
    order = _grouped_offering_order(representatives, sort)
    page = (
        sa.select(
            *representatives.c,
            sa.func.row_number().over(order_by=order).label("page_order"),
        )
        .order_by(*order)
        .offset(offset)
        .limit(limit)
        .cte("se_offering_page")
    )
    total = (
        sa.select(sa.func.count().label("group_total"))
        .select_from(representatives)
        .cte("se_offering_total")
    )
    statement = (
        sa.select(total.c.group_total, *page.c)
        .select_from(total.outerjoin(page, sa.true()))
        .order_by(page.c.page_order.asc().nullslast())
    )
    raw_rows = [dict(row) for row in (await session.execute(statement)).mappings()]
    group_total = int(raw_rows[0].pop("group_total")) if raw_rows else 0
    if raw_rows and raw_rows[0]["id"] is None:
        return [], group_total
    for row in raw_rows:
        row.pop("group_total", None)
        row.pop("page_order", None)
        row["_fingerprint"] = str(row.pop("commercial_key"))
        row["_group_published_at"] = row.pop("group_published_at")
        row.pop("bundle_ids", None)
        row.pop("base_key", None)
        row.pop("representative_rank", None)
        row.pop("modification_is_active", None)
        row.pop("model_is_active", None)
        row.pop("mark_is_active", None)
    await _attach_product_collections(session, raw_rows)
    return raw_rows, group_total


async def list_grouped_product_ids_for_member(
    session: AsyncSession,
    product_id: UUID,
    *,
    category_id: UUID | None = None,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> tuple[UUID, ...]:
    """Resolve a detail/checkout member to fulfillable physical rows in SQL."""

    physical_ids, _available_count = await get_grouped_product_inventory_for_member(
        session,
        product_id,
        category_id=category_id,
        scope=scope,
    )
    return physical_ids


async def get_grouped_product_inventory_for_member(
    session: AsyncSession,
    product_id: UUID,
    *,
    category_id: UUID | None = None,
    candidate_ids: Sequence[UUID] | None = None,
    availability: tuple[Literal["available", "on_order"], ...] = (
        "available",
        "on_order",
    ),
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> tuple[tuple[UUID, ...], int]:
    """Return every alternative UUID and checkout-safe capacity in one query."""

    _eligible, fulfillable = _public_offering_group_rows(
        SpecialEquipmentFilters(
            scope=scope,
            category_id=category_id,
            availability=availability,
        )
    )
    if candidate_ids is not None:
        unique_candidate_ids = tuple(dict.fromkeys(candidate_ids))
        if not unique_candidate_ids:
            return (), 0
        fulfillable = (
            sa.select(*fulfillable.c)
            .where(fulfillable.c.id.in_(unique_candidate_ids))
            .cte("se_offering_member_candidates")
        )
    bundle_counts = _deterministic_disjoint_bundle_counts(fulfillable)
    anchor_key = (
        sa.select(fulfillable.c.commercial_key)
        .where(fulfillable.c.id == product_id)
        .scalar_subquery()
    )
    statement = (
        sa.select(fulfillable.c.id, bundle_counts.c.available_count)
        .join(
            bundle_counts,
            bundle_counts.c.commercial_key == fulfillable.c.commercial_key,
        )
        .where(fulfillable.c.commercial_key == anchor_key)
        .order_by(fulfillable.c.id)
    )
    rows = (await session.execute(statement)).all()
    if not rows:
        return (), 0
    return tuple(row.id for row in rows), int(rows[0].available_count)


async def list_warehouse_stock(
    session: AsyncSession,
    product_ids: Sequence[UUID],
    *,
    maximum_count: int | None = None,
) -> list[dict[str, Any]]:
    """Aggregate physical offering members by their warehouse."""

    unique_ids = tuple(dict.fromkeys(product_ids))
    if not unique_ids:
        return []
    rows = list(
        (
            await session.execute(
                sa.select(
                    Warehouse.id.label("warehouse_id"),
                    Warehouse.address,
                    Warehouse.brand,
                    Company.name.label("owner_company_name"),
                    sa.func.count(sa.distinct(SpecialEquipmentProduct.id)).label(
                        "count"
                    ),
                )
                .join(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
                .join(Company, Company.id == Warehouse.owner_company_id)
                .where(SpecialEquipmentProduct.id.in_(unique_ids))
                .group_by(
                    Warehouse.id, Warehouse.address, Warehouse.brand, Company.name
                )
                .order_by(Warehouse.address, Warehouse.id)
            )
        ).mappings()
    )
    remaining = maximum_count
    result: list[dict[str, Any]] = []
    for row in rows:
        if remaining is not None and remaining <= 0:
            break
        count = int(row["count"])
        if remaining is not None:
            count = min(count, remaining)
            remaining -= count
        result.append(
            {
                "warehouse_id": row["warehouse_id"],
                "address": row["address"],
                "brand": row["brand"],
                "owner_company_name": row["owner_company_name"],
                "count": count,
            }
        )
    return result


async def list_active_category_edges(
    session: AsyncSession,
) -> list[tuple[UUID, UUID]]:
    """(parent_id, child_id) where both categories are active."""
    parent_category = aliased(SpecialEquipmentCategory, name="se_edge_parent")
    child_category = aliased(SpecialEquipmentCategory, name="se_edge_child")
    result = await session.execute(
        sa.select(
            SpecialEquipmentCategoryRelation.parent_id,
            SpecialEquipmentCategoryRelation.child_id,
        )
        .join(
            parent_category,
            parent_category.id == SpecialEquipmentCategoryRelation.parent_id,
        )
        .join(
            child_category,
            child_category.id == SpecialEquipmentCategoryRelation.child_id,
        )
        .where(
            parent_category.is_active.is_(True),
            parent_category.is_visible_in_catalog.is_(True),
            child_category.is_active.is_(True),
            child_category.is_visible_in_catalog.is_(True),
        )
        .order_by(
            SpecialEquipmentCategoryRelation.parent_id,
            SpecialEquipmentCategoryRelation.sort_order,
            SpecialEquipmentCategoryRelation.child_id,
        )
    )
    return [(row[0], row[1]) for row in result.tuples()]


async def get_active_category_link(
    session: AsyncSession, category_id: UUID
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategory.id,
                SpecialEquipmentCategory.code,
                SpecialEquipmentCategory.name,
                SpecialEquipmentCategory.slug,
            ).where(
                SpecialEquipmentCategory.id == category_id,
                SpecialEquipmentCategory.is_active.is_(True),
                SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
            )
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def list_products_by_ids(
    session: AsyncSession,
    product_ids: Sequence[UUID],
    *,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> list[dict]:
    """Load a public physical-product subset in one batch."""

    unique_ids = tuple(dict.fromkeys(product_ids))
    if not unique_ids:
        return []
    rows = (
        (
            await session.execute(
                _product_projection().where(
                    SpecialEquipmentProduct.id.in_(unique_ids),
                    SpecialEquipmentProduct.publication_status == "published",
                    SpecialEquipmentProduct.sale_status.in_(
                        ("available", "on_order")
                    ),
                    special_equipment_visible_in(scope),
                )
            )
        )
        .mappings()
        .all()
    )
    result = [dict(row) for row in rows]
    await _attach_product_collections(session, result)
    return result


async def list_products_by_ids_unrestricted(
    session: AsyncSession,
    product_ids: Sequence[UUID],
) -> list[dict]:
    """Load physical products for stale-cart fingerprint recovery."""

    unique_ids = tuple(dict.fromkeys(product_ids))
    if not unique_ids:
        return []
    rows = (
        (
            await session.execute(
                _product_projection().where(
                    SpecialEquipmentProduct.id.in_(unique_ids),
                )
            )
        )
        .mappings()
        .all()
    )
    result = [dict(row) for row in rows]
    await _attach_product_collections(session, result)
    return result


async def get_product(
    session: AsyncSession,
    *,
    product_id: UUID,
    category_id: UUID | None,
) -> dict | None:
    # Public composite eligibility and inherited categories are checked by the
    # exact point-group query after this physical row has been loaded.
    del category_id
    row = (
        (
            await session.execute(
                _product_projection().where(
                    SpecialEquipmentProduct.id == product_id,
                    SpecialEquipmentProduct.publication_status == "published",
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    result = dict(row)
    rows = [result]
    await _attach_product_collections(session, rows)
    result["images"] = await list_product_images(session, product_id)
    return result


async def _attach_product_collections(session: AsyncSession, rows: list[dict]) -> None:
    product_ids = [row["id"] for row in rows]
    if not product_ids:
        return
    category_source_ids = [
        row.get("_category_source_id", row["id"]) for row in rows
    ]
    modification_ids = tuple({row["modification_id"] for row in rows})
    warehouse_ids_by_product = {
        row["id"]: tuple(
            row.pop("_warehouse_ids", None)
            or ((row["warehouse_id"],) if row.get("warehouse_id") else ())
        )
        for row in rows
    }
    warehouse_ids = {
        warehouse_id
        for item_ids in warehouse_ids_by_product.values()
        for warehouse_id in item_ids
    }
    category_rows = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentProductCategory.product_id,
                    SpecialEquipmentCategory.id,
                    SpecialEquipmentCategory.code,
                    SpecialEquipmentCategory.name,
                    SpecialEquipmentCategory.slug,
                )
                .join(
                    SpecialEquipmentCategory,
                    SpecialEquipmentCategory.id
                    == SpecialEquipmentProductCategory.category_id,
                )
                .where(
                    SpecialEquipmentProductCategory.product_id.in_(
                        category_source_ids
                    ),
                    SpecialEquipmentCategory.is_active.is_(True),
                    SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
                )
                .order_by(
                    SpecialEquipmentCategory.sort_order,
                    SpecialEquipmentCategory.name,
                    SpecialEquipmentCategory.id,
                )
            )
        )
        .mappings()
        .all()
    )
    image_rows = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentProductImage.product_id,
                    SpecialEquipmentProductImage.id,
                    SpecialEquipmentProductImage.alt_text,
                ).where(
                    SpecialEquipmentProductImage.product_id.in_(product_ids),
                    SpecialEquipmentProductImage.is_primary.is_(True),
                )
            )
        )
        .mappings()
        .all()
    )
    primary_category_rows = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentModificationCategory.modification_id,
                    SpecialEquipmentCategory.id,
                    SpecialEquipmentCategory.code,
                    SpecialEquipmentCategory.name,
                    SpecialEquipmentCategory.slug,
                )
                .join(
                    SpecialEquipmentCategory,
                    SpecialEquipmentCategory.id
                    == SpecialEquipmentModificationCategory.category_id,
                )
                .where(
                    SpecialEquipmentModificationCategory.modification_id.in_(
                        modification_ids
                    ),
                    SpecialEquipmentModificationCategory.is_primary.is_(True),
                    SpecialEquipmentCategory.is_active.is_(True),
                    SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
                )
                .order_by(
                    SpecialEquipmentModificationCategory.sort_order,
                    SpecialEquipmentCategory.sort_order,
                    SpecialEquipmentCategory.name,
                    SpecialEquipmentCategory.id,
                )
            )
        )
        .mappings()
        .all()
    )
    warehouse_rows = (
        (
            await session.execute(
                sa.select(
                    Warehouse.id,
                    Warehouse.address,
                    Warehouse.brand,
                    Company.name.label("owner_company_name"),
                )
                .join(Company, Company.id == Warehouse.owner_company_id)
                .where(Warehouse.id.in_(warehouse_ids))
                .order_by(Warehouse.address, Warehouse.id)
            )
        )
        .mappings()
        .all()
        if warehouse_ids
        else []
    )
    categories: dict[UUID, list[dict]] = {}
    for item in category_rows:
        categories.setdefault(item["product_id"], []).append(
            {
                "id": item["id"],
                "code": item["code"],
                "name": item["name"],
                "slug": item["slug"],
            }
        )
    images = {
        item["product_id"]: {
            "id": item["id"],
            "alt_text": item["alt_text"],
        }
        for item in image_rows
    }
    primary_categories: dict[UUID, dict[str, Any]] = {}
    for item in primary_category_rows:
        primary_categories.setdefault(
            item["modification_id"],
            {
                "id": item["id"],
                "code": item["code"],
                "name": item["name"],
                "slug": item["slug"],
            },
        )
    warehouses = {item["id"]: dict(item) for item in warehouse_rows}
    for row in rows:
        category_source_id = row.pop("_category_source_id", row["id"])
        row["categories"] = categories.get(category_source_id, [])
        row["primary_image"] = images.get(row["id"])
        row["primary_category"] = primary_categories.get(row["modification_id"])
        counts = Counter(warehouse_ids_by_product[row["id"]])
        remaining = int(row.get("available_count", sum(counts.values())))
        stock: list[dict[str, Any]] = []
        for warehouse_id, count in sorted(
            counts.items(),
            key=lambda item: (
                warehouses.get(item[0], {}).get("address", ""),
                str(item[0]),
            ),
        ):
            warehouse = warehouses.get(warehouse_id)
            if warehouse is None or remaining <= 0:
                continue
            effective_count = min(count, remaining)
            stock.append(
                {
                    "warehouse_id": warehouse_id,
                    "address": warehouse["address"],
                    "brand": warehouse["brand"],
                    "owner_company_name": warehouse["owner_company_name"],
                    "count": effective_count,
                }
            )
            remaining -= effective_count
        row["warehouse_stock"] = stock


async def list_modification_attributes(
    session: AsyncSession,
    *,
    modification_id: UUID,
    category_ids: tuple[UUID, ...],
) -> list[dict]:
    metadata = [
        row
        for row in await _effective_attribute_metadata(
            session,
            category_ids=category_ids,
            modification_id=modification_id,
        )
        if row["is_visible"]
    ]
    if not metadata:
        return []
    by_id = {row["id"]: row for row in metadata}
    values = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentModificationAttributeValue.option_id,
                SpecialEquipmentModificationAttributeValue.value_number,
                SpecialEquipmentModificationAttributeValue.value_text,
                SpecialEquipmentModificationAttributeValue.value_boolean,
                SpecialEquipmentAttributeOption.code.label("option_code"),
                SpecialEquipmentAttributeOption.name.label("option_name"),
            )
            .outerjoin(
                SpecialEquipmentAttributeOption,
                SpecialEquipmentAttributeOption.id
                == SpecialEquipmentModificationAttributeValue.option_id,
            )
            .where(
                SpecialEquipmentModificationAttributeValue.modification_id
                == modification_id,
                SpecialEquipmentModificationAttributeValue.attribute_id.in_(by_id),
            )
        )
    ).mappings()
    values_by_id = {row["attribute_id"]: dict(row) for row in values}
    return [
        {**item, **values_by_id[item["id"]]}
        for item in metadata
        if item["id"] in values_by_id
    ]


async def list_trim_attributes(
    session: AsyncSession,
    *,
    trim_id: UUID | None,
) -> list[dict]:
    if trim_id is None:
        return []
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentAttribute.id,
                SpecialEquipmentAttribute.code,
                SpecialEquipmentAttribute.name,
                SpecialEquipmentAttribute.data_type,
                SpecialEquipmentUnit.name.label("unit"),
                SpecialEquipmentTrimAttribute.group_id,
                sa.func.coalesce(
                    SpecialEquipmentAttributeGroup.name,
                    sa.literal("Прочие"),
                ).label("group_name"),
                sa.func.coalesce(
                    SpecialEquipmentAttributeGroup.sort_order,
                    sa.literal(999999),
                ).label("group_sort_order"),
                SpecialEquipmentTrimAttributeValue.value_number,
                SpecialEquipmentTrimAttributeValue.value_text,
                SpecialEquipmentTrimAttributeValue.value_boolean,
                SpecialEquipmentTrimAttributeValue.option_id,
                SpecialEquipmentAttributeOption.code.label("option_code"),
                SpecialEquipmentAttributeOption.name.label("option_name"),
            )
            .select_from(SpecialEquipmentTrimAttribute)
            .join(
                SpecialEquipmentAttribute,
                SpecialEquipmentAttribute.id
                == SpecialEquipmentTrimAttribute.attribute_id,
            )
            .outerjoin(
                SpecialEquipmentUnit,
                SpecialEquipmentUnit.id == SpecialEquipmentAttribute.unit_id,
            )
            .outerjoin(
                SpecialEquipmentAttributeGroup,
                SpecialEquipmentAttributeGroup.id
                == SpecialEquipmentTrimAttribute.group_id,
            )
            .outerjoin(
                SpecialEquipmentTrimAttributeValue,
                sa.and_(
                    SpecialEquipmentTrimAttributeValue.trim_id
                    == SpecialEquipmentTrimAttribute.trim_id,
                    SpecialEquipmentTrimAttributeValue.attribute_id
                    == SpecialEquipmentTrimAttribute.attribute_id,
                ),
            )
            .outerjoin(
                SpecialEquipmentAttributeOption,
                SpecialEquipmentAttributeOption.id
                == SpecialEquipmentTrimAttributeValue.option_id,
            )
            .where(
                SpecialEquipmentTrimAttribute.trim_id == trim_id,
                SpecialEquipmentAttribute.is_active.is_(True),
                sa.or_(
                    SpecialEquipmentTrimAttributeValue.value_number.is_not(None),
                    SpecialEquipmentTrimAttributeValue.value_text.is_not(None),
                    SpecialEquipmentTrimAttributeValue.value_boolean.is_not(None),
                    SpecialEquipmentTrimAttributeValue.option_id.is_not(None),
                ),
            )
            .order_by(
                SpecialEquipmentAttributeGroup.sort_order,
                SpecialEquipmentTrimAttribute.sort_order,
                SpecialEquipmentAttribute.name,
                SpecialEquipmentAttribute.id,
            )
        )
    ).mappings()
    return [dict(row) for row in rows]


def _ordered_effective_card_category_ids(
    *,
    direct_category_ids: Sequence[UUID],
    modification_category_ids: Sequence[UUID],
) -> tuple[UUID, ...]:
    """Prefer modification categories, then retain product-specific additions."""

    preferred = tuple(dict.fromkeys(modification_category_ids))
    preferred_set = set(preferred)
    additions = sorted(set(direct_category_ids) - preferred_set, key=str)
    return (*preferred, *additions)


async def list_product_attributes_batch(  # noqa: PLR0912, PLR0915
    session: AsyncSession,
    products: Sequence[Mapping[str, Any]],
    *,
    include_hidden: bool = False,
) -> dict[UUID, list[dict]]:
    """Resolve modification attributes for many products.

    When include_hidden=False (default), only card-visible attributes
    (is_visible=True) are returned. When include_hidden=True, all attributes
    having category rules are returned regardless of is_visible.

    Category precedence is still calculated independently for every product,
    but all database reads are batched.  Component count therefore never
    changes the number of SQL statements used by composite detail.
    """

    if not products:
        return {}
    modification_ids = tuple(
        {
            UUID(str(product["modification_id"]))
            for product in products
            if product.get("modification_id") is not None
        }
    )
    direct_categories_by_product = {
        UUID(str(product["id"])): {
            UUID(str(category["id"]))
            for category in product.get("categories", ())
        }
        for product in products
    }
    modification_category_rows = list(
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentModificationCategory.modification_id,
                    SpecialEquipmentModificationCategory.category_id,
                    SpecialEquipmentModificationCategory.is_primary,
                    SpecialEquipmentModificationCategory.sort_order,
                ).where(
                    SpecialEquipmentModificationCategory.modification_id.in_(
                        modification_ids
                    ),
                )
            )
        ).mappings()
    ) if modification_ids else []
    ordered_categories: dict[UUID, list[UUID]] = {}
    for row in sorted(
        modification_category_rows,
        key=lambda item: (
            str(item["modification_id"]),
            not bool(item["is_primary"]),
            int(item["sort_order"]),
            str(item["category_id"]),
        ),
    ):
        ordered_categories.setdefault(row["modification_id"], []).append(
            row["category_id"]
        )
    edges = list(
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentCategoryRelation.parent_id,
                    SpecialEquipmentCategoryRelation.child_id,
                )
            )
        ).tuples()
    )
    attachment_ids = await _active_attachment_branch_category_ids(session)
    rule_edges = _rule_edges(edges, attachment_ids)
    ranks_by_product: dict[UUID, dict[UUID, tuple[int, int]]] = {}
    for product in products:
        product_id = UUID(str(product["id"]))
        mod_id_val = product.get("modification_id")
        modification_id = UUID(str(mod_id_val)) if mod_id_val is not None else None
        anchors = _ordered_effective_card_category_ids(
            direct_category_ids=tuple(direct_categories_by_product[product_id]),
            modification_category_ids=tuple(
                ordered_categories.get(modification_id, ())
                if modification_id is not None
                else ()
            ),
        )
        ranks_by_product[product_id] = _category_context_ranks(
            anchor_ids=anchors,
            edges=rule_edges,
        )
    relevant_categories = {
        category_id
        for ranks in ranks_by_product.values()
        for category_id in ranks
    }
    rule_rows = [
        dict(row)
        for row in (
            await session.execute(
                sa.select(
                    SpecialEquipmentCategoryAttribute.category_id,
                    SpecialEquipmentAttribute.id,
                    SpecialEquipmentAttribute.code,
                    SpecialEquipmentAttribute.name,
                    SpecialEquipmentAttribute.data_type,
                    SpecialEquipmentAttribute.filter_kind,
                    SpecialEquipmentUnit.name.label("unit"),
                    SpecialEquipmentAttribute.attribute_group_id.label(
                        "default_group_id"
                    ),
                    SpecialEquipmentCategoryAttribute.group_id.label(
                        "override_group_id"
                    ),
                    SpecialEquipmentCategoryAttribute.is_filterable,
                    SpecialEquipmentCategoryAttribute.is_visible,
                    SpecialEquipmentCategoryAttribute.sort_order,
                )
                .join(
                    SpecialEquipmentAttribute,
                    SpecialEquipmentAttribute.id
                    == SpecialEquipmentCategoryAttribute.attribute_id,
                )
                .outerjoin(
                    SpecialEquipmentUnit,
                    SpecialEquipmentUnit.id == SpecialEquipmentAttribute.unit_id,
                )
                .where(
                    SpecialEquipmentCategoryAttribute.category_id.in_(
                        relevant_categories
                    ),
                    SpecialEquipmentAttribute.is_active.is_(True),
                )
            )
        ).mappings()
    ]
    group_ids = {
        group_id
        for row in rule_rows
        for group_id in (row["override_group_id"], row["default_group_id"])
        if group_id is not None
    }
    groups = {
        row["id"]: dict(row)
        for row in (
            await session.execute(
                sa.select(
                    SpecialEquipmentAttributeGroup.id,
                    SpecialEquipmentAttributeGroup.name,
                    SpecialEquipmentAttributeGroup.sort_order,
                    SpecialEquipmentAttributeGroup.is_active,
                ).where(SpecialEquipmentAttributeGroup.id.in_(group_ids))
            )
        ).mappings()
    }
    value_rows = list(
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentModificationAttributeValue.modification_id,
                    SpecialEquipmentModificationAttributeValue.attribute_id,
                    SpecialEquipmentModificationAttributeValue.value_number,
                    SpecialEquipmentModificationAttributeValue.value_text,
                    SpecialEquipmentModificationAttributeValue.value_boolean,
                    SpecialEquipmentModificationAttributeValue.option_id,
                    SpecialEquipmentAttributeOption.code.label("option_code"),
                    SpecialEquipmentAttributeOption.name.label("option_name"),
                )
                .outerjoin(
                    SpecialEquipmentAttributeOption,
                    SpecialEquipmentAttributeOption.id
                    == SpecialEquipmentModificationAttributeValue.option_id,
                )
                .where(
                    SpecialEquipmentModificationAttributeValue.modification_id.in_(
                        modification_ids
                    )
                )
            )
        ).mappings()
    ) if modification_ids else []
    values_by_modification: dict[UUID, dict[UUID, dict[str, Any]]] = {}
    for row in value_rows:
        values_by_modification.setdefault(row["modification_id"], {})[
            row["attribute_id"]
        ] = dict(row)

    no_mod_product_ids = tuple(
        UUID(str(product["id"]))
        for product in products
        if product.get("modification_id") is None
    )
    values_by_product: dict[UUID, dict[UUID, dict[str, Any]]] = {}
    if no_mod_product_ids:
        chassis_value_rows = list(
            (
                await session.execute(
                    sa.select(
                        SpecialEquipmentProductChassisValue.product_id,
                        SpecialEquipmentProductChassisValue.attribute_id,
                        SpecialEquipmentProductChassisValue.value_number,
                        SpecialEquipmentProductChassisValue.value_text,
                        SpecialEquipmentProductChassisValue.value_boolean,
                        SpecialEquipmentProductChassisValue.option_id,
                        SpecialEquipmentAttributeOption.code.label("option_code"),
                        SpecialEquipmentAttributeOption.name.label("option_name"),
                    )
                    .outerjoin(
                        SpecialEquipmentAttributeOption,
                        SpecialEquipmentAttributeOption.id
                        == SpecialEquipmentProductChassisValue.option_id,
                    )
                    .where(
                        SpecialEquipmentProductChassisValue.product_id.in_(
                            no_mod_product_ids
                        )
                    )
                )
            ).mappings()
        )
        for row in chassis_value_rows:
            values_by_product.setdefault(row["product_id"], {})[
                row["attribute_id"]
            ] = dict(row)

    superstructure_ids = tuple(
        {
            UUID(str(product["superstructure_id"]))
            for product in products
            if product.get("superstructure_id") is not None
        }
    )
    superstructure_attrs_by_id: dict[UUID, list[dict]] = {}
    superstructure_values_by_product: dict[UUID, dict[UUID, dict[str, Any]]] = {}
    if superstructure_ids:
        super_attr_group = aliased(
            SpecialEquipmentAttributeGroup, name="se_super_attr_group"
        )
        super_attr_rows = list(
            (
                await session.execute(
                    sa.select(
                        SpecialEquipmentSuperstructureAttribute.superstructure_id,
                        SpecialEquipmentAttribute.id,
                        SpecialEquipmentAttribute.code,
                        SpecialEquipmentAttribute.name,
                        SpecialEquipmentAttribute.data_type,
                        SpecialEquipmentAttribute.filter_kind,
                        SpecialEquipmentUnit.name.label("unit"),
                        SpecialEquipmentSuperstructureAttribute.group_id.label(
                            "group_id"
                        ),
                        super_attr_group.name.label("group_name"),
                        super_attr_group.sort_order.label("group_sort_order"),
                        SpecialEquipmentSuperstructureAttribute.is_filterable,
                        SpecialEquipmentSuperstructureAttribute.is_visible,
                        SpecialEquipmentSuperstructureAttribute.sort_order,
                    )
                    .join(
                        SpecialEquipmentAttribute,
                        SpecialEquipmentAttribute.id
                        == SpecialEquipmentSuperstructureAttribute.attribute_id,
                    )
                    .outerjoin(
                        SpecialEquipmentUnit,
                        SpecialEquipmentUnit.id == SpecialEquipmentAttribute.unit_id,
                    )
                    .outerjoin(
                        super_attr_group,
                        super_attr_group.id
                        == SpecialEquipmentSuperstructureAttribute.group_id,
                    )
                    .where(
                        SpecialEquipmentSuperstructureAttribute.superstructure_id.in_(
                            superstructure_ids
                        ),
                        SpecialEquipmentAttribute.is_active.is_(True),
                    )
                    .order_by(
                        super_attr_group.sort_order.nullslast(),
                        SpecialEquipmentSuperstructureAttribute.sort_order,
                        SpecialEquipmentAttribute.name,
                        SpecialEquipmentAttribute.id,
                    )
                )
            ).mappings()
        )
        for row in super_attr_rows:
            superstructure_attrs_by_id.setdefault(
                row["superstructure_id"], []
            ).append(dict(row))

        super_prod_ids = tuple(
            UUID(str(p["id"]))
            for p in products
            if p.get("superstructure_id") is not None
        )
        super_val_rows = list(
            (
                await session.execute(
                    sa.select(
                        SpecialEquipmentProductSuperstructureValue.product_id,
                        SpecialEquipmentProductSuperstructureValue.attribute_id,
                        SpecialEquipmentProductSuperstructureValue.value_number,
                        SpecialEquipmentProductSuperstructureValue.value_text,
                        SpecialEquipmentProductSuperstructureValue.value_boolean,
                        SpecialEquipmentProductSuperstructureValue.option_id,
                        SpecialEquipmentAttributeOption.code.label("option_code"),
                        SpecialEquipmentAttributeOption.name.label("option_name"),
                    )
                    .outerjoin(
                        SpecialEquipmentAttributeOption,
                        SpecialEquipmentAttributeOption.id
                        == SpecialEquipmentProductSuperstructureValue.option_id,
                    )
                    .where(
                        SpecialEquipmentProductSuperstructureValue.product_id.in_(
                            super_prod_ids
                        )
                    )
                )
            ).mappings()
        )
        for row in super_val_rows:
            superstructure_values_by_product.setdefault(
                row["product_id"], {}
            )[row["attribute_id"]] = dict(row)

    result: dict[UUID, list[dict]] = {}
    for product in products:
        product_id = UUID(str(product["id"]))
        mod_id_val = product.get("modification_id")
        modification_id = UUID(str(mod_id_val)) if mod_id_val is not None else None
        metadata = [
            row
            for row in _resolve_attribute_metadata(
                rows=rule_rows,
                category_ranks=ranks_by_product[product_id],
                groups=groups,
            )
            if include_hidden or row["is_visible"]
        ]
        values = (
            values_by_modification.get(modification_id, {})
            if modification_id is not None
            else values_by_product.get(product_id, {})
        )
        chassis_attributes = [
            {**item, **values[item["id"]], "section": "chassis"}
            for item in metadata
            if item["id"] in values
        ]
        super_id_val = product.get("superstructure_id")
        if super_id_val is not None:
            super_id = UUID(str(super_id_val))
            super_attrs = superstructure_attrs_by_id.get(super_id, [])
            super_vals = superstructure_values_by_product.get(product_id, {})
            super_rows = [
                {**item, **super_vals[item["id"]], "section": "superstructure"}
                for item in super_attrs
                if (include_hidden or item["is_visible"])
                and item["id"] in super_vals
            ]
            if include_hidden:
                result[product_id] = chassis_attributes + super_rows
            else:
                from domain.special_equipment_kits import kit_card_attributes

                result[product_id] = kit_card_attributes(
                    superstructure_rows=super_rows,
                    chassis_rows=chassis_attributes,
                    limit=6,
                )
        else:
            result[product_id] = chassis_attributes
    return result


async def list_product_images(session: AsyncSession, product_id: UUID) -> list[dict]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductImage.id,
                SpecialEquipmentProductImage.alt_text,
                SpecialEquipmentProductImage.sort_order,
                SpecialEquipmentProductImage.is_primary,
            )
            .where(SpecialEquipmentProductImage.product_id == product_id)
            .order_by(
                SpecialEquipmentProductImage.sort_order,
                SpecialEquipmentProductImage.id,
            )
        )
    ).mappings()
    return [dict(row) for row in rows]


def _active_color_facet_value(color_id: Any) -> Any:
    """Keep inactive values filterable while hiding them from facet options."""

    return sa.exists(
        sa.select(1).where(
            SpecialEquipmentColor.id == color_id,
            SpecialEquipmentColor.is_active.is_(True),
        )
    )


async def get_facets(  # noqa: PLR0915 -- composed facets query
    session: AsyncSession, filters: SpecialEquipmentFilters
) -> dict:
    ids = _public_eligible_product_ids(filters).subquery()
    mark_ids = _public_eligible_product_ids(
        replace(filters, mark_ids=())
    ).subquery()
    model_ids = _public_eligible_product_ids(
        replace(filters, model_ids=(), modification_ids=())
    ).subquery()
    modification_ids = _public_eligible_product_ids(
        replace(filters, modification_ids=())
    ).subquery()
    trim_representatives = _public_offering_representatives(
        replace(filters, trim_ids=())
    )
    body_color_representatives = _public_offering_representatives(
        replace(filters, body_color_ids=())
    )
    interior_color_representatives = _public_offering_representatives(
        replace(filters, interior_color_ids=())
    )
    availability_ids = _public_eligible_product_ids(
        replace(filters, availability=("available", "on_order"))
    ).subquery()
    city_facet_ids = _public_eligible_product_ids(
        replace(filters, city_id=None)
    ).subquery()
    warehouse_facet_ids = _public_eligible_product_ids(
        replace(filters, warehouse_id=None)
    ).subquery()
    city_rows = [
        dict(row)
        for row in (
        (
            await session.execute(
                sa.select(
                    City.id,
                    City.name,
                    sa.func.count(sa.distinct(SpecialEquipmentProduct.id)).label(
                        "count"
                    ),
                )
                .join(Warehouse, Warehouse.city_id == City.id)
                .join(
                    SpecialEquipmentProduct,
                    SpecialEquipmentProduct.warehouse_id == Warehouse.id,
                )
                .where(
                    Warehouse.status == "active",
                    SpecialEquipmentProduct.id.in_(sa.select(city_facet_ids.c.id)),
                )
                .group_by(City.id, City.name)
                .order_by(City.name, City.id)
            )
        ).mappings().all()
        )
    ]
    warehouse_rows = [
        dict(row)
        for row in (
        (
            await session.execute(
                sa.select(
                    Warehouse.id,
                    Warehouse.city_id,
                    City.name.label("city_name"),
                    Warehouse.address,
                    Warehouse.brand,
                    sa.func.count(sa.distinct(SpecialEquipmentProduct.id)).label(
                        "count"
                    ),
                )
                .outerjoin(City, City.id == Warehouse.city_id)
                .join(
                    SpecialEquipmentProduct,
                    SpecialEquipmentProduct.warehouse_id == Warehouse.id,
                )
                .where(
                    Warehouse.status == "active",
                    SpecialEquipmentProduct.id.in_(
                        sa.select(warehouse_facet_ids.c.id)
                    ),
                )
                .group_by(
                    Warehouse.id,
                    Warehouse.city_id,
                    City.name,
                    Warehouse.address,
                    Warehouse.brand,
                )
                .order_by(City.name.nullslast(), Warehouse.id)
            )
        ).mappings().all()
        )
    ]
    if filters.city_id is not None and all(
        row["id"] != filters.city_id for row in city_rows
    ):
        selected_city = (
            await session.execute(
                sa.select(City.id, City.name).where(City.id == filters.city_id)
            )
        ).mappings().one_or_none()
        if selected_city is not None:
            city_rows.append({**dict(selected_city), "count": 0})
    city_rows.sort(key=lambda row: (str(row["name"]), str(row["id"])))
    if filters.warehouse_id is not None and all(
        row["id"] != filters.warehouse_id for row in warehouse_rows
    ):
        selected_warehouse = (
            await session.execute(
                sa.select(
                    Warehouse.id,
                    Warehouse.city_id,
                    City.name.label("city_name"),
                    Warehouse.address,
                    Warehouse.brand,
                )
                .outerjoin(City, City.id == Warehouse.city_id)
                .where(Warehouse.id == filters.warehouse_id)
            )
        ).mappings().one_or_none()
        if selected_warehouse is not None:
            warehouse_rows.append({**dict(selected_warehouse), "count": 0})
    warehouse_rows.sort(
        key=lambda row: (
            str(row["city_name"] or ""),
            str(row["id"]),
        )
    )
    mark_rows = (
        (
            await session.execute(
                _product_model_join(
                    sa.select(
                        SpecialEquipmentMark.id,
                        SpecialEquipmentMark.name,
                        sa.func.count(sa.distinct(SpecialEquipmentProduct.id)).label(
                            "count"
                        ),
                    ).select_from(SpecialEquipmentProduct),
                    product=SpecialEquipmentProduct,
                    modification=SpecialEquipmentModification,
                    model=SpecialEquipmentModel,
                )
                .join(
                    SpecialEquipmentMark,
                    SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
                )
                .where(SpecialEquipmentProduct.id.in_(sa.select(mark_ids.c.id)))
                .group_by(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
                .order_by(SpecialEquipmentMark.name)
            )
        )
        .mappings()
        .all()
    )
    model_rows = (
        (
            await session.execute(
                _product_model_join(
                    sa.select(
                        SpecialEquipmentModel.id,
                        SpecialEquipmentModel.name,
                        SpecialEquipmentModel.mark_id,
                        sa.func.count(sa.distinct(SpecialEquipmentProduct.id)).label(
                            "count"
                        ),
                    ).select_from(SpecialEquipmentProduct),
                    product=SpecialEquipmentProduct,
                    modification=SpecialEquipmentModification,
                    model=SpecialEquipmentModel,
                )
                .where(SpecialEquipmentProduct.id.in_(sa.select(model_ids.c.id)))
                .group_by(
                    SpecialEquipmentModel.id,
                    SpecialEquipmentModel.name,
                    SpecialEquipmentModel.mark_id,
                )
                .order_by(SpecialEquipmentModel.name, SpecialEquipmentModel.id)
            )
        )
        .mappings()
        .all()
    )
    modification_rows = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentModification.id,
                    SpecialEquipmentModification.name,
                    SpecialEquipmentModification.model_id,
                    sa.func.count(sa.distinct(SpecialEquipmentProduct.id)).label(
                        "count"
                    ),
                )
                .join(
                    SpecialEquipmentProduct,
                    SpecialEquipmentProduct.modification_id
                    == SpecialEquipmentModification.id,
                )
                .where(
                    SpecialEquipmentProduct.id.in_(
                        sa.select(modification_ids.c.id)
                    )
                )
                .group_by(
                    SpecialEquipmentModification.id,
                    SpecialEquipmentModification.name,
                    SpecialEquipmentModification.model_id,
                )
                .order_by(
                    SpecialEquipmentModification.name,
                    SpecialEquipmentModification.id,
                )
            )
        )
        .mappings()
        .all()
    )
    trim_rows = (
        (
            await session.execute(
                sa.select(
                    trim_representatives.c.trim_id.label("id"),
                    trim_representatives.c.trim_name.label("name"),
                    trim_representatives.c.modification_id,
                    sa.func.count(sa.distinct(trim_representatives.c.id)).label("count"),
                )
                .where(trim_representatives.c.trim_id.is_not(None))
                .group_by(
                    trim_representatives.c.trim_id,
                    trim_representatives.c.trim_name,
                    trim_representatives.c.modification_id,
                )
                .order_by(
                    trim_representatives.c.trim_name,
                    trim_representatives.c.trim_id,
                )
            )
        )
        .mappings()
        .all()
    )
    availability_rows = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentProduct.sale_status,
                    sa.func.count().label("count"),
                )
                .where(
                    SpecialEquipmentProduct.id.in_(
                        sa.select(availability_ids.c.id)
                    )
                )
                .group_by(SpecialEquipmentProduct.sale_status)
            )
        )
        .mappings()
        .all()
    )
    body_color_rows = (
        (
            await session.execute(
                sa.select(
                    body_color_representatives.c.body_color_id.label("id"),
                    body_color_representatives.c.body_color_name.label("name"),
                    sa.func.count(sa.distinct(body_color_representatives.c.id)).label("count"),
                )
                .where(
                    body_color_representatives.c.body_color_id.is_not(None),
                    _active_color_facet_value(
                        body_color_representatives.c.body_color_id
                    ),
                )
                .group_by(
                    body_color_representatives.c.body_color_id,
                    body_color_representatives.c.body_color_name,
                )
                .order_by(body_color_representatives.c.body_color_name)
            )
        )
        .mappings()
        .all()
    )
    interior_color_rows = (
        (
            await session.execute(
                sa.select(
                    interior_color_representatives.c.interior_color_id.label("id"),
                    interior_color_representatives.c.interior_color_name.label("name"),
                    sa.func.count(sa.distinct(interior_color_representatives.c.id)).label("count"),
                )
                .where(
                    interior_color_representatives.c.interior_color_id.is_not(None),
                    _active_color_facet_value(
                        interior_color_representatives.c.interior_color_id
                    ),
                )
                .group_by(
                    interior_color_representatives.c.interior_color_id,
                    interior_color_representatives.c.interior_color_name,
                )
                .order_by(interior_color_representatives.c.interior_color_name)
            )
        )
        .mappings()
        .all()
    )
    availability = {"available": 0, "on_order": 0}
    for row in availability_rows:
        if row["sale_status"] in availability:
            availability[row["sale_status"]] = int(row["count"])
    price_row = (
        await session.execute(
            sa.select(
                sa.func.min(
                    effective_product_price()
                ),
                sa.func.max(
                    effective_product_price()
                ),
            ).where(SpecialEquipmentProduct.id.in_(sa.select(ids.c.id)))
        )
    ).one()
    condition_rows = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentProduct.condition,
                    sa.func.count().label("count"),
                )
                .where(SpecialEquipmentProduct.id.in_(sa.select(ids.c.id)))
                .group_by(SpecialEquipmentProduct.condition)
            )
        )
        .mappings()
        .all()
    )
    conditions = {"new": 0, "used": 0}
    for row in condition_rows:
        conditions[row["condition"]] = int(row["count"])
    usage: dict[str, Any] = {"metric": None, "min": None, "max": None}
    attributes: list[dict] = []
    if filters.category_id is not None:
        metric = (
            await session.execute(
                sa.select(SpecialEquipmentCategory.usage_metric).where(
                    SpecialEquipmentCategory.id == filters.category_id
                )
            )
        ).scalar_one()
        column = (
            SpecialEquipmentProduct.mileage_km
            if metric == "mileage_km"
            else SpecialEquipmentProduct.engine_hours
        )
        minimum, maximum = (
            await session.execute(
                sa.select(sa.func.min(column), sa.func.max(column)).where(
                    SpecialEquipmentProduct.id.in_(sa.select(ids.c.id))
                )
            )
        ).one()
        usage = {"metric": metric, "min": minimum, "max": maximum}
        active_exact_values: dict[UUID, tuple[str, ...]] = {}
        for predicate in filters.attributes:
            if predicate.operator != "eq":
                continue
            values = active_exact_values.setdefault(predicate.attribute_id, ())
            if predicate.value not in values:
                active_exact_values[predicate.attribute_id] = (*values, predicate.value)
        attributes = await _attribute_facets(
            session,
            category_id=filters.category_id,
            product_ids=sa.select(ids.c.id),
            active_attribute_ids={item.attribute_id for item in filters.attributes},
            active_exact_values=active_exact_values,
        )
    superstructure_ids = _public_eligible_product_ids(
        replace(filters, superstructure_ids=())
    ).subquery()
    superstructure_rows = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentSuperstructure.id,
                    SpecialEquipmentSuperstructure.name,
                    sa.func.count(sa.distinct(SpecialEquipmentProduct.id)).label(
                        "count"
                    ),
                )
                .join(
                    SpecialEquipmentProduct,
                    SpecialEquipmentProduct.superstructure_id
                    == SpecialEquipmentSuperstructure.id,
                )
                .where(
                    SpecialEquipmentProduct.id.in_(
                        sa.select(superstructure_ids.c.id)
                    ),
                    SpecialEquipmentSuperstructure.is_active.is_(True),
                )
                .group_by(
                    SpecialEquipmentSuperstructure.id,
                    SpecialEquipmentSuperstructure.name,
                )
                .order_by(
                    SpecialEquipmentSuperstructure.name,
                    SpecialEquipmentSuperstructure.id,
                )
            )
        )
        .mappings()
        .all()
    )
    return {
        "marks": [dict(row) for row in mark_rows],
        "models": [dict(row) for row in model_rows],
        "modifications": [dict(row) for row in modification_rows],
        "trims": [dict(row) for row in trim_rows],
        "superstructures": [dict(row) for row in superstructure_rows],
        "body_colors": [dict(row) for row in body_color_rows],
        "interior_colors": [dict(row) for row in interior_color_rows],
        "availability": availability,
        "conditions": conditions,
        "price": {"min": price_row[0], "max": price_row[1]},
        "usage": usage,
        "attributes": attributes,
        "cities": city_rows,
        "warehouses": warehouse_rows,
    }


async def _attribute_facets(  # noqa: PLR0912, PLR0915 -- facet aggregation
    session: AsyncSession,
    *,
    category_id: UUID,
    product_ids: sa.Select,
    active_attribute_ids: set[UUID],
    active_exact_values: Mapping[UUID, Sequence[str]],
) -> list[dict]:
    descendants = _descendant_ids(
        category_id,
        name="special_equipment_facet_product_descendants",
    )
    represented_descendant_ids = tuple(
        (
            await session.execute(
                sa.select(SpecialEquipmentProductCategory.category_id)
                .join(
                    SpecialEquipmentCategory,
                    SpecialEquipmentCategory.id
                    == SpecialEquipmentProductCategory.category_id,
                )
                .where(
                    SpecialEquipmentProductCategory.product_id.in_(product_ids),
                    SpecialEquipmentProductCategory.category_id.in_(
                        sa.select(descendants.c.id)
                    ),
                    SpecialEquipmentCategory.is_active.is_(True),
                    SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
                )
                .distinct()
                .order_by(SpecialEquipmentProductCategory.category_id)
            )
        ).scalars()
    )
    context_ids = (
        category_id,
        *(item for item in represented_descendant_ids if item != category_id),
    )
    metadata = [
        row
        for row in await _effective_attribute_metadata(
            session,
            category_ids=context_ids,
            override_category_id=category_id,
        )
        if row["is_filterable"]
    ]
    superstructure_facet_attrs = [
        dict(row)
        for row in (
            await session.execute(
                sa.select(
                    SpecialEquipmentAttribute.id,
                    SpecialEquipmentAttribute.code,
                    SpecialEquipmentAttribute.name,
                    SpecialEquipmentAttribute.data_type,
                    SpecialEquipmentAttribute.filter_kind,
                    SpecialEquipmentUnit.name.label("unit"),
                    SpecialEquipmentSuperstructureAttribute.group_id.label(
                        "group_id"
                    ),
                    SpecialEquipmentAttributeGroup.name.label("group_name"),
                    SpecialEquipmentAttributeGroup.sort_order.label(
                        "group_sort_order"
                    ),
                    SpecialEquipmentSuperstructureAttribute.is_filterable,
                    SpecialEquipmentSuperstructureAttribute.sort_order,
                )
                .join(
                    SpecialEquipmentSuperstructureAttribute,
                    SpecialEquipmentSuperstructureAttribute.attribute_id
                    == SpecialEquipmentAttribute.id,
                )
                .join(
                    SpecialEquipmentProduct,
                    SpecialEquipmentProduct.superstructure_id
                    == SpecialEquipmentSuperstructureAttribute.superstructure_id,
                )
                .outerjoin(
                    SpecialEquipmentUnit,
                    SpecialEquipmentUnit.id
                    == SpecialEquipmentAttribute.unit_id,
                )
                .outerjoin(
                    SpecialEquipmentAttributeGroup,
                    SpecialEquipmentAttributeGroup.id
                    == SpecialEquipmentSuperstructureAttribute.group_id,
                )
                .where(
                    SpecialEquipmentProduct.id.in_(product_ids),
                    SpecialEquipmentSuperstructureAttribute.is_filterable.is_(
                        True
                    ),
                    SpecialEquipmentAttribute.is_active.is_(True),
                )
                .distinct()
            )
        ).mappings()
    ]
    existing_attr_ids = {row["id"] for row in metadata}
    for row in superstructure_facet_attrs:
        if row["id"] not in existing_attr_ids:
            metadata.append(row)
            existing_attr_ids.add(row["id"])

    if not metadata:
        return []
    by_id: dict[UUID, dict] = {
        row["id"]: {
            **row,
            "numbers": [],
            "counts": {},
            "labels": {},
            "seen": set(),
        }
        for row in metadata
    }
    selected_products = (
        sa.select(
            SpecialEquipmentProduct.id.label("product_id"),
            SpecialEquipmentProduct.modification_id,
            SpecialEquipmentProduct.trim_id,
        )
        .where(SpecialEquipmentProduct.id.in_(product_ids))
        .cte("se_facet_effective_products")
    )
    values = sa.union_all(
        sa.select(
            SpecialEquipmentModificationAttributeValue.attribute_id,
            SpecialEquipmentModificationAttributeValue.value_number,
            SpecialEquipmentModificationAttributeValue.value_text,
            SpecialEquipmentModificationAttributeValue.value_boolean,
            SpecialEquipmentModificationAttributeValue.option_id,
            selected_products.c.product_id,
        )
        .join(
            selected_products,
            selected_products.c.modification_id
            == SpecialEquipmentModificationAttributeValue.modification_id,
        )
        .where(SpecialEquipmentModificationAttributeValue.attribute_id.in_(by_id)),
        sa.select(
            SpecialEquipmentTrimAttributeValue.attribute_id,
            SpecialEquipmentTrimAttributeValue.value_number,
            SpecialEquipmentTrimAttributeValue.value_text,
            SpecialEquipmentTrimAttributeValue.value_boolean,
            SpecialEquipmentTrimAttributeValue.option_id,
            selected_products.c.product_id,
        )
        .join(
            selected_products,
            selected_products.c.trim_id == SpecialEquipmentTrimAttributeValue.trim_id,
        )
        .where(SpecialEquipmentTrimAttributeValue.attribute_id.in_(by_id)),
        sa.select(
            SpecialEquipmentProductChassisValue.attribute_id,
            SpecialEquipmentProductChassisValue.value_number,
            SpecialEquipmentProductChassisValue.value_text,
            SpecialEquipmentProductChassisValue.value_boolean,
            SpecialEquipmentProductChassisValue.option_id,
            selected_products.c.product_id,
        )
        .join(
            selected_products,
            selected_products.c.product_id
            == SpecialEquipmentProductChassisValue.product_id,
        )
        .where(SpecialEquipmentProductChassisValue.attribute_id.in_(by_id)),
        sa.select(
            SpecialEquipmentProductSuperstructureValue.attribute_id,
            SpecialEquipmentProductSuperstructureValue.value_number,
            SpecialEquipmentProductSuperstructureValue.value_text,
            SpecialEquipmentProductSuperstructureValue.value_boolean,
            SpecialEquipmentProductSuperstructureValue.option_id,
            selected_products.c.product_id,
        )
        .join(
            selected_products,
            selected_products.c.product_id
            == SpecialEquipmentProductSuperstructureValue.product_id,
        )
        .where(SpecialEquipmentProductSuperstructureValue.attribute_id.in_(by_id)),
    ).subquery("se_facet_attribute_values")
    rows = (
        (
            await session.execute(
                sa.select(
                    values.c.attribute_id,
                    values.c.value_number,
                    values.c.value_text,
                    values.c.value_boolean,
                    SpecialEquipmentAttributeOption.code.label("option_code"),
                    SpecialEquipmentAttributeOption.name.label("option_name"),
                    values.c.product_id,
                ).outerjoin(
                    SpecialEquipmentAttributeOption,
                    SpecialEquipmentAttributeOption.id == values.c.option_id,
                )
            )
        )
        .mappings()
        .all()
    )
    for val_row in rows:
        item = by_id[val_row["attribute_id"]]
        if val_row["value_number"] is not None:
            item["numbers"].append(val_row["value_number"])
        if val_row["option_code"] is not None:
            value = val_row["option_code"]
            item["labels"][value] = val_row["option_name"]
        elif val_row["value_boolean"] is not None:
            value = "true" if val_row["value_boolean"] else "false"
            active_values = active_exact_values.get(item["id"], ())
            if (
                item["data_type"] == "boolean"
                and not val_row["value_boolean"]
                and "false" not in {value.casefold() for value in active_values}
            ):
                continue
            item["labels"][value] = "Есть" if val_row["value_boolean"] else "Нет"
        elif val_row["value_text"] is not None:
            value = val_row["value_text"]
            item["labels"][value] = value
        else:
            continue
        marker = (val_row["product_id"], value)
        if marker not in item["seen"]:
            item["seen"].add(marker)
            item["counts"][value] = item["counts"].get(value, 0) + 1

    result: list[dict] = []
    for item in by_id.values():
        numbers = item.pop("numbers")
        counts = item.pop("counts")
        labels = item.pop("labels")
        item.pop("seen")
        item.pop("is_visible")
        item.pop("is_filterable")
        item.pop("sort_order")
        item["min"] = min(numbers) if numbers else None
        item["max"] = max(numbers) if numbers else None
        if item["filter_kind"] == "exact":
            for value in active_exact_values.get(item["id"], ()):
                if value not in labels:
                    normalized_value = value.casefold()
                    labels[value] = (
                        "Есть"
                        if item["data_type"] == "boolean" and normalized_value == "true"
                        else "Нет"
                        if item["data_type"] == "boolean"
                        and normalized_value == "false"
                        else value
                    )
                    counts[value] = 0
        item["options"] = [
            {"value": value, "label": labels[value], "count": count}
            for value, count in sorted(counts.items())
        ]
        # Text search facets are rendered as inputs and do not expose every
        # distinct free-form value as a checkbox option.
        if item["filter_kind"] == "search":
            item["options"] = []
        is_active = item["id"] in active_attribute_ids
        has_values = (
            bool(item["options"])
            if item["filter_kind"] == "exact"
            else bool(numbers)
            if item["filter_kind"] == "range"
            else bool(counts)
        )
        if not has_values and not is_active:
            continue
        result.append(item)
    return result


async def list_effective_attribute_rules(
    session: AsyncSession, category_id: UUID
) -> list[dict]:
    ancestors = _ancestor_ids((category_id,))
    effective_group_id = sa.func.coalesce(
        SpecialEquipmentCategoryAttribute.group_id,
        SpecialEquipmentAttribute.attribute_group_id,
    )
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategoryAttribute.category_id,
                SpecialEquipmentCategoryAttribute.attribute_id,
                effective_group_id.label("group_id"),
                SpecialEquipmentAttribute.data_type,
                SpecialEquipmentAttribute.filter_kind,
                SpecialEquipmentCategoryAttribute.is_required,
                SpecialEquipmentCategoryAttribute.is_filterable,
                SpecialEquipmentCategoryAttribute.is_visible,
                SpecialEquipmentCategoryAttribute.sort_order,
            )
            .join(
                SpecialEquipmentAttribute,
                SpecialEquipmentAttribute.id
                == SpecialEquipmentCategoryAttribute.attribute_id,
            )
            .where(
                SpecialEquipmentCategoryAttribute.category_id.in_(
                    sa.select(ancestors.c.id)
                )
            )
        )
    ).mappings()
    return [dict(row) for row in rows]


async def get_category_image_key(
    session: AsyncSession, category_id: UUID
) -> str | None:
    return (
        await session.execute(
            sa.select(SpecialEquipmentCategory.image_key).where(
                SpecialEquipmentCategory.id == category_id,
                SpecialEquipmentCategory.is_active.is_(True),
                SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
            )
        )
    ).scalar_one_or_none()


def _public_image_storage_key_query(image_id: UUID) -> sa.Select:
    return (
        sa.select(SpecialEquipmentProductImage.storage_key)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == SpecialEquipmentProductImage.product_id,
        )
        .where(
            SpecialEquipmentProductImage.id == image_id,
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status.in_(("available", "on_order")),
        )
    )


async def get_image_storage_key(session: AsyncSession, image_id: UUID) -> str | None:
    return (
        await session.execute(_public_image_storage_key_query(image_id))
    ).scalar_one_or_none()
