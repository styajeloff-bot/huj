"""Pure invariants for the corrected special-equipment catalog."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from typing import Any, Literal
from uuid import UUID

from domain.errors import DomainError

UsageMetric = Literal["mileage_km", "engine_hours"]
EquipmentCondition = Literal["new", "used"]
MAX_CARD_ATTRIBUTES_PER_MODIFICATION = 6

_CYRILLIC_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def format_attribute_display_value(
    value: object | None, unit: str | None = None
) -> str | None:
    """Render one non-empty attribute value consistently across API surfaces."""

    if value is None:
        return None
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, Decimal):
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        rendered = rendered or "0"
    else:
        rendered = str(value).strip()
    if not rendered or rendered.casefold() == "none":
        return None
    normalized_unit = str(unit or "").strip()
    return f"{rendered} {normalized_unit}" if normalized_unit else rendered


class SpecialEquipmentCatalogError(DomainError):
    """Base error for corrected catalog invariants."""


class CategoryGraphError(SpecialEquipmentCatalogError):
    """The category graph or requested context path is invalid."""


class CategoryCycleError(CategoryGraphError):
    def __init__(self) -> None:
        super().__init__("Связь категорий создаёт цикл")


class CategoryPathError(CategoryGraphError):
    """A contextual breadcrumb is not a real root-to-category path."""


class DirectoryChainError(SpecialEquipmentCatalogError):
    """Mark, model and modification do not form one directory chain."""


class UsageMetricConflictError(SpecialEquipmentCatalogError):
    """Selected categories disagree about mileage versus engine hours."""


def generate_catalog_slug(value: str) -> str:
    """Generate a stable SEO slug from a Russian or Latin display name."""

    transliterated = value.strip().casefold().translate(_CYRILLIC_TRANSLITERATION)
    slug = _NON_SLUG.sub("-", transliterated).strip("-")
    return slug or "item"


@dataclass(frozen=True)
class CategoryGraph:
    """Immutable category DAG used by writes and contextual public reads."""

    category_ids: frozenset[UUID]
    edges: frozenset[tuple[UUID, UUID]]

    @classmethod
    def from_edges(
        cls,
        *,
        category_ids: Iterable[UUID],
        edges: Iterable[tuple[UUID, UUID]],
    ) -> CategoryGraph:
        graph = cls(frozenset(category_ids), frozenset(edges))
        graph._validate()
        return graph

    def with_edge(self, *, parent_id: UUID, child_id: UUID) -> CategoryGraph:
        if parent_id == child_id:
            raise CategoryCycleError
        if parent_id not in self.category_ids or child_id not in self.category_ids:
            raise CategoryGraphError("Связь ссылается на неизвестную категорию")
        return CategoryGraph.from_edges(
            category_ids=self.category_ids,
            edges=(*self.edges, (parent_id, child_id)),
        )

    def without_edge(self, *, parent_id: UUID, child_id: UUID) -> CategoryGraph:
        return CategoryGraph.from_edges(
            category_ids=self.category_ids,
            edges=self.edges - {(parent_id, child_id)},
        )

    def resolve_context_path(
        self, *, category_id: UUID, path: Sequence[UUID]
    ) -> tuple[UUID, ...]:
        normalized = tuple(path)
        if not normalized or normalized[-1] != category_id:
            raise CategoryPathError(
                "Путь должен заканчиваться выбранной категорией"
            )
        if len(set(normalized)) != len(normalized):
            raise CategoryPathError("Путь категорий содержит повтор")
        roots = self.category_ids - {child_id for _, child_id in self.edges}
        if normalized[0] not in roots:
            raise CategoryPathError("Путь должен начинаться с корневой категории")
        if any(
            edge not in self.edges
            for edge in pairwise(normalized)
        ):
            raise CategoryPathError("Передан несуществующий путь категорий")
        return normalized

    def _validate(self) -> None:
        if any(
            parent_id not in self.category_ids or child_id not in self.category_ids
            for parent_id, child_id in self.edges
        ):
            raise CategoryGraphError("Связь ссылается на неизвестную категорию")

        children: dict[UUID, set[UUID]] = {}
        incoming: dict[UUID, int] = dict.fromkeys(self.category_ids, 0)
        for parent_id, child_id in self.edges:
            if parent_id == child_id:
                raise CategoryCycleError
            children.setdefault(parent_id, set()).add(child_id)
            incoming[child_id] += 1

        ready = [category_id for category_id, count in incoming.items() if count == 0]
        processed = 0
        while ready:
            parent_id = ready.pop()
            processed += 1
            for child_id in children.get(parent_id, ()):
                incoming[child_id] -= 1
                if incoming[child_id] == 0:
                    ready.append(child_id)
        if processed != len(self.category_ids):
            raise CategoryCycleError


def ensure_directory_chain(
    *,
    selected_mark_id: UUID,
    selected_model_id: UUID,
    selected_modification_id: UUID,
    model_mark_id: UUID,
    modification_model_id: UUID,
) -> None:
    """Require one Mark → Model → Modification chain."""

    if (
        selected_mark_id != model_mark_id
        or selected_model_id != modification_model_id
    ):
        raise DirectoryChainError(
            "Марка, модель и модификация должны принадлежать одной цепочке"
        )
    if selected_modification_id.int == 0:
        raise DirectoryChainError("Модификация не выбрана")


def ensure_single_usage_metric(
    *,
    category_ids: Sequence[UUID],
    metric_by_category: Mapping[UUID, UsageMetric],
) -> UsageMetric:
    """Return the one allowed product usage metric for selected categories."""

    if not category_ids:
        raise UsageMetricConflictError("Товар должен принадлежать категории")
    try:
        metrics = {metric_by_category[category_id] for category_id in category_ids}
    except KeyError as exc:
        raise UsageMetricConflictError("Неизвестна метрика выбранной категории") from exc
    if len(metrics) != 1:
        raise UsageMetricConflictError(
            "Категории товара должны использовать один показатель эксплуатации"
        )
    return metrics.pop()


def ensure_condition_usage(
    *,
    condition: EquipmentCondition,
    usage_metric: UsageMetric,
    mileage_km: int | None,
    engine_hours: int | None,
) -> None:
    """Enforce new/used and category-selected usage fields."""

    if condition == "new":
        if mileage_km is not None or engine_hours is not None:
            raise UsageMetricConflictError(
                "Для новой техники пробег и моточасы не заполняются"
            )
        return
    expected = mileage_km if usage_metric == "mileage_km" else engine_hours
    unexpected = engine_hours if usage_metric == "mileage_km" else mileage_km
    if expected is None or unexpected is not None:
        label = "пробег" if usage_metric == "mileage_km" else "моточасы"
        raise UsageMetricConflictError(
            f"Для бывшей в употреблении техники разрешён только показатель: {label}"
        )


@dataclass(frozen=True)
class CategoryAttributeRule:
    attribute_id: UUID
    group_id: UUID | None
    is_required: bool
    is_filterable: bool
    is_visible: bool
    sort_order: int


@dataclass(frozen=True)
class TrimAttributeGroupConflict:
    """One attribute inherited into different trim groups."""

    attribute_id: UUID
    group_ids: tuple[UUID | None, ...]


@dataclass(frozen=True)
class TrimAttributeContract:
    """Effective assignments and ambiguous groups for one modification."""

    allowed_pairs: frozenset[tuple[UUID, UUID | None]]
    group_conflicts: tuple[TrimAttributeGroupConflict, ...]

    @property
    def conflicting_attribute_ids(self) -> frozenset[UUID]:
        return frozenset(conflict.attribute_id for conflict in self.group_conflicts)


def trim_attribute_group_conflicts(
    pairs: Iterable[tuple[UUID, UUID | None]],
) -> tuple[TrimAttributeGroupConflict, ...]:
    """Return deterministic conflicts for attributes assigned to several groups."""

    groups_by_attribute: dict[UUID, set[UUID | None]] = {}
    for attribute_id, group_id in pairs:
        groups_by_attribute.setdefault(attribute_id, set()).add(group_id)
    return tuple(
        TrimAttributeGroupConflict(
            attribute_id=attribute_id,
            group_ids=tuple(sorted(group_ids, key=str)),
        )
        for attribute_id, group_ids in sorted(
            groups_by_attribute.items(), key=lambda item: str(item[0])
        )
        if len(group_ids) > 1
    )


def effective_attribute_rules(
    *,
    graph: CategoryGraph,
    category_id: UUID,
    rules_by_category: Mapping[UUID, Sequence[CategoryAttributeRule]],
) -> tuple[CategoryAttributeRule, ...]:
    """Union direct and all ancestor rules with deterministic OR semantics."""

    if category_id not in graph.category_ids:
        raise CategoryGraphError("Неизвестная категория")
    parents: dict[UUID, set[UUID]] = {}
    for parent_id, child_id in graph.edges:
        parents.setdefault(child_id, set()).add(parent_id)
    distance: dict[UUID, int] = {category_id: 0}
    stack = [category_id]
    while stack:
        child_id = stack.pop()
        for parent_id in parents.get(child_id, ()):
            new_distance = distance[child_id] + 1
            if new_distance > distance.get(parent_id, -1):
                distance[parent_id] = new_distance
                stack.append(parent_id)
    ordered_categories = sorted(
        distance,
        key=lambda item: (-distance[item], str(item)),
    )
    merged: dict[UUID, CategoryAttributeRule] = {}
    order: list[UUID] = []
    for current_id in ordered_categories:
        for rule in sorted(
            rules_by_category.get(current_id, ()),
            key=lambda item: (item.sort_order, str(item.attribute_id)),
        ):
            current = merged.get(rule.attribute_id)
            if current is None:
                merged[rule.attribute_id] = rule
                order.append(rule.attribute_id)
                continue
            merged[rule.attribute_id] = CategoryAttributeRule(
                attribute_id=rule.attribute_id,
                # Categories are traversed from root to the selected node, so
                # the most specific non-null override wins deterministically.
                group_id=(
                    rule.group_id
                    if rule.group_id is not None
                    else current.group_id
                ),
                is_required=current.is_required or rule.is_required,
                is_filterable=current.is_filterable or rule.is_filterable,
                is_visible=current.is_visible or rule.is_visible,
                sort_order=min(current.sort_order, rule.sort_order),
            )
    return tuple(merged[attribute_id] for attribute_id in order)


def resolve_trim_attribute_contract(
    *,
    graph: CategoryGraph,
    category_ids: Iterable[UUID],
    rules_by_category: Mapping[UUID, Sequence[CategoryAttributeRule]],
) -> TrimAttributeContract:
    """Resolve the shared trim assignment contract across modification categories."""

    allowed_pairs = frozenset(
        (rule.attribute_id, rule.group_id)
        for category_id in category_ids
        for rule in effective_attribute_rules(
            graph=graph,
            category_id=category_id,
            rules_by_category=rules_by_category,
        )
    )
    return TrimAttributeContract(
        allowed_pairs=allowed_pairs,
        group_conflicts=trim_attribute_group_conflicts(allowed_pairs),
    )


def ensure_condition_owners(
    *, condition: EquipmentCondition, owners_count: int | None
) -> None:
    """Require owners only for used equipment."""

    if condition == "new" and owners_count is not None:
        raise SpecialEquipmentCatalogError(
            "Для новой техники количество владельцев не заполняется"
        )
    if condition == "used" and (owners_count is None or owners_count < 0):
        raise SpecialEquipmentCatalogError(
            "Для техники «С пробегом» укажите количество владельцев не меньше 0"
        )


def ensure_vin_choice(*, vin: str | None, no_vin: bool) -> None:
    """Require either a normalized VIN of at most 17 characters or no_vin."""

    normalized = vin.strip() if vin is not None else ""
    if no_vin:
        if normalized:
            raise SpecialEquipmentCatalogError(
                "При отметке «Нет VIN» поле VIN должно быть пустым"
            )
        return
    if not normalized:
        raise SpecialEquipmentCatalogError(
            "Укажите VIN или установите отметку «Нет VIN»"
        )
    if len(normalized) > 17:
        raise SpecialEquipmentCatalogError("VIN не может быть длиннее 17 символов")


def effective_attribute_ids(
    *,
    graph: CategoryGraph,
    category_id: UUID,
    rules_by_category: Mapping[UUID, Sequence[CategoryAttributeRule]],
) -> tuple[UUID, ...]:
    return tuple(
        rule.attribute_id
        for rule in effective_attribute_rules(
            graph=graph,
            category_id=category_id,
            rules_by_category=rules_by_category,
        )
    )


def ensure_card_attribute_limit(
    *,
    graph: CategoryGraph,
    category_ids: Sequence[UUID],
    rules_by_category: Mapping[UUID, Sequence[CategoryAttributeRule]],
    limit: int = MAX_CARD_ATTRIBUTES_PER_MODIFICATION,
) -> tuple[UUID, ...]:
    """Return visible attribute ids and reject an oversized effective union."""

    visible_ids = {
        rule.attribute_id
        for category_id in category_ids
        for rule in effective_attribute_rules(
            graph=graph,
            category_id=category_id,
            rules_by_category=rules_by_category,
        )
        if rule.is_visible
    }
    ordered = tuple(sorted(visible_ids, key=str))
    if len(ordered) > limit:
        raise SpecialEquipmentCatalogError(
            "Для карточки модификации можно выбрать не более "
            f"{limit} характеристик (получено: {len(ordered)})"
        )
    return ordered


def ensure_category_change_card_attribute_limits(
    *,
    graph: CategoryGraph,
    category_id: UUID,
    modification_category_sets: Iterable[Sequence[UUID]],
    rules_by_category: Mapping[UUID, Sequence[CategoryAttributeRule]],
    limit: int = MAX_CARD_ATTRIBUTES_PER_MODIFICATION,
) -> None:
    """Validate only modifications affected by one category change."""

    if category_id not in graph.category_ids:
        raise CategoryGraphError("Неизвестная категория")

    children: dict[UUID, set[UUID]] = {}
    for parent_id, child_id in graph.edges:
        children.setdefault(parent_id, set()).add(child_id)

    affected_category_ids = {category_id}
    pending = [category_id]
    while pending:
        parent_id = pending.pop()
        for child_id in children.get(parent_id, ()):
            if child_id in affected_category_ids:
                continue
            affected_category_ids.add(child_id)
            pending.append(child_id)

    for modification_category_ids in modification_category_sets:
        if affected_category_ids.isdisjoint(modification_category_ids):
            continue
        ensure_card_attribute_limit(
            graph=graph,
            category_ids=modification_category_ids,
            rules_by_category=rules_by_category,
            limit=limit,
        )


def _normalize_category_id(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _build_children_map(
    edges: Iterable[tuple[UUID, UUID]],
) -> dict[UUID, list[UUID]]:
    children_map: dict[UUID, list[UUID]] = {}
    for parent_raw, child_raw in edges:
        parent_id = _normalize_category_id(parent_raw)
        child_id = _normalize_category_id(child_raw)
        if parent_id is not None and child_id is not None:
            children_map.setdefault(parent_id, []).append(child_id)
    return children_map


def _collect_descendants(
    children_map: Mapping[UUID, Sequence[UUID]],
    node_id: UUID,
    cache: dict[UUID, set[UUID]],
) -> set[UUID]:
    if node_id in cache:
        return cache[node_id]
    visited: set[UUID] = set()
    queue = list(children_map.get(node_id, ()))
    for child in queue:
        visited.add(child)
    while queue:
        curr = queue.pop()
        for child in children_map.get(curr, ()):
            if child not in visited:
                visited.add(child)
                queue.append(child)
    cache[node_id] = visited
    return visited


def _filter_context_candidates(
    candidates: list[Mapping[str, Any]],
    context_category_id: UUID | None,
    children_map: Mapping[UUID, Sequence[UUID]],
    cache: dict[UUID, set[UUID]],
) -> list[Mapping[str, Any]]:
    if context_category_id is None:
        return candidates
    norm_ctx_id = _normalize_category_id(context_category_id)
    if norm_ctx_id is None:
        return candidates
    allowed_ids = {norm_ctx_id} | _collect_descendants(
        children_map, norm_ctx_id, cache
    )
    context_candidates = [
        cat
        for cat in candidates
        if _normalize_category_id(cat.get("id")) in allowed_ids
    ]
    return context_candidates or candidates


def _filter_terminal_candidates(
    candidates: Sequence[Mapping[str, Any]],
    children_map: Mapping[UUID, Sequence[UUID]],
    cache: dict[UUID, set[UUID]],
) -> list[Mapping[str, Any]]:
    terminal: list[Mapping[str, Any]] = []
    for cat in candidates:
        cat_id = _normalize_category_id(cat.get("id"))
        if cat_id is None:
            terminal.append(cat)
            continue
        descendants = _collect_descendants(children_map, cat_id, cache)
        has_descendant = any(
            (other_id := _normalize_category_id(other.get("id"))) is not None
            and other_id != cat_id
            and other_id in descendants
            for other in candidates
        )
        if not has_descendant:
            terminal.append(cat)
    return terminal


def resolve_terminal_category(
    *,
    edges: Iterable[tuple[UUID, UUID]],
    product_categories: Sequence[Mapping[str, Any]],
    context_category_id: UUID | None,
    primary_category: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Most specific own category of a product, optionally inside a browsed context."""

    candidates = list(product_categories)
    if not candidates:
        return primary_category

    children_map = _build_children_map(edges)
    descendants_cache: dict[UUID, set[UUID]] = {}

    candidates = _filter_context_candidates(
        candidates,
        context_category_id,
        children_map,
        descendants_cache,
    )

    terminal_candidates = _filter_terminal_candidates(
        candidates,
        children_map,
        descendants_cache,
    )
    if not terminal_candidates:
        return primary_category

    if primary_category is not None:
        norm_primary_id = _normalize_category_id(primary_category.get("id"))
        if norm_primary_id is not None:
            for cat in terminal_candidates:
                if _normalize_category_id(cat.get("id")) == norm_primary_id:
                    return cat

    return terminal_candidates[0]


