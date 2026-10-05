"""Persistence adapter for corrected special-equipment catalog management."""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Iterable, Mapping, Sequence, Set
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from domain.special_equipment_attachments import (
    attachment_branch_ids,
    rule_inheritance_graph,
)
from domain.special_equipment_catalog import (
    CategoryAttributeRule,
    CategoryGraph,
    effective_attribute_rules,
    format_attribute_display_value,
)
from domain.special_equipment_management import (
    CategoryCanonicalPath,
    CategoryPathEdge,
    CategoryPathNode,
    canonical_category_paths,
    category_scope_for_levels,
)
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentAttribute,
    SpecialEquipmentAttributeGroup,
    SpecialEquipmentAttributeOption,
    SpecialEquipmentCatalogDeletionLog,
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
    SpecialEquipmentSuperstructureCategory,
    SpecialEquipmentTrim,
    SpecialEquipmentTrimAttribute,
    SpecialEquipmentTrimAttributeValue,
    SpecialEquipmentUnit,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentCartItem,
    SpecialEquipmentFavorite,
    SpecialEquipmentPayment,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.models.special_equipment_import import (
    SpecialEquipmentCatalogState,
)
from infrastructure.models.special_equipment_registry import (
    SpecialEquipmentCatalogMutationReceipt,
    SpecialEquipmentMediaCleanupJob,
)
from infrastructure.models.vehicles import Warehouse

EntityType = Literal[
    "category",
    "mark",
    "model",
    "modification",
    "trim",
    "attribute_group",
    "attribute",
    "attribute_option",
    "product",
    "color",
    "unit",
    "superstructure",
]
CategorySort = Literal["hierarchy", "updated_desc"]
ProductCandidateRole = Literal["attachment"]
ProductSaleStatus = Literal[
    "available",
    "on_order",
    "reserved",
    "sold",
    "unavailable",
]


class AttributeIdRow(TypedDict):
    attribute_id: UUID


class TrimModificationLinkRow(TypedDict):
    trim_id: UUID
    modification_id: UUID
    is_active: bool

_MODEL_BY_TYPE: dict[EntityType, Any] = {
    "category": SpecialEquipmentCategory,
    "mark": SpecialEquipmentMark,
    "model": SpecialEquipmentModel,
    "modification": SpecialEquipmentModification,
    "trim": SpecialEquipmentTrim,
    "attribute_group": SpecialEquipmentAttributeGroup,
    "attribute": SpecialEquipmentAttribute,
    "attribute_option": SpecialEquipmentAttributeOption,
    "product": SpecialEquipmentProduct,
    "color": SpecialEquipmentColor,
    "unit": SpecialEquipmentUnit,
    "superstructure": SpecialEquipmentSuperstructure,
}

_SNAPSHOT_TYPE_KEY = "__carcraft_catalog_snapshot_type__"
_SNAPSHOT_VALUE_KEY = "value"


def _encode_response_snapshot(value: Any) -> Any:  # noqa: PLR0911
    """Encode DB-native response values into lossless JSONB data."""

    if isinstance(value, UUID):
        return {_SNAPSHOT_TYPE_KEY: "uuid", _SNAPSHOT_VALUE_KEY: str(value)}
    if isinstance(value, datetime):
        return {
            _SNAPSHOT_TYPE_KEY: "datetime",
            _SNAPSHOT_VALUE_KEY: value.isoformat(),
        }
    if isinstance(value, date):
        return {_SNAPSHOT_TYPE_KEY: "date", _SNAPSHOT_VALUE_KEY: value.isoformat()}
    if isinstance(value, Decimal):
        return {_SNAPSHOT_TYPE_KEY: "decimal", _SNAPSHOT_VALUE_KEY: str(value)}
    if isinstance(value, Enum):
        return _encode_response_snapshot(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): _encode_response_snapshot(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return {
            _SNAPSHOT_TYPE_KEY: "tuple",
            _SNAPSHOT_VALUE_KEY: [
                _encode_response_snapshot(item) for item in value
            ],
        }
    if isinstance(value, Set) and not isinstance(value, (str, bytes)):
        return {
            _SNAPSHOT_TYPE_KEY: (
                "frozenset" if isinstance(value, frozenset) else "set"
            ),
            _SNAPSHOT_VALUE_KEY: [
                _encode_response_snapshot(item) for item in value
            ],
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_encode_response_snapshot(item) for item in value]
    return value


def _decode_response_snapshot(value: Any) -> Any:  # noqa: PLR0911
    """Restore DB-native response values from a tagged JSONB snapshot."""

    if isinstance(value, list):
        return [_decode_response_snapshot(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    value_type = value.get(_SNAPSHOT_TYPE_KEY)
    if value_type == "uuid":
        return UUID(str(value[_SNAPSHOT_VALUE_KEY]))
    if value_type == "datetime":
        return datetime.fromisoformat(str(value[_SNAPSHOT_VALUE_KEY]))
    if value_type == "date":
        return date.fromisoformat(str(value[_SNAPSHOT_VALUE_KEY]))
    if value_type == "decimal":
        return Decimal(str(value[_SNAPSHOT_VALUE_KEY]))
    if value_type in {"tuple", "set", "frozenset"}:
        items = [
            _decode_response_snapshot(item)
            for item in value[_SNAPSHOT_VALUE_KEY]
        ]
        if value_type == "tuple":
            return tuple(items)
        if value_type == "frozenset":
            return frozenset(items)
        return set(items)
    return {
        str(key): _decode_response_snapshot(item)
        for key, item in value.items()
    }

_CATALOG_SECTION_MODELS: dict[str, Any] = {
    "products": SpecialEquipmentProduct,
    "categories": SpecialEquipmentCategory,
    "marks": SpecialEquipmentMark,
    "models": SpecialEquipmentModel,
    "modifications": SpecialEquipmentModification,
    "trims": SpecialEquipmentTrim,
    "attributes": SpecialEquipmentAttribute,
    "attribute_groups": SpecialEquipmentAttributeGroup,
    "colors": SpecialEquipmentColor,
    "units": SpecialEquipmentUnit,
    "superstructures": SpecialEquipmentSuperstructure,
}

_CATALOG_ADVISORY_LOCK = 21808


async def lock_catalog_for_mutation(session: AsyncSession) -> None:
    """Serialize writes with management peers and import apply."""

    await session.execute(
        sa.select(sa.func.pg_advisory_xact_lock(_CATALOG_ADVISORY_LOCK))
    )
    await session.execute(
        sa.select(SpecialEquipmentCatalogState.singleton)
        .where(SpecialEquipmentCatalogState.singleton.is_(True))
        .with_for_update()
    )


async def increment_catalog_revision(session: AsyncSession) -> int:
    """Invalidate import previews after one successful management mutation."""

    revision = (
        await session.execute(
            sa.update(SpecialEquipmentCatalogState)
            .where(SpecialEquipmentCatalogState.singleton.is_(True))
            .values(
                revision=SpecialEquipmentCatalogState.revision + 1,
                updated_at=sa.func.now(),
                updated_by=None,
            )
            .returning(SpecialEquipmentCatalogState.revision)
        )
    ).scalar_one()
    return int(revision)


async def lock_idempotency_key(
    session: AsyncSession, actor_id: UUID, idempotency_key: str
) -> None:
    """Serialize one actor-scoped catalog create idempotency key."""

    digest = hashlib.blake2b(
        actor_id.bytes + idempotency_key.encode("utf-8"), digest_size=8
    ).digest()
    lock_id = int.from_bytes(digest, byteorder="big", signed=True)
    await session.execute(sa.select(sa.func.pg_advisory_xact_lock(lock_id)))


async def get_mutation_receipt(
    session: AsyncSession, actor_id: UUID, idempotency_key: str
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.select(
                SpecialEquipmentCatalogMutationReceipt.request_hash,
                SpecialEquipmentCatalogMutationReceipt.resource_type,
                SpecialEquipmentCatalogMutationReceipt.resource_id,
                SpecialEquipmentCatalogMutationReceipt.response_snapshot,
            ).where(
                SpecialEquipmentCatalogMutationReceipt.actor_id == actor_id,
                SpecialEquipmentCatalogMutationReceipt.idempotency_key
                == idempotency_key,
            )
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    receipt = dict(row)
    snapshot = receipt["response_snapshot"]
    if snapshot is not None:
        receipt["response_snapshot"] = _decode_response_snapshot(snapshot)
    return receipt


async def add_mutation_receipt(
    session: AsyncSession,
    *,
    actor_id: UUID,
    idempotency_key: str,
    request_hash: str,
    resource_type: EntityType,
    resource_id: UUID,
    response_snapshot: Mapping[str, Any],
) -> None:
    session.add(
        SpecialEquipmentCatalogMutationReceipt(
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            resource_type=resource_type,
            resource_id=resource_id,
            response_snapshot=_encode_response_snapshot(response_snapshot),
        )
    )
    await session.flush()


async def delete_mutation_receipts_for_resource(
    session: AsyncSession,
    *,
    resource_type: EntityType,
    resource_id: UUID,
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentCatalogMutationReceipt).where(
            SpecialEquipmentCatalogMutationReceipt.resource_type
            == resource_type,
            SpecialEquipmentCatalogMutationReceipt.resource_id == resource_id,
        )
    )


async def create_entity(
    session: AsyncSession, entity_type: EntityType, values: Mapping[str, Any]
) -> UUID:
    model = _MODEL_BY_TYPE[entity_type]
    row = model(**dict(values))
    session.add(row)
    await session.flush()
    return row.id


async def replace_product_warehouse(
    session: AsyncSession, *, product_id: UUID, warehouse_id: UUID | None
) -> None:
    """Replace the canonical warehouse field and advance optimistic locking."""
    await session.execute(
        sa.update(SpecialEquipmentProduct)
        .where(SpecialEquipmentProduct.id == product_id)
        .values(
            warehouse_id=warehouse_id,
            lock_version=SpecialEquipmentProduct.lock_version + 1,
        )
    )


async def warehouse_is_active(session: AsyncSession, warehouse_id: UUID) -> bool:
    return (
        await session.execute(
            sa.select(Warehouse.id).where(
                Warehouse.id == warehouse_id, Warehouse.is_active.is_(True)
            )
        )
    ).scalar_one_or_none() is not None


async def warehouse_exists(session: AsyncSession, warehouse_id: UUID) -> bool:
    return (
        await session.execute(
            sa.select(Warehouse.id).where(Warehouse.id == warehouse_id)
        )
    ).scalar_one_or_none() is not None


async def superstructure_name_exists(
    session: AsyncSession,
    name: str,
    exclude_id: UUID | None = None,
) -> bool:
    """Check if a superstructure with the same normalized name already exists."""
    stmt = sa.select(sa.func.count()).select_from(SpecialEquipmentSuperstructure).where(
        sa.func.lower(sa.func.btrim(SpecialEquipmentSuperstructure.name))
        == sa.func.lower(sa.func.btrim(name))
    )
    if exclude_id is not None:
        stmt = stmt.where(SpecialEquipmentSuperstructure.id != exclude_id)
    count = await session.scalar(stmt)
    return bool(count and count > 0)


def product_warehouse_integrity_error_code(exc: BaseException) -> str | None:
    """Translate only warehouse DB backstops into stable application codes."""

    original = getattr(exc, "orig", exc)
    diagnostic = getattr(original, "diag", None)
    cause = getattr(original, "__cause__", None)
    constraint_name = (
        getattr(original, "constraint_name", None)
        or getattr(diagnostic, "constraint_name", None)
        or getattr(cause, "constraint_name", None)
    )
    return {
        "fk_se_products_warehouse": "WAREHOUSE_NOT_FOUND",
        "trg_se_product_warehouse_active": "WAREHOUSE_INACTIVE",
        "trg_se_product_warehouse_no_vin": "WAREHOUSE_NOT_ALLOWED",
        "trg_se_product_warehouse_required": "WAREHOUSE_REQUIRED",
    }.get(str(constraint_name))


async def patch_entity(
    session: AsyncSession,
    entity_type: EntityType,
    entity_id: UUID,
    values: Mapping[str, Any],
) -> bool:
    model = _MODEL_BY_TYPE[entity_type]
    result = await session.execute(
        sa.update(model)
        .where(model.id == entity_id)
        .values(**dict(values), lock_version=model.lock_version + 1)
    )
    return bool(getattr(result, "rowcount", 0))


async def delete_entity(
    session: AsyncSession, entity_type: EntityType, entity_id: UUID
) -> bool:
    if entity_type == "trim":
        await session.execute(
            sa.delete(SpecialEquipmentTrimAttributeValue).where(
                SpecialEquipmentTrimAttributeValue.trim_id == entity_id
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentTrimAttribute).where(
                SpecialEquipmentTrimAttribute.trim_id == entity_id
            )
        )
    model = _MODEL_BY_TYPE[entity_type]
    result = await session.execute(sa.delete(model).where(model.id == entity_id))
    return bool(getattr(result, "rowcount", 0))


async def get_entity(
    session: AsyncSession,
    entity_type: EntityType,
    entity_id: UUID,
) -> dict | None:
    if entity_type == "category":
        return await _get_category_resource(session, entity_id)
    model = _MODEL_BY_TYPE[entity_type]
    row = (
        await session.execute(
            sa.select(*model.__table__.c).where(model.id == entity_id)
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    return await _enrich(session, entity_type, dict(row))


async def lock_entity(
    session: AsyncSession, entity_type: EntityType, entity_id: UUID
) -> dict | None:
    """Lock one mutable aggregate before validating its dependencies."""

    model = _MODEL_BY_TYPE[entity_type]
    locked_id = (
        await session.execute(
            sa.select(model.id).where(model.id == entity_id).with_for_update()
        )
    ).scalar_one_or_none()
    if locked_id is None:
        return None
    return await get_entity(session, entity_type, entity_id)


async def get_warehouse_assignment(
    session: AsyncSession, warehouse_id: UUID
) -> dict[str, Any] | None:
    """Return assignment metadata without exposing an ORM object."""

    row = (
        await session.execute(
            sa.select(
                Warehouse.id,
                Warehouse.address,
                Warehouse.brand,
                Warehouse.company_id,
                Warehouse.dealer_id,
                Warehouse.status,
            ).where(Warehouse.id == warehouse_id)
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def _case_insensitive_contains(column: Any, value: str) -> Any:
    escaped = (
        value.replace("/", "//")
        .replace("%", "/%")
        .replace("_", "/_")
    )
    return sa.func.lower(column).like(
        sa.func.lower(f"%{escaped}%"), escape="/"
    )


def _attachment_category_cte() -> Any:
    attachment_categories = (
        sa.select(SpecialEquipmentCategory.id.label("id"))
        .where(
            SpecialEquipmentCategory.is_attachment_category.is_(True),
            SpecialEquipmentCategory.is_active.is_(True),
        )
        .cte("management_attachment_categories", recursive=True)
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
            SpecialEquipmentCategory.id == SpecialEquipmentCategoryRelation.child_id,
        )
        .where(SpecialEquipmentCategory.is_active.is_(True))
    )


def _product_is_attachment(attachment_categories: Any) -> Any:
    direct_category = sa.exists(
        sa.select(sa.literal(1)).where(
            SpecialEquipmentProductCategory.product_id
            == SpecialEquipmentProduct.id,
            SpecialEquipmentProductCategory.category_id.in_(
                sa.select(attachment_categories.c.id)
            ),
        )
    )
    modification_category = sa.exists(
        sa.select(sa.literal(1)).where(
            SpecialEquipmentModificationCategory.modification_id
            == SpecialEquipmentProduct.modification_id,
            SpecialEquipmentModificationCategory.category_id.in_(
                sa.select(attachment_categories.c.id)
            ),
        )
    )
    return sa.or_(direct_category, modification_category)


def _product_is_composite() -> Any:
    return sa.literal(False)


def _filter_product_candidate_query(
    query: Any,
    *,
    mark_id: UUID | None,
    model_id: UUID | None,
    category_id: UUID | None,
    sale_status: ProductSaleStatus | None,
    role: ProductCandidateRole | None,
    category_scope_ids: frozenset[UUID] | None = None,
) -> Any:
    if mark_id is not None:
        query = query.where(
            sa.exists(
                sa.select(sa.literal(1))
                .select_from(SpecialEquipmentModel)
                .where(
                    SpecialEquipmentModel.id
                    == sa.func.coalesce(
                        SpecialEquipmentProduct.model_id,
                        sa.select(SpecialEquipmentModification.model_id)
                        .where(
                            SpecialEquipmentModification.id
                            == SpecialEquipmentProduct.modification_id
                        )
                        .scalar_subquery(),
                    ),
                    SpecialEquipmentModel.mark_id == mark_id,
                )
                .correlate(SpecialEquipmentProduct)
            )
        )
    if model_id is not None:
        query = query.where(
            sa.or_(
                SpecialEquipmentProduct.model_id == model_id,
                sa.exists(
                    sa.select(sa.literal(1)).where(
                        SpecialEquipmentModification.id
                        == SpecialEquipmentProduct.modification_id,
                        SpecialEquipmentModification.model_id == model_id,
                    ).correlate(SpecialEquipmentProduct)
                ),
            )
        )
    if category_id is not None:
        direct_category = sa.exists(
            sa.select(sa.literal(1)).where(
                SpecialEquipmentProductCategory.product_id
                == SpecialEquipmentProduct.id,
                SpecialEquipmentProductCategory.category_id == category_id,
            ).correlate(SpecialEquipmentProduct)
        )
        modification_category = sa.exists(
            sa.select(sa.literal(1)).where(
                SpecialEquipmentModificationCategory.modification_id
                == SpecialEquipmentProduct.modification_id,
                SpecialEquipmentModificationCategory.category_id == category_id,
            ).correlate(SpecialEquipmentProduct)
        )
        query = query.where(sa.or_(direct_category, modification_category))
    if category_scope_ids is not None:
        ordered_scope_ids = tuple(sorted(category_scope_ids, key=str))
        direct_category = sa.exists(
            sa.select(sa.literal(1)).where(
                SpecialEquipmentProductCategory.product_id
                == SpecialEquipmentProduct.id,
                SpecialEquipmentProductCategory.category_id.in_(
                    ordered_scope_ids
                ),
            ).correlate(SpecialEquipmentProduct)
        )
        modification_category = sa.exists(
            sa.select(sa.literal(1)).where(
                SpecialEquipmentModificationCategory.modification_id
                == SpecialEquipmentProduct.modification_id,
                SpecialEquipmentModificationCategory.category_id.in_(
                    ordered_scope_ids
                ),
            ).correlate(SpecialEquipmentProduct)
        )
        query = query.where(sa.or_(direct_category, modification_category))
    if sale_status is not None:
        query = query.where(SpecialEquipmentProduct.sale_status == sale_status)
    if role is not None:
        attachment_categories = _attachment_category_cte()
        if role == "attachment":
            query = query.where(
                _product_is_attachment(attachment_categories),
            )
    return query


def _category_snapshot_query(*, sort: CategorySort | None) -> sa.Select:
    query = sa.select(*SpecialEquipmentCategory.__table__.c)
    if sort == "updated_desc":
        query = query.order_by(
            sa.func.greatest(
                SpecialEquipmentCategory.created_at,
                SpecialEquipmentCategory.updated_at,
            ).desc(),
            SpecialEquipmentCategory.id.desc(),
        )
    return query


async def _category_management_snapshot(
    session: AsyncSession,
    *,
    sort: CategorySort | None = None,
) -> tuple[
    dict[UUID, dict[str, Any]],
    list[dict[str, Any]],
    dict[UUID, CategoryCanonicalPath],
]:
    category_rows = (
        await session.execute(_category_snapshot_query(sort=sort))
    ).mappings()
    categories = {row["id"]: dict(row) for row in category_rows}
    edge_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategoryRelation.parent_id,
                SpecialEquipmentCategoryRelation.child_id,
                SpecialEquipmentCategoryRelation.sort_order,
            )
        )
    ).mappings()
    edges = [dict(row) for row in edge_rows]
    paths = canonical_category_paths(
        nodes=(
            CategoryPathNode(
                id=category_id,
                name=row["name"],
                sort_order=row["sort_order"],
            )
            for category_id, row in categories.items()
        ),
        edges=(
            CategoryPathEdge(
                parent_id=row["parent_id"],
                child_id=row["child_id"],
                sort_order=row["sort_order"],
            )
            for row in edges
        ),
    )
    return categories, edges, paths


def _category_page_ids(
    *,
    categories: Mapping[UUID, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    paths: Mapping[UUID, CategoryCanonicalPath],
    offset: int,
    limit: int,
    search: str | None,
    level_ids: Sequence[UUID | None],
    sort: CategorySort | None,
) -> tuple[list[UUID], int]:
    term = search.strip().casefold() if search else None
    scope = category_scope_for_levels(
        category_ids=categories,
        edges=(
            CategoryPathEdge(
                parent_id=edge["parent_id"],
                child_id=edge["child_id"],
                sort_order=edge["sort_order"],
            )
            for edge in edges
        ),
        level_ids=level_ids,
    )
    category_ids = [
        category_id
        for category_id, row in categories.items()
        if category_id in scope
        and (
            term is None
            or term in row["name"].casefold()
            or term in paths[category_id].display.casefold()
        )
    ]
    if sort != "updated_desc":
        category_ids.sort(key=lambda category_id: paths[category_id].order_key)
    return category_ids[offset : offset + limit], len(category_ids)


async def _category_attribute_links_by_id(
    session: AsyncSession, category_ids: Sequence[UUID]
) -> dict[UUID, list[dict[str, Any]]]:
    if not category_ids:
        return {}
    effective_group_id = sa.func.coalesce(
        SpecialEquipmentCategoryAttribute.group_id,
        SpecialEquipmentAttribute.attribute_group_id,
    )
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategoryAttribute.category_id,
                SpecialEquipmentCategoryAttribute.attribute_id,
                SpecialEquipmentAttribute.name.label("attribute_name"),
                SpecialEquipmentAttribute.data_type,
                SpecialEquipmentAttribute.filter_kind,
                SpecialEquipmentAttribute.is_active.label("attribute_is_active"),
                effective_group_id.label("group_id"),
                sa.func.coalesce(
                    SpecialEquipmentAttributeGroup.name, "Прочие"
                ).label("group_name"),
                sa.func.coalesce(
                    SpecialEquipmentAttributeGroup.sort_order,
                    2**31 - 1,
                ).label("group_sort_order"),
                SpecialEquipmentAttributeGroup.is_active.label("group_is_active"),
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
            .outerjoin(
                SpecialEquipmentAttributeGroup,
                SpecialEquipmentAttributeGroup.id == effective_group_id,
            )
            .where(SpecialEquipmentCategoryAttribute.category_id.in_(category_ids))
            .order_by(
                SpecialEquipmentCategoryAttribute.category_id,
                SpecialEquipmentCategoryAttribute.sort_order,
                SpecialEquipmentAttribute.name,
                SpecialEquipmentCategoryAttribute.attribute_id,
            )
        )
    ).mappings()
    result: dict[UUID, list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        category_id = item.pop("category_id")
        result.setdefault(category_id, []).append(item)
    return result


def _effective_category_attribute_links_by_id(
    *,
    category_ids: Sequence[UUID],
    all_category_ids: Sequence[UUID],
    edges: Sequence[Mapping[str, Any]],
    links_by_category: Mapping[UUID, Sequence[Mapping[str, Any]]],
    attachment_root_ids: Iterable[UUID] = (),
) -> dict[UUID, list[dict[str, Any]]]:
    if not category_ids:
        return {}
    graph = CategoryGraph.from_edges(
        category_ids=all_category_ids,
        edges=(
            (edge["parent_id"], edge["child_id"])
            for edge in edges
        ),
    )
    attachment_ids = attachment_branch_ids(
        graph=graph,
        attachment_roots=tuple(attachment_root_ids),
    )
    rule_graph = rule_inheritance_graph(
        graph=graph,
        attachment_ids=attachment_ids,
    )
    rules_by_category: dict[UUID, list[CategoryAttributeRule]] = {}
    attribute_metadata: dict[UUID, dict[str, Any]] = {}
    group_metadata: dict[UUID | None, tuple[str, int]] = {
        None: ("Прочие", 2**31 - 1)
    }
    for source_category_id, category_links in links_by_category.items():
        for row in category_links:
            if not row["attribute_is_active"] or row["group_is_active"] is False:
                continue
            rules_by_category.setdefault(source_category_id, []).append(
                CategoryAttributeRule(
                    attribute_id=row["attribute_id"],
                    group_id=row["group_id"],
                    is_required=row["is_required"],
                    is_filterable=row["is_filterable"],
                    is_visible=row["is_visible"],
                    sort_order=row["sort_order"],
                )
            )
            attribute_metadata[row["attribute_id"]] = {
                "attribute_name": row["attribute_name"],
                "data_type": row["data_type"],
                "filter_kind": row["filter_kind"],
            }
            group_metadata[row["group_id"]] = (
                row["group_name"],
                row["group_sort_order"],
            )

    result: dict[UUID, list[dict[str, Any]]] = {}
    for category_id in category_ids:
        effective_rows: list[dict[str, Any]] = []
        for rule in effective_attribute_rules(
            graph=rule_graph,
            category_id=category_id,
            rules_by_category=rules_by_category,
        ):
            group_name, group_sort_order = group_metadata[rule.group_id]
            effective_rows.append(
                {
                    "attribute_id": rule.attribute_id,
                    **attribute_metadata[rule.attribute_id],
                    "group_id": rule.group_id,
                    "group_name": group_name,
                    "group_sort_order": group_sort_order,
                    "is_required": rule.is_required,
                    "is_filterable": rule.is_filterable,
                    "is_visible": rule.is_visible,
                    "sort_order": rule.sort_order,
                }
            )
        result[category_id] = sorted(
            effective_rows,
            key=lambda item: (
                item["group_sort_order"],
                item["sort_order"],
                item["attribute_name"].casefold(),
                str(item["attribute_id"]),
            ),
        )
    return result


async def _category_product_counts(
    session: AsyncSession, category_ids: Sequence[UUID]
) -> dict[UUID, int]:
    if not category_ids:
        return {}
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductCategory.category_id,
                sa.func.count().label("product_count"),
            )
            .where(SpecialEquipmentProductCategory.category_id.in_(category_ids))
            .group_by(SpecialEquipmentProductCategory.category_id)
        )
    ).all()
    return {category_id: int(count) for category_id, count in rows}


def _category_directory_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in ("id", "code", "name", "slug", "is_active")
    }


async def _category_page_resources(
    *,
    session: AsyncSession,
    category_ids: Sequence[UUID],
    categories: Mapping[UUID, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    paths: Mapping[UUID, CategoryCanonicalPath],
) -> list[dict[str, Any]]:
    parents_by_id: dict[UUID, list[UUID]] = {}
    children_by_id: dict[UUID, list[UUID]] = {}
    for edge in edges:
        parents_by_id.setdefault(edge["child_id"], []).append(edge["parent_id"])
        children_by_id.setdefault(edge["parent_id"], []).append(edge["child_id"])
    relevant_ids = set(category_ids)
    pending = list(category_ids)
    while pending:
        child_id = pending.pop()
        for parent_id in parents_by_id.get(child_id, ()):
            if parent_id in relevant_ids:
                continue
            relevant_ids.add(parent_id)
            pending.append(parent_id)
    all_attribute_links = await _category_attribute_links_by_id(
        session, tuple(relevant_ids)
    )
    effective_attribute_links = _effective_category_attribute_links_by_id(
        category_ids=category_ids,
        all_category_ids=tuple(categories),
        edges=edges,
        links_by_category=all_attribute_links,
        attachment_root_ids=[
            cid for cid, cat in categories.items() if cat.get("is_attachment_category")
        ],
    )
    product_counts = await _category_product_counts(session, category_ids)
    resources: list[dict[str, Any]] = []
    for category_id in category_ids:
        source = categories[category_id]
        parent_ids = sorted(parents_by_id.get(category_id, ()), key=str)
        child_ids = sorted(children_by_id.get(category_id, ()), key=str)
        parents = sorted(
            (_category_directory_ref(categories[parent_id]) for parent_id in parent_ids),
            key=lambda row: (row["name"].casefold(), str(row["id"])),
        )
        resource = dict(source)
        resource.update(
            canonical_path=paths[category_id].display,
            parent_ids=parent_ids,
            child_ids=child_ids,
            parents=parents,
            attribute_links=[
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"attribute_is_active", "group_is_active"}
                }
                for item in all_attribute_links.get(category_id, [])
            ],
            effective_attribute_links=effective_attribute_links.get(
                category_id, []
            ),
            product_count=product_counts.get(category_id, 0),
            image_url=(
                f"/api/v1/special-equipment/categories/{category_id}/image/content"
                if source.get("image_key")
                else None
            ),
        )
        resource.pop("image_key", None)
        resources.append(resource)
    return resources


async def _get_category_resource(
    session: AsyncSession, category_id: UUID
) -> dict[str, Any] | None:
    categories, edges, paths = await _category_management_snapshot(session)
    if category_id not in categories:
        return None
    resources = await _category_page_resources(
        session=session,
        category_ids=(category_id,),
        categories=categories,
        edges=edges,
        paths=paths,
    )
    return resources[0]


async def _list_categories(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
    search: str | None,
    category_level_ids: Sequence[UUID | None],
    sort: CategorySort | None,
) -> tuple[list[dict], int]:
    categories, edges, paths = await _category_management_snapshot(
        session,
        sort=sort,
    )
    category_ids, total = _category_page_ids(
        categories=categories,
        edges=edges,
        paths=paths,
        offset=offset,
        limit=limit,
        search=search,
        level_ids=category_level_ids,
        sort=sort,
    )
    resources = await _category_page_resources(
        session=session,
        category_ids=category_ids,
        categories=categories,
        edges=edges,
        paths=paths,
    )
    return resources, total


async def list_entities(  # noqa: PLR0912 - registry dispatcher already branches by entity type
    session: AsyncSession,
    entity_type: EntityType,
    *,
    offset: int,
    limit: int,
    search: str | None = None,
    mark_id: UUID | None = None,
    model_id: UUID | None = None,
    modification_id: UUID | None = None,
    category_id: UUID | None = None,
    sale_status: ProductSaleStatus | None = None,
    attribute_id: UUID | None = None,
    category_level_ids: Sequence[UUID | None] = (),
    sort: CategorySort | None = None,
    attribute_group_id: UUID | None = None,
    normalization_state: Literal["normalized", "legacy", "conflict"] | None = None,
    role: ProductCandidateRole | None = None,
    applicability: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[dict], int]:
    if entity_type == "category":
        return await _list_categories(
            session,
            offset=offset,
            limit=limit,
            search=search,
            category_level_ids=category_level_ids,
            sort=sort,
        )
    if entity_type == "product" and normalization_state in {"legacy", "conflict"}:
        return [], 0
    if entity_type == "color":
        return await list_colors(
            session,
            offset=offset,
            limit=limit,
            search=search,
            applicability=applicability,
            is_active=is_active,
        )
    product_category_scope: frozenset[UUID] | None = None
    if entity_type == "product" and any(
        category_id is not None for category_id in category_level_ids
    ):
        category_graph = await category_graph_snapshot(session)
        product_category_scope = category_scope_for_levels(
            category_ids=category_graph["category_ids"],
            edges=(
                CategoryPathEdge(
                    parent_id=parent_id,
                    child_id=child_id,
                    sort_order=0,
                )
                for parent_id, child_id in category_graph["edges"]
            ),
            level_ids=category_level_ids,
        )
        if not product_category_scope:
            return [], 0
    model = _MODEL_BY_TYPE[entity_type]
    query = sa.select(model.id)
    if entity_type == "product":
        query = _filter_product_candidate_query(
            query,
            mark_id=mark_id,
            model_id=model_id,
            category_id=category_id,
            category_scope_ids=product_category_scope,
            sale_status=sale_status,
            role=role,
        )
    if search:
        term = search.strip()
        if entity_type == "product":
            query = (
                query.outerjoin(
                    SpecialEquipmentModification,
                    SpecialEquipmentModification.id
                    == SpecialEquipmentProduct.modification_id,
                )
                .join(
                    SpecialEquipmentModel,
                    SpecialEquipmentModel.id
                    == sa.func.coalesce(
                        SpecialEquipmentModification.model_id,
                        SpecialEquipmentProduct.model_id,
                    ),
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
                .where(
                    sa.or_(
                        _case_insensitive_contains(
                            SpecialEquipmentProduct.code, term
                        ),
                        _case_insensitive_contains(
                            SpecialEquipmentProduct.description, term
                        ),
                        _case_insensitive_contains(
                            sa.func.coalesce(SpecialEquipmentModification.name, ""), term
                        ),
                        _case_insensitive_contains(
                            SpecialEquipmentModel.name, term
                        ),
                        _case_insensitive_contains(
                            SpecialEquipmentMark.name, term
                        ),
                        _case_insensitive_contains(
                            sa.func.coalesce(SpecialEquipmentProduct.superstructure_name, ""), term
                        ),
                        _case_insensitive_contains(
                            sa.func.coalesce(SpecialEquipmentProduct.superstructure_manufacturer, ""), term
                        ),
                        _case_insensitive_contains(
                            sa.func.coalesce(SpecialEquipmentSuperstructure.name, ""), term
                        ),
                    )
                )
            )
        elif hasattr(model, "name"):
            if hasattr(model, "code"):
                query = query.where(
                    sa.or_(
                        _case_insensitive_contains(model.name, term),
                        _case_insensitive_contains(model.code, term),
                    )
                )
            else:
                query = query.where(_case_insensitive_contains(model.name, term))
    if is_active is not None and hasattr(model, "is_active"):
        query = query.where(model.is_active.is_(is_active))
    if entity_type == "model" and mark_id is not None:
        query = query.where(SpecialEquipmentModel.mark_id == mark_id)
    if entity_type == "model" and category_id is not None:
        query = query.where(SpecialEquipmentModel.category_id == category_id)
    if entity_type == "mark" and category_id is not None:
        query = query.where(
            sa.exists(
                sa.select(sa.literal(1)).where(
                    SpecialEquipmentModel.mark_id == SpecialEquipmentMark.id,
                    SpecialEquipmentModel.category_id == category_id,
                )
            )
        )
    if entity_type == "modification" and model_id is not None:
        query = query.where(SpecialEquipmentModification.model_id == model_id)
    if entity_type == "trim" and modification_id is not None:
        query = query.where(SpecialEquipmentTrim.modification_id == modification_id)
    if entity_type == "trim" and model_id is not None:
        query = query.join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentTrim.modification_id,
        ).where(SpecialEquipmentModification.model_id == model_id)
    if entity_type == "trim" and category_id is not None:
        query = query.where(
            sa.exists(
                sa.select(sa.literal(1)).where(
                    SpecialEquipmentModificationCategory.modification_id
                    == SpecialEquipmentTrim.modification_id,
                    SpecialEquipmentModificationCategory.category_id == category_id,
                )
            )
        )
    if entity_type == "attribute_option" and attribute_id is not None:
        query = query.where(
            SpecialEquipmentAttributeOption.attribute_id == attribute_id
        )
    if entity_type == "attribute" and attribute_group_id is not None:
        query = query.where(
            SpecialEquipmentAttribute.attribute_group_id == attribute_group_id
        )
    total = int(
        (
            await session.execute(
                sa.select(sa.func.count()).select_from(query.subquery())
            )
        ).scalar_one()
    )
    ordering = (
        model.name if hasattr(model, "name") else model.id,
        model.id,
    )
    ids = (
        await session.execute(
            query.order_by(*ordering).offset(offset).limit(limit)
        )
    ).scalars()
    rows: list[dict] = []
    for entity_id in ids:
        row = await get_entity(session, entity_type, entity_id)
        if row is not None:
            rows.append(row)
    return rows, total


async def list_trim_lifecycle_items(
    session: AsyncSession,
    *,
    modification_id: UUID,
) -> list[dict[str, Any]]:
    """Return the compact, deterministic trim selector for one modification."""

    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentTrim.id,
                SpecialEquipmentTrim.modification_id,
                SpecialEquipmentTrim.name,
                SpecialEquipmentTrim.is_active,
            )
            .where(SpecialEquipmentTrim.modification_id == modification_id)
            .order_by(SpecialEquipmentTrim.name.asc(), SpecialEquipmentTrim.id.asc())
        )
    ).mappings()
    return [dict(row) for row in rows]


async def catalog_section_counts(session: AsyncSession) -> dict[str, int]:
    """Return unfiltered totals for every management registry in one query."""

    columns = [
        sa.select(sa.func.count(model.id))
        .select_from(model)
        .scalar_subquery()
        .label(section)
        for section, model in _CATALOG_SECTION_MODELS.items()
    ]
    row = (await session.execute(sa.select(*columns))).mappings().one()
    return {section: int(row[section]) for section in _CATALOG_SECTION_MODELS}


async def category_graph_snapshot(session: AsyncSession) -> dict[str, list]:
    category_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategory.id,
                SpecialEquipmentCategory.is_attachment_category,
            )
        )
    ).all()
    category_ids = [row.id for row in category_rows]
    attachment_root_ids = [
        row.id for row in category_rows if row.is_attachment_category
    ]
    edges = [
        (row.parent_id, row.child_id)
        for row in (
            await session.execute(
                sa.select(
                    SpecialEquipmentCategoryRelation.parent_id,
                    SpecialEquipmentCategoryRelation.child_id,
                )
            )
        )
    ]
    return {
        "category_ids": category_ids,
        "edges": edges,
        "attachment_root_ids": attachment_root_ids,
    }


async def replace_category_parents(
    session: AsyncSession,
    *,
    category_id: UUID,
    parent_ids: Sequence[UUID],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentCategoryRelation).where(
            SpecialEquipmentCategoryRelation.child_id == category_id
        )
    )
    session.add_all(
        [
            SpecialEquipmentCategoryRelation(
                parent_id=parent_id,
                child_id=category_id,
                sort_order=index,
            )
            for index, parent_id in enumerate(parent_ids)
        ]
    )
    await session.flush()


async def replace_modification_categories(
    session: AsyncSession,
    *,
    modification_id: UUID,
    category_ids: Sequence[UUID],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentModificationCategory).where(
            SpecialEquipmentModificationCategory.modification_id
            == modification_id
        )
    )
    session.add_all(
        [
            SpecialEquipmentModificationCategory(
                modification_id=modification_id,
                category_id=category_id,
                sort_order=index,
                is_primary=index == 0,
            )
            for index, category_id in enumerate(category_ids)
        ]
    )
    await session.flush()


async def replace_attribute_group_members(
    session: AsyncSession,
    *,
    group_id: UUID,
    attribute_ids: Sequence[UUID],
) -> None:
    """Atomically replace the attributes using this group by default."""

    await session.execute(
        sa.update(SpecialEquipmentAttribute)
        .where(SpecialEquipmentAttribute.attribute_group_id == group_id)
        .values(attribute_group_id=None)
    )
    if attribute_ids:
        await session.execute(
            sa.update(SpecialEquipmentAttribute)
            .where(SpecialEquipmentAttribute.id.in_(attribute_ids))
            .values(attribute_group_id=group_id)
        )
    await session.flush()


async def replace_modification_values(
    session: AsyncSession,
    *,
    modification_id: UUID,
    values: Sequence[Mapping[str, Any]],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentModificationAttributeValue).where(
            SpecialEquipmentModificationAttributeValue.modification_id
            == modification_id
        )
    )
    session.add_all(
        [
            SpecialEquipmentModificationAttributeValue(
                modification_id=modification_id, **dict(value)
            )
            for value in values
        ]
    )
    await session.flush()


async def replace_category_attributes(
    session: AsyncSession,
    *,
    category_id: UUID,
    links: Sequence[Mapping[str, Any]],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentCategoryAttribute).where(
            SpecialEquipmentCategoryAttribute.category_id == category_id
        )
    )
    session.add_all(
        [
            SpecialEquipmentCategoryAttribute(
                category_id=category_id, **dict(link)
            )
            for link in links
        ]
    )
    await session.flush()


async def replace_trim_attributes(
    session: AsyncSession,
    *,
    trim_id: UUID,
    links: Sequence[Mapping[str, Any]],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentTrimAttribute).where(
            SpecialEquipmentTrimAttribute.trim_id == trim_id
        )
    )
    session.add_all(
        [SpecialEquipmentTrimAttribute(trim_id=trim_id, **dict(link)) for link in links]
    )
    await session.flush()


async def replace_trim_values(
    session: AsyncSession,
    *,
    trim_id: UUID,
    values: Sequence[Mapping[str, Any]],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentTrimAttributeValue).where(
            SpecialEquipmentTrimAttributeValue.trim_id == trim_id
        )
    )
    session.add_all(
        [
            SpecialEquipmentTrimAttributeValue(trim_id=trim_id, **dict(value))
            for value in values
        ]
    )
    await session.flush()


async def lock_trim_state(
    session: AsyncSession, trim_id: UUID
) -> dict[str, Any] | None:
    """Lock a trim state in the shared modification -> trim order."""

    modification_id = (
        await session.execute(
            sa.select(SpecialEquipmentTrim.modification_id).where(
                SpecialEquipmentTrim.id == trim_id
            )
        )
    ).scalar_one_or_none()
    if modification_id is None:
        return None
    await session.execute(
        sa.select(SpecialEquipmentModification.id)
        .where(SpecialEquipmentModification.id == modification_id)
        .with_for_update()
    )
    await session.execute(
        sa.select(SpecialEquipmentTrim.id)
        .where(SpecialEquipmentTrim.id == trim_id)
        .with_for_update()
    )
    return await get_entity(session, "trim", trim_id)


async def lock_modification_trim_states(
    session: AsyncSession, modification_id: UUID
) -> None:
    """Lock one modification and all its trims in deterministic order."""

    await session.execute(
        sa.select(SpecialEquipmentModification.id)
        .where(SpecialEquipmentModification.id == modification_id)
        .with_for_update()
    )
    await session.execute(
        sa.select(SpecialEquipmentTrim.id)
        .where(SpecialEquipmentTrim.modification_id == modification_id)
        .order_by(SpecialEquipmentTrim.id)
        .with_for_update()
    )


async def trim_attribute_state(
    session: AsyncSession, trim_id: UUID
) -> list[dict[str, Any]]:
    """Return the canonical full assignment/value state for ETag calculation."""

    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentTrimAttribute.attribute_id,
                SpecialEquipmentTrimAttribute.group_id,
                SpecialEquipmentTrimAttribute.is_required,
                SpecialEquipmentTrimAttribute.is_filterable,
                SpecialEquipmentTrimAttribute.sort_order,
                SpecialEquipmentTrimAttributeValue.value_number,
                SpecialEquipmentTrimAttributeValue.value_text,
                SpecialEquipmentTrimAttributeValue.value_boolean,
                SpecialEquipmentTrimAttributeValue.option_id,
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
            .where(SpecialEquipmentTrimAttribute.trim_id == trim_id)
            .order_by(SpecialEquipmentTrimAttribute.attribute_id)
        )
    ).mappings()
    return [dict(row) for row in rows]


async def add_trim_attribute(
    session: AsyncSession,
    *,
    trim_id: UUID,
    link: Mapping[str, Any],
) -> None:
    session.add(SpecialEquipmentTrimAttribute(trim_id=trim_id, **dict(link)))
    await session.flush()


async def delete_trim_attribute(
    session: AsyncSession,
    *,
    trim_id: UUID,
    attribute_id: UUID,
) -> bool:
    await session.execute(
        sa.delete(SpecialEquipmentTrimAttributeValue).where(
            SpecialEquipmentTrimAttributeValue.trim_id == trim_id,
            SpecialEquipmentTrimAttributeValue.attribute_id == attribute_id,
        )
    )
    result = await session.execute(
        sa.delete(SpecialEquipmentTrimAttribute).where(
            SpecialEquipmentTrimAttribute.trim_id == trim_id,
            SpecialEquipmentTrimAttribute.attribute_id == attribute_id,
        )
    )
    await session.flush()
    return bool(getattr(result, "rowcount", 0))


async def upsert_trim_attribute_values(
    session: AsyncSession,
    *,
    trim_id: UUID,
    values: Sequence[Mapping[str, Any]],
    delete_attribute_ids: Sequence[UUID],
) -> None:
    attribute_ids = [item["attribute_id"] for item in values]
    targets = tuple({*attribute_ids, *delete_attribute_ids})
    if targets:
        await session.execute(
            sa.delete(SpecialEquipmentTrimAttributeValue).where(
                SpecialEquipmentTrimAttributeValue.trim_id == trim_id,
                SpecialEquipmentTrimAttributeValue.attribute_id.in_(targets),
            )
        )
    session.add_all(
        [
            SpecialEquipmentTrimAttributeValue(trim_id=trim_id, **dict(value))
            for value in values
        ]
    )
    await session.flush()


async def modification_attribute_values(
    session: AsyncSession, modification_id: UUID
) -> dict[UUID, dict[str, Any]]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentModificationAttributeValue.value_number,
                SpecialEquipmentModificationAttributeValue.value_text,
                SpecialEquipmentModificationAttributeValue.value_boolean,
                SpecialEquipmentModificationAttributeValue.option_id,
            ).where(
                SpecialEquipmentModificationAttributeValue.modification_id
                == modification_id
            )
        )
    ).mappings()
    return {row["attribute_id"]: dict(row) for row in rows}


async def trim_value_attributes_for_modification(
    session: AsyncSession, modification_id: UUID
) -> list[AttributeIdRow]:
    attribute_ids = (
        await session.execute(
            sa.select(SpecialEquipmentTrimAttributeValue.attribute_id)
            .join(
                SpecialEquipmentTrim,
                SpecialEquipmentTrim.id == SpecialEquipmentTrimAttributeValue.trim_id,
            )
            .where(SpecialEquipmentTrim.modification_id == modification_id)
            .distinct()
            .order_by(SpecialEquipmentTrimAttributeValue.attribute_id)
        )
    ).scalars()
    return [AttributeIdRow(attribute_id=attribute_id) for attribute_id in attribute_ids]


async def trim_attributes(
    session: AsyncSession, trim_id: UUID
) -> list[AttributeIdRow]:
    attribute_ids = (
        await session.execute(
            sa.select(SpecialEquipmentTrimAttribute.attribute_id)
            .where(SpecialEquipmentTrimAttribute.trim_id == trim_id)
            .order_by(SpecialEquipmentTrimAttribute.attribute_id)
        )
    ).scalars()
    return [AttributeIdRow(attribute_id=attribute_id) for attribute_id in attribute_ids]


async def get_trim_modification_link(
    session: AsyncSession,
    *,
    trim_id: UUID,
    modification_id: UUID,
    require_active: bool = True,
) -> TrimModificationLinkRow | None:
    filters = [
        SpecialEquipmentTrim.id == trim_id,
        SpecialEquipmentTrim.modification_id == modification_id,
    ]
    if require_active:
        filters.append(SpecialEquipmentTrim.is_active.is_(True))
    row = (
        await session.execute(
            sa.select(
                SpecialEquipmentTrim.id.label("trim_id"),
                SpecialEquipmentTrim.modification_id,
                SpecialEquipmentTrim.is_active,
            ).where(*filters)
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    return TrimModificationLinkRow(
        trim_id=row["trim_id"],
        modification_id=row["modification_id"],
        is_active=bool(row["is_active"]),
    )


async def replace_product_categories(
    session: AsyncSession,
    *,
    product_id: UUID,
    category_ids: Sequence[UUID],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentProductCategory).where(
            SpecialEquipmentProductCategory.product_id == product_id
        )
    )
    session.add_all(
        [
            SpecialEquipmentProductCategory(
                product_id=product_id, category_id=category_id
            )
            for category_id in category_ids
        ]
    )
    await session.flush()


async def replace_product_chassis_values(
    session: AsyncSession,
    *,
    product_id: UUID,
    values: Sequence[Mapping[str, Any]],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentProductChassisValue).where(
            SpecialEquipmentProductChassisValue.product_id == product_id
        )
    )
    if values:
        session.add_all(
            [
                SpecialEquipmentProductChassisValue(product_id=product_id, **dict(value))
                for value in values
            ]
        )
    await session.flush()


async def list_product_chassis_values(
    session: AsyncSession, product_id: UUID
) -> list[dict]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductChassisValue.attribute_id,
                SpecialEquipmentProductChassisValue.option_id,
                SpecialEquipmentProductChassisValue.value_number,
                SpecialEquipmentProductChassisValue.value_text,
                SpecialEquipmentProductChassisValue.value_boolean,
                SpecialEquipmentAttribute.name.label("attribute_name"),
                SpecialEquipmentAttribute.data_type,
                SpecialEquipmentUnit.name.label("unit"),
                SpecialEquipmentAttributeOption.name.label("option_name"),
            )
            .join(
                SpecialEquipmentAttribute,
                SpecialEquipmentAttribute.id
                == SpecialEquipmentProductChassisValue.attribute_id,
            )
            .outerjoin(
                SpecialEquipmentUnit,
                SpecialEquipmentUnit.id == SpecialEquipmentAttribute.unit_id,
            )
            .outerjoin(
                SpecialEquipmentAttributeOption,
                SpecialEquipmentAttributeOption.id
                == SpecialEquipmentProductChassisValue.option_id,
            )
            .where(
                SpecialEquipmentProductChassisValue.product_id == product_id
            )
            .order_by(
                SpecialEquipmentAttribute.name,
                SpecialEquipmentProductChassisValue.attribute_id,
            )
        )
    ).mappings()
    result: list[dict] = []
    for row in rows:
        value = (
            row["option_name"]
            if row["option_id"] is not None
            else row["value_number"]
            if row["value_number"] is not None
            else row["value_text"]
            if row["value_text"] is not None
            else row["value_boolean"]
        )
        display_value = format_attribute_display_value(value, row["unit"])
        if display_value is None:
            continue
        result.append(
            {
                "attribute_id": row["attribute_id"],
                "option_id": row["option_id"],
                "attribute_name": row["attribute_name"],
                "data_type": row["data_type"],
                "value": value,
                "display_value": display_value,
                "value_number": row["value_number"],
                "value_text": row["value_text"],
                "value_boolean": row["value_boolean"],
            }
        )
    return result


async def replace_product_superstructure_values(
    session: AsyncSession,
    *,
    product_id: UUID,
    superstructure_id: UUID,
    values: Sequence[Mapping[str, Any]],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentProductSuperstructureValue).where(
            SpecialEquipmentProductSuperstructureValue.product_id == product_id
        )
    )
    if values:
        session.add_all(
            [
                SpecialEquipmentProductSuperstructureValue(
                    product_id=product_id,
                    superstructure_id=superstructure_id,
                    **dict(value),
                )
                for value in values
            ]
        )
    await session.flush()


async def list_product_superstructure_values(
    session: AsyncSession, product_id: UUID
) -> list[dict]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductSuperstructureValue.attribute_id,
                SpecialEquipmentProductSuperstructureValue.option_id,
                SpecialEquipmentProductSuperstructureValue.value_number,
                SpecialEquipmentProductSuperstructureValue.value_text,
                SpecialEquipmentProductSuperstructureValue.value_boolean,
                SpecialEquipmentAttribute.name.label("attribute_name"),
                SpecialEquipmentAttribute.data_type,
                SpecialEquipmentUnit.name.label("unit"),
                SpecialEquipmentAttributeOption.name.label("option_name"),
            )
            .join(
                SpecialEquipmentAttribute,
                SpecialEquipmentAttribute.id
                == SpecialEquipmentProductSuperstructureValue.attribute_id,
            )
            .outerjoin(
                SpecialEquipmentUnit,
                SpecialEquipmentUnit.id == SpecialEquipmentAttribute.unit_id,
            )
            .outerjoin(
                SpecialEquipmentAttributeOption,
                SpecialEquipmentAttributeOption.id
                == SpecialEquipmentProductSuperstructureValue.option_id,
            )
            .where(
                SpecialEquipmentProductSuperstructureValue.product_id == product_id
            )
            .order_by(
                SpecialEquipmentAttribute.name,
                SpecialEquipmentProductSuperstructureValue.attribute_id,
            )
        )
    ).mappings()
    result: list[dict] = []
    for row in rows:
        value = (
            row["option_name"]
            if row["option_id"] is not None
            else row["value_number"]
            if row["value_number"] is not None
            else row["value_text"]
            if row["value_text"] is not None
            else row["value_boolean"]
        )
        display_value = format_attribute_display_value(value, row["unit"])
        if display_value is None:
            continue
        result.append(
            {
                "attribute_id": row["attribute_id"],
                "option_id": row["option_id"],
                "attribute_name": row["attribute_name"],
                "data_type": row["data_type"],
                "value": value,
                "display_value": display_value,
                "value_number": row["value_number"],
                "value_text": row["value_text"],
                "value_boolean": row["value_boolean"],
            }
        )
    return result


async def list_attachment_sources(
    session: AsyncSession,
    *,
    model_id: UUID,
    modification_id: UUID | None = None,
    exclude_product_id: UUID | None = None,
    search: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    attachment_categories = _attachment_category_cte()
    stmt = (
        sa.select(
            SpecialEquipmentProduct.id,
            SpecialEquipmentProduct.code,
            SpecialEquipmentProduct.publication_status,
            SpecialEquipmentProduct.modification_id,
            SpecialEquipmentModification.name.label("modification_name"),
            SpecialEquipmentModification.code.label("modification_code"),
            SpecialEquipmentModel.id.label("model_id"),
            SpecialEquipmentModel.name.label("model_name"),
            SpecialEquipmentModel.code.label("model_code"),
            SpecialEquipmentMark.id.label("mark_id"),
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentMark.code.label("mark_code"),
        )
        .join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id == SpecialEquipmentModification.model_id,
        )
        .join(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(
            SpecialEquipmentProduct.superstructure_id.is_(None),
            SpecialEquipmentProduct.publication_status.in_(["draft", "published"]),
            _product_is_attachment(attachment_categories),
            SpecialEquipmentModel.id == model_id,
        )
        .order_by(
            SpecialEquipmentProduct.updated_at.desc(),
            SpecialEquipmentProduct.id.desc(),
        )
        .limit(limit)
    )
    if modification_id is not None:
        stmt = stmt.where(SpecialEquipmentModification.id == modification_id)
    if exclude_product_id is not None:
        stmt = stmt.where(SpecialEquipmentProduct.id != exclude_product_id)
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            sa.or_(
                SpecialEquipmentProduct.code.ilike(term),
                SpecialEquipmentModification.name.ilike(term),
                SpecialEquipmentModel.name.ilike(term),
                SpecialEquipmentMark.name.ilike(term),
            )
        )
    rows = (await session.execute(stmt)).mappings().all()
    if not rows:
        return []

    items: list[dict[str, Any]] = []
    for r in rows:
        mod_id = r["modification_id"]
        mod_values = await _modification_values(session, mod_id)
        values_by_attr = {
            str(v["attribute_id"]): {
                "attribute_id": v["attribute_id"],
                "option_id": v.get("option_id"),
                "value_number": str(v["value_number"]) if v.get("value_number") is not None else None,
                "value_text": v.get("value_text"),
                "value_boolean": v.get("value_boolean"),
                "value": v.get("value"),
            }
            for v in mod_values
        }

        superstructure_name = r["model_name"]
        superstructure_manufacturer = r["mark_name"]
        items.append(
            {
                "id": r["id"],
                "code": r["code"],
                "name": f"{r['mark_name']} {r['model_name']} {r['modification_name']}".strip(),
                "publication_status": r["publication_status"],
                "mark": {"id": r["mark_id"], "name": r["mark_name"], "code": r["mark_code"]},
                "model": {"id": r["model_id"], "name": r["model_name"], "code": r["model_code"]},
                "modification": {"id": mod_id, "name": r["modification_name"], "code": r["modification_code"]},
                "superstructure_name": superstructure_name,
                "superstructure_manufacturer": superstructure_manufacturer,
                "superstructure_values_by_attribute": values_by_attr,
            }
        )
    return items


async def get_product_offering_states(
    session: AsyncSession,
    product_ids: Sequence[UUID] | None = None,
) -> dict[UUID, dict[str, Any]]:
    """Load classification and composition inputs without leaking ORM rows."""

    unique_ids = tuple(dict.fromkeys(product_ids or ()))
    if product_ids is not None and not unique_ids:
        return {}
    attachment_categories = _attachment_category_cte()
    product_query = sa.select(
        SpecialEquipmentProduct.id,
        SpecialEquipmentProduct.modification_id,
        SpecialEquipmentProduct.superstructure_id,
        SpecialEquipmentProduct.manufacture_year,
        SpecialEquipmentProduct.condition,
        SpecialEquipmentProduct.owners_count,
        SpecialEquipmentProduct.mileage_km,
        SpecialEquipmentProduct.engine_hours,
        _product_is_attachment(attachment_categories).label("is_attachment"),
    )
    if product_ids is not None:
        product_query = product_query.where(
            SpecialEquipmentProduct.id.in_(unique_ids)
        )
    products = [
        dict(row) for row in (await session.execute(product_query)).mappings()
    ]
    if not products:
        return {}
    loaded_product_ids = tuple(row["id"] for row in products)
    modification_ids = tuple(
        dict.fromkeys(
            row["modification_id"]
            for row in products
            if row["modification_id"] is not None
        )
    )
    direct_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductCategory.product_id,
                SpecialEquipmentProductCategory.category_id,
                SpecialEquipmentCategory.usage_metric,
            )
            .join(
                SpecialEquipmentCategory,
                SpecialEquipmentProductCategory.category_id
                == SpecialEquipmentCategory.id,
            )
            .where(
                SpecialEquipmentProductCategory.product_id.in_(loaded_product_ids)
            )
        )
    ).all()
    modification_rows = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentModificationCategory.modification_id,
                    SpecialEquipmentModificationCategory.category_id,
                ).where(
                    SpecialEquipmentModificationCategory.modification_id.in_(
                        modification_ids
                    )
                )
            )
        ).all()
        if modification_ids
        else []
    )
    direct_by_product: dict[UUID, list[UUID]] = {}
    metric_by_product: dict[UUID, str] = {}
    for product_id, category_id, metric in direct_rows:
        direct_by_product.setdefault(product_id, []).append(category_id)
        if product_id not in metric_by_product:
            metric_by_product[product_id] = metric
    by_modification: dict[UUID, list[UUID]] = {}
    for modification_id, category_id in modification_rows:
        by_modification.setdefault(modification_id, []).append(category_id)
    result: dict[UUID, dict[str, Any]] = {}
    for product in products:
        direct_category_ids = direct_by_product.get(product["id"], [])
        modification_category_ids = by_modification.get(
            product["modification_id"], []
        )
        result[product["id"]] = {
            **product,
            "direct_category_ids": direct_category_ids,
            "category_ids": list(
                dict.fromkeys(direct_category_ids + modification_category_ids)
            ),
            "is_composite": False,
            "usage_metric": metric_by_product.get(product["id"]),
        }
    return result


async def list_modification_category_sets(
    session: AsyncSession,
) -> dict[UUID, list[UUID]]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationCategory.modification_id,
                SpecialEquipmentModificationCategory.category_id,
            ).order_by(
                SpecialEquipmentModificationCategory.modification_id,
                SpecialEquipmentModificationCategory.sort_order,
                SpecialEquipmentModificationCategory.category_id,
            )
        )
    ).all()
    result: dict[UUID, list[UUID]] = {}
    for modification_id, category_id in rows:
        result.setdefault(modification_id, []).append(category_id)
    return result


async def list_all_product_attachment_links(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductAttachment.product_id,
                SpecialEquipmentProductAttachment.attachment_product_id,
                SpecialEquipmentProductAttachment.position,
            )
        )
    ).mappings()
    return [dict(row) for row in rows]


async def product_ids_for_modification(
    session: AsyncSession, modification_id: UUID
) -> set[UUID]:
    return set(
        (
            await session.execute(
                sa.select(SpecialEquipmentProduct.id).where(
                    SpecialEquipmentProduct.modification_id == modification_id
                )
            )
        ).scalars()
    )


async def offering_neighborhood(
    session: AsyncSession, product_ids: Sequence[UUID]
) -> dict[str, Any]:
    """Load complete one-hop offering aggregates around changed products."""

    seeds = set(product_ids)
    if not seeds:
        return {"product_ids": set(), "attachments": []}
    touching_attachments = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductAttachment.product_id,
                SpecialEquipmentProductAttachment.attachment_product_id,
                SpecialEquipmentProductAttachment.position,
            ).where(
                sa.or_(
                    SpecialEquipmentProductAttachment.product_id.in_(seeds),
                    SpecialEquipmentProductAttachment.attachment_product_id.in_(seeds),
                )
            )
        )
    ).mappings().all()
    attachment_owner_ids = {
        row["product_id"] for row in touching_attachments
    } | seeds
    attachments = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductAttachment.product_id,
                SpecialEquipmentProductAttachment.attachment_product_id,
                SpecialEquipmentProductAttachment.position,
            ).where(
                SpecialEquipmentProductAttachment.product_id.in_(attachment_owner_ids)
            )
        )
    ).mappings().all()
    neighborhood_ids = set(seeds)
    for row in attachments:
        neighborhood_ids.update(
            (row["product_id"], row["attachment_product_id"])
        )
    return {
        "product_ids": neighborhood_ids,
        "attachments": [dict(row) for row in attachments],
    }


async def _product_resources_by_ids(
    session: AsyncSession, product_ids: Sequence[UUID]
) -> dict[UUID, dict[str, Any]]:
    """Load relation-card products with a query count independent of page size."""

    unique_ids = tuple(dict.fromkeys(product_ids))
    if not unique_ids:
        return {}
    attachment_categories = _attachment_category_cte()
    product_rows = (
        await session.execute(
            sa.select(
                *SpecialEquipmentProduct.__table__.c,
                _product_is_attachment(attachment_categories).label("is_attachment"),
                _product_is_composite().label("is_composite"),
            ).where(SpecialEquipmentProduct.id.in_(unique_ids))
        )
    ).mappings().all()
    modification_ids = tuple(
        {row["modification_id"] for row in product_rows}
    )
    modification_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentModification.id,
                SpecialEquipmentModification.name,
                SpecialEquipmentModification.model_id,
                SpecialEquipmentModification.year_from,
                SpecialEquipmentModification.year_to,
                SpecialEquipmentModel.name.label("model_name"),
                SpecialEquipmentModel.mark_id,
                SpecialEquipmentMark.name.label("mark_name"),
            )
            .join(
                SpecialEquipmentModel,
                SpecialEquipmentModel.id == SpecialEquipmentModification.model_id,
            )
            .join(
                SpecialEquipmentMark,
                SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
            )
            .where(SpecialEquipmentModification.id.in_(modification_ids))
        )
    ).mappings()
    modifications = {row["id"]: dict(row) for row in modification_rows}
    company_ids = tuple(
        {
            row["seller_company_id"]
            for row in product_rows
            if row["seller_company_id"] is not None
        }
    )
    companies: dict[UUID, str] = {}
    if company_ids:
        company_rows = (
            await session.execute(
                sa.select(Company.id, Company.name).where(
                    Company.id.in_(company_ids)
                )
            )
        ).mappings()
        companies = {row["id"]: row["name"] for row in company_rows}
    color_ids = tuple(
        {
            color_id
            for row in product_rows
            for color_id in (
                row.get("body_color_id"),
                row.get("interior_color_id"),
            )
            if color_id is not None
        }
    )
    colors: dict[UUID, dict[str, Any]] = {}
    if color_ids:
        color_rows = (
            await session.execute(
                sa.select(
                    SpecialEquipmentColor.id,
                    SpecialEquipmentColor.code,
                    SpecialEquipmentColor.name,
                    SpecialEquipmentColor.is_active,
                ).where(SpecialEquipmentColor.id.in_(color_ids))
            )
        ).mappings()
        colors = {row["id"]: dict(row) for row in color_rows}
    category_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductCategory.product_id,
                SpecialEquipmentCategory.id,
                SpecialEquipmentCategory.code,
                SpecialEquipmentCategory.name,
                SpecialEquipmentCategory.slug,
                SpecialEquipmentCategory.is_active,
            )
            .join(
                SpecialEquipmentCategory,
                SpecialEquipmentCategory.id
                == SpecialEquipmentProductCategory.category_id,
            )
            .where(SpecialEquipmentProductCategory.product_id.in_(unique_ids))
            .order_by(
                SpecialEquipmentProductCategory.product_id,
                SpecialEquipmentCategory.name,
                SpecialEquipmentCategory.id,
            )
        )
    ).mappings()
    categories: dict[UUID, list[dict[str, Any]]] = {}
    for source in category_rows:
        item = dict(source)
        product_id = item.pop("product_id")
        categories.setdefault(product_id, []).append(item)
    image_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductImage.product_id,
                SpecialEquipmentProductImage.id,
                SpecialEquipmentProductImage.alt_text,
                SpecialEquipmentProductImage.sort_order,
                SpecialEquipmentProductImage.is_primary,
            )
            .where(SpecialEquipmentProductImage.product_id.in_(unique_ids))
            .order_by(
                SpecialEquipmentProductImage.product_id,
                SpecialEquipmentProductImage.sort_order,
                SpecialEquipmentProductImage.id,
            )
        )
    ).mappings()
    images: dict[UUID, list[dict[str, Any]]] = {}
    for source in image_rows:
        item = dict(source)
        product_id = item.pop("product_id")
        item["content_url"] = (
            f"/api/v1/admin/special-equipment/images/{item['id']}/content"
        )
        images.setdefault(product_id, []).append(item)

    resources: dict[UUID, dict[str, Any]] = {}
    for source in product_rows:
        row = dict(source)
        product_id = row["id"]
        modification = modifications.get(row["modification_id"], {})
        product_categories = categories.get(product_id, [])
        body_color_id = row.get("body_color_id")
        interior_color_id = row.get("interior_color_id")
        row.update(
            modification_name=str(modification.get("name") or ""),
            model_name=str(modification.get("model_name") or ""),
            mark_name=str(modification.get("mark_name") or ""),
            modification=modification,
            seller_company_name=companies.get(row["seller_company_id"]),
            body_color=(
                colors.get(body_color_id) if body_color_id is not None else None
            ),
            interior_color=(
                colors.get(interior_color_id)
                if interior_color_id is not None
                else None
            ),
            category_ids=[item["id"] for item in product_categories],
            categories=product_categories,
            images=images.get(product_id, []),
            price=f"{row['price']:.2f}" if row["price"] is not None else None,
            special_price=(
                f"{row['special_price']:.2f}"
                if row.get("special_price") is not None
                else None
            ),
            price_from=(
                f"{row['price_from']:.2f}"
                if row.get("price_from") is not None
                else None
            ),
            normalization_state="normalized",
            is_attachment=bool(row["is_attachment"]),
            is_composite=bool(row["is_composite"]),
        )
        resources[product_id] = row
    return resources


async def list_product_attachments(
    session: AsyncSession,
    *,
    product_id: UUID,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    total = int(
        (
            await session.execute(
                sa.select(sa.func.count()).where(
                    SpecialEquipmentProductAttachment.product_id == product_id
                )
            )
        ).scalar_one()
    )
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductAttachment.attachment_product_id,
                SpecialEquipmentProductAttachment.position,
            )
            .where(SpecialEquipmentProductAttachment.product_id == product_id)
            .order_by(
                SpecialEquipmentProductAttachment.position,
                SpecialEquipmentProductAttachment.attachment_product_id,
            )
            .offset(offset)
            .limit(limit)
        )
    ).mappings().all()
    products = await _product_resources_by_ids(
        session, [row["attachment_product_id"] for row in rows]
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        product = products.get(row["attachment_product_id"])
        if product is not None:
            items.append(
                {
                    "attachment_product_id": row["attachment_product_id"],
                    "position": row["position"],
                    "product": product,
                }
            )
    return items, total



async def get_product_attachment_links(
    session: AsyncSession, product_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductAttachment.attachment_product_id,
                SpecialEquipmentProductAttachment.position,
            )
            .where(SpecialEquipmentProductAttachment.product_id == product_id)
            .order_by(
                SpecialEquipmentProductAttachment.position,
                SpecialEquipmentProductAttachment.attachment_product_id,
            )
        )
    ).mappings()
    return [dict(row) for row in rows]



async def replace_product_attachments(
    session: AsyncSession,
    *,
    product_id: UUID,
    links: Sequence[Mapping[str, Any]],
    actor_id: UUID,
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentProductAttachment).where(
            SpecialEquipmentProductAttachment.product_id == product_id
        )
    )
    session.add_all(
        SpecialEquipmentProductAttachment(
            product_id=product_id,
            attachment_product_id=link["attachment_product_id"],
            position=link["position"],
            created_by=actor_id,
        )
        for link in links
    )
    await session.flush()


async def has_product_compatibility_links(
    session: AsyncSession,
    product_id: UUID,
) -> bool:
    return bool(
        (
            await session.execute(
                sa.select(sa.literal(True))
                .where(
                    sa.or_(
                        SpecialEquipmentProductAttachment.product_id == product_id,
                        SpecialEquipmentProductAttachment.attachment_product_id
                        == product_id,
                    )
                )
                .limit(1)
            )
        ).scalar_one_or_none()
    )


async def get_modification_chain(
    session: AsyncSession, modification_id: UUID
) -> dict | None:
    row = (
        await session.execute(
            sa.select(
                SpecialEquipmentModification.id,
                SpecialEquipmentModification.is_active.label(
                    "modification_active"
                ),
                SpecialEquipmentModification.year_from,
                SpecialEquipmentModification.year_to,
                SpecialEquipmentModel.id.label("model_id"),
                SpecialEquipmentModel.is_active.label("model_active"),
                SpecialEquipmentMark.id.label("mark_id"),
                SpecialEquipmentMark.is_active.label("mark_active"),
            )
            .join(
                SpecialEquipmentModel,
                SpecialEquipmentModel.id == SpecialEquipmentModification.model_id,
            )
            .join(
                SpecialEquipmentMark,
                SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
            )
            .where(SpecialEquipmentModification.id == modification_id)
        )
    ).mappings().one_or_none()
    return dict(row) if row else None


async def get_category_metrics(
    session: AsyncSession, category_ids: Sequence[UUID]
) -> dict[UUID, Literal["mileage_km", "engine_hours"]]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategory.id,
                SpecialEquipmentCategory.usage_metric,
            ).where(SpecialEquipmentCategory.id.in_(category_ids))
        )
    ).all()
    return {
        row.id: (
            "mileage_km"
            if row.usage_metric == "mileage_km"
            else "engine_hours"
        )
        for row in rows
    }


async def get_active_category_ids(
    session: AsyncSession, category_ids: Sequence[UUID]
) -> set[UUID]:
    return set(
        (
            await session.execute(
                sa.select(SpecialEquipmentCategory.id).where(
                    SpecialEquipmentCategory.id.in_(category_ids),
                    SpecialEquipmentCategory.is_active.is_(True),
                )
            )
        ).scalars()
    )


async def published_product_ids_for_entity(
    session: AsyncSession,
    entity_type: EntityType,
    entity_id: UUID,
) -> list[UUID]:
    """Return published products whose validity can depend on one entity."""

    query: sa.Select[tuple[UUID]]
    if entity_type == "category":
        descendants = (
            sa.select(sa.literal(entity_id, type_=sa.Uuid).label("category_id"))
            .cte("affected_categories", recursive=True)
        )
        descendants = descendants.union(
            sa.select(SpecialEquipmentCategoryRelation.child_id).where(
                SpecialEquipmentCategoryRelation.parent_id
                == descendants.c.category_id
            )
        )
        query = (
            sa.select(SpecialEquipmentProductCategory.product_id)
            .join(
                SpecialEquipmentProduct,
                SpecialEquipmentProduct.id
                == SpecialEquipmentProductCategory.product_id,
            )
            .where(
                SpecialEquipmentProduct.publication_status == "published",
                SpecialEquipmentProductCategory.category_id.in_(
                    sa.select(descendants.c.category_id)
                ),
            )
        )
    elif entity_type == "mark":
        query = (
            sa.select(SpecialEquipmentProduct.id)
            .outerjoin(
                SpecialEquipmentModification,
                SpecialEquipmentModification.id
                == SpecialEquipmentProduct.modification_id,
            )
            .join(
                SpecialEquipmentModel,
                SpecialEquipmentModel.id
                == sa.func.coalesce(
                    SpecialEquipmentModification.model_id,
                    SpecialEquipmentProduct.model_id,
                ),
            )
            .where(
                SpecialEquipmentProduct.publication_status == "published",
                SpecialEquipmentModel.mark_id == entity_id,
            )
        )
    elif entity_type == "model":
        query = (
            sa.select(SpecialEquipmentProduct.id)
            .outerjoin(
                SpecialEquipmentModification,
                SpecialEquipmentModification.id
                == SpecialEquipmentProduct.modification_id,
            )
            .where(
                SpecialEquipmentProduct.publication_status == "published",
                sa.func.coalesce(
                    SpecialEquipmentModification.model_id,
                    SpecialEquipmentProduct.model_id,
                ) == entity_id,
            )
        )
    elif entity_type == "superstructure":
        query = sa.select(SpecialEquipmentProduct.id).where(
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.superstructure_id == entity_id,
        )
    elif entity_type == "modification":
        query = sa.select(SpecialEquipmentProduct.id).where(
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.modification_id == entity_id,
        )
    elif entity_type == "product":
        query = sa.select(SpecialEquipmentProduct.id).where(
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.id == entity_id,
        )
    elif entity_type in {"attribute", "attribute_group", "unit"}:
        # Default-group changes can affect every category where an attribute
        # is inherited.  Catalog metadata mutations are rare, so prefer a
        # complete publication guard over an incomplete direct-link query.
        query = sa.select(SpecialEquipmentProduct.id).where(
            SpecialEquipmentProduct.publication_status == "published"
        )
    else:
        return []
    return list(
        (
            await session.execute(
                query.distinct().order_by(
                    (
                        SpecialEquipmentProductCategory.product_id
                        if entity_type == "category"
                        else SpecialEquipmentProduct.id
                    )
                )
            )
        ).scalars()
    )


async def published_product_validation_snapshots(
    session: AsyncSession,
    product_ids: Sequence[UUID],
) -> list[dict[str, Any]]:
    """Load publication invariants in bounded batches without N+1 enrichment."""

    snapshots: list[dict[str, Any]] = []
    for start in range(0, len(product_ids), 1000):
        batch = product_ids[start : start + 1000]
        product_rows = list(
            (
                await session.execute(
                    sa.select(
                        SpecialEquipmentProduct.id,
                        SpecialEquipmentProduct.code,
                        SpecialEquipmentProduct.modification_id,
                        SpecialEquipmentProduct.model_id,
                        SpecialEquipmentProduct.superstructure_id,
                        SpecialEquipmentProduct.seller_company_id,
                        SpecialEquipmentProduct.condition,
                        SpecialEquipmentProduct.mileage_km,
                        SpecialEquipmentProduct.engine_hours,
                        SpecialEquipmentProduct.manufacture_year,
                        SpecialEquipmentProduct.publication_status,
                        SpecialEquipmentProduct.sale_status,
                        SpecialEquipmentModification.is_active.label(
                            "modification_active"
                        ),
                        SpecialEquipmentModification.year_from,
                        SpecialEquipmentModification.year_to,
                        SpecialEquipmentModel.is_active.label("model_active"),
                        SpecialEquipmentMark.is_active.label("mark_active"),
                        SpecialEquipmentSuperstructure.is_active.label(
                            "superstructure_active"
                        ),
                    )
                    .outerjoin(
                        SpecialEquipmentModification,
                        SpecialEquipmentModification.id
                        == SpecialEquipmentProduct.modification_id,
                    )
                    .join(
                        SpecialEquipmentModel,
                        SpecialEquipmentModel.id
                        == sa.func.coalesce(
                            SpecialEquipmentModification.model_id,
                            SpecialEquipmentProduct.model_id,
                        ),
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
                    .where(SpecialEquipmentProduct.id.in_(batch))
                )
            ).mappings()
        )
        seller_ids = {
            row["seller_company_id"]
            for row in product_rows
            if row["seller_company_id"] is not None
        }
        active_seller_ids = set(
            (
                await session.execute(
                    sa.select(Company.id)
                    .where(
                        Company.id.in_(seller_ids),
                        Company.is_active.is_(True),
                    )
                    .with_for_update()
                )
            ).scalars()
        )
        categories_by_product: dict[UUID, list[dict[str, Any]]] = {}
        category_rows = (
            await session.execute(
                sa.select(
                    SpecialEquipmentProductCategory.product_id,
                    SpecialEquipmentCategory.id,
                    SpecialEquipmentCategory.usage_metric,
                    SpecialEquipmentCategory.is_active,
                )
                .join(
                    SpecialEquipmentCategory,
                    SpecialEquipmentCategory.id
                    == SpecialEquipmentProductCategory.category_id,
                )
                .where(SpecialEquipmentProductCategory.product_id.in_(batch))
            )
        ).mappings()
        for row in category_rows:
            categories_by_product.setdefault(row["product_id"], []).append(
                {
                    "id": row["id"],
                    "usage_metric": row["usage_metric"],
                    "is_active": row["is_active"],
                }
            )
        modification_ids = {
            row["modification_id"]
            for row in product_rows
            if row["modification_id"] is not None
        }
        values_by_modification: dict[UUID, set[UUID]] = {}
        value_activity_by_modification: dict[
            UUID, list[dict[str, Any]]
        ] = {}
        value_rows: Sequence[RowMapping] = ()
        if modification_ids:
            value_rows = (
                await session.execute(
                    sa.select(
                        SpecialEquipmentModificationAttributeValue.modification_id,
                        SpecialEquipmentModificationAttributeValue.attribute_id,
                        SpecialEquipmentAttribute.is_active.label(
                            "attribute_active"
                        ),
                        SpecialEquipmentModificationAttributeValue.option_id,
                        SpecialEquipmentAttributeOption.is_active.label(
                            "option_active"
                        ),
                    )
                    .join(
                        SpecialEquipmentAttribute,
                        SpecialEquipmentAttribute.id
                        == SpecialEquipmentModificationAttributeValue.attribute_id,
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
            ).mappings().all()
        for row in value_rows:
            values_by_modification.setdefault(
                row["modification_id"], set()
            ).add(row["attribute_id"])
            value_activity_by_modification.setdefault(
                row["modification_id"], []
            ).append(
                {
                    "attribute_id": row["attribute_id"],
                    "attribute_active": row["attribute_active"],
                    "option_id": row["option_id"],
                    "option_active": row["option_active"],
                }
            )
        snapshots.extend(
            {
                **dict(row),
                "seller_exists": row["seller_company_id"] in active_seller_ids,
                "categories": categories_by_product.get(row["id"], []),
                "value_attribute_ids": values_by_modification.get(
                    row["modification_id"], set()
                ),
                "value_activity": value_activity_by_modification.get(
                    row["modification_id"], []
                ),
            }
            for row in product_rows
        )
    return snapshots


async def get_allowed_modification_categories(
    session: AsyncSession, modification_id: UUID
) -> set[UUID]:
    return set(
        (
            await session.execute(
                sa.select(SpecialEquipmentModificationCategory.category_id).where(
                    SpecialEquipmentModificationCategory.modification_id
                    == modification_id
                )
            )
        ).scalars()
    )


async def get_attribute_definitions(
    session: AsyncSession, attribute_ids: Sequence[UUID]
) -> dict[UUID, dict]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentAttribute.id,
                SpecialEquipmentAttribute.code,
                SpecialEquipmentAttribute.data_type,
                SpecialEquipmentAttribute.is_active,
            ).where(SpecialEquipmentAttribute.id.in_(attribute_ids))
        )
    ).mappings()
    return {row["id"]: dict(row) for row in rows}


async def list_attribute_values_for_type_conversion(
    session: AsyncSession,
    attribute_id: UUID,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.modification_id,
                SpecialEquipmentModificationAttributeValue.option_id,
                SpecialEquipmentModificationAttributeValue.value_number,
                SpecialEquipmentModificationAttributeValue.value_text,
                SpecialEquipmentModificationAttributeValue.value_boolean,
            )
            .where(
                SpecialEquipmentModificationAttributeValue.attribute_id
                == attribute_id
            )
            .order_by(
                SpecialEquipmentModificationAttributeValue.modification_id
            )
        )
    ).mappings()
    return [dict(row) for row in rows]


async def convert_text_attribute_values_to_options(
    session: AsyncSession,
    *,
    attribute_id: UUID,
    options: Sequence[Mapping[str, Any]],
) -> None:
    existing_options = (
        await session.execute(
            sa.select(
                SpecialEquipmentAttributeOption.id,
                SpecialEquipmentAttributeOption.name,
            )
            .where(SpecialEquipmentAttributeOption.attribute_id == attribute_id)
            .order_by(
                SpecialEquipmentAttributeOption.sort_order,
                SpecialEquipmentAttributeOption.id,
            )
        )
    ).mappings()
    option_id_by_name: dict[str, UUID] = {}
    for row in existing_options:
        option_id_by_name.setdefault(row["name"].strip(), row["id"])
    option_rows = [
        SpecialEquipmentAttributeOption(
            attribute_id=attribute_id,
            **dict(option),
        )
        for option in options
    ]
    session.add_all(option_rows)
    await session.flush()
    option_id_by_name.update({row.name: row.id for row in option_rows})
    await session.execute(
        sa.delete(SpecialEquipmentModificationAttributeValue).where(
            SpecialEquipmentModificationAttributeValue.attribute_id
            == attribute_id,
            sa.func.btrim(
                SpecialEquipmentModificationAttributeValue.value_text
            )
            == "",
        )
    )
    if not option_id_by_name:
        await session.flush()
        return
    option_id = sa.case(
        option_id_by_name,
        value=sa.func.btrim(
            SpecialEquipmentModificationAttributeValue.value_text
        ),
    )
    await session.execute(
        sa.update(SpecialEquipmentModificationAttributeValue)
        .where(
            SpecialEquipmentModificationAttributeValue.attribute_id
            == attribute_id,
            SpecialEquipmentModificationAttributeValue.value_text.is_not(None),
        )
        .values(
            option_id=option_id,
            value_text=None,
        )
    )
    await session.flush()


async def delete_attribute_options(
    session: AsyncSession,
    attribute_id: UUID,
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentAttributeOption).where(
            SpecialEquipmentAttributeOption.attribute_id == attribute_id
        )
    )
    await session.flush()


async def get_option_definitions(
    session: AsyncSession, option_ids: Sequence[UUID]
) -> dict[UUID, dict]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentAttributeOption.id,
                SpecialEquipmentAttributeOption.attribute_id,
                SpecialEquipmentAttributeOption.code,
                SpecialEquipmentAttributeOption.is_active,
            ).where(SpecialEquipmentAttributeOption.id.in_(option_ids))
        )
    ).mappings()
    return {row["id"]: dict(row) for row in rows}


async def dependencies(
    session: AsyncSession, entity_type: EntityType, entity_id: UUID
) -> dict[str, int]:
    counters: dict[str, sa.Select] = {}
    if entity_type == "category":
        counters = {
            "parent_relations": sa.select(sa.func.count()).where(
                SpecialEquipmentCategoryRelation.parent_id == entity_id
            ),
            "child_relations": sa.select(sa.func.count()).where(
                SpecialEquipmentCategoryRelation.child_id == entity_id
            ),
            "modifications": sa.select(sa.func.count()).where(
                SpecialEquipmentModificationCategory.category_id == entity_id
            ),
            "products": sa.select(sa.func.count()).where(
                SpecialEquipmentProductCategory.category_id == entity_id
            ),
            "attributes": sa.select(sa.func.count()).where(
                SpecialEquipmentCategoryAttribute.category_id == entity_id
            ),
        }
    elif entity_type == "mark":
        counters = {
            "models": sa.select(sa.func.count()).where(
                SpecialEquipmentModel.mark_id == entity_id
            )
        }
    elif entity_type == "model":
        counters = {
            "modifications": sa.select(sa.func.count()).where(
                SpecialEquipmentModification.model_id == entity_id
            ),
            "products": sa.select(sa.func.count()).where(
                SpecialEquipmentProduct.model_id == entity_id
            ),
        }
    elif entity_type == "superstructure":
        counters = {
            "products": sa.select(sa.func.count()).where(
                SpecialEquipmentProduct.superstructure_id == entity_id
            ),
        }
    elif entity_type == "unit":
        counters = {
            "attributes": sa.select(sa.func.count()).where(
                SpecialEquipmentAttribute.unit_id == entity_id
            ),
        }
    elif entity_type == "modification":
        counters = {
            "trims": sa.select(sa.func.count()).where(
                SpecialEquipmentTrim.modification_id == entity_id
            ),
            "products": sa.select(sa.func.count()).where(
                SpecialEquipmentProduct.modification_id == entity_id
            ),
        }
    elif entity_type == "trim":
        counters = {
            "products": sa.select(sa.func.count()).where(
                SpecialEquipmentProduct.trim_id == entity_id
            )
        }
    elif entity_type == "attribute_group":
        counters = {
            "attributes": sa.select(sa.func.count()).where(
                SpecialEquipmentAttribute.attribute_group_id == entity_id
            ),
            "category_attributes": sa.select(sa.func.count()).where(
                SpecialEquipmentCategoryAttribute.group_id == entity_id
            )
        }
    elif entity_type == "attribute":
        counters = {
            "category_attributes": sa.select(sa.func.count()).where(
                SpecialEquipmentCategoryAttribute.attribute_id == entity_id
            ),
            "modification_values": sa.select(sa.func.count()).where(
                SpecialEquipmentModificationAttributeValue.attribute_id == entity_id
            ),
            "options": sa.select(sa.func.count()).where(
                SpecialEquipmentAttributeOption.attribute_id == entity_id
            ),
        }
    elif entity_type == "attribute_option":
        counters = {
            "modification_values": sa.select(sa.func.count()).where(
                SpecialEquipmentModificationAttributeValue.option_id == entity_id
            )
        }
    elif entity_type == "product":
        counters = {
            "compatible_attachments": sa.select(sa.func.count()).where(
                SpecialEquipmentProductAttachment.product_id == entity_id
            ),
            "compatible_with_products": sa.select(sa.func.count()).where(
                SpecialEquipmentProductAttachment.attachment_product_id
                == entity_id
            ),
            "favorites": sa.select(sa.func.count()).where(
                SpecialEquipmentFavorite.product_id == entity_id
            ),
            "cart_items": sa.select(sa.func.count()).where(
                SpecialEquipmentCartItem.product_id == entity_id
            ),
            "applications": sa.select(sa.func.count()).where(
                SpecialEquipmentApplicationItem.product_id == entity_id
            ),
            "orders": sa.select(sa.func.count()).where(
                SpecialEquipmentPurchaseOrder.product_id == entity_id
            ),
        }
    return {
        name: int((await session.execute(statement)).scalar_one())
        for name, statement in counters.items()
    }


async def product_archive_dependencies(
    session: AsyncSession, product_id: UUID
) -> dict[str, int]:
    active_application_statuses = ("active", "reserved")
    active_order_statuses = (
        "payment_pending",
        "reserved",
        "purchased",
        "leasing_pending",
        "leasing_active",
        "cancellation_requested",
    )
    counters = {
        "applications": sa.select(sa.func.count()).where(
            SpecialEquipmentApplicationItem.product_id == product_id,
            SpecialEquipmentApplicationItem.item_status.in_(
                active_application_statuses
            ),
        ),
        "orders": sa.select(sa.func.count()).where(
            SpecialEquipmentPurchaseOrder.product_id == product_id,
            SpecialEquipmentPurchaseOrder.status.in_(active_order_statuses),
        ),
        "payments": (
            sa.select(sa.func.count())
            .select_from(SpecialEquipmentPayment)
            .join(
                SpecialEquipmentPurchaseOrder,
                SpecialEquipmentPurchaseOrder.id
                == SpecialEquipmentPayment.purchase_order_id,
            )
            .where(
                SpecialEquipmentPurchaseOrder.product_id == product_id,
                SpecialEquipmentPayment.status.in_(("pending", "processing")),
            )
        ),
    }
    return {
        name: int((await session.execute(statement)).scalar_one())
        for name, statement in counters.items()
    }


async def list_seller_companies(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            sa.select(Company.id, Company.name, Company.inn)
            .where(Company.is_active.is_(True))
            .order_by(Company.name, Company.id)
        )
    ).mappings()
    return [dict(row) for row in rows]


async def seller_exists(session: AsyncSession, seller_id: UUID | None) -> bool:
    if seller_id is None:
        return False
    return bool(
        (
            await session.execute(
                sa.select(sa.literal(True)).where(
                    sa.exists(
                        sa.select(Company.id).where(
                            Company.id == seller_id,
                            Company.is_active.is_(True),
                        )
                    )
                )
            )
        ).scalar_one()
    )


async def lock_active_seller_company(
    session: AsyncSession, seller_id: UUID | None
) -> bool:
    """Serialize product seller selection with company deactivation."""

    if seller_id is None:
        return False
    return (
        await session.execute(
            sa.select(Company.id)
            .where(Company.id == seller_id, Company.is_active.is_(True))
            .with_for_update()
        )
    ).scalar_one_or_none() is not None


async def reserve_media_upload(session: AsyncSession, storage_key: str) -> None:
    await session.execute(
        insert(SpecialEquipmentMediaCleanupJob)
        .values(
            storage_key=storage_key,
            next_attempt_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        .on_conflict_do_nothing(index_elements=["storage_key"])
    )


async def cancel_media_cleanup(
    session: AsyncSession, storage_key: str
) -> bool:
    result = await session.execute(
        sa.delete(SpecialEquipmentMediaCleanupJob).where(
            SpecialEquipmentMediaCleanupJob.storage_key == storage_key,
            SpecialEquipmentMediaCleanupJob.status == "pending",
        )
    )
    return bool(getattr(result, "rowcount", 0))


async def enqueue_media_cleanup(
    session: AsyncSession, storage_key: str
) -> None:
    await session.execute(
        insert(SpecialEquipmentMediaCleanupJob)
        .values(storage_key=storage_key)
        .on_conflict_do_update(
            index_elements=["storage_key"],
            set_={
                "status": "pending",
                "next_attempt_at": datetime.now(UTC),
                "lease_owner": None,
                "lease_until": None,
                "completed_at": None,
            },
        )
    )


async def get_category_image_key(
    session: AsyncSession, category_id: UUID
) -> str | None:
    return await session.scalar(
        sa.select(SpecialEquipmentCategory.image_key).where(
            SpecialEquipmentCategory.id == category_id
        )
    )


async def set_category_image_key(
    session: AsyncSession, category_id: UUID, storage_key: str | None
) -> None:
    await session.execute(
        sa.update(SpecialEquipmentCategory)
        .where(SpecialEquipmentCategory.id == category_id)
        .values(
            image_key=storage_key,
            lock_version=SpecialEquipmentCategory.lock_version + 1,
            updated_at=datetime.now(UTC),
        )
    )


async def get_product_image_storage(
    session: AsyncSession,
    image_id: UUID,
    *,
    product_id: UUID | None = None,
) -> dict | None:
    query = sa.select(
        SpecialEquipmentProductImage.id,
        SpecialEquipmentProductImage.product_id,
        SpecialEquipmentProductImage.storage_key,
        SpecialEquipmentProductImage.alt_text,
        SpecialEquipmentProductImage.sort_order,
        SpecialEquipmentProductImage.is_primary,
    ).where(SpecialEquipmentProductImage.id == image_id)
    if product_id is not None:
        query = query.where(
            SpecialEquipmentProductImage.product_id == product_id
        )
    row = (await session.execute(query)).mappings().one_or_none()
    return dict(row) if row is not None else None


async def touch_product(session: AsyncSession, product_id: UUID) -> None:
    await session.execute(
        sa.update(SpecialEquipmentProduct)
        .where(SpecialEquipmentProduct.id == product_id)
        .values(
            lock_version=SpecialEquipmentProduct.lock_version + 1,
            updated_at=datetime.now(UTC),
        )
    )


async def create_product_image(
    session: AsyncSession,
    *,
    product_id: UUID,
    storage_key: str,
    alt_text: str | None,
) -> UUID:
    maximum = await session.scalar(
        sa.select(sa.func.max(SpecialEquipmentProductImage.sort_order)).where(
            SpecialEquipmentProductImage.product_id == product_id
        )
    )
    has_primary = bool(
        await session.scalar(
            sa.select(sa.literal(True)).where(
                SpecialEquipmentProductImage.product_id == product_id,
                SpecialEquipmentProductImage.is_primary.is_(True),
            )
        )
    )
    image = SpecialEquipmentProductImage(
        product_id=product_id,
        storage_key=storage_key,
        alt_text=alt_text,
        sort_order=int(maximum) + 1 if maximum is not None else 0,
        is_primary=not has_primary,
    )
    session.add(image)
    await session.flush()
    await touch_product(session, product_id)
    return image.id


async def patch_product_image(
    session: AsyncSession,
    *,
    product_id: UUID,
    image_id: UUID,
    values: Mapping[str, Any],
) -> bool:
    patch = dict(values)
    sort_order = patch.get("sort_order")
    is_primary = patch.get("is_primary")
    images = list(
        (
            await session.execute(
                sa.select(SpecialEquipmentProductImage.id)
                .where(SpecialEquipmentProductImage.product_id == product_id)
                .order_by(
                    SpecialEquipmentProductImage.sort_order,
                    SpecialEquipmentProductImage.id,
                )
            )
        ).scalars()
    )
    if image_id not in images:
        return False
    if sort_order is not None:
        images.remove(image_id)
        images.insert(min(sort_order, len(images)), image_id)
        offset = len(images) * 2 + 1
        await session.execute(
            sa.update(SpecialEquipmentProductImage)
            .where(SpecialEquipmentProductImage.product_id == product_id)
            .values(
                sort_order=SpecialEquipmentProductImage.sort_order + offset
            )
        )
        for index, ordered_id in enumerate(images):
            await session.execute(
                sa.update(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.id == ordered_id)
                .values(sort_order=index)
            )
    if is_primary is True:
        await session.execute(
            sa.update(SpecialEquipmentProductImage)
            .where(SpecialEquipmentProductImage.product_id == product_id)
            .values(is_primary=False)
        )
    scalar_values: dict[str, Any] = {}
    if "alt_text" in patch:
        scalar_values["alt_text"] = patch["alt_text"]
    if is_primary is not None:
        scalar_values["is_primary"] = is_primary
    if scalar_values:
        await session.execute(
            sa.update(SpecialEquipmentProductImage)
            .where(
                SpecialEquipmentProductImage.id == image_id,
                SpecialEquipmentProductImage.product_id == product_id,
            )
            .values(**scalar_values)
        )
    await touch_product(session, product_id)
    return True


async def delete_product_image(
    session: AsyncSession, *, product_id: UUID, image_id: UUID
) -> str | None:
    image = await get_product_image_storage(
        session, image_id, product_id=product_id
    )
    if image is None:
        return None
    await session.execute(
        sa.delete(SpecialEquipmentProductImage).where(
            SpecialEquipmentProductImage.id == image_id
        )
    )
    remaining = list(
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentProductImage.id,
                    SpecialEquipmentProductImage.is_primary,
                )
                .where(SpecialEquipmentProductImage.product_id == product_id)
                .order_by(
                    SpecialEquipmentProductImage.sort_order,
                    SpecialEquipmentProductImage.id,
                )
            )
        ).mappings()
    )
    if remaining and not any(item["is_primary"] for item in remaining):
        await session.execute(
            sa.update(SpecialEquipmentProductImage)
            .where(SpecialEquipmentProductImage.id == remaining[0]["id"])
            .values(is_primary=True)
        )
    for index, item in enumerate(remaining):
        await session.execute(
            sa.update(SpecialEquipmentProductImage)
            .where(SpecialEquipmentProductImage.id == item["id"])
            .values(sort_order=index)
        )
    await touch_product(session, product_id)
    return str(image["storage_key"])


async def all_category_attribute_rules(session: AsyncSession) -> list[dict]:
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
                SpecialEquipmentAttribute.is_active.label("attribute_active"),
                sa.func.coalesce(
                    SpecialEquipmentAttributeGroup.is_active, sa.true()
                ).label("group_active"),
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
            .outerjoin(
                SpecialEquipmentAttributeGroup,
                SpecialEquipmentAttributeGroup.id
                == effective_group_id,
            )
        )
    ).mappings()
    return [dict(row) for row in rows]


async def get_modification_value_activity(
    session: AsyncSession, modification_id: UUID
) -> list[dict[str, Any]]:
    """Return active-state metadata needed by publication guards."""

    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentAttribute.is_active.label("attribute_active"),
                SpecialEquipmentModificationAttributeValue.option_id,
                SpecialEquipmentAttributeOption.is_active.label("option_active"),
            )
            .join(
                SpecialEquipmentAttribute,
                SpecialEquipmentAttribute.id
                == SpecialEquipmentModificationAttributeValue.attribute_id,
            )
            .outerjoin(
                SpecialEquipmentAttributeOption,
                SpecialEquipmentAttributeOption.id
                == SpecialEquipmentModificationAttributeValue.option_id,
            )
            .where(
                SpecialEquipmentModificationAttributeValue.modification_id
                == modification_id
            )
        )
    ).mappings()
    return [dict(row) for row in rows]


async def _directory_refs(
    session: AsyncSession,
    model: Any,
    ids: Sequence[UUID],
) -> list[dict]:
    if not ids:
        return []
    rows = (
        await session.execute(
            sa.select(
                model.id,
                model.code,
                model.name,
                model.slug,
                model.is_active,
            )
            .where(model.id.in_(ids))
            .order_by(model.name, model.id)
        )
    ).mappings()
    return [dict(item) for item in rows]


def _refs_in_id_order(
    ids: Sequence[UUID], refs: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {item["id"]: dict(item) for item in refs}
    return [by_id[entity_id] for entity_id in ids if entity_id in by_id]


async def _modification_values(
    session: AsyncSession, modification_id: UUID
) -> list[dict]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentModificationAttributeValue.option_id,
                SpecialEquipmentModificationAttributeValue.value_number,
                SpecialEquipmentModificationAttributeValue.value_text,
                SpecialEquipmentModificationAttributeValue.value_boolean,
                SpecialEquipmentAttribute.name.label("attribute_name"),
                SpecialEquipmentAttribute.data_type,
                SpecialEquipmentUnit.name.label("unit"),
                SpecialEquipmentAttributeOption.name.label("option_name"),
            )
            .join(
                SpecialEquipmentAttribute,
                SpecialEquipmentAttribute.id
                == SpecialEquipmentModificationAttributeValue.attribute_id,
            )
            .outerjoin(
                SpecialEquipmentUnit,
                SpecialEquipmentUnit.id == SpecialEquipmentAttribute.unit_id,
            )
            .outerjoin(
                SpecialEquipmentAttributeOption,
                SpecialEquipmentAttributeOption.id
                == SpecialEquipmentModificationAttributeValue.option_id,
            )
            .where(
                SpecialEquipmentModificationAttributeValue.modification_id
                == modification_id
            )
            .order_by(
                SpecialEquipmentAttribute.name,
                SpecialEquipmentModificationAttributeValue.attribute_id,
            )
        )
    ).mappings()
    result: list[dict] = []
    for row in rows:
        value = (
            row["option_name"]
            if row["option_id"] is not None
            else row["value_number"]
            if row["value_number"] is not None
            else row["value_text"]
            if row["value_text"] is not None
            else row["value_boolean"]
        )
        display_value = format_attribute_display_value(value, row["unit"])
        if display_value is None:
            continue
        result.append(
            {
                "attribute_id": row["attribute_id"],
                "option_id": row["option_id"],
                "attribute_name": row["attribute_name"],
                "data_type": row["data_type"],
                "value": value,
                "display_value": display_value,
            }
        )
    return result


async def list_product_images(
    session: AsyncSession, product_id: UUID
) -> list[dict]:
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
    return [
        {
            **dict(row),
            "content_url": (
                f"/api/v1/admin/special-equipment/images/{row['id']}/content"
            ),
        }
        for row in rows
    ]


async def _enrich(  # noqa: PLR0912, PLR0915
    session: AsyncSession,
    entity_type: EntityType,
    row: dict,
) -> dict:
    entity_id = row["id"]
    blockers = await dependencies(session, entity_type, entity_id)
    if entity_type == "mark":
        row["model_count"] = blockers.get("models", 0)
    elif entity_type == "model":
        mark = await get_entity(session, "mark", row["mark_id"])
        category = None
        category_name = None
        if row.get("category_id") is not None:
            cat_dict = await get_entity(session, "category", row["category_id"])
            if cat_dict:
                category = {
                    "id": cat_dict["id"],
                    "code": cat_dict["code"],
                    "name": cat_dict["name"],
                }
                category_name = cat_dict["name"]
        row.update(
            mark_name=mark["name"] if mark else "",
            mark=mark,
            category_id=row.get("category_id"),
            category_name=category_name,
            category=category,
            modification_count=blockers.get("modifications", 0),
        )
    elif entity_type == "modification":
        model = await get_entity(session, "model", row["model_id"])
        category_ids = list(
            (
                await session.execute(
                    sa.select(SpecialEquipmentModificationCategory.category_id)
                    .where(
                        SpecialEquipmentModificationCategory.modification_id
                        == entity_id
                    )
                    .order_by(
                        SpecialEquipmentModificationCategory.sort_order,
                        SpecialEquipmentModificationCategory.category_id,
                    )
                )
            ).scalars()
        )
        category_refs = await _directory_refs(
            session, SpecialEquipmentCategory, category_ids
        )
        row.update(
            model_name=model["name"] if model else "",
            mark_id=model["mark_id"] if model else UUID(int=0),
            mark_name=model["mark_name"] if model else "",
            model=model,
            category_ids=category_ids,
            categories=_refs_in_id_order(category_ids, category_refs),
            attribute_values=await _modification_values(session, entity_id),
            trim_count=blockers.get("trims", 0),
            product_count=blockers.get("products", 0),
        )
    elif entity_type == "trim":
        modification = await get_entity(
            session, "modification", row["modification_id"]
        )
        row.update(
            modification_name=modification["name"] if modification else "",
            model_id=modification["model_id"] if modification else UUID(int=0),
            model_name=modification["model_name"] if modification else "",
            mark_id=modification["mark_id"] if modification else UUID(int=0),
            mark_name=modification["mark_name"] if modification else "",
            attribute_links=[
                dict(item)
                for item in (
                    await session.execute(
                        sa.select(
                            SpecialEquipmentTrimAttribute.attribute_id,
                            SpecialEquipmentTrimAttribute.group_id,
                            SpecialEquipmentTrimAttribute.is_required,
                            SpecialEquipmentTrimAttribute.is_filterable,
                            SpecialEquipmentTrimAttribute.sort_order,
                        )
                        .where(SpecialEquipmentTrimAttribute.trim_id == entity_id)
                        .order_by(
                            SpecialEquipmentTrimAttribute.sort_order,
                            SpecialEquipmentTrimAttribute.attribute_id,
                        )
                    )
                ).mappings()
            ],
            attribute_values=[
                dict(item)
                for item in (
                    await session.execute(
                        sa.select(
                            SpecialEquipmentTrimAttributeValue.attribute_id,
                            SpecialEquipmentTrimAttributeValue.value_number,
                            SpecialEquipmentTrimAttributeValue.value_text,
                            SpecialEquipmentTrimAttributeValue.value_boolean,
                            SpecialEquipmentTrimAttributeValue.option_id,
                        )
                        .where(SpecialEquipmentTrimAttributeValue.trim_id == entity_id)
                        .order_by(SpecialEquipmentTrimAttributeValue.attribute_id)
                    )
                ).mappings()
            ],
            product_count=blockers.get("products", 0),
        )
    elif entity_type == "attribute_group":
        row["category_attribute_count"] = blockers.get(
            "category_attributes", 0
        )
        row["attribute_ids"] = list(
            (
                await session.execute(
                    sa.select(SpecialEquipmentAttribute.id)
                    .where(
                        SpecialEquipmentAttribute.attribute_group_id == entity_id
                    )
                    .order_by(
                        SpecialEquipmentAttribute.name,
                        SpecialEquipmentAttribute.id,
                    )
                )
            ).scalars()
        )
    elif entity_type == "attribute":
        options, _ = await list_entities(
            session,
            "attribute_option",
            offset=0,
            limit=1000,
            attribute_id=entity_id,
        )
        unit_name = None
        if row.get("unit_id") is not None:
            unit = await get_entity(session, "unit", row["unit_id"])
            if unit:
                unit_name = unit.get("name")
        row.update(
            unit=unit_name,
            options=options,
            category_count=blockers.get("category_attributes", 0),
            modification_value_count=blockers.get("modification_values", 0),
        )
    elif entity_type == "product":
        modification = (
            await get_entity(session, "modification", row["modification_id"])
            if row.get("modification_id") is not None
            else None
        )
        model = None
        model_id = (
            modification["model_id"]
            if modification
            else row.get("model_id")
        )
        if model_id is not None:
            model = await get_entity(session, "model", model_id)
        superstructure = (
            await get_entity(session, "superstructure", row["superstructure_id"])
            if row.get("superstructure_id") is not None
            else None
        )
        attachment_categories = _attachment_category_cte()
        offering_kind = (
            await session.execute(
                sa.select(
                    _product_is_attachment(attachment_categories).label(
                        "is_attachment"
                    ),
                    _product_is_composite().label("is_composite"),
                )
                .select_from(SpecialEquipmentProduct)
                .where(SpecialEquipmentProduct.id == entity_id)
            )
        ).mappings().one()
        company_name = None
        if row["seller_company_id"] is not None:
            company_name = (
                await session.execute(
                    sa.select(Company.name).where(
                        Company.id == row["seller_company_id"]
                    )
                )
            ).scalar_one_or_none()
        category_ids = list(
            (
                await session.execute(
                    sa.select(SpecialEquipmentProductCategory.category_id)
                    .where(
                        SpecialEquipmentProductCategory.product_id == entity_id
                    )
                    .order_by(SpecialEquipmentProductCategory.category_id)
                )
            ).scalars()
        )
        trim = (
            await get_entity(session, "trim", row["trim_id"])
            if row.get("trim_id") is not None
            else None
        )
        is_kit = bool(
            row.get("model_id") is not None
            and row.get("superstructure_id") is not None
        )
        chassis_values: list[dict] = []
        superstructure_values: list[dict] = []
        if is_kit:
            chassis_values = await list_product_chassis_values(session, entity_id)
            superstructure_values = await list_product_superstructure_values(session, entity_id)

        superstructure_model = None
        if row.get("superstructure_model_id"):
            m_row = (
                await session.execute(
                    sa.select(
                        SpecialEquipmentModel.id,
                        SpecialEquipmentModel.code,
                        SpecialEquipmentModel.name,
                        SpecialEquipmentMark.id.label("mark_id"),
                        SpecialEquipmentMark.code.label("mark_code"),
                        SpecialEquipmentMark.name.label("mark_name"),
                    )
                    .outerjoin(
                        SpecialEquipmentMark,
                        SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
                    )
                    .where(SpecialEquipmentModel.id == row["superstructure_model_id"])
                )
            ).mappings().first()
            if m_row:
                superstructure_model = {
                    "id": m_row["id"],
                    "code": m_row["code"],
                    "name": m_row["name"],
                    "mark": {
                        "id": m_row["mark_id"],
                        "code": m_row["mark_code"],
                        "name": m_row["mark_name"],
                    }
                    if m_row.get("mark_id")
                    else None,
                }

        superstructure_source = None
        if row.get("superstructure_source_product_id"):
            s_row = (
                await session.execute(
                    sa.select(
                        SpecialEquipmentProduct.id,
                        SpecialEquipmentProduct.code,
                        SpecialEquipmentProduct.vin,
                        SpecialEquipmentProduct.publication_status,
                        SpecialEquipmentMark.id.label("mark_id"),
                        SpecialEquipmentMark.code.label("mark_code"),
                        SpecialEquipmentMark.name.label("mark_name"),
                        SpecialEquipmentModel.id.label("model_id"),
                        SpecialEquipmentModel.code.label("model_code"),
                        SpecialEquipmentModel.name.label("model_name"),
                        SpecialEquipmentModification.id.label("mod_id"),
                        SpecialEquipmentModification.code.label("mod_code"),
                        SpecialEquipmentModification.name.label("mod_name"),
                    )
                    .outerjoin(
                        SpecialEquipmentModification,
                        SpecialEquipmentModification.id
                        == SpecialEquipmentProduct.modification_id,
                    )
                    .outerjoin(
                        SpecialEquipmentModel,
                        SpecialEquipmentModel.id == SpecialEquipmentModification.model_id,
                    )
                    .outerjoin(
                        SpecialEquipmentMark,
                        SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
                    )
                    .where(
                        SpecialEquipmentProduct.id
                        == row["superstructure_source_product_id"]
                    )
                )
            ).mappings().first()
            if s_row:
                superstructure_source = {
                    "id": s_row["id"],
                    "code": s_row["code"],
                    "name": s_row["vin"] or s_row["code"],
                    "publication_status": s_row["publication_status"],
                    "mark": {
                        "id": s_row["mark_id"],
                        "code": s_row["mark_code"],
                        "name": s_row["mark_name"],
                    }
                    if s_row.get("mark_id")
                    else None,
                    "model": {
                        "id": s_row["model_id"],
                        "code": s_row["model_code"],
                        "name": s_row["model_name"],
                    }
                    if s_row.get("model_id")
                    else None,
                    "modification": {
                        "id": s_row["mod_id"],
                        "code": s_row["mod_code"],
                        "name": s_row["mod_name"],
                    }
                    if s_row.get("mod_id")
                    else None,
                }

        title = None
        if is_kit:
            from domain.special_equipment_kits import kit_title

            ss_name = (
                row.get("superstructure_name")
                or (
                    superstructure_source["model"]["name"]
                    if superstructure_source and superstructure_source.get("model")
                    else None
                )
                or (
                    superstructure_source.get("code")
                    if superstructure_source
                    else None
                )
                or (superstructure["name"] if superstructure else None)
                or ""
            ).strip()
            ch_mark = (model["mark_name"] if model else (modification["mark_name"] if modification else "")).strip()
            ch_model = (model["name"] if model else (modification["model_name"] if modification else "")).strip()
            if ss_name and (ch_mark or ch_model):
                title = kit_title(
                    superstructure_name=ss_name,
                    chassis_mark_name=ch_mark,
                    chassis_model_name=ch_model,
                )
            elif ss_name:
                title = ss_name
            else:
                title = row.get("code")

        row.update(
            title=title,
            modification_name=modification["name"] if modification else "",
            trim_name=trim["name"] if trim else None,
            model_name=model["name"] if model else (modification["model_name"] if modification else ""),
            mark_name=model["mark_name"] if model else (modification["mark_name"] if modification else ""),
            modification=modification,
            model=model,
            superstructure=superstructure,
            superstructure_name=row.get("superstructure_name") or (superstructure["name"] if superstructure else None),
            superstructure_model_id=row.get("superstructure_model_id"),
            superstructure_model=superstructure_model,
            superstructure_source_product_id=row.get("superstructure_source_product_id"),
            superstructure_source=superstructure_source,
            seller_company_name=company_name,
            category_ids=category_ids,
            categories=await _directory_refs(
                session, SpecialEquipmentCategory, category_ids
            ),
            images=await list_product_images(session, entity_id),
            price=f"{row['price']:.2f}" if row["price"] is not None else None,
            special_price=(
                f"{row['special_price']:.2f}"
                if row.get("special_price") is not None
                else None
            ),
            price_from=(
                f"{row['price_from']:.2f}"
                if row.get("price_from") is not None
                else None
            ),
            normalization_state="normalized",
            is_attachment=bool(offering_kind["is_attachment"]),
            is_composite=bool(offering_kind["is_composite"]),
            is_kit=is_kit,
            chassis_values=chassis_values,
            superstructure_values=superstructure_values,
        )
    elif entity_type == "unit":
        row["attribute_count"] = blockers.get("attributes", 0)
    elif entity_type == "superstructure":
        attrs_stmt = (
            sa.select(
                SpecialEquipmentSuperstructureAttribute.attribute_id,
                SpecialEquipmentSuperstructureAttribute.group_id,
                SpecialEquipmentSuperstructureAttribute.is_required,
                SpecialEquipmentSuperstructureAttribute.is_visible,
                SpecialEquipmentSuperstructureAttribute.is_filterable,
                SpecialEquipmentSuperstructureAttribute.sort_order,
                SpecialEquipmentAttribute.name.label("attribute_name"),
                SpecialEquipmentAttribute.code.label("attribute_code"),
                SpecialEquipmentAttribute.data_type.label("data_type"),
                SpecialEquipmentUnit.name.label("unit"),
                SpecialEquipmentAttributeGroup.name.label("group_name"),
                SpecialEquipmentAttributeGroup.code.label("group_code"),
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
            .join(
                SpecialEquipmentAttributeGroup,
                SpecialEquipmentAttributeGroup.id
                == SpecialEquipmentSuperstructureAttribute.group_id,
            )
            .where(
                SpecialEquipmentSuperstructureAttribute.superstructure_id == entity_id
            )
            .order_by(
                SpecialEquipmentSuperstructureAttribute.sort_order,
                SpecialEquipmentAttribute.name,
            )
        )
        attr_rows = [dict(r) for r in (await session.execute(attrs_stmt)).mappings()]
        cat_ids = await get_superstructure_category_ids(session, entity_id)
        cat_refs = await _directory_refs(session, SpecialEquipmentCategory, cat_ids)
        row.update(
            attributes=attr_rows,
            attribute_count=len(attr_rows),
            category_ids=cat_ids,
            categories=_refs_in_id_order(cat_ids, cat_refs),
            product_count=blockers.get("products", 0),
        )
    return row


async def get_superstructure_category_ids(
    session: AsyncSession,
    superstructure_id: UUID,
) -> list[UUID]:
    stmt = (
        sa.select(SpecialEquipmentSuperstructureCategory.category_id)
        .where(
            SpecialEquipmentSuperstructureCategory.superstructure_id
            == superstructure_id
        )
        .order_by(
            SpecialEquipmentSuperstructureCategory.created_at,
            SpecialEquipmentSuperstructureCategory.category_id,
        )
    )
    return list((await session.execute(stmt)).scalars())


async def replace_superstructure_categories(
    session: AsyncSession,
    superstructure_id: UUID,
    category_ids: Sequence[UUID],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentSuperstructureCategory).where(
            SpecialEquipmentSuperstructureCategory.superstructure_id == superstructure_id
        )
    )
    for cat_id in dict.fromkeys(category_ids):
        session.add(
            SpecialEquipmentSuperstructureCategory(
                superstructure_id=superstructure_id,
                category_id=cat_id,
            )
        )


async def replace_superstructure_attributes(
    session: AsyncSession,
    superstructure_id: UUID,
    attributes: Sequence[dict],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentSuperstructureAttribute).where(
            SpecialEquipmentSuperstructureAttribute.superstructure_id == superstructure_id
        )
    )
    for attr in attributes:
        session.add(
            SpecialEquipmentSuperstructureAttribute(
                superstructure_id=superstructure_id,
                attribute_id=attr["attribute_id"],
                group_id=attr["group_id"],
                is_required=attr.get("is_required", False),
                is_visible=attr.get("is_visible", False),
                is_filterable=attr.get("is_filterable", False),
                sort_order=attr.get("sort_order", 0),
            )
        )


async def list_superstructure_attribute_candidates(
    session: AsyncSession,
    group_id: UUID,
) -> list[dict]:
    stmt = (
        sa.select(
            SpecialEquipmentAttribute.id.label("attribute_id"),
            SpecialEquipmentAttribute.code.label("attribute_code"),
            SpecialEquipmentAttribute.name.label("attribute_name"),
            SpecialEquipmentAttribute.data_type,
            SpecialEquipmentUnit.name.label("unit"),
            SpecialEquipmentAttributeGroup.id.label("group_id"),
            SpecialEquipmentAttributeGroup.name.label("group_name"),
            SpecialEquipmentAttribute.is_active,
        )
        .join(
            SpecialEquipmentAttributeGroup,
            SpecialEquipmentAttributeGroup.id == SpecialEquipmentAttribute.attribute_group_id,
        )
        .outerjoin(
            SpecialEquipmentUnit,
            SpecialEquipmentUnit.id == SpecialEquipmentAttribute.unit_id,
        )
        .where(
            SpecialEquipmentAttribute.attribute_group_id == group_id,
            SpecialEquipmentAttribute.is_active.is_(True),
        )
        .order_by(SpecialEquipmentAttribute.name, SpecialEquipmentAttribute.id)
    )
    return [dict(r) for r in (await session.execute(stmt)).mappings()]


async def rebind_unit_attributes(
    session: AsyncSession,
    *,
    source_unit_id: UUID,
    target_unit_id: UUID,
) -> int:
    """Rebind all attributes referencing source_unit_id to target_unit_id."""
    stmt = (
        sa.update(SpecialEquipmentAttribute)
        .where(SpecialEquipmentAttribute.unit_id == source_unit_id)
        .values(unit_id=target_unit_id)
    )
    result = await session.execute(stmt)
    return int(getattr(result, "rowcount", 0) or 0)


async def record_catalog_deletion(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    root_type: str,
    root_id: UUID,
    root_code: str | None,
    root_name: str | None,
    catalog_revision: int,
    counts: dict[str, Any],
    items: list[dict[str, Any]],
) -> None:
    deletion_log = SpecialEquipmentCatalogDeletionLog(
        user_id=user_id,
        root_type=root_type,
        root_id=root_id,
        root_code=root_code,
        root_name=root_name,
        catalog_revision=catalog_revision,
        counts=counts,
        items=items,
    )
    session.add(deletion_log)


async def list_colors(
    session: AsyncSession,
    *,
    search: str | None = None,
    applicability: str | None = None,
    is_active: bool | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    query = sa.select(SpecialEquipmentColor)
    count_query = sa.select(sa.func.count()).select_from(SpecialEquipmentColor)
    clauses: list[Any] = []
    if search:
        term = f"%{search.strip().lower()}%"
        clauses.append(
            sa.or_(
                sa.func.lower(SpecialEquipmentColor.code).like(term),
                sa.func.lower(SpecialEquipmentColor.name).like(term),
            )
        )
    if applicability is not None:
        clauses.append(SpecialEquipmentColor.applicability == applicability)
    if is_active is not None:
        clauses.append(SpecialEquipmentColor.is_active.is_(is_active))
    if clauses:
        query = query.where(*clauses)
        count_query = count_query.where(*clauses)
    rows = (
        await session.execute(
            query.order_by(
                sa.func.lower(SpecialEquipmentColor.name),
                SpecialEquipmentColor.id,
            )
            .offset(offset)
            .limit(limit)
        )
    ).scalars()
    total = int((await session.execute(count_query)).scalar_one())
    return [_color_row(row) for row in rows], total


async def select_active_colors(
    session: AsyncSession,
    *,
    applicability: str,
    search: str | None = None,
    limit: int = 50,
) -> list[dict]:
    query = sa.select(
        SpecialEquipmentColor.id,
        SpecialEquipmentColor.name,
        SpecialEquipmentColor.applicability,
    ).where(
        SpecialEquipmentColor.is_active.is_(True),
        SpecialEquipmentColor.applicability.in_((applicability, "both")),
    )
    if search:
        query = query.where(
            sa.func.lower(SpecialEquipmentColor.name).like(
                f"%{search.strip().lower()}%"
            )
        )
    rows = (
        (
            await session.execute(
                query.order_by(
                    sa.func.lower(SpecialEquipmentColor.name),
                    SpecialEquipmentColor.id,
                ).limit(min(limit, 100))
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def get_color(session: AsyncSession, color_id: UUID) -> dict | None:
    color = await session.get(SpecialEquipmentColor, color_id)
    return _color_row(color) if color is not None else None


def _color_row(color: SpecialEquipmentColor) -> dict:
    return {
        "id": color.id,
        "code": color.code,
        "name": color.name,
        "applicability": color.applicability,
        "is_active": color.is_active,
        "lock_version": color.lock_version,
        "created_at": color.created_at,
        "updated_at": color.updated_at,
    }


async def create_color(session: AsyncSession, values: Mapping[str, Any]) -> dict:
    color = SpecialEquipmentColor(**dict(values))
    session.add(color)
    await session.flush()
    await session.refresh(color)
    return _color_row(color)


async def update_color(
    session: AsyncSession,
    color_id: UUID,
    values: Mapping[str, Any],
    *,
    lock_version: int,
) -> dict | None:
    values = {**dict(values), "lock_version": lock_version + 1}
    row = (
        await session.execute(
            sa.update(SpecialEquipmentColor)
            .where(
                SpecialEquipmentColor.id == color_id,
                SpecialEquipmentColor.lock_version == lock_version,
            )
            .values(**values)
            .returning(SpecialEquipmentColor)
        )
    ).scalar_one_or_none()
    await session.flush()
    return _color_row(row) if row is not None else None


async def delete_color(
    session: AsyncSession, color_id: UUID, *, lock_version: int) -> bool:
    deleted_id = (
        await session.execute(
            sa.delete(SpecialEquipmentColor)
            .where(
                SpecialEquipmentColor.id == color_id,
                SpecialEquipmentColor.lock_version == lock_version,
            )
            .returning(SpecialEquipmentColor.id)
        )
    ).scalar_one_or_none()
    await session.flush()
    return deleted_id is not None


async def color_usage_counts(session: AsyncSession, color_id: UUID) -> dict[str, int]:
    body_count = int(
        (
            await session.execute(
                sa.select(sa.func.count()).where(
                    SpecialEquipmentProduct.body_color_id == color_id
                )
            )
        ).scalar_one()
    )
    interior_count = int(
        (
            await session.execute(
                sa.select(sa.func.count()).where(
                    SpecialEquipmentProduct.interior_color_id == color_id
                )
            )
        ).scalar_one()
    )
    return {"body": body_count, "interior": interior_count}


async def count_products_with_superstructure_attribute_values(
    session: AsyncSession,
    superstructure_id: UUID,
    attribute_ids: Collection[UUID],
) -> int:
    if not attribute_ids:
        return 0
    stmt = sa.select(
        sa.func.count(sa.distinct(SpecialEquipmentProductSuperstructureValue.product_id))
    ).where(
        SpecialEquipmentProductSuperstructureValue.superstructure_id == superstructure_id,
        SpecialEquipmentProductSuperstructureValue.attribute_id.in_(attribute_ids),
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def count_published_products_missing_superstructure_attributes(
    session: AsyncSession,
    superstructure_id: UUID,
    attribute_ids: Collection[UUID],
) -> int:
    if not attribute_ids:
        return 0
    missing_conds = [
        ~sa.exists(
            sa.select(sa.literal(1)).where(
                SpecialEquipmentProductSuperstructureValue.product_id
                == SpecialEquipmentProduct.id,
                SpecialEquipmentProductSuperstructureValue.attribute_id == attr_id,
            )
        )
        for attr_id in attribute_ids
    ]
    stmt = sa.select(sa.func.count(SpecialEquipmentProduct.id)).where(
        SpecialEquipmentProduct.superstructure_id == superstructure_id,
        SpecialEquipmentProduct.publication_status == "published",
        sa.or_(*missing_conds),
    )
    return int((await session.execute(stmt)).scalar_one() or 0)

