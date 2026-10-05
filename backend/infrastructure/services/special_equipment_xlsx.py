"""Strict, read-only parser for the Russian special-equipment XLSX schema v2."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, TextIO
from uuid import UUID

from openpyxl import Workbook, load_workbook
from openpyxl.cell import Cell

from domain.special_equipment_import import (
    DATA_SHEET_FIELDS,
    DATA_SHEET_HEADERS,
    DATA_SHEET_NAMES,
    INSTRUCTIONS_SHEET_NAME,
    MANIFEST_HEADERS,
    NULL_TOKEN,
    PARAMETERS_SHEET_NAME,
    SUPPORTED_TEMPLATE_VERSIONS,
    TEMPLATE_VERSION,
    TEMPLATE_VERSION_UNSUPPORTED,
    ImportContractError,
    ImportIssue,
    ImportMode,
    error_policy_for_mode,
    normalize_color_applicability,
    normalize_condition,
    normalize_data_type,
    normalize_filter_kind,
    normalize_operation,
    normalize_publication_status,
    normalize_sale_status,
    normalize_usage_metric,
    parse_bool,
    russian_publication_status,
    russian_sale_status,
)

_MAX_ZIP_ENTRIES = 512
_MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 500
_MAX_CELL_TEXT = 100_000

_DATA_SHEET_HEADERS_V8: dict[str, tuple[str, ...]] = {
    "units": ("Код", "Название", "Активность"),
    "marks": ("Код", "Название", "Активность"),
    "models": (
        "Код",
        "Название",
        "Код марки",
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
        "VIN",
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

_DATA_SHEET_FIELDS_V8: dict[str, tuple[str, ...]] = {
    "units": ("code", "name", "is_active"),
    "marks": ("code", "name", "is_active"),
    "models": ("code", "name", "mark_code", "is_active"),
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

_VERSIONED_HEADERS = {
    8: _DATA_SHEET_HEADERS_V8,
    9: DATA_SHEET_HEADERS,
}
_VERSIONED_FIELDS = {
    8: _DATA_SHEET_FIELDS_V8,
    9: DATA_SHEET_FIELDS,
}


@dataclass
class ParsedWorkbook:
    manifest: dict[str, str]
    rows: dict[str, JsonlRows] = field(default_factory=dict)
    sheet_names: list[str] = field(default_factory=list)
    spool_dir: Path | None = None
    adapter_issues: list[ImportIssue] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return sum(len(items) for items in self.rows.values())


class JsonlRows:
    """Re-iterable append-only JSONL rows with O(1) process memory."""

    def __init__(self, path: Path, *, count: int = 0) -> None:
        self.path = path
        self._count = count
        self._writer: TextIO | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, row: dict[str, Any]) -> None:
        encoded = json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
        if self._writer is None:
            self._writer = self.path.open("a", encoding="utf-8")
        self._writer.write(encoded)
        self._writer.write("\n")
        self._count += 1

    def extend(self, rows: Iterable[dict[str, Any]]) -> None:
        if self._writer is None:
            self._writer = self.path.open("a", encoding="utf-8")
        for row in rows:
            self._writer.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=_json_default,
                )
            )
            self._writer.write("\n")
            self._count += 1

    def replace(self, rows: Iterable[dict[str, Any]]) -> None:
        self.close()
        replacement = self.path.with_suffix(".replacement.jsonl")
        count = 0
        with replacement.open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        default=_json_default,
                    )
                )
                stream.write("\n")
                count += 1
        replacement.replace(self.path)
        self._count = count

    def __iter__(self) -> Iterator[dict[str, Any]]:
        self.close()
        with self.path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield dict(json.loads(line))

    def __len__(self) -> int:
        return self._count

    def close(self) -> None:
        if self._writer is not None:
            self._writer.flush()
            self._writer.close()
            self._writer = None


def create_row_stores(root: Path, families: Iterable[str]) -> dict[str, JsonlRows]:
    root.mkdir(parents=True, exist_ok=True)
    return {family: JsonlRows(root / f"{family}.jsonl") for family in families}


def write_rows_archive(
    path: Path,
    *,
    metadata: dict[str, Any],
    rows: dict[str, JsonlRows],
) -> None:
    """Package normalized JSONL files without materializing their contents."""
    manifest = {
        **metadata,
        "row_counts": {family: len(store) for family, store in rows.items()},
    }
    with zipfile.ZipFile(
        path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=_json_default,
            ),
        )
        for family, store in sorted(rows.items()):
            store.close()
            archive.write(store.path, arcname=f"rows/{family}.jsonl")


def read_rows_archive(
    path: Path, *, output_dir: Path
) -> tuple[dict[str, Any], dict[str, JsonlRows]]:
    """Extract a trusted internal normalized artifact with bounded copying."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "manifest.json" not in names:
            raise ImportContractError("NORMALIZED_ARTIFACT_INVALID")
        metadata = json.loads(archive.read("manifest.json"))
        counts = metadata.get("row_counts")
        if not isinstance(counts, dict):
            raise ImportContractError("NORMALIZED_ARTIFACT_INVALID")
        stores: dict[str, JsonlRows] = {}
        for family, raw_count in counts.items():
            if family not in DATA_SHEET_HEADERS:
                raise ImportContractError("NORMALIZED_ARTIFACT_INVALID")
            member = f"rows/{family}.jsonl"
            if member not in names:
                raise ImportContractError("NORMALIZED_ARTIFACT_INVALID")
            target = output_dir / f"{family}.jsonl"
            with archive.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
            stores[family] = JsonlRows(target, count=int(raw_count))
    return metadata, stores


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    raise TypeError(f"Unsupported normalized value: {type(value).__name__}")


def sheet_family(name: str) -> str | None:
    return next(
        (
            family
            for family, sheet_name in DATA_SHEET_NAMES.items()
            if name == sheet_name
        ),
        None,
    )


def preflight_xlsx(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise ImportContractError("XLSX_ZIP_INVALID")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > _MAX_ZIP_ENTRIES:
                raise ImportContractError("XLSX_TOO_MANY_ZIP_ENTRIES")
            total_uncompressed = sum(info.file_size for info in infos)
            total_compressed = sum(max(info.compress_size, 1) for info in infos)
            if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
                raise ImportContractError("XLSX_UNCOMPRESSED_SIZE_EXCEEDED")
            if total_uncompressed / max(total_compressed, 1) > _MAX_COMPRESSION_RATIO:
                raise ImportContractError("XLSX_COMPRESSION_RATIO_EXCEEDED")
            names = {info.filename.casefold() for info in infos}
            if "[content_types].xml" not in names or "xl/workbook.xml" not in names:
                raise ImportContractError("XLSX_OOXML_STRUCTURE_INVALID")
            forbidden = (
                "vbaProject.bin",
                "/externalLinks/",
                "/embeddings/",
                "/activeX/",
                "oleObject",
            )
            for info in infos:
                if any(
                    token.casefold() in info.filename.casefold() for token in forbidden
                ):
                    raise ImportContractError("XLSX_ACTIVE_CONTENT_FORBIDDEN")
                if info.filename.startswith(
                    "xl/worksheets/"
                ) and info.filename.endswith(".xml"):
                    forbidden_code = _stream_forbidden_xml_code(archive, info)
                    if forbidden_code is not None:
                        raise ImportContractError(forbidden_code)
    except zipfile.BadZipFile as exc:
        raise ImportContractError("XLSX_ZIP_INVALID") from exc


def _stream_forbidden_xml_code(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo
) -> str | None:
    needles = {
        b"<mergeCell": "XLSX_MERGED_CELLS_FORBIDDEN",
        b"<f>": "XLSX_FORMULA_FORBIDDEN",
        b"<f ": "XLSX_FORMULA_FORBIDDEN",
        b"<formula": "XLSX_FORMULA_FORBIDDEN",
    }
    overlap = max(len(needle) for needle in needles) - 1
    tail = b""
    with archive.open(info) as stream:
        while chunk := stream.read(64 * 1024):
            window = tail + chunk
            for needle, code in needles.items():
                if needle in window:
                    return code
            tail = window[-overlap:]
    return None


def parse_xlsx(  # noqa: PLR0912, PLR0915
    path: Path,
    *,
    expected_mode: ImportMode,
    expected_template_version: int | None = None,
    spool_dir: Path | None = None,
) -> ParsedWorkbook:
    preflight_xlsx(path)
    try:
        workbook = load_workbook(
            filename=path,
            read_only=True,
            data_only=False,
            keep_links=False,
        )
    except Exception as exc:
        raise ImportContractError("XLSX_OPEN_FAILED") from exc

    try:
        if "manifest" in workbook.sheetnames:
            raise ImportContractError(
                f"Поддерживается только шаблон v{TEMPLATE_VERSION}. Скачайте актуальный шаблон",
                code=TEMPLATE_VERSION_UNSUPPORTED,
            )
        if expected_template_version not in {None, TEMPLATE_VERSION}:
            raise ImportContractError(
                f"Поддерживается только шаблон v{TEMPLATE_VERSION}. Скачайте актуальный шаблон",
                code=TEMPLATE_VERSION_UNSUPPORTED,
            )
        if PARAMETERS_SHEET_NAME not in workbook.sheetnames:
            raise ImportContractError("PARAMETERS_SHEET_MISSING")
        unknown = [
            name
            for name in workbook.sheetnames
            if name not in {PARAMETERS_SHEET_NAME, INSTRUCTIONS_SHEET_NAME}
            and sheet_family(name) is None
        ]
        if unknown:
            raise ImportContractError(f"UNKNOWN_SHEET:{unknown[0]}")

        manifest_sheet = workbook[PARAMETERS_SHEET_NAME]
        manifest_iter = manifest_sheet.iter_rows(values_only=False)
        manifest_header = _header(next(manifest_iter, ()))
        if manifest_header != MANIFEST_HEADERS:
            raise ImportContractError("MANIFEST_HEADER_INVALID")
        manifest: dict[str, str] = {}
        for cells in manifest_iter:
            _ensure_no_formula(cells)
            external_key = _string(cells[0].value if cells else None)
            value = _string(cells[1].value if len(cells) > 1 else None)
            if not external_key and not value:
                continue
            key = _PARAMETER_KEYS.get(external_key)
            if key is None:
                raise ImportContractError("PARAMETERS_KEY_INVALID")
            if not key or key in manifest:
                raise ImportContractError("PARAMETERS_KEY_INVALID")
            manifest[key] = value
        manifest_version = _validate_manifest(
            manifest,
            expected_mode,
            expected_template_version=expected_template_version,
        )
        manifest["mode"] = expected_mode.value
        manifest["error_policy"] = error_policy_for_mode(expected_mode).value

        if spool_dir is None:
            spool_dir = Path(tempfile.mkdtemp(prefix="se-xlsx-rows-"))
        parsed = ParsedWorkbook(
            manifest=manifest,
            sheet_names=list(workbook.sheetnames),
            spool_dir=spool_dir,
        )
        present_families: set[str] = set()
        for name in workbook.sheetnames:
            family = sheet_family(name)
            if family is None:
                continue
            present_families.add(family)
            sheet = workbook[name]
            rows_iter = sheet.iter_rows(values_only=False)
            actual_header = _header(next(rows_iter, ()))
            headers_by_family = _VERSIONED_HEADERS[manifest_version]
            fields_by_family = _VERSIONED_FIELDS[manifest_version]
            if family not in headers_by_family:
                raise ImportContractError(f"UNKNOWN_SHEET:{name}")
            expected_header = headers_by_family[family]
            is_valid_header = actual_header == expected_header
            ignored_product_col_idx: int | None = None
            if (
                not is_valid_header
                and family == "products"
                and "ID склада" in actual_header
            ):
                filtered_header = tuple(h for h in actual_header if h != "ID склада")
                if filtered_header == expected_header:
                    is_valid_header = True
                    ignored_product_col_idx = actual_header.index("ID склада")
            if (
                not is_valid_header
                and family == "categories"
                and manifest_version >= 6
                and len(actual_header) == len(expected_header)
            ):
                image_idx = fields_by_family[family].index("image_source_url")
                if (
                    actual_header[image_idx] == "Ссылка на изображение"
                    and actual_header[:image_idx] == expected_header[:image_idx]
                    and actual_header[image_idx + 1 :] == expected_header[image_idx + 1 :]
                ):
                    is_valid_header = True
            if not is_valid_header:
                raise ImportContractError(f"SHEET_HEADER_INVALID:{name}")
            fields = fields_by_family[family]
            target = parsed.rows.setdefault(
                family, JsonlRows(spool_dir / f"{family}.jsonl")
            )
            for row_number, cells in enumerate(rows_iter, start=2):
                _ensure_no_formula(cells)
                if ignored_product_col_idx is not None:
                    row_cells = [
                        cell
                        for idx, cell in enumerate(cells[: len(actual_header)])
                        if idx != ignored_product_col_idx
                    ]
                else:
                    row_cells = list(cells[: len(expected_header)])
                values = [cell.value for cell in row_cells[: len(expected_header)]]
                if len(values) < len(expected_header):
                    values.extend([None] * (len(expected_header) - len(values)))
                if all(value is None or str(value).strip() == "" for value in values):
                    continue
                row = _normalize_row_values(
                    fields,
                    values,
                    null_token=NULL_TOKEN,
                )
                row["_sheet_code"] = name
                row["_row_number"] = row_number
                row["operation"] = normalize_operation(
                    row.get("operation"), mode=expected_mode, sheet_family=family
                )
                _normalize_catalog_values(row, family=family)
                target.append(row)

        if expected_mode is ImportMode.FULL_SNAPSHOT:
            required_sheets = frozenset(_VERSIONED_HEADERS[manifest_version])
            missing = required_sheets - present_families
            if missing:
                raise ImportContractError(
                    f"FULL_SNAPSHOT_SHEETS_MISSING:{','.join(sorted(missing))}"
                )
        return parsed
    finally:
        workbook.close()


def _header(cells: tuple[Cell, ...] | list[Cell]) -> tuple[str, ...]:
    _ensure_no_formula(cells)
    values = tuple(_string(cell.value) for cell in cells)
    while values and not values[-1]:
        values = values[:-1]
    return values


def _ensure_no_formula(cells: tuple[Cell, ...] | list[Cell]) -> None:
    if any(cell.data_type == "f" for cell in cells):
        raise ImportContractError("XLSX_FORMULA_FORBIDDEN")


def _normalize_cell(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > _MAX_CELL_TEXT:
            raise ImportContractError("CELL_TEXT_TOO_LONG")
        return value.strip()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.isoformat()
    return value


def _normalize_row_values(
    fields: tuple[str, ...],
    values: list[Any],
    *,
    null_token: str,
) -> dict[str, Any]:
    """Preserve explicit NULL separately from a blank PATCH cell."""

    normalized: dict[str, Any] = {}
    clear_fields: list[str] = []
    for field_name, raw_value in zip(fields, values, strict=True):
        value = _normalize_cell(raw_value)
        if isinstance(value, str) and value == null_token:
            normalized[field_name] = None
            clear_fields.append(field_name)
        else:
            normalized[field_name] = value
    if clear_fields:
        normalized["_clear_fields"] = clear_fields
    return normalized


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _validate_manifest(
    manifest: dict[str, str],
    _expected_mode: ImportMode,
    *,
    expected_template_version: int | None,
) -> int:
    required = {"schema_version", "generated_at", "null_token"}
    missing = required - manifest.keys()
    if missing:
        raise ImportContractError(
            f"PARAMETERS_KEYS_MISSING:{','.join(sorted(missing))}"
        )
    allowed = required | {"mode"}
    unknown = manifest.keys() - allowed
    if unknown:
        raise ImportContractError(
            f"PARAMETERS_KEY_UNKNOWN:{next(iter(sorted(unknown)))}"
        )
    try:
        manifest_version = int(manifest["schema_version"])
    except ValueError as exc:
        raise ImportContractError(
            f"Поддерживается только шаблон v{TEMPLATE_VERSION}. Скачайте актуальный шаблон",
            code=TEMPLATE_VERSION_UNSUPPORTED,
        ) from exc
    if manifest_version not in SUPPORTED_TEMPLATE_VERSIONS:
        raise ImportContractError(
            f"Поддерживается только шаблон v{TEMPLATE_VERSION}. Скачайте актуальный шаблон",
            code=TEMPLATE_VERSION_UNSUPPORTED,
        )
    if (
        expected_template_version is not None
        and manifest_version != expected_template_version
    ):
        raise ImportContractError(
            f"Поддерживается только шаблон v{TEMPLATE_VERSION}. Скачайте актуальный шаблон",
            code=TEMPLATE_VERSION_UNSUPPORTED,
        )
    if manifest["null_token"] != NULL_TOKEN:
        raise ImportContractError("PARAMETERS_CLEAR_TOKEN_INVALID")
    try:
        datetime.fromisoformat(manifest["generated_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ImportContractError("PARAMETERS_GENERATED_AT_INVALID") from exc
    return manifest_version


def _build_template(
    *,
    version: int = TEMPLATE_VERSION,
    mode: ImportMode = ImportMode.APPEND,
) -> bytes:
    """Build a versioned Russian workbook with strict per-version sheets."""
    _ = mode
    if version not in _VERSIONED_HEADERS:
        raise ImportContractError("PARAMETERS_VERSION_MISMATCH")
    headers_by_family = _VERSIONED_HEADERS[version]
    workbook = Workbook()
    manifest = workbook.active
    manifest.title = PARAMETERS_SHEET_NAME
    manifest.append(MANIFEST_HEADERS)
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest_rows: list[tuple[str, str]] = [
        ("Версия шаблона", str(version)),
        ("Дата формирования", now),
        ("Маркер очистки", NULL_TOKEN),
    ]
    for item in manifest_rows:
        manifest.append(item)
    for family, headers in headers_by_family.items():
        sheet = workbook.create_sheet(DATA_SHEET_NAMES[family])
        sheet.append(headers)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{sheet.cell(1, len(headers)).coordinate}"
    instructions = workbook.create_sheet(INSTRUCTIONS_SHEET_NAME)
    instructions.append(("Раздел", "Описание"))
    instructions.append(
        (
            "Идентичность",
            "Код задаётся один раз, не изменяется и используется для связей между листами.",
        )
    )
    instructions.append(
        (
            "Изменение",
            f"Пустая ячейка не изменяет поле, «{NULL_TOKEN}» очищает необязательное поле.",
        )
    )
    instructions.append(
        (
            "Единицы измерения",
            (
                "Справочник единиц измерения задаётся в листе «Единицы измерения». "
                "Характеристики ссылаются на единицы измерения через «Код единицы измерения» (unit_code)."
            ),
        )
    )
    instructions.append(
        (
            "Надстройки и характеристики",
            (
                "Справочник надстроек задаётся в листе «Надстройки». "
                "Характеристики надстроек задаются в листе «Характеристики надстроек»."
            ),
        )
    )
    instructions.append(
        (
            "Комплекты (Шасси + надстройка)",
            (
                "При указании «Код надстройки» («superstructure_code») объявление считается комплектом «Шасси + надстройка». "
                "Модель шасси должна совпадать с моделью модификации шасси. "
                "Надстройка комплекта может быть задана двумя способами: "
                "1) Вручную: указываются «Код модели надстройки», «Название надстройки» и «Производитель надстройки» "
                "(опционально также «Код модификации надстройки»); "
                "2) Ссылкой на объявление: указывается «Код объявления надстройки» (одиночное объявление из ветви категорий надстроек). "
                "При указании «Кода объявления надстройки» поля модели, модификации, названия и производителя надстройки должны оставаться пустыми. "
                "Характеристики шасси указываются в листе «Значения характеристик шасси», "
                "характеристики надстройки — в листе «Значения характеристик надстроек». "
                "Комплекты не могут относиться к ветви категорий надстроек и не могут участвовать в связях совместимости."
            ),
        )
    )
    instructions.append(
        (
            "Категория надстроек",
            (
                "Категория надстроек — «Да» или «Нет». Пустая ячейка у новой категории "
                "означает «Нет», у существующей — сохраняет текущее значение."
            ),
        )
    )
    instructions.append(
        (
            "Статус публикации",
            "Допустимые значения: "
            + ", ".join(
                russian_publication_status(value)
                for value in ("draft", "published", "archived")
            )
            + ".",
        )
    )
    instructions.append(
        (
            "Статус продажи",
            "Допустимые значения: "
            + ", ".join(
                russian_sale_status(value)
                for value in (
                    "available",
                    "on_order",
                    "reserved",
                    "sold",
                    "unavailable",
                )
            )
            + ".",
        )
    )
    instructions.append(
        (
            "Состояние и владельцы",
            (
                "Для «Новое» количество владельцев должно быть пустым; "
                "для «С пробегом» укажите целое количество владельцев "
                "не меньше 0. Значение «Б/у» поддерживается для старых файлов."
            ),
        )
    )
    instructions.append(
        (
            "VIN",
            (
                "«VIN транспортного средства» содержит не более 17 символов. "
                "«VIN шасси» обязателен для комплектов при отсутствии чекбокса «Нет VIN». "
                "«VIN надстройки» может быть указан для надстроек и комплектов. "
                "Если VIN отсутствует, укажите «Да» в колонке «Нет VIN» — в этом случае все три поля VIN должны оставаться пустыми."
            ),
        )
    )
    instructions.append(
        (
            "Под заказ",
            (
                "Для статуса «Под заказ» обязательна положительная цена; "
                "такие объявления оформляются только по предоплате."
            ),
        )
    )
    instructions.append(
        (
            "Категории надстроек",
            (
                "Связи типов надстроек с разрешенными категориями задаются в листе «Категории надстроек». "
                "При создании или изменении типа надстройки указываются пары «Код надстройки» и «Код категории». "
                "Признак ветви категорий надстроек задаётся в листе «Категории»."
            ),
        )
    )
    instructions.append(
        (
            "Совместимость",
            (
                "Связи задаются кодами конкретных объявлений техники и "
                "надстроек. В PATCH используйте явные действия; в полной "
                "замене пустой лист очищает все связи. Владелец связи — "
                "обычное одиночное объявление. Надстройка — одиночное "
                "объявление из ветви надстроек. Связь объявления с самим "
                "собой запрещена. Комплекты не могут участвовать в связях совместимости."
            ),
        )
    )
    instructions.append(
        (
            "Изображения",
            (
                "Колонка «Ссылка на изображение» листа «Объявления» задаёт все "
                "фото объявления: ссылки через запятую, точку с запятой или с новой "
                "строки, до 50 штук. Первая ссылка — основное фото. При импорте "
                "фото объявления заменяются списком из файла. Пустая ячейка в "
                f"режиме изменения не меняет фото, «{NULL_TOKEN}» удаляет все. "
                "Для категории указывается одна ссылка в колонке «Картинка»."
            ),
        )
    )
    instructions.append(
        (
            "Специальная цена",
            (
                "Специальная цена должна быть больше нуля и "
                "меньше обычной цены."
            ),
        )
    )
    instructions.append(
        (
            "Комплектации и цвета",
            (
                "Комплектации определяются парой кодов "
                "модификации и комплектации. Цвета задаются отдельным "
                "листом со значениями применимости «Только кузов», "
                "«Только салон» или «Кузов и салон»; объявления "
                "ссылаются на комплектации и цвета по кодам. Значения "
                "характеристик задаются в листе «Значения комплектаций»."
            ),
        )
    )
    instructions.append(
        (
            "Цена по запросу",
            (
                "Если обычная цена и признак режима пусты, объявление "
                "импортируется с режимом «Цена по запросу» без нижней "
                "границы. Цену «от» можно оставить пустой или указать "
                "положительное значение. Обычная и специальная цены "
                "сохраняются как внутренние значения, но не публикуются "
                "в каталоге."
            ),
        )
    )
    instructions.append(
        (
            "Категории",
            (
                "Для категорий изображение указывается в колонке «Картинка»."
            ),
        )
    )
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def build_template_v9(*, mode: ImportMode = ImportMode.APPEND) -> bytes:
    """Build the current v9 workbook with superstructures, units and kits."""
    return _build_template(version=9, mode=mode)


def build_template_v8(*, mode: ImportMode = ImportMode.APPEND) -> bytes:
    """Build the legacy v8 workbook."""
    return _build_template(version=8, mode=mode)


def build_template_v7(*, mode: ImportMode = ImportMode.APPEND) -> bytes:
    """Backwards compatibility alias for template generation."""
    return _build_template(version=TEMPLATE_VERSION, mode=mode)


def export_product_row(  # noqa: PLR0912, PLR0915
    product: Mapping[str, Any],
    *,
    version: int = TEMPLATE_VERSION,
) -> dict[str, Any]:
    """Format product attributes into export dictionary matching versioned columns.

    For kits with superstructure_source, fill 'superstructure_source_code' (Код объявления надстройки)
    and leave manual superstructure fields empty.
    For kits with manual superstructure, fill 'superstructure_model_code' (Код модели надстройки)
    along with name and manufacturer.
    For standalone superstructures, retain 'superstructure_code' and clear kit-only fields.
    """
    fields = _VERSIONED_FIELDS[version]["products"]
    row: dict[str, Any] = dict.fromkeys(fields, None)
    for col_field in fields:
        if col_field in product:
            row[col_field] = product[col_field]

    if "chassis_vin" in fields:
        row["chassis_vin"] = product.get("chassis_vin")
    if "superstructure_vin" in fields:
        row["superstructure_vin"] = product.get("superstructure_vin")

    has_superstructure = bool(
        product.get("superstructure_id") or product.get("superstructure_code")
    )
    has_model = bool(product.get("model_id") or product.get("model_code"))
    has_source = bool(
        product.get("superstructure_source_product_id")
        or product.get("superstructure_source_code")
        or product.get("superstructure_source")
    )
    has_manual_kit = bool(
        product.get("superstructure_name")
        or product.get("superstructure_manufacturer")
        or product.get("superstructure_model_id")
        or product.get("superstructure_model_code")
    )
    is_kit = has_superstructure and (has_model or has_source or has_manual_kit)

    if is_kit:
        superstructure_code = product.get("superstructure_code")
        if not superstructure_code and isinstance(product.get("superstructure"), Mapping):
            superstructure_code = product["superstructure"].get("code")
        row["superstructure_code"] = superstructure_code

        if has_source:
            source_code = product.get("superstructure_source_code")
            if not source_code and isinstance(product.get("superstructure_source"), Mapping):
                source_code = product["superstructure_source"].get("code")
            row["superstructure_source_code"] = source_code
            row["superstructure_model_code"] = None
            row["superstructure_modification_code"] = None
            row["superstructure_name"] = None
            row["superstructure_manufacturer"] = None
        else:
            model_code = product.get("superstructure_model_code")
            if not model_code and isinstance(product.get("superstructure_model"), Mapping):
                model_code = product["superstructure_model"].get("code")
            row["superstructure_source_code"] = None
            row["superstructure_model_code"] = model_code
            row["superstructure_modification_code"] = product.get(
                "superstructure_modification_code"
            )
            row["superstructure_name"] = product.get("superstructure_name")
            row["superstructure_manufacturer"] = product.get("superstructure_manufacturer")
    elif has_superstructure:
        superstructure_code = product.get("superstructure_code")
        if not superstructure_code and isinstance(product.get("superstructure"), Mapping):
            superstructure_code = product["superstructure"].get("code")
        row["superstructure_code"] = superstructure_code
        row["superstructure_model_code"] = None
        row["superstructure_modification_code"] = None
        row["superstructure_source_code"] = None
        row["superstructure_name"] = None
        row["superstructure_manufacturer"] = None
    else:
        row["superstructure_code"] = None
        row["superstructure_model_code"] = None
        row["superstructure_modification_code"] = None
        row["superstructure_source_code"] = None
        row["superstructure_name"] = None
        row["superstructure_manufacturer"] = None

    return row


def format_product_export_cells(
    product: Mapping[str, Any],
    *,
    version: int = TEMPLATE_VERSION,
) -> tuple[Any, ...]:
    """Return tuple of cell values for product export row."""
    row = export_product_row(product, version=version)
    fields = _VERSIONED_FIELDS[version]["products"]
    return tuple(row.get(field) for field in fields)


_PARAMETER_KEYS = {
    "Версия шаблона": "schema_version",
    "Режим": "mode",
    "Дата формирования": "generated_at",
    "Маркер очистки": "null_token",
}

_MODE_LABELS = {
    ImportMode.APPEND: "Только добавление",
    ImportMode.PATCH: "Добавление и изменение",
    ImportMode.FULL_SNAPSHOT: "Полная замена",
}

_BOOLEAN_FIELDS = {
    "is_active",
    "is_required",
    "is_filterable",
    "is_card_visible",
    "is_primary",
    "is_attachment_category",
    "is_visible_in_catalog",
    "no_vin",
    "price_on_request",
}


def _normalize_catalog_values(  # noqa: PLR0912 -- strict per-family workbook map
    row: dict[str, Any], *, family: str
) -> None:
    for field_name in _BOOLEAN_FIELDS.intersection(row):
        value = row[field_name]
        if value is not None and str(value).strip():
            try:
                row[field_name] = parse_bool(value)
            except ImportContractError:
                row[field_name] = value
    if family == "categories":
        if str(row.get("usage_metric") or "").strip():
            row["usage_metric"] = normalize_usage_metric(row.get("usage_metric"))
    elif family == "attributes":
        if str(row.get("data_type") or "").strip():
            row["data_type"] = normalize_data_type(row.get("data_type"))
        if str(row.get("filter_kind") or "").strip():
            row["filter_kind"] = normalize_filter_kind(row.get("filter_kind"))
    elif family == "colors":
        if str(row.get("applicability") or "").strip():
            row["applicability"] = normalize_color_applicability(
                row.get("applicability")
            )
    elif family == "products":
        if str(row.get("condition") or "").strip():
            row["condition"] = normalize_condition(row.get("condition"))
        if str(row.get("publication_status") or "").strip():
            row["publication_status"] = normalize_publication_status(
                row.get("publication_status")
            )
        if str(row.get("sale_status") or "").strip():
            row["sale_status"] = normalize_sale_status(row.get("sale_status"))
