"""Pure contracts and invariants for special-equipment XLSX imports."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from domain.special_equipment_management import TrimModificationValueConflict


class ImportMode(StrEnum):
    APPEND = "APPEND"
    PATCH = "PATCH"
    FULL_SNAPSHOT = "FULL_SNAPSHOT"


class ImportErrorPolicy(StrEnum):
    ATOMIC = "ATOMIC"
    BEST_EFFORT = "BEST_EFFORT"


class ImportStatus(StrEnum):
    AWAITING_UPLOAD = "awaiting_upload"
    UPLOADED = "uploaded"
    VALIDATING_FILE = "validating_file"
    VALIDATING_DATA = "validating_data"
    TRANSFERRING_IMAGES = "transferring_images"
    PREVIEW_READY = "preview_ready"
    VALIDATION_FAILED = "validation_failed"
    APPLYING = "applying"
    PREVIEW_STALE = "preview_stale"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    FAILED_RETRYABLE = "failed_retryable"
    CANCELLED = "cancelled"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ImportEntityType(StrEnum):
    UNIT = "unit"
    CATEGORY = "category"
    MARK = "mark"
    MODEL = "model"
    MODIFICATION = "modification"
    ATTRIBUTE_GROUP = "attribute_group"
    ATTRIBUTE = "attribute"
    ATTRIBUTE_OPTION = "attribute_option"
    SUPERSTRUCTURE = "superstructure"
    PRODUCT = "product"


class ImportContractError(ValueError):
    """A deterministic client/workbook contract violation."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        column_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or message
        self.column_name = column_name


REFERENCE_NOT_IN_SNAPSHOT = "REFERENCE_NOT_IN_SNAPSHOT"
REFERENCE_NOT_IN_SNAPSHOT_MESSAGE = (
    "Сущность отсутствует в файле полной замены и будет деактивирована"
)


class ReferenceNotInSnapshotError(ImportContractError):
    code = "REFERENCE_NOT_IN_SNAPSHOT"

    def __init__(
        self,
        message: str = REFERENCE_NOT_IN_SNAPSHOT_MESSAGE,
    ) -> None:
        super().__init__(message)
        self.code = "REFERENCE_NOT_IN_SNAPSHOT"


class ImportAggregateSemanticConflictError(Exception):
    """A persisted race makes an import aggregate semantically invalid."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def apply_trim_value_import_policy(
    conflicts: tuple[TrimModificationValueConflict, ...],
    *,
    error_policy: ImportErrorPolicy,
) -> tuple[TrimModificationValueConflict, ...]:
    """Abort ATOMIC imports or return exact rows for BEST_EFFORT rejection."""

    if conflicts and error_policy is ImportErrorPolicy.ATOMIC:
        conflict = conflicts[0]
        raise ImportAggregateSemanticConflictError(
            conflict.message,
            code=conflict.code,
        )
    return conflicts


def trim_value_plan_scope(
    plan: Mapping[str, Iterable[Mapping[str, Any]]],
) -> tuple[
    set[tuple[uuid.UUID, uuid.UUID]],
    set[tuple[uuid.UUID, uuid.UUID]],
    dict[uuid.UUID, uuid.UUID],
]:
    """Extract incoming value markers and trim ownership hints from one plan."""

    modification_markers = {
        (
            uuid.UUID(str(row["values"]["modification_id"])),
            uuid.UUID(str(row["values"]["attribute_id"])),
        )
        for row in plan.get("modification_attribute_values", ())
        if row["operation"] != "DELETE"
    }
    trim_markers = {
        (
            uuid.UUID(str(row["values"]["trim_id"])),
            uuid.UUID(str(row["values"]["attribute_id"])),
        )
        for row in plan.get("trim_attribute_values", ())
        if row["operation"] != "DELETE"
    }
    trim_ids = {trim_id for trim_id, _attribute_id in trim_markers}
    modification_by_trim_hint = {
        uuid.UUID(str(row["id"])): uuid.UUID(
            str(row["values"]["modification_id"])
        )
        for row in plan.get("trims", ())
        if row["operation"] != "DELETE"
        and uuid.UUID(str(row["id"])) in trim_ids
        and row["values"].get("modification_id") is not None
    }
    return modification_markers, trim_markers, modification_by_trim_hint


@dataclass(frozen=True)
class ImportIssue:
    sheet_code: str
    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.ERROR
    row_number: int | None = None
    column_name: str | None = None
    raw_value_preview: str | None = None
    entity_type: str | None = None
    external_key: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


TEMPLATE_VERSION = 9
SUPPORTED_TEMPLATE_VERSIONS = frozenset({TEMPLATE_VERSION})
NULL_TOKEN = "Очистить"  # noqa: S105 - workbook marker, not a credential
PART_SIZE_BYTES = 16 * 1024 * 1024
MAX_PARALLEL_PARTS = 3
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024 * 1024
MAX_UI_ISSUES = 100_000

MANIFEST_HEADERS = ("Параметр", "Значение")
PARAMETERS_SHEET_NAME = "Параметры"
INSTRUCTIONS_SHEET_NAME = "Инструкция"

DATA_SHEET_NAMES: dict[str, str] = {
    "units": "Единицы измерения",
    "marks": "Марки",
    "models": "Модели",
    "modifications": "Модификации",
    "trims": "Комплектации",
    "modification_categories": "Категории модификаций",
    "modification_attribute_values": "Характеристики модификаций",
    "trim_attributes": "Характеристики комплектаций",
    "trim_attribute_values": "Значения комплектаций",
    "categories": "Категории",
    "category_relations": "Связи категорий",
    "attribute_groups": "Группы характеристик",
    "attributes": "Характеристики",
    "attribute_options": "Варианты характеристик",
    "category_attributes": "Характеристики категорий",
    "colors": "Цвета",
    "superstructures": "Надстройки",
    "superstructure_categories": "Категории надстроек",
    "superstructure_attributes": "Характеристики надстроек",
    "products": "Объявления",
    "product_categories": "Категории объявлений",
    "product_chassis_values": "Характеристики шасси объявлений",
    "product_superstructure_values": "Значения надстроек объявлений",
    "product_attachments": "Совместимые надстройки",
}

SUPERSTRUCTURE_NOT_FOUND = "SUPERSTRUCTURE_NOT_FOUND"
SUPERSTRUCTURE_MODIFICATION_MODEL_MISMATCH = (
    "SUPERSTRUCTURE_MODIFICATION_MODEL_MISMATCH"
)
SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH = (
    "SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH"
)
SUPERSTRUCTURE_CARD_LIMIT_EXCEEDED = "SUPERSTRUCTURE_CARD_LIMIT_EXCEEDED"
SUPERSTRUCTURE_MODEL_IN_USE = "SUPERSTRUCTURE_MODEL_IN_USE"
SUPERSTRUCTURE_ATTRIBUTE_IN_USE = "SUPERSTRUCTURE_ATTRIBUTE_IN_USE"
SUPERSTRUCTURE_REQUIRED_VALUE_MISSING = "SUPERSTRUCTURE_REQUIRED_VALUE_MISSING"
SUPERSTRUCTURE_NAME_CONFLICT = "SUPERSTRUCTURE_NAME_CONFLICT"

KIT_SUPERSTRUCTURE_MODIFICATION_MISMATCH = (
    "KIT_SUPERSTRUCTURE_MODIFICATION_MISMATCH"
)
KIT_SUPERSTRUCTURE_MODIFICATION_MODEL_MISMATCH = (
    "KIT_SUPERSTRUCTURE_MODIFICATION_MODEL_MISMATCH"
)
KIT_CHASSIS_MODIFICATION_MODEL_MISMATCH = (
    "KIT_CHASSIS_MODIFICATION_MODEL_MISMATCH"
)
KIT_CHASSIS_VALUES_WITH_MODIFICATION = "KIT_CHASSIS_VALUES_WITH_MODIFICATION"
KIT_CHASSIS_ATTRIBUTE_NOT_IN_CATEGORY = "KIT_CHASSIS_ATTRIBUTE_NOT_IN_CATEGORY"
KIT_REQUIRED_VALUE_MISSING = "KIT_REQUIRED_VALUE_MISSING"
KIT_ATTACHMENT_CATEGORY = "KIT_ATTACHMENT_CATEGORY"
KIT_SUPERSTRUCTURE_MODEL_REQUIRED = "KIT_SUPERSTRUCTURE_MODEL_REQUIRED"
KIT_SUPERSTRUCTURE_SOURCE_INVALID = "KIT_SUPERSTRUCTURE_SOURCE_INVALID"
KIT_SUPERSTRUCTURE_SOURCE_CONFLICT = "KIT_SUPERSTRUCTURE_SOURCE_CONFLICT"
KIT_COMPATIBILITY_FORBIDDEN = "KIT_COMPATIBILITY_FORBIDDEN"

PRODUCT_KIND_CONFLICT = "PRODUCT_KIND_CONFLICT"
PRODUCT_KIND_IMMUTABLE = "PRODUCT_KIND_IMMUTABLE"

UNIT_NOT_FOUND = "UNIT_NOT_FOUND"
UNIT_INACTIVE = "UNIT_INACTIVE"
UNIT_CODE_CONFLICT = "UNIT_CODE_CONFLICT"
UNIT_NAME_CONFLICT = "UNIT_NAME_CONFLICT"

TEMPLATE_VERSION_UNSUPPORTED = "TEMPLATE_VERSION_UNSUPPORTED"


DATA_SHEET_HEADERS: dict[str, tuple[str, ...]] = {
    "units": ("Код", "Название", "Активность"),
    "marks": ("Код", "Название", "Активность"),
    "models": (
        "Код",
        "Название",
        "Код марки",
        "Код категории",
        "Активность",
    ),
    "modifications": (
        "Код",
        "Название",
        "Код модели",
        "Год с",
        "Год по",
        "Активность",
    ),
    "trims": (
        "Код",
        "Название",
        "Код модификации",
        "Порядок",
        "Активность",
    ),
    "modification_categories": (
        "Код модификации",
        "Код категории",
        "Порядок",
        "Основная",
    ),
    "modification_attribute_values": (
        "Код модификации",
        "Код характеристики",
        "Код варианта",
        "Значение",
    ),
    "trim_attributes": (
        "Код модификации",
        "Код комплектации",
        "Код характеристики",
        "Код группы",
        "Обязательная",
        "В фильтре",
        "Порядок",
    ),
    "trim_attribute_values": (
        "Код модификации",
        "Код комплектации",
        "Код характеристики",
        "Код варианта",
        "Значение",
    ),
    "categories": (
        "Код",
        "Название",
        "Картинка",
        "Показатель эксплуатации",
        "Категория надстроек",
        "Отображать в каталоге",
        "Порядок",
        "Активность",
    ),
    "category_relations": (
        "Код родительской категории",
        "Код дочерней категории",
        "Порядок",
    ),
    "attribute_groups": (
        "Код",
        "Название",
        "Порядок",
        "Активность",
    ),
    "attributes": (
        "Код",
        "Название",
        "Код группы по умолчанию",
        "Тип данных",
        "Код единицы измерения",
        "Тип фильтра",
        "Активность",
    ),
    "attribute_options": (
        "Код характеристики",
        "Код варианта",
        "Название",
        "Порядок",
        "Активность",
    ),
    "category_attributes": (
        "Код категории",
        "Код характеристики",
        "Код группы",
        "Обязательная",
        "В фильтре",
        "В карточке",
        "Порядок",
    ),
    "colors": (
        "Код",
        "Название",
        "Применимость",
        "Активность",
    ),
    "superstructures": (
        "Код",
        "Название",
        "Активность",
    ),
    "superstructure_categories": (
        "Код надстройки",
        "Код категории",
    ),
    "superstructure_attributes": (
        "Код надстройки",
        "Код группы",
        "Код характеристики",
        "Обязательная",
        "В карточке",
        "В фильтре",
        "Порядок",
    ),
    "products": (
        "Код",
        "Код модификации",
        "Код комплектации",
        "Код модели",
        "Код надстройки",
        "Код модели надстройки",
        "Код модификации надстройки",
        "Код объявления надстройки",
        "Название надстройки",
        "Производитель надстройки",
        "ИНН продавца",
        "Состояние",
        "Год выпуска",
        "Описание",
        "Код цвета кузова",
        "Код цвета салона",
        "Цена",
        "Специальная цена",
        "Цена по запросу",
        "Цена от",
        "Валюта",
        "Количество владельцев",
        "Нет VIN",
        "VIN транспортного средства",
        "VIN шасси",
        "VIN надстройки",
        "Пробег, км",
        "Моточасы",
        "Статус публикации",
        "Статус продажи",
        "Дата публикации",
        "Ссылка на изображение",
    ),
    "product_categories": (
        "Код объявления",
        "Код категории",
    ),
    "product_chassis_values": (
        "Код объявления",
        "Код характеристики",
        "Код варианта",
        "Значение",
    ),
    "product_superstructure_values": (
        "Код объявления",
        "Код характеристики",
        "Код варианта",
        "Значение",
    ),
    "product_attachments": (
        "Код техники",
        "Код надстройки",
        "Порядок",
    ),
}

DATA_SHEET_FIELDS: dict[str, tuple[str, ...]] = {
    "units": ("code", "name", "is_active"),
    "marks": ("code", "name", "is_active"),
    "models": ("code", "name", "mark_code", "category_code", "is_active"),
    "modifications": (
        "code",
        "name",
        "model_code",
        "year_from",
        "year_to",
        "is_active",
    ),
    "trims": (
        "code",
        "name",
        "modification_code",
        "sort_order",
        "is_active",
    ),
    "modification_categories": (
        "modification_code",
        "category_code",
        "sort_order",
        "is_primary",
    ),
    "modification_attribute_values": (
        "modification_code",
        "attribute_code",
        "option_code",
        "value",
    ),
    "trim_attributes": (
        "modification_code",
        "trim_code",
        "attribute_code",
        "group_code",
        "is_required",
        "is_filterable",
        "sort_order",
    ),
    "trim_attribute_values": (
        "modification_code",
        "trim_code",
        "attribute_code",
        "option_code",
        "value",
    ),
    "categories": (
        "code",
        "name",
        "image_source_url",
        "usage_metric",
        "is_attachment_category",
        "is_visible_in_catalog",
        "sort_order",
        "is_active",
    ),
    "category_relations": (
        "parent_category_code",
        "child_category_code",
        "sort_order",
    ),
    "attribute_groups": (
        "code",
        "name",
        "sort_order",
        "is_active",
    ),
    "attributes": (
        "code",
        "name",
        "group_code",
        "data_type",
        "unit_code",
        "filter_kind",
        "is_active",
    ),
    "attribute_options": (
        "attribute_code",
        "code",
        "name",
        "sort_order",
        "is_active",
    ),
    "category_attributes": (
        "category_code",
        "attribute_code",
        "group_code",
        "is_required",
        "is_filterable",
        "is_card_visible",
        "sort_order",
    ),
    "colors": (
        "code",
        "name",
        "applicability",
        "is_active",
    ),
    "superstructures": (
        "code",
        "name",
        "is_active",
    ),
    "superstructure_categories": (
        "superstructure_code",
        "category_code",
    ),
    "superstructure_attributes": (
        "superstructure_code",
        "group_code",
        "attribute_code",
        "is_required",
        "is_card_visible",
        "is_filterable",
        "sort_order",
    ),
    "products": (
        "code",
        "modification_code",
        "trim_code",
        "model_code",
        "superstructure_code",
        "superstructure_model_code",
        "superstructure_modification_code",
        "superstructure_source_code",
        "superstructure_name",
        "superstructure_manufacturer",
        "seller_inn",
        "condition",
        "manufacture_year",
        "description",
        "body_color_code",
        "interior_color_code",
        "price",
        "special_price",
        "price_on_request",
        "price_from",
        "currency_code",
        "owners_count",
        "no_vin",
        "vin",
        "chassis_vin",
        "superstructure_vin",
        "mileage_km",
        "engine_hours",
        "publication_status",
        "sale_status",
        "published_at",
        "image_source_url",
    ),
    "product_categories": (
        "product_code",
        "category_code",
    ),
    "product_chassis_values": (
        "product_code",
        "attribute_code",
        "option_code",
        "value",
    ),
    "product_superstructure_values": (
        "product_code",
        "attribute_code",
        "option_code",
        "value",
    ),
    "product_attachments": (
        "product_code",
        "attachment_product_code",
        "position",
    ),
}
FULL_SNAPSHOT_REQUIRED_SHEETS = frozenset(DATA_SHEET_HEADERS)

_FAMILY_PLURALS: dict[str, str] = {
    "unit": "units",
    "category": "categories",
    "mark": "marks",
    "model": "models",
    "modification": "modifications",
    "trim": "trims",
    "attribute_group": "attribute_groups",
    "attribute": "attributes",
    "attribute_option": "attribute_options",
    "color": "colors",
    "superstructure": "superstructures",
    "superstructure_category": "superstructure_categories",
    "product": "products",
}

_SPECIAL_EQUIPMENT_FIELD_ALIASES: dict[str, dict[str, str]] = {
    "units": {
        "slug": "Название",
    },
    "models": {
        "mark_id": "Код марки",
        "category_id": "Код категории",
        "slug": "Название",
    },
    "modifications": {
        "model_id": "Код модели",
        "slug": "Название",
    },
    "trims": {
        "modification_id": "Код модификации",
        "slug": "Название",
    },
    "categories": {
        "image_key": "Картинка",
        "is_visible_in_catalog": "Отображать в каталоге",
        "slug": "Название",
    },
    "marks": {
        "slug": "Название",
    },
    "attribute_groups": {
        "slug": "Название",
    },
    "attributes": {
        "attribute_group_id": "Код группы по умолчанию",
        "group_id": "Код группы по умолчанию",
        "unit_id": "Код единицы измерения",
    },
    "attribute_options": {
        "attribute_id": "Код характеристики",
    },
    "category_relations": {
        "parent_id": "Код родительской категории",
        "child_id": "Код дочерней категории",
    },
    "category_attributes": {
        "category_id": "Код категории",
        "attribute_id": "Код характеристики",
        "group_id": "Код группы",
        "is_visible": "В карточке",
        "is_card_visible": "В карточке",
    },
    "superstructures": {
        "slug": "Название",
    },
    "superstructure_categories": {
        "superstructure_id": "Код надстройки",
        "category_id": "Код категории",
    },
    "superstructure_attributes": {
        "superstructure_id": "Код надстройки",
        "group_id": "Код группы",
        "attribute_id": "Код характеристики",
        "is_card_visible": "В карточке",
        "is_visible": "В карточке",
    },
    "modification_categories": {
        "modification_id": "Код модификации",
        "category_id": "Код категории",
    },
    "modification_attribute_values": {
        "modification_id": "Код модификации",
        "attribute_id": "Код характеристики",
        "option_id": "Код варианта",
        "value_number": "Значение",
        "value_text": "Значение",
        "value_boolean": "Значение",
    },
    "trim_attributes": {
        "trim_id": "Код комплектации",
        "attribute_id": "Код характеристики",
        "group_id": "Код группы",
    },
    "trim_attribute_values": {
        "trim_id": "Код комплектации",
        "attribute_id": "Код характеристики",
        "option_id": "Код варианта",
        "value_number": "Значение",
        "value_text": "Значение",
        "value_boolean": "Значение",
    },
    "product_categories": {
        "product_id": "Код объявления",
        "category_id": "Код категории",
    },
    "product_chassis_values": {
        "product_id": "Код объявления",
        "attribute_id": "Код характеристики",
        "option_id": "Код варианта",
        "value_number": "Значение",
        "value_text": "Значение",
        "value_boolean": "Значение",
    },
    "product_superstructure_values": {
        "product_id": "Код объявления",
        "attribute_id": "Код характеристики",
        "option_id": "Код варианта",
        "value_number": "Значение",
        "value_text": "Значение",
        "value_boolean": "Значение",
    },
    "product_attachments": {
        "product_id": "Код техники",
        "attachment_product_id": "Код надстройки",
    },
    "products": {
        "model_id": "Код модели",
        "superstructure_id": "Код надстройки",
        "superstructure_model_id": "Код модели надстройки",
        "superstructure_modification_id": "Код модификации надстройки",
        "superstructure_source_product_id": "Код объявления надстройки",
        "superstructure_name": "Название надстройки",
        "superstructure_manufacturer": "Производитель надстройки",
        "modification_id": "Код модификации",
        "trim_id": "Код комплектации",
        "seller_company_id": "ИНН продавца",
        "body_color_id": "Код цвета кузова",
        "interior_color_id": "Код цвета салона",
        "warehouse_id": "ID склада",
        "image_key": "Ссылка на изображение",
        "slug": "Название",
        "vin": "VIN транспортного средства",
        "chassis_vin": "VIN шасси",
        "superstructure_vin": "VIN надстройки",
    },
}


def special_equipment_column_title(family: str, field_name: str) -> str | None:
    """Return Russian column header for import family sheet and field name."""
    if not family or not field_name:
        return None
    resolved_family = _FAMILY_PLURALS.get(family, family)
    if field_name == "operation":
        return "Действие"
    alias = _SPECIAL_EQUIPMENT_FIELD_ALIASES.get(resolved_family, {}).get(field_name)
    if alias is not None:
        return alias
    fields = DATA_SHEET_FIELDS.get(resolved_family)
    headers = DATA_SHEET_HEADERS.get(resolved_family)
    if fields and headers and field_name in fields:
        return headers[fields.index(field_name)]
    if headers and field_name in headers:
        return field_name
    return None



ENTITY_OPERATIONS: dict[ImportMode, frozenset[str]] = {
    ImportMode.APPEND: frozenset({"ADD"}),
    ImportMode.PATCH: frozenset({"ADD", "SET", "DELETE", "UPSERT"}),
    ImportMode.FULL_SNAPSHOT: frozenset({"ADD", "SET", "UPSERT"}),
}
LINK_OPERATIONS: dict[ImportMode, frozenset[str]] = {
    ImportMode.APPEND: frozenset({"ADD"}),
    ImportMode.PATCH: frozenset({"ADD", "SET", "DELETE", "UPSERT"}),
    ImportMode.FULL_SNAPSHOT: frozenset({"ADD", "SET", "UPSERT"}),
}
VALUE_OPERATIONS: dict[ImportMode, frozenset[str]] = {
    ImportMode.APPEND: frozenset({"SET"}),
    ImportMode.PATCH: frozenset({"SET", "DELETE", "UPSERT"}),
    ImportMode.FULL_SNAPSHOT: frozenset({"SET", "UPSERT"}),
}

# Stable namespace: retries derive the same UUID directly from entity type and code.
_ENTITY_NAMESPACE = uuid.UUID("d79863e8-5724-52dd-bfd3-b466af53de09")
_ENTITY_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_RUSSIAN_OPERATIONS = {
    "Добавить": "ADD",
    "Задать": "SET",
    "Удалить": "DELETE",
}
_RUSSIAN_BOOLEANS = {"Да": True, "Нет": False}
_RUSSIAN_CONDITIONS = {
    "Новое": "new",
    "С пробегом": "used",
    "Б/у": "used",
}
_RUSSIAN_PUBLICATION_STATUSES = {
    "Черновик": "draft",
    "Опубликовано": "published",
    "В архиве": "archived",
}
_RUSSIAN_SALE_STATUSES = {
    "Доступно": "available",
    "Под заказ": "on_order",
    "Зарезервировано": "reserved",
    "Продано": "sold",
    "Недоступно": "unavailable",
}
_RUSSIAN_USAGE_METRICS = {
    "Пробег": "mileage_km",
    "Моточасы": "engine_hours",
}
_RUSSIAN_DATA_TYPES = {
    "Число": "number",
    "Текст": "text",
    "Логическое": "boolean",
    "Список": "select",
}
_RUSSIAN_FILTER_KINDS = {
    "Диапазон": "range",
    "Выбор": "exact",
    "Точное значение": "exact",
    "Поиск": "search",
}
_RUSSIAN_COLOR_APPLICABILITIES = {
    "Только кузов": "body",
    "Только салон": "interior",
    "Кузов и салон": "both",
}


def validate_job_contract(
    *,
    filename: str,
    size: int,
    mode: ImportMode,
    template_version: int,
) -> None:
    if not filename.lower().endswith(".xlsx") or filename.lower().endswith(".xlsm"):
        raise ImportContractError("Only .xlsx files are supported")
    if "/" in filename or "\\" in filename or "\x00" in filename:
        raise ImportContractError("Filename must not contain path components")
    if size <= 0 or size > MAX_FILE_SIZE_BYTES:
        raise ImportContractError("File size is outside the supported range")
    if not isinstance(mode, ImportMode):
        raise ImportContractError("Unsupported import mode")
    if template_version not in SUPPORTED_TEMPLATE_VERSIONS:
        raise ImportContractError("Unsupported template version")


def error_policy_for_mode(mode: ImportMode) -> ImportErrorPolicy:
    if mode is ImportMode.FULL_SNAPSHOT:
        return ImportErrorPolicy.ATOMIC
    return ImportErrorPolicy.BEST_EFFORT


def validate_entity_code(value: str) -> str:
    key = value.strip()
    if not _ENTITY_CODE_RE.fullmatch(key):
        raise ImportContractError("Код имеет недопустимый формат")
    return key


def deterministic_entity_id(
    entity_type: ImportEntityType | str, entity_code: str
) -> uuid.UUID:
    return uuid.uuid5(_ENTITY_NAMESPACE, f"{entity_type!s}:{entity_code}")


def stable_request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_preview_hash(
    *, source_sha256: str, catalog_revision: int, normalized_payload: bytes
) -> str:
    digest = hashlib.sha256()
    digest.update(source_sha256.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(catalog_revision).encode("ascii"))
    digest.update(b"\0")
    digest.update(normalized_payload)
    return digest.hexdigest()


def normalize_operation(value: Any, *, mode: ImportMode, sheet_family: str) -> str:
    if value is None or str(value).strip() == "":
        if mode is ImportMode.APPEND:
            return "ADD"
        if mode is ImportMode.PATCH:
            return "UPSERT"
        if mode is ImportMode.FULL_SNAPSHOT:
            return "UPSERT"
    raw_operation = str(value).strip()
    operation = _RUSSIAN_OPERATIONS.get(raw_operation, "")
    allowed = operations_for_sheet(mode, sheet_family)
    if operation not in allowed:
        expected = ", ".join(
            label
            for label, canonical in _RUSSIAN_OPERATIONS.items()
            if canonical in allowed
        )
        raise ImportContractError(f"Действие должно быть одним из: {expected}")
    return operation


def operations_for_sheet(mode: ImportMode, sheet_family: str) -> frozenset[str]:
    if sheet_family in {
        "marks",
        "models",
        "modifications",
        "trims",
        "categories",
        "attribute_groups",
        "attributes",
        "attribute_options",
        "units",
        "superstructures",
        "colors",
        "products",
    }:
        return ENTITY_OPERATIONS[mode]
    if sheet_family in {
        "modification_categories",
        "trim_attributes",
        "category_relations",
        "category_attributes",
        "product_categories",
        "product_attachments",
        "superstructure_attributes",
        "superstructure_categories",
    }:
        return LINK_OPERATIONS[mode]
    if sheet_family in {
        "modification_attribute_values",
        "trim_attribute_values",
        "product_chassis_values",
        "product_superstructure_values",
    }:
        return VALUE_OPERATIONS[mode]
    raise ImportContractError(f"Unknown data sheet: {sheet_family}")


def parse_bool(value: Any, *, nullable: bool = False) -> bool | None:
    if value is None or str(value).strip() == "":
        if nullable:
            return None
        raise ImportContractError("boolean value is required")
    normalized = str(value).strip()
    if normalized in _RUSSIAN_BOOLEANS:
        return _RUSSIAN_BOOLEANS[normalized]
    raise ImportContractError("Значение должно быть «Да» или «Нет»")


def normalize_condition(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in _RUSSIAN_CONDITIONS.values():
        return normalized
    try:
        return _RUSSIAN_CONDITIONS[normalized]
    except KeyError as exc:
        raise ImportContractError(
            "Состояние должно быть «Новое» или «С пробегом»"
        ) from exc


def normalize_publication_status(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in _RUSSIAN_PUBLICATION_STATUSES.values():
        return normalized
    try:
        return _RUSSIAN_PUBLICATION_STATUSES[normalized]
    except KeyError as exc:
        expected = "», «".join(_RUSSIAN_PUBLICATION_STATUSES)
        raise ImportContractError(
            f"Статус публикации должен быть одним из: «{expected}»"
        ) from exc


def normalize_sale_status(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in _RUSSIAN_SALE_STATUSES.values():
        return normalized
    try:
        return _RUSSIAN_SALE_STATUSES[normalized]
    except KeyError as exc:
        expected = "», «".join(_RUSSIAN_SALE_STATUSES)
        raise ImportContractError(
            f"Статус продажи должен быть одним из: «{expected}»"
        ) from exc


def russian_publication_status(value: str) -> str:
    try:
        return {
            canonical: label
            for label, canonical in _RUSSIAN_PUBLICATION_STATUSES.items()
        }[value]
    except KeyError as exc:
        raise ImportContractError("Неизвестный внутренний статус публикации") from exc


def russian_sale_status(value: str) -> str:
    try:
        return {
            canonical: label for label, canonical in _RUSSIAN_SALE_STATUSES.items()
        }[value]
    except KeyError as exc:
        raise ImportContractError("Неизвестный внутренний статус продажи") from exc


def normalize_usage_metric(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in _RUSSIAN_USAGE_METRICS.values():
        return normalized
    try:
        return _RUSSIAN_USAGE_METRICS[normalized]
    except KeyError as exc:
        raise ImportContractError(
            "Показатель эксплуатации должен быть «Пробег» или «Моточасы»"
        ) from exc


def normalize_data_type(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in _RUSSIAN_DATA_TYPES.values():
        return normalized
    try:
        return _RUSSIAN_DATA_TYPES[normalized]
    except KeyError as exc:
        raise ImportContractError("Неизвестный тип данных характеристики") from exc


def normalize_filter_kind(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in _RUSSIAN_FILTER_KINDS.values():
        return normalized
    try:
        return _RUSSIAN_FILTER_KINDS[normalized]
    except KeyError as exc:
        raise ImportContractError("Неизвестный тип фильтра характеристики") from exc


def normalize_color_applicability(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized in _RUSSIAN_COLOR_APPLICABILITIES.values():
        return normalized
    try:
        return _RUSSIAN_COLOR_APPLICABILITIES[normalized]
    except KeyError as exc:
        raise ImportContractError(
            "Применимость цвета должна быть «Только кузов», «Только салон» "
            "или «Кузов и салон»"
        ) from exc


def patch_cell(value: Any, *, mode: ImportMode, null_token: str) -> Any:
    """Return a marker-aware cell value without conflating blank and NULL."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return _UNCHANGED if mode is ImportMode.PATCH else None
    if str(value).strip() == null_token:
        return None
    return value


class _Unchanged:
    pass


_UNCHANGED = _Unchanged()
UNCHANGED = _UNCHANGED


def make_slug(external_key: str) -> str:
    candidate = _SLUG_RE.sub("-", external_key.strip().lower()).strip("-")
    return candidate[:220] or "item"


def redact_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    if not parsed.scheme or not parsed.netloc:
        return "<invalid-url>"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def validate_https_source_url(raw_url: str, allowed_hosts: frozenset[str]) -> str:
    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() != "https":
        raise ImportContractError("Image URL must use HTTPS")
    if parsed.username or parsed.password:
        raise ImportContractError("Image URL credentials are forbidden")
    if not parsed.hostname or parsed.hostname.lower() not in allowed_hosts:
        raise ImportContractError("Image host is not allowlisted")
    if parsed.port not in {None, 443}:
        raise ImportContractError("Unexpected image URL port")
    return raw_url


PRODUCT_IMAGE_URL_INVALID = "PRODUCT_IMAGE_URL_INVALID"
PRODUCT_IMAGES_LIMIT_EXCEEDED = "PRODUCT_IMAGES_LIMIT_EXCEEDED"
PRODUCT_IMAGE_CLEAR_MIXED = "PRODUCT_IMAGE_CLEAR_MIXED"
PRODUCT_IMAGES_ALL_FAILED = "PRODUCT_IMAGES_ALL_FAILED"
CATEGORY_IMAGE_MULTIPLE = "CATEGORY_IMAGE_MULTIPLE"
IMAGE_FETCH_BUDGET_EXCEEDED = "IMAGE_FETCH_BUDGET_EXCEEDED"

_GDRIVE_HOSTS = frozenset({"drive.google.com", "drive.usercontent.google.com"})
_GDRIVE_FILE_ID_PATH_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)")
_GDRIVE_FILE_ID_QUERY_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")
_IMAGE_CELL_SPLIT_RE = re.compile(r"[,;\r\n]+")


def extract_google_drive_file_id(url: str) -> str | None:
    parsed = urlsplit(url)
    if not parsed.hostname or parsed.hostname.lower() not in _GDRIVE_HOSTS:
        return None
    match = _GDRIVE_FILE_ID_PATH_RE.search(parsed.path)
    if match:
        return match.group(1)
    match = _GDRIVE_FILE_ID_QUERY_RE.search(url)
    if match:
        return match.group(1)
    return None


def image_source_ref(url: str) -> str:
    """Canonical source reference for deduplication and unchanged link reuse."""
    file_id = extract_google_drive_file_id(url)
    if file_id:
        return f"gdrive:{file_id}"
    parsed = urlsplit(url)
    return urlunsplit((
        parsed.scheme.lower(),
        (parsed.netloc or "").lower(),
        parsed.path,
        parsed.query,
        "",
    ))


@dataclass(frozen=True)
class ImageSourceRef:
    source_ref: str
    raw_url: str
    position: int


@dataclass(frozen=True)
class ParsedImageSources:
    refs: list[ImageSourceRef]
    issues: list[ImportIssue]
    is_clear: bool = False
    is_empty: bool = False


def parse_image_source_urls(
    raw: Any,
    *,
    allowed_hosts: frozenset[str],
    limit: int = 50,
) -> ParsedImageSources:
    """Parse, validate, deduplicate, and limit image source URLs from an Excel cell."""
    if raw is None:
        return ParsedImageSources(refs=[], issues=[], is_clear=False, is_empty=True)
    raw_str = str(raw).strip()
    if not raw_str:
        return ParsedImageSources(refs=[], issues=[], is_clear=False, is_empty=True)

    tokens = [part.strip() for part in _IMAGE_CELL_SPLIT_RE.split(raw_str) if part.strip()]
    if not tokens:
        return ParsedImageSources(refs=[], issues=[], is_clear=False, is_empty=True)

    has_clear = any(token == NULL_TOKEN for token in tokens)
    non_clear_tokens = [token for token in tokens if token != NULL_TOKEN]

    if has_clear and non_clear_tokens:
        mixed_issues = [
            ImportIssue(
                sheet_code="Объявления",
                code=PRODUCT_IMAGE_CLEAR_MIXED,
                message="Маркер «Очистить» не может сочетаться со ссылками на изображения",
                severity=IssueSeverity.ERROR,
                column_name="Ссылка на изображение",
                raw_value_preview=raw_str[:300],
            )
        ]
        return ParsedImageSources(refs=[], issues=mixed_issues, is_clear=False, is_empty=False)

    if has_clear and not non_clear_tokens:
        return ParsedImageSources(refs=[], issues=[], is_clear=True, is_empty=False)

    issues: list[ImportIssue] = []
    seen_refs: set[str] = set()
    refs: list[ImageSourceRef] = []

    for idx, token in enumerate(tokens, start=1):
        try:
            validate_https_source_url(token, allowed_hosts)
        except ImportContractError as exc:
            issues.append(
                ImportIssue(
                    sheet_code="Объявления",
                    code=PRODUCT_IMAGE_URL_INVALID,
                    message=f"Фото {idx}: {exc}",
                    severity=IssueSeverity.WARNING,
                    column_name="Ссылка на изображение",
                    raw_value_preview=token[:300],
                )
            )
            continue

        ref = image_source_ref(token)
        if ref in seen_refs:
            continue
        seen_refs.add(ref)
        refs.append(ImageSourceRef(source_ref=ref, raw_url=token, position=idx))

    if len(refs) > limit:
        dropped = len(refs) - limit
        issues.append(
            ImportIssue(
                sheet_code="Объявления",
                code=PRODUCT_IMAGES_LIMIT_EXCEEDED,
                message=f"Число ссылок на изображения превышает лимит {limit} (отброшено: {dropped})",
                severity=IssueSeverity.WARNING,
                column_name="Ссылка на изображение",
            )
        )
        refs = refs[:limit]

    return ParsedImageSources(refs=refs, issues=issues, is_clear=False, is_empty=False)



def is_forbidden_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    # SSRF checks must fail closed.  Checking only the commonly dangerous
    # ranges misses other non-public networks such as carrier-grade NAT
    # (100.64.0.0/10).  Image imports may connect only to globally routable
    # addresses returned for an allowlisted hostname.
    return not address.is_global


TERMINAL_STATUSES = frozenset(
    {
        ImportStatus.VALIDATION_FAILED,
        ImportStatus.COMPLETED,
        ImportStatus.COMPLETED_WITH_WARNINGS,
        ImportStatus.FAILED,
        ImportStatus.CANCELLED,
    }
)
CANCELLABLE_STATUSES = frozenset(
    {
        ImportStatus.AWAITING_UPLOAD,
        ImportStatus.UPLOADED,
        ImportStatus.VALIDATING_FILE,
        ImportStatus.VALIDATING_DATA,
        ImportStatus.TRANSFERRING_IMAGES,
        ImportStatus.PREVIEW_READY,
        ImportStatus.PREVIEW_STALE,
        ImportStatus.FAILED_RETRYABLE,
    }
)


def ensure_can_complete_upload(status: str) -> None:
    if status not in {
        ImportStatus.AWAITING_UPLOAD.value,
        ImportStatus.UPLOADED.value,
    }:
        raise ImportContractError("Upload cannot be completed in the current state")


def ensure_can_apply(status: str, preview_hash: str | None, if_match: str) -> None:
    if (
        status
        in {
            ImportStatus.APPLYING.value,
            ImportStatus.COMPLETED.value,
            ImportStatus.COMPLETED_WITH_WARNINGS.value,
        }
        and preview_hash == if_match
    ):
        return
    if status != ImportStatus.PREVIEW_READY.value:
        raise ImportContractError("Import preview is not ready")
    if not preview_hash or preview_hash != if_match:
        raise ImportContractError("PREVIEW_STALE")


def ensure_can_cancel(status: str) -> None:
    try:
        current = ImportStatus(status)
    except ValueError as exc:
        raise ImportContractError("Unknown import status") from exc
    if current not in CANCELLABLE_STATUSES:
        raise ImportContractError("Import cannot be cancelled in the current state")
