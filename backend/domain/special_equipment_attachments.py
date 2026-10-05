"""Pure business rules for attachment products and grouped inventory."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from domain.errors import DomainError
from domain.special_equipment_catalog import (
    CategoryGraph,
)


class AttachmentClassification(StrEnum):
    ORDINARY = "ordinary"
    ATTACHMENT = "attachment"
    MIXED = "mixed"


class AttachmentInvariantError(DomainError):
    """A product or category operation violates attachment classification."""

    def __init__(self, message: str, *, code: str = "ATTACHMENT_INVARIANT") -> None:
        super().__init__(message)
        self.code = code


class AttachmentCategoryInUseError(DomainError):
    """A category DAG mutation would invalidate persisted offerings."""

    code = "ATTACHMENT_CATEGORY_IN_USE"


class InsufficientEquivalentProductsError(DomainError):
    def __init__(self, *, requested: int, available: int) -> None:
        self.requested = requested
        self.available = available
        super().__init__(
            "Недостаточно эквивалентных товаров: "
            f"запрошено {requested}, доступно {available}"
        )


def attachment_branch_ids(
    *,
    graph: CategoryGraph,
    attachment_roots: Iterable[UUID],
) -> frozenset[UUID]:
    """Return marked categories and every descendant reachable in the DAG."""

    children: dict[UUID, set[UUID]] = {}
    for parent_id, child_id in graph.edges:
        children.setdefault(parent_id, set()).add(child_id)
    result: set[UUID] = set()
    pending = list(attachment_roots)
    while pending:
        category_id = pending.pop()
        if category_id not in graph.category_ids:
            raise AttachmentInvariantError("Неизвестная категория надстроек")
        if category_id in result:
            continue
        result.add(category_id)
        pending.extend(children.get(category_id, ()))
    return frozenset(result)


def is_boundary_edge(
    *, parent_id: UUID, child_id: UUID, attachment_ids: frozenset[UUID]
) -> bool:
    """True when child is in the attachment branch but parent is not."""
    return child_id in attachment_ids and parent_id not in attachment_ids


def rule_inheritance_graph(
    *, graph: CategoryGraph, attachment_ids: frozenset[UUID]
) -> CategoryGraph:
    """Same categories, without boundary edges. Used for rule inheritance."""
    return CategoryGraph.from_edges(
        category_ids=graph.category_ids,
        edges=(
            e
            for e in graph.edges
            if not is_boundary_edge(
                parent_id=e[0], child_id=e[1], attachment_ids=attachment_ids
            )
        ),
    )


def classify_category_selection(
    *,
    category_ids: Sequence[UUID],
    attachment_ids: frozenset[UUID],
) -> AttachmentClassification:
    """Classify a product/modification selection and expose mixed assignment."""

    if not category_ids:
        raise AttachmentInvariantError("Товар должен принадлежать категории")
    flags = {category_id in attachment_ids for category_id in category_ids}
    if flags == {True}:
        return AttachmentClassification.ATTACHMENT
    if flags == {False}:
        return AttachmentClassification.ORDINARY
    return AttachmentClassification.MIXED


def ensure_single_attachment_classification(
    *,
    category_ids: Sequence[UUID],
    attachment_ids: frozenset[UUID],
) -> AttachmentClassification:
    classification = classify_category_selection(
        category_ids=category_ids,
        attachment_ids=attachment_ids,
    )
    if classification is AttachmentClassification.MIXED:
        raise AttachmentInvariantError(
            "Товар не может одновременно относиться к обычной ветви и надстройкам",
            code="MIXED_ATTACHMENT_CATEGORIES",
        )
    return classification


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset, tuple, list)):
        normalized = [_json_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def commercial_fingerprint(
    *,
    modification_id: UUID,
    category_ids: Sequence[UUID],
    seller_company_id: UUID | None,
    condition: str,
    manufacture_year: int | None,
    price: Decimal | None,
    currency_code: str,
    mileage_km: int | None,
    engine_hours: int | None,
    owners_count: int | None,
    sale_status: str,
    description: str | None,
    attributes: Mapping[str | UUID, object],
    compatible_attachment_ids: Sequence[UUID],
    component_fingerprints: Sequence[str] = (),
) -> str:
    """Hash only fields that are commercially visible to the buyer."""

    payload = {
        "modification_id": modification_id,
        "category_ids": category_ids,
        "seller_company_id": seller_company_id,
        "condition": condition,
        "manufacture_year": manufacture_year,
        "price": price,
        "currency_code": currency_code,
        "mileage_km": mileage_km,
        "engine_hours": engine_hours,
        "owners_count": owners_count,
        "sale_status": sale_status,
        "description": description,
        "attributes": attributes,
        "compatible_attachment_ids": compatible_attachment_ids,
        "component_fingerprints": component_fingerprints,
    }
    encoded = json.dumps(
        _json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def allocate_equivalent_products(
    product_ids: Iterable[UUID],
    *,
    requested: int,
) -> tuple[UUID, ...]:
    """Choose physical UUIDs in one deterministic lock/allocation order."""

    available = tuple(sorted(set(product_ids), key=str))
    if requested <= 0:
        raise AttachmentInvariantError("Количество должно быть больше нуля")
    if requested > len(available):
        raise InsufficientEquivalentProductsError(
            requested=requested,
            available=len(available),
        )
    return available[:requested]


