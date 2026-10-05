"""Pure policies for corrected special-equipment catalog management."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from typing import Literal
from uuid import UUID

from domain.errors import DomainError


class SpecialEquipmentManagementError(DomainError):
    """Base management error."""


@dataclass(frozen=True)
class CatalogDependency:
    """One machine-readable dependency exposed by management conflicts."""

    entity_type: str
    entity_id: UUID
    code: str
    name: str
    count: int


class SpecialEquipmentManagementConflictError(SpecialEquipmentManagementError):
    """The requested mutation conflicts with persisted dependencies."""

    def __init__(
        self,
        message: str,
        *,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        entity_code: str | None = None,
        entity_name: str | None = None,
        dependencies: Sequence[CatalogDependency] = (),
    ) -> None:
        super().__init__(message)
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.entity_code = entity_code
        self.entity_name = entity_name
        self.dependencies = tuple(dependencies)


class ProductPriceOnRequestModeLockedError(
    SpecialEquipmentManagementConflictError
):
    """A published advert cannot switch its commercial pricing mode."""

    code = "PRICE_ON_REQUEST_MODE_LOCKED"

    def __init__(self) -> None:
        super().__init__(
            "Режим «Цена по запросу» нельзя изменить после публикации"
        )


class AttributeTypeConversionBlockedError(
    SpecialEquipmentManagementConflictError
):
    """Saved values cannot be represented by the requested attribute type."""

    code = "ATTRIBUTE_TYPE_CONVERSION_BLOCKED"

    def __init__(self, message: str, *, value_count: int) -> None:
        super().__init__(message)
        self.value_count = value_count


class UnitInUseError(SpecialEquipmentManagementConflictError):
    code = "UNIT_IN_USE"

    def __init__(
        self,
        message: str = "Единица измерения используется в характеристиках",
        *,
        attribute_count: int,
    ) -> None:
        super().__init__(message)
        self.attribute_count = attribute_count


class SpecialEquipmentManagementValidationError(SpecialEquipmentManagementError):
    """The mutation violates catalog invariants."""


class UnitInactiveError(SpecialEquipmentManagementValidationError):
    code = "UNIT_INACTIVE"

    def __init__(
        self,
        message: str = "Нельзя выбрать неактивную единицу измерения",
    ) -> None:
        super().__init__(message)


class UnitNotFoundError(SpecialEquipmentManagementValidationError):
    code = "UNIT_NOT_FOUND"

    def __init__(
        self,
        message: str = "Единица измерения не найдена",
    ) -> None:
        super().__init__(message)


class ProductWarehouseValidationError(SpecialEquipmentManagementValidationError):
    """A product warehouse invariant with a stable API error code."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.error_code = code


def ensure_product_warehouse_assignment(
    *,
    no_vin: bool,
    sale_status: str,
    warehouse_id: UUID | None,
    warehouse_explicit: bool = True,
) -> UUID | None:
    """Return the canonical assignment after enforcing product stock rules.

    Switching a product to ``no_vin`` clears an inherited assignment, while
    an explicitly supplied warehouse in the same mutation is a conflict.
    Physical in-stock products always require a warehouse; ``on_order`` keeps
    the nullable assignment delivered by the later catalog contract.
    """

    if no_vin:
        if warehouse_explicit and warehouse_id is not None:
            raise ProductWarehouseValidationError(
                "Товар без VIN не может быть привязан к складу",
                code="WAREHOUSE_NOT_ALLOWED",
            )
        return None
    if sale_status == "available" and warehouse_id is None:
        raise ProductWarehouseValidationError(
            "Для товара с VIN требуется активный склад",
            code="WAREHOUSE_REQUIRED",
        )
    return warehouse_id


class SpecialEquipmentManagementPreconditionError(SpecialEquipmentManagementError):
    """The supplied optimistic-lock version is stale."""


class SpecialEquipmentManagementNotFoundError(SpecialEquipmentManagementError):
    """A referenced resource does not exist."""


class SpecialEquipmentManagementIntegrityError(SpecialEquipmentManagementError):
    """Persisted catalog state violates invariants required for safe reads."""


class SpecialEquipmentTrimContractError(SpecialEquipmentManagementError):
    """A stable machine-readable failure of the trim subresource contract."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        kind: Literal["validation", "conflict", "not_found", "precondition"],
        errors: Sequence[Mapping[str, object]] = (),
        detail: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.kind = kind
        self.errors = tuple(dict(item) for item in errors)
        self.detail = dict(detail) if detail is not None else None


def ensure_special_price(
    *,
    price: Decimal | None,
    special_price: Decimal | None,
) -> Decimal | None:
    """Validate a special offer and return its effective public price."""

    if special_price is None:
        return price
    if price is None:
        raise SpecialEquipmentManagementValidationError(
            "Специальная цена требует обычную цену"
        )
    if special_price <= Decimal("0"):
        raise SpecialEquipmentManagementValidationError(
            "Специальная цена должна быть больше нуля"
        )
    if special_price >= price:
        raise SpecialEquipmentManagementValidationError(
            "Специальная цена должна быть меньше заданной обычной цены"
        )
    return special_price


def ensure_product_commercial_terms(
    *,
    price: Decimal | None,
    special_price: Decimal | None,
    price_on_request: bool,
    price_from: Decimal | None,
) -> Decimal | None:
    """Validate product prices and return the public effective price.

    Fixed prices remain stored while request pricing is active, but the lower
    request bound is the only commercial value visible to catalog callers.
    """

    if price is not None and price <= Decimal("0"):
        raise SpecialEquipmentManagementValidationError(
            "Обычная цена должна быть больше нуля"
        )
    fixed_effective_price = ensure_special_price(
        price=price,
        special_price=special_price,
    )
    if price_from is not None and price_from <= Decimal("0"):
        raise SpecialEquipmentManagementValidationError(
            "Цена «от» должна быть больше нуля"
        )
    if price_on_request:
        return price_from
    return fixed_effective_price


def ensure_price_on_request_mode_change(
    *,
    current: bool,
    requested: bool,
    published_at: datetime | None,
) -> None:
    """Keep the price-on-request flag immutable after first publication."""

    if published_at is not None and current != requested:
        raise ProductPriceOnRequestModeLockedError()


def ensure_warehouse_owner_matches_seller(
    *,
    company_id: UUID | None,
    dealer_id: UUID | None,
    seller_company_id: UUID | None,
) -> None:
    """Reject foreign or ambiguous warehouse ownership assignments."""

    if (
        company_id is not None
        and dealer_id is not None
        and company_id != dealer_id
    ):
        raise SpecialEquipmentManagementValidationError(
            "У склада указаны разные владельцы"
        )
    for owner_id in (company_id, dealer_id):
        if owner_id is not None and owner_id != seller_company_id:
            raise SpecialEquipmentManagementValidationError(
                "Владелец склада должен совпадать с продавцом объявления"
            )


ColorApplicability = Literal["body", "interior", "both"]
COLOR_APPLICABILITIES: frozenset[str] = frozenset(("body", "interior", "both"))
_COLOR_CODE_PATTERN = re.compile(r"^[a-z0-9_-]+$")


TrimModificationValueMarker = tuple[UUID, UUID]
TrimModificationValueWriteLevel = Literal["modification", "trim"]


@dataclass(frozen=True)
class TrimModificationValueConflict:
    """One attempted value write blocked by the opposite catalog level."""

    write_level: TrimModificationValueWriteLevel
    modification_id: UUID
    attribute_id: UUID

    @property
    def code(self) -> str:
        if self.write_level == "modification":
            return "ATTRIBUTE_ALREADY_ASSIGNED_IN_TRIM"
        return "ATTRIBUTE_ALREADY_USED_IN_MODIFICATION"

    @property
    def message(self) -> str:
        if self.write_level == "modification":
            return "Характеристика уже заполнена в комплектации модификации"
        return "Характеристика уже заполнена на уровне модификации"


def trim_modification_value_conflicts(
    *,
    incoming_modification_values: Iterable[TrimModificationValueMarker],
    incoming_trim_values: Iterable[TrimModificationValueMarker],
    persisted_modification_values: Iterable[TrimModificationValueMarker],
    persisted_trim_values: Iterable[TrimModificationValueMarker],
) -> tuple[TrimModificationValueConflict, ...]:
    """Compare both write directions without persistence or transport policy."""

    incoming_modification = set(incoming_modification_values)
    incoming_trim = set(incoming_trim_values)
    modification_conflicts = incoming_modification & (
        set(persisted_trim_values) | incoming_trim
    )
    trim_conflicts = incoming_trim & (
        set(persisted_modification_values) | incoming_modification
    )
    return tuple(
        [
            TrimModificationValueConflict(
                write_level="modification",
                modification_id=modification_id,
                attribute_id=attribute_id,
            )
            for modification_id, attribute_id in sorted(
                modification_conflicts,
                key=lambda marker: (str(marker[0]), str(marker[1])),
            )
        ]
        + [
            TrimModificationValueConflict(
                write_level="trim",
                modification_id=modification_id,
                attribute_id=attribute_id,
            )
            for modification_id, attribute_id in sorted(
                trim_conflicts,
                key=lambda marker: (str(marker[0]), str(marker[1])),
            )
        ]
    )


class SpecialEquipmentColorValidationError(SpecialEquipmentManagementValidationError):
    """Color-specific validation with stable field/code metadata."""

    def __init__(
        self,
        message: str,
        *,
        field: str,
        code: str,
        field_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.error_code = code
        self.field_error_code = field_code or code


class SpecialEquipmentColorConflictError(SpecialEquipmentManagementConflictError):
    """Color-specific conflict with stable code/detail metadata."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        detail: Mapping[str, object] | None = None,
        field_errors: Sequence[Mapping[str, object]] = (),
    ) -> None:
        super().__init__(message, entity_type="color")
        self.error_code = code
        self.detail = detail
        self.field_errors = tuple(field_errors)


def normalize_color_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise SpecialEquipmentColorValidationError(
            "Название цвета обязательно", field="name", code="required"
        )
    if len(name) > 255:
        raise SpecialEquipmentColorValidationError(
            "Название цвета не должно превышать 255 символов",
            field="name",
            code="too_long",
        )
    return name


def _generated_color_code(name: str) -> str:
    value = name.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    return value.strip("-")


def normalize_color_code(value: str | None, *, name: str) -> str:
    code = value.strip().lower() if value is not None else _generated_color_code(name)
    if not code:
        raise SpecialEquipmentColorValidationError(
            "Технический код цвета обязателен", field="code", code="required"
        )
    if len(code) > 100:
        raise SpecialEquipmentColorValidationError(
            "Технический код цвета не должен превышать 100 символов",
            field="code",
            code="too_long",
        )
    if not _COLOR_CODE_PATTERN.fullmatch(code):
        raise SpecialEquipmentColorValidationError(
            "Технический код цвета допускает латиницу, цифры, _ и -",
            field="code",
            code="invalid_format",
        )
    return code


def normalize_color_applicability(value: str) -> ColorApplicability:
    if value not in COLOR_APPLICABILITIES:
        raise SpecialEquipmentColorValidationError(
            "Применимость цвета должна быть body, interior или both",
            field="applicability",
            code="invalid",
        )
    return value  # type: ignore[return-value]


def ensure_color_applicability_change_allowed(
    *,
    current: str,
    requested: str,
    body_products_count: int,
    interior_products_count: int,
) -> None:
    if requested in (current, "both"):
        return
    conflict_reference: str | None = None
    count = 0
    if requested == "body" and interior_products_count > 0:
        conflict_reference = "interior_color_id"
        count = interior_products_count
    elif requested == "interior" and body_products_count > 0:
        conflict_reference = "body_color_id"
        count = body_products_count
    if conflict_reference is None:
        return
    transition = f"{current}_to_{requested}"
    raise SpecialEquipmentColorConflictError(
        "Применимость нельзя сузить: цвет используется в объявлениях",
        code="applicability_narrowing_conflict",
        detail={
            "attempted_transition": transition,
            "conflicting_reference": conflict_reference,
            "conflicting_products_count": count,
        },
        field_errors=(
            {
                "field": "applicability",
                "code": "narrowing_conflict",
                "message": "Нельзя изменить применимость: цвет используется в объявлениях",
            },
        ),
    )


def ensure_product_color_assignment_allowed(
    *,
    current_color_id: UUID | None,
    field_present: bool,
    requested_color_id: UUID | None,
    is_active: bool | None,
    color_applicability: str | None,
    required_applicability: Literal["body", "interior"],
    field: str,
) -> None:
    """Validate only a new color assignment, preserving historical values."""

    if (
        not field_present
        or requested_color_id is None
        or requested_color_id == current_color_id
    ):
        return
    if is_active is not True:
        raise SpecialEquipmentColorValidationError(
            "Цвет неактивен и не может быть назначен",
            field=field,
            code="color_inactive",
            field_code="inactive",
        )
    if color_applicability not in {required_applicability, "both"}:
        raise SpecialEquipmentColorValidationError(
            "Цвет не может быть выбран для этого поля",
            field=field,
            code="invalid_applicability",
            field_code="applicability_mismatch",
        )


@dataclass(frozen=True)
class CategoryPathNode:
    id: UUID
    name: str
    sort_order: int


@dataclass(frozen=True)
class CategoryPathEdge:
    parent_id: UUID
    child_id: UUID
    sort_order: int


@dataclass(frozen=True)
class CategoryCanonicalPath:
    category_ids: tuple[UUID, ...]
    names: tuple[str, ...]
    order_key: tuple[tuple[int, str, str], ...]

    @property
    def display(self) -> str:
        return " / ".join(self.names)


def _category_path_segment(
    node: CategoryPathNode, *, sort_order: int
) -> tuple[int, str, str]:
    return sort_order, node.name.casefold(), str(node.id)


def canonical_category_paths(
    *,
    nodes: Iterable[CategoryPathNode],
    edges: Iterable[CategoryPathEdge],
) -> dict[UUID, CategoryCanonicalPath]:
    """Resolve one minimal path per DAG node in O(vertices + edges)."""

    nodes_by_id: dict[UUID, CategoryPathNode] = {}
    for node in nodes:
        if node.id in nodes_by_id:
            raise SpecialEquipmentManagementIntegrityError(
                "Каталог категорий содержит повторяющийся узел"
            )
        nodes_by_id[node.id] = node
    incoming = dict.fromkeys(nodes_by_id, 0)
    children: dict[UUID, list[CategoryPathEdge]] = {
        category_id: [] for category_id in nodes_by_id
    }
    for edge in edges:
        if edge.parent_id not in nodes_by_id or edge.child_id not in nodes_by_id:
            raise SpecialEquipmentManagementIntegrityError(
                "Связь категорий ссылается на отсутствующий узел"
            )
        incoming[edge.child_id] += 1
        children[edge.parent_id].append(edge)

    paths: dict[UUID, CategoryCanonicalPath] = {}
    ready: deque[UUID] = deque()
    for category_id, degree in incoming.items():
        if degree != 0:
            continue
        node = nodes_by_id[category_id]
        order_key = (
            _category_path_segment(node, sort_order=node.sort_order),
        )
        paths[category_id] = CategoryCanonicalPath(
            category_ids=(category_id,),
            names=(node.name,),
            order_key=order_key,
        )
        ready.append(category_id)

    processed = 0
    while ready:
        parent_id = ready.popleft()
        processed += 1
        parent_path = paths[parent_id]
        for edge in children[parent_id]:
            child = nodes_by_id[edge.child_id]
            candidate = CategoryCanonicalPath(
                category_ids=(*parent_path.category_ids, child.id),
                names=(*parent_path.names, child.name),
                order_key=(
                    *parent_path.order_key,
                    _category_path_segment(
                        child,
                        sort_order=edge.sort_order,
                    ),
                ),
            )
            current = paths.get(child.id)
            if current is None or candidate.order_key < current.order_key:
                paths[child.id] = candidate
            incoming[child.id] -= 1
            if incoming[child.id] == 0:
                ready.append(child.id)

    if processed != len(nodes_by_id):
        raise SpecialEquipmentManagementIntegrityError(
            "Каталог категорий содержит цикл или компонент без корневого узла"
        )
    return paths


def category_scope_for_levels(
    *,
    category_ids: Iterable[UUID],
    edges: Iterable[CategoryPathEdge],
    level_ids: Sequence[UUID | None],
) -> frozenset[UUID]:
    """Resolve the selected placement and all descendants of its last node."""

    known_ids = set(category_ids)
    normalized = tuple(level_ids[:5])
    last_selected = max(
        (index for index, value in enumerate(normalized) if value is not None),
        default=-1,
    )
    if last_selected < 0:
        return frozenset(known_ids)
    selected = normalized[: last_selected + 1]
    if any(value is None for value in selected):
        return frozenset()
    placement = tuple(value for value in selected if value is not None)
    if any(category_id not in known_ids for category_id in placement):
        return frozenset()

    edge_rows = tuple(edges)
    edge_pairs = {(edge.parent_id, edge.child_id) for edge in edge_rows}
    if any(
        (parent_id, child_id) not in edge_pairs
        for parent_id, child_id in pairwise(placement)
    ):
        return frozenset()
    children: dict[UUID, list[UUID]] = {
        category_id: [] for category_id in known_ids
    }
    for edge in edge_rows:
        children[edge.parent_id].append(edge.child_id)
    scope: set[UUID] = set()
    pending = [placement[-1]]
    while pending:
        category_id = pending.pop()
        if category_id in scope:
            continue
        scope.add(category_id)
        pending.extend(children[category_id])
    return frozenset(scope)


@dataclass(frozen=True)
class AttributeDefinition:
    id: UUID
    code: str
    data_type: Literal["number", "text", "boolean", "select"]
    is_active: bool = True


def typed_modification_value(  # noqa: PLR0912
    *,
    definition: AttributeDefinition,
    raw: object | None,
    option_id: UUID | None,
    option_attribute_id: UUID | None,
) -> dict[str, object]:
    """Select exactly one typed persistence column for a modification value."""

    if not definition.is_active:
        raise SpecialEquipmentManagementValidationError(
            f"Характеристика {definition.code} неактивна"
        )
    result: dict[str, object] = {"attribute_id": definition.id}
    if definition.data_type == "select":
        if (
            option_id is None
            or raw is not None
            or option_attribute_id != definition.id
        ):
            raise SpecialEquipmentManagementValidationError(
                f"Для {definition.code} требуется существующий option_id"
            )
        result["option_id"] = option_id
        return result
    if option_id is not None or raw is None:
        raise SpecialEquipmentManagementValidationError(
            f"Для {definition.code} option_id недопустим"
        )
    if definition.data_type == "number":
        if isinstance(raw, bool):
            raise SpecialEquipmentManagementValidationError(
                f"Значение {definition.code} должно быть числом"
            )
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError) as exc:
            raise SpecialEquipmentManagementValidationError(
                f"Значение {definition.code} должно быть числом"
            ) from exc
        if not value.is_finite() or abs(value) >= Decimal("10000000000000000"):
            raise SpecialEquipmentManagementValidationError(
                f"Значение {definition.code} не помещается в NUMERIC(20,4)"
            )
        exponent = value.as_tuple().exponent
        scale = -exponent if isinstance(exponent, int) and exponent < 0 else 0
        if scale > 4:
            raise SpecialEquipmentManagementValidationError(
                f"Значение {definition.code} допускает 4 знака после запятой"
            )
        result["value_number"] = value
    elif definition.data_type == "boolean":
        if not isinstance(raw, bool):
            raise SpecialEquipmentManagementValidationError(
                f"Значение {definition.code} должно быть true или false"
            )
        result["value_boolean"] = raw
    else:
        if not isinstance(raw, str) or not raw.strip():
            raise SpecialEquipmentManagementValidationError(
                f"Значение {definition.code} должно быть непустой строкой"
            )
        if len(raw.strip().encode()) > 2000:
            raise SpecialEquipmentManagementValidationError(
                f"Значение {definition.code} слишком длинное"
            )
        result["value_text"] = raw.strip()
    return result


def ensure_publication_ready(
    *,
    publication_status: str,
    directory_chain_active: bool,
    seller_exists: bool,
    categories_active: bool = True,
    attribute_groups_active: bool = True,
    attributes_active: bool = True,
    attribute_options_active: bool = True,
    category_ids: Sequence[UUID],
    required_attribute_ids: Iterable[UUID],
    value_attribute_ids: Iterable[UUID],
) -> None:
    if publication_status != "published":
        return
    problems: list[str] = []
    if not directory_chain_active:
        problems.append("цепочка марки, модели и модификации неактивна")
    if not seller_exists:
        problems.append("не выбран продавец")
    if not category_ids:
        problems.append("не выбрана категория")
    elif not categories_active:
        problems.append("выбрана неактивная категория")
    if not attribute_groups_active:
        problems.append("есть неактивная группа характеристик")
    if not attributes_active:
        problems.append("есть неактивная характеристика")
    if not attribute_options_active:
        problems.append("выбран неактивный вариант характеристики")
    missing = set(required_attribute_ids) - set(value_attribute_ids)
    if missing:
        problems.append("не заполнены обязательные характеристики")
    if problems:
        raise SpecialEquipmentManagementValidationError(
            "Товар нельзя опубликовать: " + "; ".join(problems)
        )


def ensure_sale_transition(
    *, current: str | None, requested: str, publication_status: str
) -> None:
    if requested in {"reserved", "sold"} and requested != current:
        raise SpecialEquipmentManagementConflictError(
            "Статусы reserved и sold изменяются commerce-контуром"
        )
    if current in {"reserved", "sold"} and requested != current:
        raise SpecialEquipmentManagementConflictError(
            "Реестр не может изменить commerce-owned статус товара"
        )
    if current in {"reserved", "sold"} and publication_status != "published":
        raise SpecialEquipmentManagementConflictError(
            "Зарезервированный или проданный товар должен быть опубликован"
        )


def _structured_dependencies(
    *,
    entity_id: UUID,
    dependencies: Mapping[str, int],
) -> tuple[CatalogDependency, ...]:
    labels = {
        "parent_relations": "Дочерние связи категорий",
        "child_relations": "Родительские связи категорий",
        "modifications": "Модификации",
        "products": "Объявления",
        "attributes": "Характеристики категорий",
        "models": "Модели",
        "category_attributes": "Характеристики категорий",
        "modification_values": "Значения характеристик модификаций",
        "options": "Варианты характеристик",
        "favorites": "Избранное",
        "cart_items": "Корзина",
        "applications": "Заявки",
        "orders": "Заказы",
        "payments": "Платежи",
        "compatible_attachments": "Совместимые надстройки товара",
        "compatible_with_products": "Совместимость с техникой",
        "composite_components": "Компоненты составного объявления",
        "component_of_products": "Участие в составных объявлениях",
        "sale_status:reserved": "Зарезервированное объявление",
        "sale_status:sold": "Проданное объявление",
    }
    return tuple(
        CatalogDependency(
            entity_type=name,
            entity_id=entity_id,
            code=name,
            name=labels.get(name, name),
            count=count,
        )
        for name, count in sorted(dependencies.items())
        if count > 0
    )


def ensure_delete_allowed(
    dependencies: Mapping[str, int],
    *,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    entity_code: str | None = None,
    entity_name: str | None = None,
) -> None:
    blockers = sorted(name for name, count in dependencies.items() if count > 0)
    if blockers:
        raise SpecialEquipmentManagementConflictError(
            "Удаление заблокировано зависимостями: " + ", ".join(blockers),
            entity_type=entity_type,
            entity_id=entity_id,
            entity_code=entity_code,
            entity_name=entity_name,
            dependencies=(
                _structured_dependencies(
                    entity_id=entity_id,
                    dependencies=dependencies,
                )
                if entity_id is not None
                else ()
            ),
        )


def ensure_deactivation_allowed(
    dependencies: Mapping[str, int],
    *,
    entity_type: str,
    entity_id: UUID,
    entity_code: str | None = None,
    entity_name: str | None = None,
) -> None:
    """Keep active catalog links from pointing at inactive directories."""

    blockers = sorted(name for name, count in dependencies.items() if count > 0)
    if blockers:
        raise SpecialEquipmentManagementConflictError(
            "Деактивация заблокирована зависимостями: "
            + ", ".join(blockers),
            entity_type=entity_type,
            entity_id=entity_id,
            entity_code=entity_code,
            entity_name=entity_name,
            dependencies=_structured_dependencies(
                entity_id=entity_id,
                dependencies=dependencies,
            ),
        )


def ensure_product_archive_allowed(
    *,
    dependencies: Mapping[str, int],
    sale_status: str,
    entity_id: UUID | None = None,
    entity_code: str | None = None,
    entity_name: str | None = None,
) -> None:
    blockers_by_name = {
        name: count for name, count in dependencies.items() if count > 0
    }
    if sale_status in {"reserved", "sold"}:
        blockers_by_name[f"sale_status:{sale_status}"] = 1
    blockers = sorted(blockers_by_name)
    if blockers:
        raise SpecialEquipmentManagementConflictError(
            "Архивация заблокирована зависимостями: " + ", ".join(blockers),
            entity_type="product" if entity_id is not None else None,
            entity_id=entity_id,
            entity_code=entity_code,
            entity_name=entity_name,
            dependencies=(
                _structured_dependencies(
                    entity_id=entity_id,
                    dependencies=blockers_by_name,
                )
                if entity_id is not None
                else ()
            ),
        )


def ensure_year_range(year_from: int | None, year_to: int | None) -> None:
    if year_from is not None and not 1900 <= year_from <= 2200:
        raise SpecialEquipmentManagementValidationError("Некорректный год начала")
    if year_to is not None and not 1900 <= year_to <= 2200:
        raise SpecialEquipmentManagementValidationError("Некорректный год окончания")
    if year_from is not None and year_to is not None and year_from > year_to:
        raise SpecialEquipmentManagementValidationError(
            "Год начала не может быть больше года окончания"
        )


def ensure_manufacture_year_within_range(
    *,
    manufacture_year: int | None,
    year_from: int | None,
    year_to: int | None,
) -> None:
    """Keep a published unit inside its live modification year range."""

    if manufacture_year is None:
        return
    if year_from is not None and manufacture_year < year_from:
        raise SpecialEquipmentManagementValidationError(
            "Год выпуска товара меньше года начала модификации"
        )
    if year_to is not None and manufacture_year > year_to:
        raise SpecialEquipmentManagementValidationError(
            "Год выпуска товара больше года окончания модификации"
        )
