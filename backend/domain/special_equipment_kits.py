"""Pure domain rules and helpers for special equipment superstructures and kits."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from domain.errors import DomainError


class KitInvariantError(DomainError):
    """Business rule violation for kits or superstructures."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SuperstructureAttributeAssignment:
    attribute_id: UUID
    group_id: UUID
    is_required: bool = False
    is_visible: bool = False
    is_filterable: bool = False
    sort_order: int = 0


@dataclass(frozen=True, slots=True)
class ChassisAttributeRule:
    attribute_id: UUID
    group_id: UUID | None
    is_required: bool
    is_visible: bool
    is_filterable: bool
    sort_order: int


@dataclass(frozen=True, slots=True)
class ChassisAttributeContract:
    rules_by_attribute_id: Mapping[UUID, ChassisAttributeRule]

    @property
    def allowed_attribute_ids(self) -> frozenset[UUID]:
        return frozenset(self.rules_by_attribute_id.keys())

    @property
    def required_attribute_ids(self) -> frozenset[UUID]:
        return frozenset(
            attr_id
            for attr_id, rule in self.rules_by_attribute_id.items()
            if rule.is_required
        )


def kit_title(
    superstructure_name: str,
    chassis_mark_name: str,
    chassis_model_name: str,
) -> str:
    """Format storefront / snapshot title for a kit product (Rule К4)."""
    return f"{superstructure_name.strip()} на базе {chassis_mark_name.strip()} {chassis_model_name.strip()}"


def ensure_kit_categories(
    category_ids: Sequence[UUID],
    attachment_branch_category_ids: Collection[UUID],
    allowed_superstructure_category_ids: Collection[UUID] | None = None,
) -> None:
    """Validate kit categories (Rule Ш1).

    At least one category must be provided, none can belong to the attachment branch,
    and all must belong to allowed superstructure categories if specified.
    """
    if not category_ids:
        raise KitInvariantError(
            "Для комплекта техники необходимо указать хотя бы одну категорию размещения",
            code="KIT_ATTACHMENT_CATEGORY",
        )
    attachment_set = frozenset(attachment_branch_category_ids)
    if any(cat_id in attachment_set for cat_id in category_ids):
        raise KitInvariantError(
            "Категории комплекта техники не могут входить в ветку надстроек",
            code="KIT_ATTACHMENT_CATEGORY",
        )
    if allowed_superstructure_category_ids is not None:
        if not allowed_superstructure_category_ids:
            raise KitInvariantError(
                "У выбранного типа надстройки нет разрешенных категорий каталога для размещения комплекта",
                code="KIT_CATEGORY_NOT_ALLOWED",
            )
        allowed_set = frozenset(allowed_superstructure_category_ids)
        if any(cat_id not in allowed_set for cat_id in category_ids):
            raise KitInvariantError(
                "Категория комплекта не входит в список разрешенных категорий выбранного типа надстройки",
                code="KIT_CATEGORY_NOT_ALLOWED",
            )


def ensure_superstructure_card_limit(visible_card_count: int, limit: int = 6) -> None:
    """Rule С4: «В карточке» не больше 6 на тип."""
    if visible_card_count > limit:
        raise KitInvariantError(
            f"Количество характеристик с признаком «В карточке» не может превышать {limit}",
            code="SUPERSTRUCTURE_CARD_LIMIT_EXCEEDED",
        )


def ensure_superstructure_attribute_groups(
    assignments: Sequence[SuperstructureAttributeAssignment],
    attribute_group_by_id: Mapping[UUID, UUID],
) -> None:
    """Rule С3: Каждая назначенная характеристика должна принадлежать указанной группе."""
    seen_attrs: set[UUID] = set()
    card_count = 0
    for assignment in assignments:
        if assignment.attribute_id in seen_attrs:
            raise KitInvariantError(
                "Характеристика не может быть назначена повторно",
                code="SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
            )
        seen_attrs.add(assignment.attribute_id)
        expected_group_id = attribute_group_by_id.get(assignment.attribute_id)
        if expected_group_id != assignment.group_id:
            raise KitInvariantError(
                f"Характеристика {assignment.attribute_id} не принадлежит группе {assignment.group_id}",
                code="SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
            )
        if assignment.sort_order < 0:
            raise KitInvariantError(
                "Порядок сортировки не может быть отрицательным",
                code="SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
            )
        if assignment.is_visible:
            card_count += 1

    ensure_superstructure_card_limit(card_count)


def ensure_kit_superstructure(
    *,
    superstructure_is_active: bool,
    superstructure_source_product_id: UUID | None = None,
    source_product: Mapping[str, Any] | None = None,
    current_product_id: UUID | None = None,
    source_is_attachment: bool = False,
    superstructure_model_id: UUID | None = None,
    superstructure_modification_model_id: UUID | None = None,
    superstructure_name: str | None = None,
    superstructure_manufacturer: str | None = None,
) -> None:
    """Rules Н1–Н5: Проверка типа надстройки и источника/модели."""
    if not superstructure_is_active:
        raise KitInvariantError(
            "Выбранный тип надстройки неактивен",
            code="SUPERSTRUCTURE_NOT_FOUND",
        )
    if superstructure_source_product_id is not None:
        if source_product is None:
            raise KitInvariantError(
                "Объявление-источник надстройки не найдено",
                code="KIT_SUPERSTRUCTURE_SOURCE_INVALID",
            )
        if (
            current_product_id is not None
            and source_product.get("id") == current_product_id
        ):
            raise KitInvariantError(
                "Комплект не может ссылаться на самого себя",
                code="KIT_SUPERSTRUCTURE_SOURCE_INVALID",
            )
        if (
            source_product.get("model_id") is not None
            and source_product.get("superstructure_id") is not None
        ):
            raise KitInvariantError(
                "Объявление-источник не может быть комплектом",
                code="KIT_SUPERSTRUCTURE_SOURCE_INVALID",
            )
        if source_product.get("publication_status") not in ("draft", "published"):
            raise KitInvariantError(
                "Объявление-источник должно иметь статус «Черновик» или «Опубликовано»",
                code="KIT_SUPERSTRUCTURE_SOURCE_INVALID",
            )
        if not source_is_attachment:
            raise KitInvariantError(
                "Объявление-источник должно входить в ветку надстроек",
                code="KIT_SUPERSTRUCTURE_SOURCE_INVALID",
            )
    else:
        if (
            superstructure_model_id is not None
            and superstructure_modification_model_id is not None
            and superstructure_modification_model_id != superstructure_model_id
        ):
            raise KitInvariantError(
                "Модификация надстройки не принадлежит указанной модели",
                code="KIT_SUPERSTRUCTURE_MODIFICATION_MODEL_MISMATCH",
            )
        name = (superstructure_name or "").strip()
        if not (1 <= len(name) <= 255):
            raise KitInvariantError(
                "Для комплекта необходимо указать название надстройки (от 1 до 255 символов)",
                code="KIT_REQUIRED_VALUE_MISSING",
            )
        manufacturer = (superstructure_manufacturer or "").strip()
        if not (1 <= len(manufacturer) <= 255):
            raise KitInvariantError(
                "Для комплекта необходимо указать производителя надстройки (от 1 до 255 символов)",
                code="KIT_REQUIRED_VALUE_MISSING",
            )


def ensure_kit_chassis_values(
    contract: ChassisAttributeContract,
    provided_attribute_ids: Collection[UUID],
    filled_attribute_ids: Collection[UUID],
    has_modification: bool,
    require_mandatory: bool = True,
) -> None:
    """Rules Ш4–Ш5: Проверка значений шасси."""
    if has_modification:
        if provided_attribute_ids:
            raise KitInvariantError(
                "При выбранной модификации шасси собственные характеристики шасси не сохраняются",
                code="KIT_CHASSIS_VALUES_WITH_MODIFICATION",
            )
        return

    # No modification selected: values are validated against category contract
    provided_set = frozenset(provided_attribute_ids)
    foreign_attrs = provided_set - contract.allowed_attribute_ids
    if foreign_attrs:
        raise KitInvariantError(
            "Указаны характеристики шасси, не входящие в правила категорий",
            code="KIT_CHASSIS_ATTRIBUTE_NOT_IN_CATEGORY",
        )

    if require_mandatory:
        filled_set = frozenset(filled_attribute_ids)
        missing_required = contract.required_attribute_ids - filled_set
        if missing_required:
            raise KitInvariantError(
                "Не заполнены обязательные характеристики шасси",
                code="KIT_REQUIRED_VALUE_MISSING",
            )


def ensure_kit_superstructure_values(
    assignments: Sequence[SuperstructureAttributeAssignment],
    provided_attribute_ids: Collection[UUID],
    filled_attribute_ids: Collection[UUID],
    require_mandatory: bool = True,
) -> None:
    """Rule Н3: Значения — только по характеристикам типа."""
    allowed_ids = {a.attribute_id for a in assignments}
    provided_set = frozenset(provided_attribute_ids)
    foreign = provided_set - allowed_ids
    if foreign:
        raise KitInvariantError(
            "Указаны характеристики надстройки, не назначенные выбранному типу",
            code="KIT_SUPERSTRUCTURE_ATTRIBUTE_NOT_ALLOWED",
        )
    if require_mandatory:
        required_ids = {a.attribute_id for a in assignments if a.is_required}
        filled_set = frozenset(filled_attribute_ids)
        missing = required_ids - filled_set
        if missing:
            raise KitInvariantError(
                "Не заполнены обязательные характеристики типа надстройки",
                code="KIT_REQUIRED_VALUE_MISSING",
            )


def values_kept_after_change(
    old_values: Mapping[UUID, Any],
    allowed_attribute_ids: Collection[UUID],
) -> dict[UUID, Any]:
    """Rules Ш6 / Н6: При смене категорий, модели или типа сохранять только общие атрибуты."""
    allowed_set = frozenset(allowed_attribute_ids)
    return {k: v for k, v in old_values.items() if k in allowed_set}


def kit_card_attributes(
    superstructure_rows: Sequence[Mapping[str, Any]],
    chassis_rows: Sequence[Mapping[str, Any]],
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Rule К6: Карточка списка — не больше 6 характеристик.

    Сначала заполненные характеристики надстройки с «В карточке» (в порядке справочника),
    затем заполненные характеристики шасси с «В карточке» по правилам категорий.
    """
    card_items: list[dict[str, Any]] = []

    for row in superstructure_rows:
        if row.get("is_visible") and (
            row.get("display_value") or row.get("value") is not None
        ):
            card_items.append(dict(row))
            if len(card_items) >= limit:
                return card_items

    for row in chassis_rows:
        if row.get("is_visible") and (
            row.get("display_value") or row.get("value") is not None
        ):
            card_items.append(dict(row))
            if len(card_items) >= limit:
                return card_items

    return card_items


def ensure_kit_vins(
    *,
    vin: str | None,
    chassis_vin: str | None,
    superstructure_vin: str | None,
    no_vin: bool,
) -> None:
    """Validate VIN, chassis_vin and superstructure_vin according to Rule Блок 5.

    - If no_vin is True:
        All three VIN fields must be empty/None.
    - If no_vin is False:
        - chassis_vin is required (1 to 32 characters).
        - superstructure_vin is optional, but if provided must be 1 to 32 characters.
    """
    v_norm = (vin or "").strip()
    c_norm = (chassis_vin or "").strip()
    s_norm = (superstructure_vin or "").strip()

    if no_vin:
        if v_norm or c_norm or s_norm:
            raise KitInvariantError(
                "При отметке «Нет VIN» все поля VIN (VIN ТС, VIN шасси, VIN надстройки) должны быть пустыми",
                code="KIT_VIN_NOT_EMPTY",
            )
        return

    if not c_norm:
        raise KitInvariantError(
            "Для комплекта техники необходимо указать VIN шасси",
            code="KIT_CHASSIS_VIN_REQUIRED",
        )
    if len(c_norm) > 32:
        raise KitInvariantError(
            "VIN шасси не может превышать 32 символов",
            code="KIT_CHASSIS_VIN_TOO_LONG",
        )
    if s_norm and len(s_norm) > 32:
        raise KitInvariantError(
            "VIN надстройки не может превышать 32 символов",
            code="KIT_SUPERSTRUCTURE_VIN_TOO_LONG",
        )


def ensure_standalone_superstructure(
    *,
    superstructure_is_active: bool,
    superstructure_id: UUID | None = None,
    allowed_category_ids: Collection[UUID] | None = None,
    category_ids: Collection[UUID] | None = None,
) -> None:
    """Validate standalone superstructure assignment (Rule Блок 7 & Блок 6.4)."""
    if superstructure_id is None:
        return
    if not superstructure_is_active:
        raise KitInvariantError(
            "Выбранный тип надстройки неактивен",
            code="SUPERSTRUCTURE_NOT_FOUND",
        )
    if allowed_category_ids is not None and category_ids is not None:
        allowed_set = frozenset(allowed_category_ids)
        if allowed_set and not any(cid in allowed_set for cid in category_ids):
            raise KitInvariantError(
                "Категория объявления не входит в список разрешенных категорий выбранного типа надстройки",
                code="SUPERSTRUCTURE_CATEGORY_NOT_ALLOWED",
            )

