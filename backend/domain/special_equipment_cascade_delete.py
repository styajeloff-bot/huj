"""Pure domain policies, structures, and planner for special equipment catalog cascade delete."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from domain.errors import DomainError

# --- Constants & Codes ---
CONFIRMATION_WORD = "УДАЛИТЬ"
CASCADE_DELETE_BLOCKED = "CASCADE_DELETE_BLOCKED"
CASCADE_PREVIEW_STALE = "CASCADE_PREVIEW_STALE"
CASCADE_CONFIRMATION_INVALID = "CASCADE_CONFIRMATION_INVALID"
CASCADE_TOO_LARGE = "CASCADE_TOO_LARGE"
DEFAULT_MAX_CASCADE_ROWS = 5000

DELETE_KEYS: tuple[str, ...] = (
    "marks",
    "models",
    "modifications",
    "trims",
    "superstructures",
    "categories",
    "attribute_groups",
    "attributes",
    "options",
    "colors",
    "products",
)

TYPE_TO_DELETE_KEY: dict[str, str] = {
    "mark": "marks",
    "marks": "marks",
    "model": "models",
    "models": "models",
    "modification": "modifications",
    "modifications": "modifications",
    "trim": "trims",
    "trims": "trims",
    "superstructure": "superstructures",
    "superstructures": "superstructures",
    "category": "categories",
    "categories": "categories",
    "attribute_group": "attribute_groups",
    "attribute-group": "attribute_groups",
    "attribute_groups": "attribute_groups",
    "attribute-groups": "attribute_groups",
    "attribute": "attributes",
    "attributes": "attributes",
    "option": "options",
    "options": "options",
    "attribute_option": "options",
    "attribute-option": "options",
    "attribute_options": "options",
    "attribute-options": "options",
    "color": "colors",
    "colors": "colors",
    "product": "products",
    "products": "products",
}


# --- Domain Data Structures ---
@dataclass(frozen=True)
class EntityRef:
    """Reference to a catalog entity."""

    type: str
    id: uuid.UUID
    code: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class UnlinkRef:
    """Summary of links being severed."""

    type: str
    count: int
    description: str


@dataclass(frozen=True)
class ClearRef:
    """Summary of fields being set to NULL."""

    type: str
    field: str
    count: int
    description: str


@dataclass(frozen=True)
class UserImpact:
    """Impact on user-facing commerce states."""

    cart_items: int = 0
    favorites: int = 0


@dataclass(frozen=True)
class ProductBlockerDocument:
    """Document that blocks product deletion."""

    type: str
    id: uuid.UUID
    number: str
    status: str


@dataclass(frozen=True)
class ProductBlocker:
    """Product blocking cascade deletion."""

    product: EntityRef
    documents: list[ProductBlockerDocument]


@dataclass(frozen=True)
class DistributorBlocker:
    """Distributor company blocking mark deletion."""

    company: dict[str, Any]


@dataclass(frozen=True)
class SupportProgramBlockerReference:
    """Entity referenced by a support program."""

    type: str
    id: uuid.UUID
    code: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class KitSourceProductRef:
    id: uuid.UUID
    code: str
    title: str = ""


@dataclass(frozen=True)
class KitSourceBlockerItem:
    id: uuid.UUID
    code: str
    title: str


@dataclass(frozen=True)
class KitSourceBlocker:
    product: KitSourceProductRef
    kits: list[KitSourceBlockerItem]


@dataclass(frozen=True)
class SupportProgramBlocker:
    """Support program blocking entity deletion."""

    program: dict[str, Any]
    references: list[SupportProgramBlockerReference]


@dataclass
class CascadeBlockers:
    """Combined blockers preventing cascade delete."""

    products: list[ProductBlocker] = field(default_factory=list)
    distributors: list[DistributorBlocker] = field(default_factory=list)
    support_programs: list[SupportProgramBlocker] = field(default_factory=list)
    kit_sources: list[KitSourceBlocker] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.products
            or self.distributors
            or self.support_programs
            or self.kit_sources
        )


@dataclass
class CascadeGraphSnapshot:
    """Immutable snapshot of the catalog neighborhood for building a cascade plan."""

    # Entities
    marks: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    models: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    modifications: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    trims: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    superstructures: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    categories: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    attribute_groups: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    attributes: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    options: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    colors: dict[uuid.UUID, EntityRef] = field(default_factory=dict)
    products: dict[uuid.UUID, EntityRef] = field(default_factory=dict)

    # Relationships & Foreign Keys
    model_mark_ids: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    modification_model_ids: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    trim_modification_ids: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    superstructure_model_ids: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    superstructure_modification_ids: dict[uuid.UUID, uuid.UUID | None] = field(default_factory=dict)
    product_modification_ids: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    product_trim_ids: dict[uuid.UUID, uuid.UUID | None] = field(default_factory=dict)
    product_superstructure_ids: dict[uuid.UUID, uuid.UUID | None] = field(default_factory=dict)
    product_superstructure_source_ids: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    product_body_color_ids: dict[uuid.UUID, uuid.UUID | None] = field(default_factory=dict)
    product_interior_color_ids: dict[uuid.UUID, uuid.UUID | None] = field(default_factory=dict)

    # Category DAG & Links
    category_parent_ids: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)
    modification_category_ids: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)
    product_category_ids: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)

    # Composite Products
    composite_components: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)

    # Attributes & Options
    option_attribute_ids: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    attribute_group_ids: dict[uuid.UUID, uuid.UUID | None] = field(default_factory=dict)
    category_attributes: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)
    category_attribute_group_ids: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID | None] = field(default_factory=dict)
    trim_attributes: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)
    trim_attribute_group_ids: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID | None] = field(default_factory=dict)

    # Stored attribute values: entity_id -> {attr_id: option_id_or_none}
    modification_attribute_values: dict[uuid.UUID, dict[uuid.UUID, uuid.UUID | None]] = field(default_factory=dict)
    trim_attribute_values: dict[uuid.UUID, dict[uuid.UUID, uuid.UUID | None]] = field(default_factory=dict)

    # Mark warehouse relations
    warehouse_mark_counts: dict[uuid.UUID, int] = field(default_factory=dict)
    warehouse_category_counts: dict[uuid.UUID, int] = field(default_factory=dict)
    warehouse_access_rule_mark_counts: dict[uuid.UUID, int] = field(default_factory=dict)

    # User impact
    product_cart_counts: dict[uuid.UUID, int] = field(default_factory=dict)
    product_favorite_counts: dict[uuid.UUID, int] = field(default_factory=dict)

    # Blockers data
    distributor_blockers_by_mark: dict[uuid.UUID, list[DistributorBlocker]] = field(default_factory=dict)
    support_program_blockers: list[SupportProgramBlocker] = field(default_factory=list)
    product_blockers_by_product: dict[uuid.UUID, list[ProductBlockerDocument]] = field(default_factory=dict)
    kit_sources_by_source_product_id: dict[uuid.UUID, list[KitSourceBlockerItem]] = field(default_factory=dict)

    # Builder helper methods
    def add_mark(self, entity_id: uuid.UUID, code: str = "", name: str = "") -> EntityRef:
        ref = EntityRef(type="mark", id=entity_id, code=code, name=name)
        self.marks[entity_id] = ref
        return ref

    def add_model(
        self,
        entity_id: uuid.UUID,
        mark_id: uuid.UUID,
        code: str = "",
        name: str = "",
    ) -> EntityRef:
        ref = EntityRef(type="model", id=entity_id, code=code, name=name)
        self.models[entity_id] = ref
        self.model_mark_ids[entity_id] = mark_id
        return ref

    def add_modification(
        self,
        entity_id: uuid.UUID,
        model_id: uuid.UUID,
        category_ids: Iterable[uuid.UUID] = (),
        code: str = "",
        name: str = "",
    ) -> EntityRef:
        ref = EntityRef(type="modification", id=entity_id, code=code, name=name)
        self.modifications[entity_id] = ref
        self.modification_model_ids[entity_id] = model_id
        self.modification_category_ids[entity_id] = set(category_ids)
        return ref

    def add_trim(
        self,
        entity_id: uuid.UUID,
        modification_id: uuid.UUID,
        code: str = "",
        name: str = "",
    ) -> EntityRef:
        ref = EntityRef(type="trim", id=entity_id, code=code, name=name)
        self.trims[entity_id] = ref
        self.trim_modification_ids[entity_id] = modification_id
        return ref

    def add_superstructure(
        self,
        entity_id: uuid.UUID,
        code: str = "",
        name: str = "",
        model_id: uuid.UUID | None = None,
        modification_id: uuid.UUID | None = None,
    ) -> EntityRef:
        ref = EntityRef(type="superstructure", id=entity_id, code=code, name=name)
        self.superstructures[entity_id] = ref
        if model_id is not None:
            self.superstructure_model_ids[entity_id] = model_id
        if modification_id is not None:
            self.superstructure_modification_ids[entity_id] = modification_id
        return ref

    def add_category(
        self,
        entity_id: uuid.UUID,
        parent_ids: Iterable[uuid.UUID] = (),
        attribute_ids: Iterable[uuid.UUID] = (),
        code: str = "",
        name: str = "",
    ) -> EntityRef:
        ref = EntityRef(type="category", id=entity_id, code=code, name=name)
        self.categories[entity_id] = ref
        self.category_parent_ids[entity_id] = set(parent_ids)
        self.category_attributes[entity_id] = set(attribute_ids)
        return ref

    def add_product(
        self,
        entity_id: uuid.UUID,
        modification_id: uuid.UUID | None = None,
        trim_id: uuid.UUID | None = None,
        category_ids: Iterable[uuid.UUID] = (),
        body_color_id: uuid.UUID | None = None,
        interior_color_id: uuid.UUID | None = None,
        superstructure_id: uuid.UUID | None = None,
        superstructure_model_id: uuid.UUID | None = None,
        superstructure_modification_id: uuid.UUID | None = None,
        superstructure_source_product_id: uuid.UUID | None = None,
        code: str = "",
        name: str = "",
    ) -> EntityRef:
        ref = EntityRef(type="product", id=entity_id, code=code, name=name)
        self.products[entity_id] = ref
        if modification_id is not None:
            self.product_modification_ids[entity_id] = modification_id
        if trim_id is not None:
            self.product_trim_ids[entity_id] = trim_id
        if superstructure_id is not None:
            self.product_superstructure_ids[entity_id] = superstructure_id
        if superstructure_model_id is not None:
            self.superstructure_model_ids[entity_id] = superstructure_model_id
        if superstructure_modification_id is not None:
            self.superstructure_modification_ids[entity_id] = superstructure_modification_id
        if superstructure_source_product_id is not None:
            self.product_superstructure_source_ids[entity_id] = superstructure_source_product_id
        if body_color_id is not None:
            self.product_body_color_ids[entity_id] = body_color_id
        if interior_color_id is not None:
            self.product_interior_color_ids[entity_id] = interior_color_id
        if category_ids:
            self.product_category_ids[entity_id] = set(category_ids)
        return ref

    def add_composite(self, composite_id: uuid.UUID, component_ids: Iterable[uuid.UUID]) -> None:
        self.composite_components.setdefault(composite_id, set()).update(component_ids)

    def add_attribute_group(self, entity_id: uuid.UUID, code: str = "", name: str = "") -> EntityRef:
        ref = EntityRef(type="attribute_group", id=entity_id, code=code, name=name)
        self.attribute_groups[entity_id] = ref
        return ref

    def add_attribute(
        self,
        entity_id: uuid.UUID,
        group_id: uuid.UUID | None = None,
        code: str = "",
        name: str = "",
    ) -> EntityRef:
        ref = EntityRef(type="attribute", id=entity_id, code=code, name=name)
        self.attributes[entity_id] = ref
        if group_id is not None:
            self.attribute_group_ids[entity_id] = group_id
        return ref

    def add_option(
        self,
        entity_id: uuid.UUID,
        attribute_id: uuid.UUID,
        code: str = "",
        name: str = "",
    ) -> EntityRef:
        ref = EntityRef(type="option", id=entity_id, code=code, name=name)
        self.options[entity_id] = ref
        self.option_attribute_ids[entity_id] = attribute_id
        return ref

    def add_color(self, entity_id: uuid.UUID, code: str = "", name: str = "") -> EntityRef:
        ref = EntityRef(type="color", id=entity_id, code=code, name=name)
        self.colors[entity_id] = ref
        return ref


@dataclass
class CascadePlan:
    """The computed cascade deletion plan with preview metadata."""

    root: EntityRef
    delete: dict[str, list[EntityRef]]
    unlink: list[UnlinkRef]
    clear: list[ClearRef]
    attribute_values_to_delete_count: int
    user_impact: UserImpact
    blockers: CascadeBlockers
    counts: dict[str, int]
    total_affected: int
    is_too_large: bool = False
    preview_token: str | None = None
    catalog_revision: int = 0


# --- Domain Errors ---
class CascadeDeleteError(DomainError):
    """Base error for special equipment cascade delete."""


class CascadeDeleteBlockedError(CascadeDeleteError):
    code = CASCADE_DELETE_BLOCKED

    def __init__(
        self,
        message: str = "Удаление заблокировано связанными сущностями или документами",
        *,
        blockers: CascadeBlockers,
    ) -> None:
        super().__init__(message)
        self.blockers = blockers


class CascadePreviewStaleError(CascadeDeleteError):
    code = CASCADE_PREVIEW_STALE

    def __init__(
        self,
        message: str = "Данные каталога изменились, проверьте список ещё раз",
        *,
        plan: CascadePlan | None = None,
    ) -> None:
        super().__init__(message)
        self.plan = plan


class CascadeConfirmationInvalidError(CascadeDeleteError):
    code = CASCADE_CONFIRMATION_INVALID

    def __init__(self, message: str = f"Для подтверждения введите {CONFIRMATION_WORD}") -> None:
        super().__init__(message)


class CascadeTooLargeError(CascadeDeleteError):
    code = CASCADE_TOO_LARGE

    def __init__(
        self,
        message: str = "Каскадное удаление затрагивает слишком много записей",
        *,
        total: int,
        max_rows: int,
    ) -> None:
        super().__init__(message)
        self.total = total
        self.max_rows = max_rows


# --- Pure Functions ---
def validate_confirmation(value: str) -> bool:
    """Check if the provided confirmation string matches the required keyword."""
    return value.strip() == CONFIRMATION_WORD


def ensure_confirmation(value: str) -> None:
    """Validate confirmation keyword or raise CascadeConfirmationInvalidError."""
    if not validate_confirmation(value):
        raise CascadeConfirmationInvalidError()


def compute_preview_token(plan: CascadePlan, catalog_revision: int) -> str:
    """Deterministic sha256 hash representing the exact previewed mutations."""
    delete_items = [
        {"type": item.type, "id": str(item.id)}
        for k in sorted(plan.delete.keys())
        for item in sorted(plan.delete[k], key=lambda x: str(x.id))
    ]

    unlink_items = [
        {"type": u.type, "count": u.count, "description": u.description}
        for u in sorted(plan.unlink, key=lambda x: (x.type, x.count, x.description))
    ]

    clear_items = [
        {"type": c.type, "field": c.field, "count": c.count, "description": c.description}
        for c in sorted(plan.clear, key=lambda x: (x.type, x.field, x.count, x.description))
    ]

    payload = {
        "root": {"type": plan.root.type, "id": str(plan.root.id)},
        "catalog_revision": catalog_revision,
        "delete": delete_items,
        "unlink": unlink_items,
        "clear": clear_items,
        "attribute_values_to_delete_count": plan.attribute_values_to_delete_count,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_effective_attributes(
    category_ids: set[uuid.UUID],
    graph: CascadeGraphSnapshot,
    deleted_category_ids: set[uuid.UUID],
) -> set[uuid.UUID]:
    """Compute effective attribute IDs for a set of surviving categories."""
    reachable_categories: set[uuid.UUID] = set()
    stack = list(category_ids)
    while stack:
        cid = stack.pop()
        if cid in reachable_categories or cid in deleted_category_ids:
            continue
        reachable_categories.add(cid)
        parents = graph.category_parent_ids.get(cid, set())
        stack.extend(
            pid
            for pid in parents
            if pid not in deleted_category_ids and pid not in reachable_categories
        )

    effective_attributes: set[uuid.UUID] = set()
    for cid in reachable_categories:
        effective_attributes.update(graph.category_attributes.get(cid, set()))
    return effective_attributes


class _CascadePlanner:
    """Internal builder orchestrating traversal for a specific root."""

    def __init__(self, root: EntityRef, graph: CascadeGraphSnapshot) -> None:
        self.root = root
        self.graph = graph
        self.delete: dict[str, list[EntityRef]] = {key: [] for key in DELETE_KEYS}
        self.deleted_ids: dict[str, set[uuid.UUID]] = {key: set() for key in DELETE_KEYS}
        self.unlink: list[UnlinkRef] = []
        self.clear: list[ClearRef] = []
        self.attribute_values_to_delete_count: int = 0

    def mark_for_deletion(self, key: str, ref: EntityRef) -> bool:
        if ref.id in self.deleted_ids[key]:
            return False
        self.deleted_ids[key].add(ref.id)
        self.delete[key].append(ref)
        return True

    def get_ref(self, key: str, entity_id: uuid.UUID) -> EntityRef:
        pools: dict[str, dict[uuid.UUID, EntityRef]] = {
            "marks": self.graph.marks,
            "models": self.graph.models,
            "modifications": self.graph.modifications,
            "trims": self.graph.trims,
            "superstructures": self.graph.superstructures,
            "categories": self.graph.categories,
            "attribute_groups": self.graph.attribute_groups,
            "attributes": self.graph.attributes,
            "options": self.graph.options,
            "colors": self.graph.colors,
            "products": self.graph.products,
        }
        pool = pools.get(key)
        if pool is not None and entity_id in pool:
            return pool[entity_id]
        singular = key.rstrip("s")
        if key == "categories":
            singular = "category"
        elif key == "attribute_groups":
            singular = "attribute_group"
        elif key == "superstructures":
            singular = "superstructure"
        return EntityRef(type=singular, id=entity_id)

    def plan_mark(self) -> None:
        self.mark_for_deletion("marks", self.root)
        for mid, mark_id in self.graph.model_mark_ids.items():
            if mark_id == self.root.id:
                self.mark_for_deletion("models", self.get_ref("models", mid))

        self._cascade_models()
        self._clear_mark_links()

    def _cascade_models(self) -> None:
        for mod_id, model_id in self.graph.modification_model_ids.items():
            if model_id in self.deleted_ids["models"]:
                self.mark_for_deletion("modifications", self.get_ref("modifications", mod_id))

        self._cascade_modifications()
        self._cascade_superstructures()

    def _cascade_modifications(self) -> None:
        for tid, mod_id in self.graph.trim_modification_ids.items():
            if mod_id in self.deleted_ids["modifications"]:
                self.mark_for_deletion("trims", self.get_ref("trims", tid))
                self.attribute_values_to_delete_count += len(self.graph.trim_attribute_values.get(tid, {}))

        for mod_id in self.deleted_ids["modifications"]:
            self.attribute_values_to_delete_count += len(self.graph.modification_attribute_values.get(mod_id, {}))

        for pid, mod_id in self.graph.product_modification_ids.items():
            if mod_id in self.deleted_ids["modifications"]:
                self.mark_for_deletion("products", self.get_ref("products", pid))

        self._cascade_superstructures()

    def _cascade_superstructures(self) -> None:
        for entity_id, model_id in self.graph.superstructure_model_ids.items():
            if model_id in self.deleted_ids["models"]:
                if entity_id in self.graph.products:
                    self.mark_for_deletion("products", self.get_ref("products", entity_id))
                elif entity_id in self.graph.superstructures:
                    self.mark_for_deletion("superstructures", self.get_ref("superstructures", entity_id))

        for entity_id, mod_id in self.graph.superstructure_modification_ids.items():
            if mod_id in self.deleted_ids["modifications"]:
                if entity_id in self.graph.products:
                    self.mark_for_deletion("products", self.get_ref("products", entity_id))
                elif entity_id in self.graph.superstructures:
                    self.mark_for_deletion("superstructures", self.get_ref("superstructures", entity_id))

        for pid, superstructure_id in self.graph.product_superstructure_ids.items():
            if superstructure_id is not None and superstructure_id in self.deleted_ids["superstructures"]:
                self.mark_for_deletion("products", self.get_ref("products", pid))

    def _clear_mark_links(self) -> None:
        wh_count = self.graph.warehouse_mark_counts.get(self.root.id, 0)
        if wh_count > 0:
            self.clear.append(
                ClearRef(
                    type="warehouse",
                    field="mark_id",
                    count=wh_count,
                    description=f"У {wh_count} складов будет очищена марка",
                )
            )
        war_count = self.graph.warehouse_access_rule_mark_counts.get(self.root.id, 0)
        if war_count > 0:
            self.clear.append(
                ClearRef(
                    type="warehouse_access_rule",
                    field="mark_id",
                    count=war_count,
                    description=f"У {war_count} правил доступа складов будет очищена марка",
                )
            )

    def plan_model(self) -> None:
        self.mark_for_deletion("models", self.root)
        for mod_id, model_id in self.graph.modification_model_ids.items():
            if model_id == self.root.id:
                self.mark_for_deletion("modifications", self.get_ref("modifications", mod_id))
        self._cascade_models()

    def plan_modification(self) -> None:
        self.mark_for_deletion("modifications", self.root)
        self._cascade_modifications()

    def plan_superstructure(self) -> None:
        self.mark_for_deletion("superstructures", self.root)
        self._cascade_superstructures()

    def plan_trim(self) -> None:
        self.mark_for_deletion("trims", self.root)
        self.attribute_values_to_delete_count += len(self.graph.trim_attribute_values.get(self.root.id, {}))
        prod_count = sum(1 for tid in self.graph.product_trim_ids.values() if tid == self.root.id)
        if prod_count > 0:
            self.clear.append(
                ClearRef(
                    type="product",
                    field="trim_id",
                    count=prod_count,
                    description=f"У {prod_count} объявлений будет очищена комплектация",
                )
            )

    def plan_category(self) -> None:
        self.mark_for_deletion("categories", self.root)
        d_categories = {self.root.id}
        changed = True
        while changed:
            changed = False
            for cid, parents in self.graph.category_parent_ids.items():
                if cid not in d_categories and len(parents) > 0 and parents.issubset(d_categories):
                    d_categories.add(cid)
                    self.mark_for_deletion("categories", self.get_ref("categories", cid))
                    changed = True

        warehouse_count = sum(self.graph.warehouse_category_counts.get(cid, 0) for cid in d_categories)
        if warehouse_count:
            self.clear.append(ClearRef(
                type="warehouse", field="category_id", count=warehouse_count,
                description=f"У {warehouse_count} складов будет очищена категория ТС",
            ))
        surviving_mods = self._resolve_category_modifications(d_categories)
        self._cascade_modifications()
        self._resolve_category_products(d_categories)
        self._enforce_surviving_modification_attributes(surviving_mods, d_categories)

    def _resolve_category_modifications(self, d_categories: set[uuid.UUID]) -> set[uuid.UUID]:
        surviving_mods: set[uuid.UUID] = set()
        unlinked_count = 0
        for mod_id, cat_ids in self.graph.modification_category_ids.items():
            if not cat_ids:
                continue
            if cat_ids.issubset(d_categories):
                self.mark_for_deletion("modifications", self.get_ref("modifications", mod_id))
            elif cat_ids & d_categories:
                unlinked_count += len(cat_ids & d_categories)
                surviving_mods.add(mod_id)

        if unlinked_count > 0:
            self.unlink.append(
                UnlinkRef(
                    type="modification_category",
                    count=unlinked_count,
                    description=f"{unlinked_count} связей модификаций с категориями будут удалены",
                )
            )
        return surviving_mods

    def _resolve_category_products(self, d_categories: set[uuid.UUID]) -> None:
        unlinked_count = 0
        for pid, cat_ids in self.graph.product_category_ids.items():
            if pid in self.deleted_ids["products"]:
                continue
            if cat_ids and cat_ids.issubset(d_categories):
                self.mark_for_deletion("products", self.get_ref("products", pid))
            elif cat_ids & d_categories:
                unlinked_count += len(cat_ids & d_categories)

        if unlinked_count > 0:
            self.unlink.append(
                UnlinkRef(
                    type="product_category",
                    count=unlinked_count,
                    description=f"{unlinked_count} связей объявлений с категориями будут удалены",
                )
            )

    def _enforce_surviving_modification_attributes(
        self, surviving_mods: set[uuid.UUID], d_categories: set[uuid.UUID]
    ) -> None:
        for mod_id in surviving_mods:
            remaining_cats = self.graph.modification_category_ids[mod_id] - d_categories
            allowed_attrs = _get_effective_attributes(remaining_cats, self.graph, d_categories)

            mod_vals = self.graph.modification_attribute_values.get(mod_id, {})
            for aid in mod_vals:
                if aid not in allowed_attrs:
                    self.attribute_values_to_delete_count += 1

            for tid, t_mod_id in self.graph.trim_modification_ids.items():
                if t_mod_id == mod_id:
                    trim_vals = self.graph.trim_attribute_values.get(tid, {})
                    for aid in trim_vals:
                        if aid not in allowed_attrs:
                            self.attribute_values_to_delete_count += 1
                    trim_assignments = self.graph.trim_attributes.get(tid, set())
                    for aid in trim_assignments:
                        if aid not in allowed_attrs and aid not in trim_vals:
                            self.attribute_values_to_delete_count += 1

    def plan_attribute_group(self) -> None:
        self.mark_for_deletion("attribute_groups", self.root)
        attr_count = sum(1 for gid in self.graph.attribute_group_ids.values() if gid == self.root.id)
        if attr_count > 0:
            self.clear.append(
                ClearRef(
                    type="attribute",
                    field="attribute_group_id",
                    count=attr_count,
                    description=f"У {attr_count} характеристик будет очищена группа",
                )
            )
        cat_count = sum(1 for gid in self.graph.category_attribute_group_ids.values() if gid == self.root.id)
        if cat_count > 0:
            self.clear.append(
                ClearRef(
                    type="category_attribute",
                    field="group_id",
                    count=cat_count,
                    description=f"У {cat_count} характеристик категорий будет очищена группа",
                )
            )
        trim_count = sum(1 for gid in self.graph.trim_attribute_group_ids.values() if gid == self.root.id)
        if trim_count > 0:
            self.clear.append(
                ClearRef(
                    type="trim_attribute",
                    field="group_id",
                    count=trim_count,
                    description=f"У {trim_count} характеристик комплектаций будет очищена группа",
                )
            )

    def plan_attribute(self) -> None:
        self.mark_for_deletion("attributes", self.root)
        for oid, aid in self.graph.option_attribute_ids.items():
            if aid == self.root.id:
                self.mark_for_deletion("options", self.get_ref("options", oid))

        for vals in self.graph.modification_attribute_values.values():
            if self.root.id in vals:
                self.attribute_values_to_delete_count += 1
        for vals in self.graph.trim_attribute_values.values():
            if self.root.id in vals:
                self.attribute_values_to_delete_count += 1

    def plan_option(self) -> None:
        self.mark_for_deletion("options", self.root)
        for vals in self.graph.modification_attribute_values.values():
            if any(v == self.root.id for v in vals.values()):
                self.attribute_values_to_delete_count += 1
        for vals in self.graph.trim_attribute_values.values():
            if any(v == self.root.id for v in vals.values()):
                self.attribute_values_to_delete_count += 1

    def plan_color(self) -> None:
        self.mark_for_deletion("colors", self.root)
        body_count = sum(1 for cid in self.graph.product_body_color_ids.values() if cid == self.root.id)
        if body_count > 0:
            self.clear.append(
                ClearRef(
                    type="product",
                    field="body_color_id",
                    count=body_count,
                    description=f"У {body_count} объявлений будет очищен цвет кузова",
                )
            )
        interior_count = sum(1 for cid in self.graph.product_interior_color_ids.values() if cid == self.root.id)
        if interior_count > 0:
            self.clear.append(
                ClearRef(
                    type="product",
                    field="interior_color_id",
                    count=interior_count,
                    description=f"У {interior_count} объявлений будет очищен цвет салона",
                )
            )

    def plan_product(self) -> None:
        self.mark_for_deletion("products", self.root)
        components = self.graph.composite_components.get(self.root.id, set())
        if components:
            self.unlink.append(
                UnlinkRef(
                    type="product_component",
                    count=len(components),
                    description=f"{len(components)} компонентов будут отвязаны от составного объявления",
                )
            )

    def cascade_composites(self) -> None:
        prod_queue = list(self.deleted_ids["products"])
        while prod_queue:
            pid = prod_queue.pop(0)
            for comp_id, components in self.graph.composite_components.items():
                if pid in components and comp_id not in self.deleted_ids["products"]:
                    self.mark_for_deletion("products", self.get_ref("products", comp_id))
                    prod_queue.append(comp_id)

    def collect_blockers(self, norm_type: str) -> CascadeBlockers:
        blockers = CascadeBlockers()
        for p in self.delete["products"]:
            docs = self.graph.product_blockers_by_product.get(p.id, [])
            if docs:
                blockers.products.append(ProductBlocker(product=p, documents=list(docs)))

            kits = self.graph.kit_sources_by_source_product_id.get(p.id, [])
            blocking_kits = [k for k in kits if k.id not in self.deleted_ids["products"]]
            if blocking_kits:
                product_ref = KitSourceProductRef(
                    id=p.id,
                    code=p.code or "",
                    title=p.name or p.code or "",
                )
                blockers.kit_sources.append(
                    KitSourceBlocker(product=product_ref, kits=blocking_kits)
                )

        if norm_type == "marks" and self.root.id in self.deleted_ids["marks"]:
            dist_list = self.graph.distributor_blockers_by_mark.get(self.root.id, [])
            if dist_list:
                blockers.distributors.extend(dist_list)

        target_ids = (
            self.deleted_ids["marks"]
            | self.deleted_ids["models"]
            | self.deleted_ids["modifications"]
            | self.deleted_ids["trims"]
            | self.deleted_ids["superstructures"]
        )
        for sp in self.graph.support_program_blockers:
            matching = [r for r in sp.references if r.id in target_ids]
            if matching:
                blockers.support_programs.append(
                    SupportProgramBlocker(program=sp.program, references=matching)
                )
        return blockers


def build_cascade_plan(
    root: EntityRef,
    graph: CascadeGraphSnapshot,
    max_rows: int = DEFAULT_MAX_CASCADE_ROWS,
    raise_on_too_large: bool = False,
) -> CascadePlan:
    """Build a deterministic cascade plan from a root entity and graph snapshot."""
    norm_type = TYPE_TO_DELETE_KEY.get(root.type.lower().replace("-", "_"))
    if not norm_type:
        raise ValueError(f"Неподдерживаемый тип сущности: {root.type}")

    planner = _CascadePlanner(root, graph)

    dispatch = {
        "marks": planner.plan_mark,
        "models": planner.plan_model,
        "modifications": planner.plan_modification,
        "trims": planner.plan_trim,
        "superstructures": planner.plan_superstructure,
        "categories": planner.plan_category,
        "attribute_groups": planner.plan_attribute_group,
        "attributes": planner.plan_attribute,
        "options": planner.plan_option,
        "colors": planner.plan_color,
        "products": planner.plan_product,
    }
    dispatch[norm_type]()

    planner.cascade_composites()

    cart_items = sum(graph.product_cart_counts.get(p.id, 0) for p in planner.delete["products"])
    favorites = sum(graph.product_favorite_counts.get(p.id, 0) for p in planner.delete["products"])
    user_impact = UserImpact(cart_items=cart_items, favorites=favorites)

    blockers = planner.collect_blockers(norm_type)

    counts = {key: len(planner.delete[key]) for key in DELETE_KEYS}
    total_deleted = sum(counts.values())
    total_unlinked = sum(u.count for u in planner.unlink)
    total_cleared = sum(c.count for c in planner.clear)
    total_affected = total_deleted + total_unlinked + total_cleared + planner.attribute_values_to_delete_count
    is_too_large = total_affected > max_rows

    if raise_on_too_large and is_too_large:
        raise CascadeTooLargeError(total=total_affected, max_rows=max_rows)

    return CascadePlan(
        root=root,
        delete=planner.delete,
        unlink=planner.unlink,
        clear=planner.clear,
        attribute_values_to_delete_count=planner.attribute_values_to_delete_count,
        user_impact=user_impact,
        blockers=blockers,
        counts=counts,
        total_affected=total_affected,
        is_too_large=is_too_large,
    )
