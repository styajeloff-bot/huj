from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from openpyxl import Workbook, load_workbook
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from application import special_equipment_import as import_service
from application import special_equipment_import_v2 as import_v2
from application.tasks import special_equipment_import as import_tasks
from domain.special_equipment_import import (
    DATA_SHEET_FIELDS,
    DATA_SHEET_HEADERS,
    DATA_SHEET_NAMES,
    FULL_SNAPSHOT_REQUIRED_SHEETS,
    NULL_TOKEN,
    REFERENCE_NOT_IN_SNAPSHOT,
    SUPPORTED_TEMPLATE_VERSIONS,
    TEMPLATE_VERSION,
    TEMPLATE_VERSION_UNSUPPORTED,
    ImportContractError,
    ImportErrorPolicy,
    ImportMode,
    error_policy_for_mode,
    normalize_condition,
    normalize_operation,
    normalize_publication_status,
    normalize_sale_status,
    normalize_usage_metric,
    russian_publication_status,
    russian_sale_status,
    special_equipment_column_title,
    validate_job_contract,
)
from infrastructure.repositories import (
    special_equipment_import_repository as import_repository,
)
from infrastructure.services.special_equipment_xlsx import (
    JsonlRows,
    ParsedWorkbook,
    build_template_v7,
    build_template_v8,
    build_template_v9,
    create_row_stores,
    export_product_row,
    format_product_export_cells,
    parse_xlsx,
)
from presentation.schemas.special_equipment_imports import (
    ApplySpecialEquipmentImportRequest,
    CreateSpecialEquipmentImportRequest,
)
from tests.special_equipment_factories import special_equipment_directory

EXPECTED_V7_DATA_SHEETS = tuple(DATA_SHEET_NAMES.values())


def test_v7_contract_uses_exact_russian_sheet_names_and_derived_policy() -> None:
    assert TEMPLATE_VERSION == 9
    assert frozenset({9}) == SUPPORTED_TEMPLATE_VERSIONS
    assert tuple(DATA_SHEET_NAMES.values()) == EXPECTED_V7_DATA_SHEETS
    assert frozenset(DATA_SHEET_HEADERS) == FULL_SNAPSHOT_REQUIRED_SHEETS
    assert error_policy_for_mode(ImportMode.APPEND) is ImportErrorPolicy.BEST_EFFORT
    assert error_policy_for_mode(ImportMode.PATCH) is ImportErrorPolicy.BEST_EFFORT
    assert error_policy_for_mode(ImportMode.FULL_SNAPSHOT) is ImportErrorPolicy.ATOMIC


def test_v7_template_is_entirely_russian_and_has_new_offer_columns() -> None:
    workbook = load_workbook(BytesIO(build_template_v7()), read_only=True)
    try:
        assert workbook.sheetnames == [
            "Параметры",
            *EXPECTED_V7_DATA_SHEETS,
            "Инструкция",
        ]
        forbidden = {
            "slug",
            "external_key",
            "source_code",
            "manufacturer",
            "is_primary",
            "options",
            "ADD",
            "UPDATE",
            "DELETE",
            "true",
            "false",
            "NULL",
        }
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            cells = {
                str(cell.value)
                for row in sheet.iter_rows()
                for cell in row
                if cell.value is not None
            }
            assert not forbidden.intersection(cells)
        for family, sheet_name in DATA_SHEET_NAMES.items():
            if sheet_name not in workbook.sheetnames:
                continue
            headers = tuple(
                cell.value for cell in next(workbook[sheet_name].iter_rows())
            )
            assert headers == DATA_SHEET_HEADERS[family]
        assert "Картинка" in DATA_SHEET_HEADERS["categories"]
        assert {
            "Специальная цена",
            "Ссылка на изображение",
        }.issubset(DATA_SHEET_HEADERS["products"])
        assert "ID склада" not in DATA_SHEET_HEADERS["products"]
        instruction_values = {
            str(cell.value)
            for row in workbook["Инструкция"].iter_rows()
            for cell in row
            if cell.value is not None
        }
        assert any(
            "Черновик, Опубликовано, В архиве" in value for value in instruction_values
        )
        assert any(
            "Доступно, Под заказ, Зарезервировано, Продано, Недоступно" in value
            for value in instruction_values
        )
        assert any("количество владельцев" in value for value in instruction_values)
        assert any(
            "для «С пробегом»" in value and "не меньше 0" in value
            for value in instruction_values
        )
        assert any("не более 17 символов" in value for value in instruction_values)
        assert any("положительная цена" in value for value in instruction_values)
    finally:
        workbook.close()


def test_v7_template_keeps_released_sheets_and_headers_exactly() -> None:
    workbook = load_workbook(BytesIO(build_template_v7()), read_only=True)
    try:
        parameters = dict(workbook["Параметры"].iter_rows(min_row=2, values_only=True))
        assert parameters["Версия шаблона"] == "9"
        assert workbook.sheetnames == [
            "Параметры",
            *EXPECTED_V7_DATA_SHEETS,
            "Инструкция",
        ]
        assert (
            tuple(cell.value for cell in next(workbook["Категории"].iter_rows()))
            == DATA_SHEET_HEADERS["categories"]
        )
        assert (
            tuple(cell.value for cell in next(workbook["Объявления"].iter_rows()))
            == DATA_SHEET_HEADERS["products"]
        )
        assert "Комплектации" in workbook.sheetnames
        assert "Цвета" in workbook.sheetnames
        assert "Единицы измерения" in workbook.sheetnames
        assert "Надстройки" in workbook.sheetnames
        assert "Характеристики надстроек" in workbook.sheetnames
        assert "Характеристики шасси объявлений" in workbook.sheetnames
        assert "Значения надстроек объявлений" in workbook.sheetnames
    finally:
        workbook.close()


def test_v7_template_adds_trim_color_sheets_and_product_codes() -> None:
    workbook = load_workbook(BytesIO(build_template_v7()), read_only=True)
    try:
        assert workbook.sheetnames == [
            "Параметры",
            *EXPECTED_V7_DATA_SHEETS,
            "Инструкция",
        ]
        assert tuple(
            cell.value for cell in next(workbook["Комплектации"].iter_rows())
        ) == (
            "Код",
            "Название",
            "Код модификации",
            "Порядок",
            "Активность",
        )
        assert tuple(
            cell.value
            for cell in next(workbook["Характеристики комплектаций"].iter_rows())
        ) == (
            "Код модификации",
            "Код комплектации",
            "Код характеристики",
            "Код группы",
            "Обязательная",
            "В фильтре",
            "Порядок",
        )
        assert tuple(
            cell.value for cell in next(workbook["Значения комплектаций"].iter_rows())
        ) == (
            "Код модификации",
            "Код комплектации",
            "Код характеристики",
            "Код варианта",
            "Значение",
        )
        assert tuple(cell.value for cell in next(workbook["Цвета"].iter_rows())) == (
            "Код",
            "Название",
            "Применимость",
            "Активность",
        )
        product_headers = tuple(
            cell.value for cell in next(workbook["Объявления"].iter_rows())
        )
        assert "Код комплектации" in product_headers
        assert "Код цвета кузова" in product_headers
        assert "Код цвета салона" in product_headers
    finally:
        workbook.close()


def test_v7_parser_maps_request_price_fields(tmp_path: Path) -> None:
    source = tmp_path / "special-equipment-v7-request-price.xlsx"
    source.write_bytes(
        build_template_v7(mode=ImportMode.APPEND)
    )
    workbook = load_workbook(source)
    sheet = workbook["Объявления"]
    headers = [cell.value for cell in next(sheet.iter_rows())]
    row: list[Any] = [None] * len(headers)
    for header, value in {
        "Код": "request-price-product",
        "Код модификации": "request-price-modification",
        "Цена по запросу": "Да",
        "Цена от": "800000.00",
    }.items():
        if header in headers:
            row[headers.index(header)] = value
    sheet.append(row)
    workbook.save(source)
    workbook.close()

    parsed = parse_xlsx(
        source,
        expected_mode=ImportMode.APPEND,
        expected_template_version=9,
    )
    product = next(iter(parsed.rows["products"]))

    assert product["price_on_request"] is True
    assert product["price_from"] == "800000.00"


def test_v7_parser_maps_trim_color_and_product_code_fields(tmp_path: Path) -> None:
    source = tmp_path / "special-equipment-v7-trim-color.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.APPEND))
    workbook = load_workbook(source)
    workbook["Комплектации"].append(
        ("premium", "Premium", "truck-x", 10, "Да")
    )
    workbook["Характеристики комплектаций"].append(
        ("truck-x", "premium", "power", "engine", "Да", "Да", 5)
    )
    workbook["Значения комплектаций"].append(
        ("truck-x", "premium", "power", None, "250")
    )
    workbook["Цвета"].append(("black", "Чёрный", "Кузов и салон", "Да"))
    product_headers = [cell.value for cell in next(workbook["Объявления"].iter_rows())]
    product_row: list[Any] = [None] * len(product_headers)
    product_values = {
        "Код": "truck-x-premium",
        "Код модификации": "truck-x",
        "Код комплектации": "premium",
        "Код цвета кузова": "black",
        "Код цвета салона": "black",
    }
    for header, value in product_values.items():
        if header in product_headers:
            product_row[product_headers.index(header)] = value
    workbook["Объявления"].append(product_row)
    workbook.save(source)
    workbook.close()

    parsed = parse_xlsx(
        source,
        expected_mode=ImportMode.APPEND,
        expected_template_version=9,
    )

    assert next(iter(parsed.rows["trims"]))["modification_code"] == "truck-x"
    assert next(iter(parsed.rows["trim_attributes"]))["attribute_code"] == "power"
    assert next(iter(parsed.rows["trim_attribute_values"]))["value"] == "250"
    assert next(iter(parsed.rows["colors"]))["applicability"] == "both"
    product = next(iter(parsed.rows["products"]))
    assert product["trim_code"] == "premium"
    assert product["body_color_code"] == "black"
    assert product["interior_color_code"] == "black"


@pytest.mark.asyncio
async def test_v7_normalize_resolves_scoped_trim_colors_and_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "special-equipment-v7-normalize.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.APPEND))
    workbook = load_workbook(source)

    def append(sheet_name: str, values: Mapping[str, Any]) -> None:
        sheet = workbook[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        row = [None] * len(headers)
        for header, value in values.items():
            if header in headers:
                row[headers.index(header)] = value
        sheet.append(row)

    append(
        "Марки",
        {
            "Действие": "Добавить",
            "Код": "kamaz",
            "Название": "КамАЗ",
            "Активность": "Да",
        },
    )
    append(
        "Модели",
        {
            "Действие": "Добавить",
            "Код": "65115",
            "Название": "65115",
            "Код марки": "kamaz",
            "Активность": "Да",
        },
    )
    for modification_code in ("mod-a", "mod-b"):
        append(
            "Модификации",
            {
                "Действие": "Добавить",
                "Код": modification_code,
                "Название": modification_code,
                "Код модели": "65115",
                "Активность": "Да",
            },
        )
        append(
            "Комплектации",
            {
                "Действие": "Добавить",
                "Код": "premium",
                "Название": f"Premium {modification_code}",
                "Код модификации": modification_code,
                "Порядок": 1,
                "Активность": "Да",
            },
        )
        append(
            "Категории модификаций",
            {
                "Действие": "Добавить",
                "Код модификации": modification_code,
                "Код категории": "trucks",
                "Порядок": 0,
                "Основная": "Да",
            },
        )
        if modification_code == "mod-a":
            append(
                "Характеристики модификаций",
                {
                    "Действие": "Задать",
                    "Код модификации": modification_code,
                    "Код характеристики": "power",
                    "Значение": 300,
                },
            )
    append(
        "Категории",
        {
            "Действие": "Добавить",
            "Код": "trucks",
            "Название": "Грузовики",
            "Показатель эксплуатации": "Пробег",
            "Категория надстроек": "Нет",
            "Порядок": 0,
            "Активность": "Да",
        },
    )
    append(
        "Группы характеристик",
        {
            "Действие": "Добавить",
            "Код": "engine",
            "Название": "Двигатель",
            "Порядок": 0,
            "Активность": "Да",
        },
    )
    append(
        "Характеристики",
        {
            "Действие": "Добавить",
            "Код": "power",
            "Название": "Мощность",
            "Код группы по умолчанию": "engine",
            "Тип данных": "Число",
            "Единица измерения": "л.с.",
            "Тип фильтра": "Диапазон",
            "Активность": "Да",
        },
    )
    append(
        "Характеристики категорий",
        {
            "Действие": "Добавить",
            "Код категории": "trucks",
            "Код характеристики": "power",
            "Код группы": "engine",
            "Обязательная": "Да",
            "В фильтре": "Да",
            "В карточке": "Да",
            "Порядок": 0,
        },
    )
    append(
        "Характеристики комплектаций",
        {
            "Действие": "Добавить",
            "Код модификации": "mod-b",
            "Код комплектации": "premium",
            "Код характеристики": "power",
            "Код группы": "engine",
            "Обязательная": "Да",
            "В фильтре": "Да",
            "Порядок": 0,
        },
    )
    append(
        "Значения комплектаций",
        {
            "Действие": "Задать",
            "Код модификации": "mod-b",
            "Код комплектации": "premium",
            "Код характеристики": "power",
            "Значение": 350,
        },
    )
    append(
        "Цвета",
        {
            "Действие": "Добавить",
            "Код": "black",
            "Название": "Чёрный",
            "Применимость": "Только кузов",
            "Активность": "Да",
        },
    )
    append(
        "Цвета",
        {
            "Действие": "Добавить",
            "Код": "gray",
            "Название": "Серый",
            "Применимость": "Только салон",
            "Активность": "Да",
        },
    )
    append(
        "Объявления",
        {
            "Действие": "Добавить",
            "Код": "truck-b",
            "Код модификации": "mod-b",
            "Код комплектации": "premium",
            "Состояние": "Новое",
            "Год выпуска": 2025,
            "Описание": "Новый грузовик",
            "Код цвета кузова": "black",
            "Код цвета салона": "gray",
            "Цена": 10_000_000,
            "Валюта": "RUB",
            "Нет VIN": "Да",
            "Статус публикации": "Черновик",
            "Статус продажи": "Доступно",
        },
    )
    append(
        "Категории объявлений",
        {
            "Действие": "Добавить",
            "Код объявления": "truck-b",
            "Код категории": "trucks",
        },
    )
    workbook.save(source)
    workbook.close()
    parsed = parse_xlsx(
        source,
        expected_mode=ImportMode.APPEND,
        expected_template_version=9,
        spool_dir=tmp_path / "parsed-v7-normalize",
    )

    async def context(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "marks": {},
            "models": {},
            "modifications": {},
            "trims": {},
            "categories": {},
            "attribute_groups": {},
            "attributes": {},
            "attribute_options": {},
            "colors": {},
            "products": {},
            "category_relations": set(),
            "modification_categories": set(),
            "_modification_category_details": {},
            "category_attributes": {},
            "modification_attribute_values": set(),
            "trim_attributes": {},
            "trim_attribute_values": set(),
            "product_categories": set(),
            "product_attachments": set(),
            "_product_component_details": {},
            "companies": {},
            "warehouses": {},
        }

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", context)
    plan, issues, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.APPEND.value},
        workbook=parsed,
        plan_spool_dir=tmp_path / "plan-v7-normalize",
    )

    assert issues.error_count == 0
    trims = {row["values"]["modification_id"]: row for row in plan["trims"]}
    assert len(trims) == 2
    product = next(iter(plan["products"]))
    assert (
        product["values"]["trim_id"]
        == trims[product["values"]["modification_id"]]["id"]
    )
    assert product["values"]["body_color_id"] == next(
        row["id"] for row in plan["colors"] if row["code"] == "black"
    )
    assert product["values"]["interior_color_id"] == next(
        row["id"] for row in plan["colors"] if row["code"] == "gray"
    )
    assert len(plan["trim_attributes"]) == 1
    assert len(plan["trim_attribute_values"]) == 1


def test_v7_template_is_downloadable_with_current_columns() -> None:
    workbook = load_workbook(BytesIO(build_template_v7()), read_only=True)
    try:
        parameters = dict(workbook["Параметры"].iter_rows(min_row=2, values_only=True))
        assert parameters["Версия шаблона"] == "9"
        assert "Картинка" in tuple(
            cell.value for cell in next(workbook["Категории"].iter_rows())
        )
        product_headers = tuple(
            cell.value for cell in next(workbook["Объявления"].iter_rows())
        )
        assert "ID склада" not in product_headers
        assert "Специальная цена" in product_headers
        instruction_sections = {
            row[0]
            for row in workbook["Инструкция"].iter_rows(values_only=True)
            if row[0]
        }
        assert "Изображения" in instruction_sections
        assert "Специальная цена" in instruction_sections
        assert "Единицы измерения" in instruction_sections
        assert "Надстройки и характеристики" in instruction_sections
        assert "Комплекты (Шасси + надстройка)" in instruction_sections
    finally:
        workbook.close()


def test_v7_parser_preserves_patch_image_semantics(tmp_path: Path) -> None:
    source = tmp_path / "special-equipment-v7-images.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.PATCH))
    workbook = load_workbook(source)
    categories = workbook["Категории"]
    categories.append(("category-keep", None, None, None, None, None, None))
    categories.append(
        (
            "category-clear",
            None,
            NULL_TOKEN,
            None,
            None,
            None,
            None,
        )
    )
    products = workbook["Объявления"]
    replace_row: list[Any] = [None] * len(DATA_SHEET_HEADERS["products"])
    replace_row[DATA_SHEET_HEADERS["products"].index("Код")] = "product-replace"
    replace_row[DATA_SHEET_HEADERS["products"].index("Ссылка на изображение")] = (
        "https://media.example.test/primary.png"
    )
    products.append(tuple(replace_row))
    workbook.save(source)
    workbook.close()
    parsed = parse_xlsx(
        source,
        expected_mode=ImportMode.PATCH,
        expected_template_version=9,
    )

    category_rows = list(parsed.rows["categories"])
    assert category_rows[0]["image_source_url"] is None
    assert "image_source_url" not in category_rows[0].get("_clear_fields", [])
    assert category_rows[1]["_clear_fields"] == ["image_source_url"]
    assert next(iter(parsed.rows["products"]))["image_source_url"] == (
        "https://media.example.test/primary.png"
    )


def test_application_prepares_versioned_import_template_artifact() -> None:
    artifact = import_service.request_import_template(
        version=8,
        mode=ImportMode.PATCH,
    )

    assert artifact.content.startswith(b"PK")
    assert len(artifact.digest) == 64
    assert artifact.filename == "special-equipment-v8.xlsx"


def test_v7_template_documents_allowed_compatibility_products() -> None:
    workbook = load_workbook(BytesIO(build_template_v7()), read_only=True)
    try:
        instructions = workbook["Инструкция"]
        instruction_rows = dict(instructions.iter_rows(values_only=True))
        description = instruction_rows["Совместимость"]
        assert isinstance(description, str)
        for required_phrase in (
            "Связи задаются кодами конкретных объявлений техники и надстроек.",
            "В PATCH используйте явные действия; в полной замене пустой лист",
            "Владелец связи — обычное одиночное объявление.",
            "Надстройка — одиночное объявление из ветви надстроек.",
            "Связь объявления с самим собой запрещена.",
            "Комплекты не могут участвовать в связях совместимости.",
        ):
            assert required_phrase in description
    finally:
        workbook.close()


def test_v7_parser_maps_russian_headers_and_values_to_canonical_rows(
    tmp_path: Path,
) -> None:
    source = tmp_path / "special-equipment-v7.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.PATCH))

    workbook = load_workbook(source)
    sheet = workbook["Категории"]
    sheet.append(("cranes", "Краны", None, "Моточасы", "Нет", "Да", 10, "Да"))
    workbook.save(source)
    workbook.close()

    parsed = parse_xlsx(source, expected_mode=ImportMode.PATCH)

    assert parsed.manifest["schema_version"] == "9"
    assert parsed.manifest["mode"] == ImportMode.PATCH.value
    assert parsed.manifest["error_policy"] == ImportErrorPolicy.BEST_EFFORT.value
    assert list(parsed.rows["categories"]) == [
        {
            "_row_number": 2,
            "_sheet_code": "Категории",
            "code": "cranes",
            "image_source_url": None,
            "is_attachment_category": False,
            "is_visible_in_catalog": True,
            "is_active": True,
            "name": "Краны",
            "operation": "UPSERT",
            "sort_order": 10,
            "usage_metric": "engine_hours",
        }
    ]


def test_v7_parser_maps_attachment_relation_sheet(
    tmp_path: Path,
) -> None:
    source = tmp_path / "special-equipment-v7-offerings.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.PATCH))
    workbook = load_workbook(source)
    workbook["Совместимые надстройки"].append(
        ("truck-1", "attachment-1", 3)
    )
    workbook.save(source)
    workbook.close()

    parsed = parse_xlsx(source, expected_mode=ImportMode.PATCH)

    assert list(parsed.rows["product_attachments"]) == [
        {
            "_row_number": 2,
            "_sheet_code": "Совместимые надстройки",
            "attachment_product_code": "attachment-1",
            "operation": "UPSERT",
            "position": 3,
            "product_code": "truck-1",
        }
    ]


@pytest.mark.asyncio
async def test_patch_prunes_links_for_rejected_existing_root_but_keeps_relation_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modification_id = uuid4()
    model_id = uuid4()
    mark_id = uuid4()
    ordinary_category_id = uuid4()
    attachment_category_id = uuid4()
    rejected_product_id = uuid4()
    relation_only_product_id = uuid4()
    attachment_product_id = uuid4()
    rows = create_row_stores(tmp_path / "rejected-root-rows", DATA_SHEET_HEADERS)
    rows["products"].append(
        {
            "_sheet_code": "Объявления",
            "_row_number": 2,
            "_clear_fields": [],
            "operation": "SET",
            "code": "rejected-product",
            "modification_code": "modification-1",
            "currency_code": "USD",
        }
    )
    for row_number, product_code in enumerate(
        ("rejected-product", "relation-only-product"), start=2
    ):
        rows["product_attachments"].append(
            {
                "_sheet_code": "Совместимые надстройки",
                "_row_number": row_number,
                "operation": "SET",
                "product_code": product_code,
                "attachment_product_code": "attachment-product",
                "position": 0,
            }
        )

    def product(product_id: UUID) -> dict[str, Any]:
        return {
            "id": product_id,
            "lock_version": 1,
            "modification_id": modification_id,
            "seller_inn": None,
            "condition": "new",
            "manufacture_year": None,
            "description": None,
            "price": 1_000_000,
            "currency_code": "RUB",
            "owners_count": None,
            "no_vin": True,
            "vin": None,
            "mileage_km": None,
            "engine_hours": None,
            "publication_status": "draft",
            "sale_status": "available",
            "published_at": None,
        }

    context = {
        "marks": {"mark-1": {"id": mark_id, "is_active": True}},
        "models": {
            "model-1": {
                "id": model_id,
                "mark_id": mark_id,
                "is_active": True,
            }
        },
        "modifications": {
            "modification-1": {
                "id": modification_id,
                "model_id": model_id,
                "year_from": None,
                "year_to": None,
                "is_active": True,
            }
        },
        "categories": {
            "ordinary": {
                "id": ordinary_category_id,
                "usage_metric": "mileage",
                "is_active": True,
                "is_attachment_category": False,
            },
            "attachment": {
                "id": attachment_category_id,
                "usage_metric": "engine_hours",
                "is_active": True,
                "is_attachment_category": True,
            },
        },
        "products": {
            "rejected-product": product(rejected_product_id),
            "relation-only-product": product(relation_only_product_id),
            "attachment-product": product(attachment_product_id),
        },
        "companies": {},
        "category_relations": set(),
        "modification_categories": set(),
        "_modification_category_details": {},
        "category_attributes": {},
        "modification_attribute_values": {},
        "product_categories": {
            (rejected_product_id, ordinary_category_id),
            (relation_only_product_id, ordinary_category_id),
            (attachment_product_id, attachment_category_id),
        },
        "product_attachments": set(),
        "_product_component_details": {},
        "attribute_groups": {},
        "attributes": {},
        "attribute_options": {},
    }

    async def get_context(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return context

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", get_context)
    plan, issues, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.PATCH.value},
        workbook=ParsedWorkbook(manifest={}, rows=rows),
        plan_spool_dir=tmp_path / "rejected-root-plan",
    )

    assert "PRODUCT_INVALID" in {issue.code for issue in issues}
    assert list(plan["products"]) == []
    assert {row["_aggregate_code"] for row in plan["product_attachments"]} == {
        "relation-only-product"
    }


def test_target_warehouse_intent_uses_normalized_product_rows() -> None:
    new_vin_id = uuid4()
    existing_vin_id = uuid4()
    no_vin_id = uuid4()
    plan: dict[str, list[dict[str, Any]]] = {
        "products": [
            {
                "id": new_vin_id,
                "code": "new-vin",
                "operation": "ADD",
                "values": {"no_vin": False},
                "_sheet_code": "Объявления",
                "_row_number": 2,
            },
            {
                "id": existing_vin_id,
                "code": "existing-vin",
                "operation": "SET",
                "values": {"no_vin": False},
                "_sheet_code": "Объявления",
                "_row_number": 3,
            },
            {
                "id": no_vin_id,
                "code": "no-vin",
                "operation": "ADD",
                "values": {"no_vin": True},
                "_sheet_code": "Объявления",
                "_row_number": 4,
            },
            {
                "id": uuid4(),
                "code": "deleted-vin",
                "operation": "DELETE",
                "values": {},
                "_sheet_code": "Объявления",
                "_row_number": 5,
            },
        ]
    }

    assert import_tasks._vin_rows_requiring_target_warehouse(plan) == [
        plan["products"][0]
    ]
    assert import_repository._target_warehouse_product_ids(
        plan=plan, mode=ImportMode.APPEND.value
    ) == {new_vin_id}
    assert import_repository._target_warehouse_product_ids(
        plan=plan, mode=ImportMode.PATCH.value
    ) == {new_vin_id, existing_vin_id}
    assert import_repository._target_warehouse_product_ids(
        plan=plan, mode=ImportMode.FULL_SNAPSHOT.value
    ) == {new_vin_id, existing_vin_id}


def test_missing_target_warehouse_prunes_new_vin_and_its_product_operations() -> None:
    rejected_product_id = uuid4()
    retained_product_id = uuid4()
    plan: dict[str, list[dict[str, Any]]] = {
        "products": [
            {
                "id": rejected_product_id,
                "code": "vin-without-warehouse",
                "operation": "ADD",
                "values": {"no_vin": False},
            },
            {
                "id": retained_product_id,
                "code": "valid-no-vin",
                "operation": "ADD",
                "values": {"no_vin": True},
            },
        ],
        "product_categories": [
            {
                "_aggregate_kind": "product",
                "_aggregate_code": "vin-without-warehouse",
                "operation": "SET",
            },
            {
                "_aggregate_kind": "product",
                "_aggregate_code": "valid-no-vin",
                "operation": "SET",
            },
        ],
        "product_attachments": [
            {
                "_aggregate_kind": "product",
                "_aggregate_code": "vin-without-warehouse",
                "operation": "SET",
            }
        ],
    }

    rejected_rows: list[Any] = []
    rejected_count = import_tasks._exclude_products_missing_target_warehouse(
        plan, on_rejected=rejected_rows.append
    )

    assert rejected_count == 1
    assert rejected_rows == [
        {
            "id": rejected_product_id,
            "code": "vin-without-warehouse",
            "operation": "ADD",
            "values": {"no_vin": False},
        }
    ]
    assert [row["code"] for row in plan["products"]] == ["valid-no-vin"]
    assert [row["_aggregate_code"] for row in plan["product_categories"]] == [
        "valid-no-vin"
    ]
    assert plan["product_attachments"] == []
    summary = import_v2.rebuild_summary_for_plan(
        {"errors": 1, "rejectedRows": 1},
        cast("Mapping[str, JsonlRows]", plan),
        ImportMode.PATCH,
    )
    assert summary["acceptedRows"] == 2
    assert summary["changesTotal"] == 2
    assert summary["operationCounts"]["products"]["create"] == 1
    assert summary["operationCounts"]["product_categories"]["update"] == 1


def test_job_target_rejects_foreign_warehouse_owner(tmp_path: Path) -> None:
    target_warehouse_id = uuid4()
    seller_company_id = uuid4()
    plan = create_row_stores(tmp_path / "target-owner", DATA_SHEET_HEADERS)
    plan["products"].append(
        {
            "id": uuid4(),
            "code": "foreign-target",
            "operation": "ADD",
            "values": {
                "no_vin": False,
                "sale_status": "available",
                "seller_company_id": seller_company_id,
                "warehouse_id": None,
            },
            "_sheet_code": "Объявления",
            "_row_number": 2,
            "_aggregate_kind": "product",
            "_aggregate_code": "foreign-target",
        }
    )
    issues = import_v2.V2IssueCollector()
    valid_codes = {"products": {"foreign-target"}}

    import_v2._apply_job_target_warehouse(
        plan,
        target_warehouse_id=target_warehouse_id,
        context={
            "warehouses": {
                str(target_warehouse_id): {
                    "id": target_warehouse_id,
                    "company_id": uuid4(),
                    "dealer_id": None,
                    "status": "active",
                }
            }
        },
        issues=issues,
        valid_codes=valid_codes,
    )

    assert list(plan["products"]) == []
    assert valid_codes["products"] == set()
    assert [issue.code for issue in issues] == ["TARGET_WAREHOUSE_INVALID"]


def test_preview_keeps_target_warehouse_diff_when_generic_changes_exceed_limit() -> None:
    target_warehouse_id = uuid4()
    plan: dict[str, list[dict[str, Any]]] = {
        "marks": [
            {
                "code": f"mark-{index}",
                "operation": "SET",
                "values": {},
            }
            for index in range(50)
        ],
        "products": [
            {
                "_aggregate_code": "moved-product",
                "operation": "SET",
                "values": {"warehouse_id": target_warehouse_id},
                "_warehouse_before": uuid4(),
                "_warehouse_target_applied": True,
            }
        ],
    }

    changes = import_v2._summary_changes(plan)

    assert len(changes) == 50
    assert changes[0] == {
        "entityType": "products",
        "entityCode": "moved-product",
        "operation": "SET",
        "field": "warehouse_id",
        "before": plan["products"][0]["_warehouse_before"],
        "after": target_warehouse_id,
    }


def test_v2_patch_distinguishes_blank_from_explicit_cleanup_marker(
    tmp_path: Path,
) -> None:
    source = tmp_path / "special-equipment-v7-clear.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.PATCH))
    workbook = load_workbook(source)
    workbook["Модификации"].append(
        ("mod-1", None, "model-1", NULL_TOKEN, None, None)
    )
    workbook.save(source)
    workbook.close()

    parsed = parse_xlsx(source, expected_mode=ImportMode.PATCH)
    row = next(iter(parsed.rows["modifications"]))
    merged = import_v2._merge_values(
        row=row,
        current={"name": "Stage V", "year_from": 2020, "year_to": 2025},
        mode=ImportMode.PATCH,
        fields=("name", "year_from", "year_to"),
        required={"name"},
    )

    assert row["_clear_fields"] == ["year_from"]
    assert merged == {"name": "Stage V", "year_from": None, "year_to": 2025}


def test_legacy_v1_manifest_sheet_is_rejected_as_unsupported(tmp_path: Path) -> None:
    source = tmp_path / "legacy.xlsx"
    workbook = Workbook()
    workbook.active.title = "manifest"
    workbook.active.append(("key", "value"))
    workbook.active.append(("schema_version", "1"))
    workbook.save(source)
    workbook.close()

    with pytest.raises(ImportContractError) as exc_info:
        parse_xlsx(source, expected_mode=ImportMode.APPEND)
    assert exc_info.value.code == TEMPLATE_VERSION_UNSUPPORTED
    assert "Поддерживается только шаблон v9" in str(exc_info.value)


@pytest.mark.parametrize("unsupported_version", [1, 2, 3, 4, 5, 6, 7, 8, 10])
def test_legacy_and_future_template_versions_are_rejected(
    tmp_path: Path, unsupported_version: int
) -> None:
    source = tmp_path / f"template-v{unsupported_version}.xlsx"
    workbook = Workbook()
    params = workbook.active
    params.title = "Параметры"
    params.append(("Параметр", "Значение"))
    params.append(("Версия шаблона", str(unsupported_version)))
    params.append(("Дата формирования", "2026-01-01T00:00:00Z"))
    params.append(("Маркер очистки", "__NULL__"))
    workbook.save(source)
    workbook.close()

    with pytest.raises(ImportContractError) as exc_info:
        parse_xlsx(source, expected_mode=ImportMode.APPEND)
    assert exc_info.value.code == TEMPLATE_VERSION_UNSUPPORTED
    assert "Поддерживается только шаблон v9" in str(exc_info.value)


def test_russian_action_and_enums_are_the_only_accepted_external_values() -> None:
    assert (
        normalize_operation("Добавить", mode=ImportMode.PATCH, sheet_family="products")
        == "ADD"
    )
    assert (
        normalize_operation("Задать", mode=ImportMode.PATCH, sheet_family="products")
        == "SET"
    )
    assert (
        normalize_operation(
            "Удалить", mode=ImportMode.PATCH, sheet_family="product_categories"
        )
        == "DELETE"
    )
    assert normalize_condition("Новое") == "new"
    assert normalize_condition("С пробегом") == "used"
    assert normalize_condition("Б/у") == "used"
    with pytest.raises(ImportContractError, match="С пробегом"):
        normalize_condition("неизвестно")
    assert normalize_publication_status("Черновик") == "draft"
    assert normalize_publication_status("Опубликовано") == "published"
    assert normalize_publication_status("В архиве") == "archived"
    assert normalize_sale_status("Доступно") == "available"
    assert normalize_sale_status("Зарезервировано") == "reserved"
    assert normalize_sale_status("Продано") == "sold"
    assert normalize_sale_status("Недоступно") == "unavailable"
    assert normalize_usage_metric("Пробег") == "mileage_km"
    assert normalize_usage_metric("Моточасы") == "engine_hours"

    for invalid in (
        "ADD",
        "SET",
        "DELETE",
        "true",
        "false",
        "invalid_condition",
        "invalid_publication_status",
        "invalid_sale_status",
    ):
        with pytest.raises(ImportContractError):
            if invalid == "invalid_condition":
                normalize_condition(invalid)
            elif invalid == "invalid_publication_status":
                normalize_publication_status(invalid)
            elif invalid == "invalid_sale_status":
                normalize_sale_status(invalid)
            elif invalid in {"true", "false"}:
                normalize_usage_metric(invalid)
            else:
                normalize_operation(
                    invalid, mode=ImportMode.PATCH, sheet_family="products"
                )


def test_status_export_labels_round_trip_to_internal_enums() -> None:
    for canonical in ("draft", "published", "archived"):
        assert (
            normalize_publication_status(russian_publication_status(canonical))
            == canonical
        )
    for canonical in (
        "available",
        "on_order",
        "reserved",
        "sold",
        "unavailable",
    ):
        assert normalize_sale_status(russian_sale_status(canonical)) == canonical


def test_v7_parser_normalizes_russian_statuses_and_preserves_patch_blanks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "statuses.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.PATCH))
    workbook = load_workbook(source)
    products = workbook["Объявления"]
    headers = [cell.value for cell in next(products.iter_rows())]

    def make_row(values_dict: dict[str, Any]) -> list[Any]:
        row: list[Any] = [None] * len(headers)
        for h, v in values_dict.items():
            if h in headers:
                row[headers.index(h)] = v
        return row

    products.append(
        make_row(
            {
                "Код": "product-1",
                "Код модификации": "modification-1",
                "Состояние": "Новое",
                "Год выпуска": 2026,
                "Валюта": "RUB",
                "Нет VIN": "Да",
                "Статус публикации": "Опубликовано",
                "Статус продажи": "Доступно",
            }
        )
    )
    products.append(
        make_row(
            {
                "Код": "product-2",
                "Код модификации": "modification-2",
            }
        )
    )
    workbook.save(source)
    workbook.close()

    rows = list(parse_xlsx(source, expected_mode=ImportMode.PATCH).rows["products"])

    assert rows[0]["publication_status"] == "published"
    assert rows[0]["sale_status"] == "available"
    assert rows[1]["publication_status"] is None
    assert rows[1]["sale_status"] is None


def test_job_contract_has_no_source_or_policy_selector() -> None:
    validate_job_contract(
        filename="спецтехника.xlsx",
        size=1024,
        mode=ImportMode.PATCH,
        template_version=9,
    )
    for unsupported_v in (1, 2, 3, 4, 5, 6, 7, 8, 10):
        with pytest.raises(ImportContractError, match="Unsupported template version"):
            validate_job_contract(
                filename="спецтехника.xlsx",
                size=1024,
                mode=ImportMode.PATCH,
                template_version=unsupported_v,
            )


def test_v7_http_contract_rejects_legacy_knobs() -> None:
    valid = {
        "filename": "спецтехника.xlsx",
        "size": 1024,
        "mode": "PATCH",
        "templateVersion": 9,
    }
    assert CreateSpecialEquipmentImportRequest.model_validate(valid).mode == "PATCH"
    for field, value in (
        ("sourceCode", "employee_excel"),
        ("errorPolicy", "ATOMIC"),
    ):
        with pytest.raises(ValidationError):
            CreateSpecialEquipmentImportRequest.model_validate({**valid, field: value})
    for legacy_ver in (1, 2, 3, 4, 5, 6, 7):
        with pytest.raises(ValidationError):
            CreateSpecialEquipmentImportRequest.model_validate(
                {**valid, "templateVersion": legacy_ver}
            )
    with pytest.raises(ValidationError):
        ApplySpecialEquipmentImportRequest.model_validate(
            {"acceptOptionalImageFailures": True}
        )


def test_v4_artifact_authentication_rejects_tampered_plan(tmp_path: Path) -> None:
    job_id = uuid4()
    plan = create_row_stores(tmp_path / "plan", DATA_SHEET_HEADERS)
    plan["marks"].append(
        {
            "id": str(uuid4()),
            "code": "kamaz",
            "operation": "ADD",
            "values": {"name": "КамАЗ"},
            "_aggregate_kind": "mark",
            "_aggregate_code": "kamaz",
        }
    )
    source_sha256 = "a" * 64
    preview_hash = import_service.compute_preview_hash(
        source_sha256=source_sha256,
        catalog_revision=7,
        plan=plan,
        expected_product_versions={},
    )
    metadata = {
        "schema_version": 5,
        "job_id": str(job_id),
        "source_sha256": source_sha256,
        "catalog_revision": 7,
        "preview_hash": preview_hash,
        "expected_product_versions": {},
        "expected_active_seller_ids": [],
        "expected_modification_value_markers": [],
        "expected_trim_value_markers": [],
    }
    job = {
        "source_sha256": source_sha256,
        "catalog_revision": 7,
        "preview_hash": preview_hash,
    }
    assert import_tasks._validate_normalized_artifact(
        metadata=metadata,
        plan=plan,
        job_id=job_id,
        job=job,
    ) == ({}, set(), set(), set())

    plan["marks"].append(
        {
            "id": str(uuid4()),
            "code": "tampered",
            "operation": "ADD",
            "values": {"name": "Подмена"},
            "_aggregate_kind": "mark",
            "_aggregate_code": "tampered",
        }
    )
    with pytest.raises(
        ImportContractError,
        match="NORMALIZED_ARTIFACT_MISMATCH",
    ):
        import_tasks._validate_normalized_artifact(
            metadata=metadata,
            plan=plan,
            job_id=job_id,
            job=job,
        )


def test_v2_apply_orders_dependencies_and_keeps_owned_links_in_aggregate() -> None:
    parent_id = uuid4()
    child_id = uuid4()
    attribute_id = uuid4()
    group_id = uuid4()
    plan = {
        "marks": [],
        "models": [],
        "modifications": [],
        "modification_categories": [],
        "modification_attribute_values": [],
        "categories": [
            {
                "id": child_id,
                "code": "child",
                "operation": "ADD",
                "_aggregate_kind": "category",
                "_aggregate_code": "child",
            },
            {
                "id": parent_id,
                "code": "parent",
                "operation": "ADD",
                "_aggregate_kind": "category",
                "_aggregate_code": "parent",
            },
        ],
        "category_relations": [
            {
                "operation": "ADD",
                "values": {"parent_id": parent_id, "child_id": child_id},
                "_aggregate_kind": "category",
                "_aggregate_code": "child",
            }
        ],
        "attribute_groups": [
            {
                "id": group_id,
                "code": "main",
                "operation": "ADD",
                "_aggregate_kind": "attribute_group",
                "_aggregate_code": "main",
            }
        ],
        "attributes": [
            {
                "id": attribute_id,
                "code": "power",
                "operation": "ADD",
                "_aggregate_kind": "attribute",
                "_aggregate_code": "power",
            }
        ],
        "attribute_options": [],
        "category_attributes": [
            {
                "operation": "ADD",
                "values": {
                    "category_id": child_id,
                    "attribute_id": attribute_id,
                    "group_id": group_id,
                },
                "_aggregate_kind": "category",
                "_aggregate_code": "child",
            }
        ],
        "products": [],
        "product_categories": [],
    }

    aggregates = import_repository._v2_group_aggregates(plan)
    keys = [key for key, _aggregate in aggregates]

    assert keys.index(("attribute_group", "main")) < keys.index(("category", "child"))
    assert keys.index(("attribute", "power")) < keys.index(("category", "child"))
    assert keys.index(("category", "parent")) < keys.index(("category", "child"))
    child = dict(aggregates)[("category", "child")]
    assert set(child) == {
        "categories",
        "category_relations",
        "category_attributes",
    }


def test_required_modification_attributes_include_ancestor_category_rules() -> None:
    parent_id = uuid4()
    child_id = uuid4()
    required_attribute_id = uuid4()
    modification_id = uuid4()
    context = {
        "_import_mode": "PATCH",
        "category_relations": {(parent_id, child_id)},
        "_planned_category_relations": [],
        "category_attributes": {
            (parent_id, required_attribute_id): {
                "is_required": True,
            }
        },
        "_planned_category_attributes": [],
        "modification_attribute_values": set(),
        "_planned_modification_attribute_values": [
            {
                "operation": "SET",
                "values": {
                    "modification_id": modification_id,
                    "attribute_id": required_attribute_id,
                },
            }
        ],
    }

    assert import_v2._required_attributes_for_categories(
        context=context,
        category_ids=[child_id],
    ) == {required_attribute_id}
    assert import_v2._attributes_for_modification(
        context=context,
        modification_id=modification_id,
    ) == {required_attribute_id}


def test_product_may_use_category_outside_modification_default_categories() -> None:
    product_id = uuid4()
    modification_id = uuid4()
    category_id = uuid4()
    issues = import_v2.V2IssueCollector()
    row = {
        "_code": "listing-1",
        "_id": product_id,
        "_sheet_code": "Объявления",
        "_row_number": 2,
        "operation": "ADD",
        "modification_code": "modification-1",
        "seller_inn": None,
        "condition": "new",
        "manufacture_year": 2025,
        "description": "Новая техника",
        "price": 1_000_000,
        "currency_code": "RUB",
        "owners_count": None,
        "no_vin": True,
        "vin": None,
        "mileage_km": None,
        "engine_hours": None,
        "publication_status": "draft",
        "sale_status": "available",
        "published_at": None,
    }
    context = {
        "modifications": {
            "modification-1": {
                "id": modification_id,
            }
        },
        "products": {},
        "categories": {
            "unrelated-category": {
                "id": category_id,
                "usage_metric": "engine_hours",
            }
        },
        "companies": {},
        "modification_categories": set(),
        "_planned_modification_categories": set(),
        "_planned_category_metrics": {},
    }

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is not None
    assert issues.error_count == 0
    assert normalized["values"]["modification_id"] == modification_id


def test_import_rejects_vin_when_no_vin_is_selected() -> None:
    row, context, category_id = _published_product_case()
    row["no_vin"] = True
    row["vin"] = "VIN-MUST-NOT-BE-DROPPED"
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is None
    assert issues.error_count == 1
    assert "поле VIN должно быть пустым" in issues[0].message


def test_import_rejects_search_filter_for_non_text_attribute() -> None:
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_directory_entity(
        family="attributes",
        row={
            "_sheet_code": "Характеристики",
            "_row_number": 2,
            "_code": "power",
            "operation": "ADD",
            "name": "Мощность",
            "group_code": None,
            "data_type": "number",
            "unit": "л.с.",
            "filter_kind": "search",
            "is_active": True,
        },
        mode=ImportMode.APPEND,
        context={},
        identity={},
        valid_codes={},
        issues=issues,
    )

    assert normalized is None
    assert issues.error_count == 1
    assert "только для текстовой характеристики" in issues[0].message.lower()


def test_import_allows_category_attribute_without_group_override(
    tmp_path: Path,
) -> None:
    category_id = uuid4()
    attribute_id = uuid4()
    plan = create_row_stores(tmp_path / "nullable-group", DATA_SHEET_HEADERS)
    issues = import_v2.V2IssueCollector()

    import_v2._normalize_category_attributes(
        plan=plan,
        rows=[
            {
                "_sheet_code": "Характеристики категорий",
                "_row_number": 2,
                "operation": "ADD",
                "category_code": "trucks",
                "attribute_code": "power",
                "group_code": None,
                "is_required": True,
                "is_filterable": True,
                "is_card_visible": True,
                "sort_order": 0,
            }
        ],
        identity={
            "categories": {"trucks": category_id},
            "attributes": {"power": attribute_id},
        },
        valid_codes={
            "categories": {"trucks"},
            "attributes": {"power"},
        },
        mode=ImportMode.APPEND,
        context={},
        issues=issues,
    )

    assert issues.error_count == 0
    assert next(iter(plan["category_attributes"]))["values"]["group_id"] is None


def test_patch_category_attribute_clears_group_but_preserves_blank_fields(
    tmp_path: Path,
) -> None:
    category_id = uuid4()
    attribute_id = uuid4()
    old_group_id = uuid4()
    plan = create_row_stores(tmp_path / "clear-category-group", DATA_SHEET_HEADERS)
    issues = import_v2.V2IssueCollector()

    import_v2._normalize_category_attributes(
        plan=plan,
        rows=[
            {
                "_sheet_code": "Характеристики категорий",
                "_row_number": 2,
                "_clear_fields": ["group_code"],
                "operation": "SET",
                "category_code": "trucks",
                "attribute_code": "power",
                "group_code": None,
                "is_required": None,
                "is_filterable": None,
                "is_card_visible": None,
                "sort_order": None,
            }
        ],
        identity={},
        valid_codes={},
        mode=ImportMode.PATCH,
        context={
            "categories": {"trucks": {"id": category_id}},
            "attributes": {"power": {"id": attribute_id}},
            "category_attributes": {
                (category_id, attribute_id): {
                    "group_id": old_group_id,
                    "is_required": True,
                    "is_filterable": False,
                    "is_visible": True,
                    "sort_order": 7,
                }
            },
        },
        issues=issues,
    )

    values = next(iter(plan["category_attributes"]))["values"]
    assert issues.error_count == 0
    assert values == {
        "category_id": str(category_id),
        "attribute_id": str(attribute_id),
        "group_id": None,
        "is_required": True,
        "is_filterable": False,
        "is_visible": True,
        "sort_order": 7,
    }


def test_import_orders_modification_categories_and_selects_one_primary(
    tmp_path: Path,
) -> None:
    modification_id = uuid4()
    category_a = uuid4()
    category_b = uuid4()
    plan = create_row_stores(tmp_path / "ordered-categories", DATA_SHEET_HEADERS)
    issues = import_v2.V2IssueCollector()

    import_v2._normalize_modification_categories(
        plan=plan,
        rows=[
            {
                "_sheet_code": "Категории модификаций",
                "_row_number": 2,
                "operation": "ADD",
                "modification_code": "crane",
                "category_code": "secondary",
                "sort_order": 20,
                "is_primary": False,
            },
            {
                "_sheet_code": "Категории модификаций",
                "_row_number": 3,
                "operation": "ADD",
                "modification_code": "crane",
                "category_code": "primary",
                "sort_order": 10,
                "is_primary": True,
            },
        ],
        identity={
            "modifications": {"crane": modification_id},
            "categories": {"secondary": category_a, "primary": category_b},
        },
        valid_codes={
            "modifications": {"crane"},
            "categories": {"secondary", "primary"},
        },
        mode=ImportMode.APPEND,
        context={},
        issues=issues,
    )

    values = [row["values"] for row in plan["modification_categories"]]
    assert issues.error_count == 0
    assert sum(item["is_primary"] for item in values) == 1
    primary = next(item for item in values if item["is_primary"])
    secondary = next(item for item in values if not item["is_primary"])
    assert UUID(str(primary["category_id"])) == category_b
    assert primary["sort_order"] == 0
    assert secondary["sort_order"] == 1


def test_patch_modification_categories_preserves_existing_primary_and_order(
    tmp_path: Path,
) -> None:
    modification_id = uuid4()
    primary_id = uuid4()
    secondary_id = uuid4()
    added_id = uuid4()
    plan = create_row_stores(tmp_path / "patch-ordered-categories", DATA_SHEET_HEADERS)
    issues = import_v2.V2IssueCollector()

    import_v2._normalize_modification_categories(
        plan=plan,
        rows=[
            {
                "_sheet_code": "Категории модификаций",
                "_row_number": 2,
                "operation": "ADD",
                "modification_code": "crane",
                "category_code": "added",
                "sort_order": None,
                "is_primary": False,
            }
        ],
        identity={},
        valid_codes={},
        mode=ImportMode.PATCH,
        context={
            "modifications": {"crane": {"id": modification_id}},
            "categories": {"added": {"id": added_id}},
            "_modification_category_details": {
                modification_id: {
                    primary_id: {"sort_order": 0, "is_primary": True},
                    secondary_id: {"sort_order": 1, "is_primary": False},
                }
            },
        },
        issues=issues,
    )

    values = [row["values"] for row in plan["modification_categories"]]
    assert issues.error_count == 0
    assert [UUID(str(row["category_id"])) for row in values] == [
        primary_id,
        secondary_id,
        added_id,
    ]
    assert [row["sort_order"] for row in values] == [0, 1, 2]
    assert [row["is_primary"] for row in values] == [True, False, False]


def test_patch_requires_explicit_primary_when_current_primary_is_deleted(
    tmp_path: Path,
) -> None:
    modification_id = uuid4()
    primary_id = uuid4()
    secondary_id = uuid4()
    plan = create_row_stores(tmp_path / "patch-primary-delete", DATA_SHEET_HEADERS)
    issues = import_v2.V2IssueCollector()

    import_v2._normalize_modification_categories(
        plan=plan,
        rows=[
            {
                "_sheet_code": "Категории модификаций",
                "_row_number": 2,
                "operation": "DELETE",
                "modification_code": "crane",
                "category_code": "primary",
                "sort_order": None,
                "is_primary": None,
            }
        ],
        identity={},
        valid_codes={},
        mode=ImportMode.PATCH,
        context={
            "modifications": {"crane": {"id": modification_id}},
            "categories": {"primary": {"id": primary_id}},
            "_modification_category_details": {
                modification_id: {
                    primary_id: {"sort_order": 0, "is_primary": True},
                    secondary_id: {"sort_order": 1, "is_primary": False},
                }
            },
        },
        issues=issues,
    )

    assert len(plan["modification_categories"]) == 0
    assert {issue.code for issue in issues} == {
        "MODIFICATION_PRIMARY_CATEGORY_REQUIRED"
    }


def _published_product_case() -> tuple[dict[str, Any], dict[str, Any], UUID]:
    product_id = uuid4()
    mark_id = uuid4()
    model_id = uuid4()
    modification_id = uuid4()
    category_id = uuid4()
    seller_id = uuid4()
    row = {
        "_code": "listing-1",
        "_id": product_id,
        "_sheet_code": "Объявления",
        "_row_number": 2,
        "operation": "ADD",
        "modification_code": "modification-1",
        "seller_inn": "7700000000",
        "condition": "new",
        "manufacture_year": 2025,
        "description": "Новая техника",
        "price": 1_000_000,
        "currency_code": "RUB",
        "owners_count": None,
        "no_vin": True,
        "vin": None,
        "mileage_km": None,
        "engine_hours": None,
        "publication_status": "published",
        "sale_status": "available",
        "published_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    context = {
        "marks": {
            "mark-1": {
                "id": mark_id,
                "is_active": True,
            }
        },
        "models": {
            "model-1": {
                "id": model_id,
                "mark_id": mark_id,
                "is_active": True,
            }
        },
        "modifications": {
            "modification-1": {
                "id": modification_id,
                "model_id": model_id,
                "year_from": 2020,
                "year_to": 2026,
                "is_active": True,
            }
        },
        "products": {},
        "categories": {
            "category-1": {
                "id": category_id,
                "usage_metric": "engine_hours",
                "is_active": True,
            }
        },
        "companies": {
            "7700000000": {
                "id": seller_id,
                "is_active": True,
            }
        },
        "modification_categories": set(),
        "_planned_modification_categories": set(),
        "_planned_category_metrics": {},
    }
    return row, context, category_id


def test_v3_product_normalizer_accepts_compatible_warehouse_special_price_and_image() -> (
    None
):
    row, context, category_id = _published_product_case()
    warehouse_id = uuid4()
    seller_id = context["companies"]["7700000000"]["id"]
    context["warehouses"] = {
        str(warehouse_id): {
            "id": warehouse_id,
            "company_id": seller_id,
            "dealer_id": None,
            "status": "active",
        }
    }
    row.update(
        warehouse_id=str(warehouse_id),
        special_price="900000.00",
        image_source_url="https://media.example.test/listing.webp",
    )
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is not None
    assert normalized["values"]["warehouse_id"] is None
    assert normalized["values"]["special_price"] == 900_000
    assert normalized["values"]["_image_action"] == "replace"
    assert normalized["values"]["_image_source_url"].startswith("https://")
    assert issues.error_count == 0


def test_v3_patch_blank_keeps_offer_fields_and_image_clear_is_explicit() -> None:
    row, context, category_id = _published_product_case()
    warehouse_id = uuid4()
    seller_id = context["companies"]["7700000000"]["id"]
    context["warehouses"] = {
        str(warehouse_id): {
            "id": warehouse_id,
            "company_id": seller_id,
            "dealer_id": None,
            "status": "active",
        }
    }
    context["products"] = {
        row["_code"]: {
            "id": row["_id"],
            "seller_company_id": seller_id,
            "warehouse_id": warehouse_id,
            "special_price": Decimal("900000.00"),
        }
    }
    row.update(
        operation="SET",
        seller_inn=None,
        warehouse_id=None,
        special_price=None,
        image_source_url=None,
    )
    issues = import_v2.V2IssueCollector()

    unchanged = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.PATCH,
        context=context,
        issues=issues,
    )

    assert unchanged is not None
    assert unchanged["values"]["seller_company_id"] == seller_id
    assert unchanged["values"]["warehouse_id"] is None
    assert unchanged["values"]["special_price"] == Decimal("900000.00")
    assert "_image_action" not in unchanged["values"]

    cleared = import_v2._normalize_product(
        row={**row, "_clear_fields": ["image_source_url"]},
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.PATCH,
        context=context,
        issues=issues,
    )

    assert cleared is not None
    assert cleared["values"]["_image_action"] == "clear"
    assert issues.error_count == 0


def test_v4_full_snapshot_preserves_existing_request_price_mode() -> None:
    row, context, category_id = _published_product_case()
    row["operation"] = "SET"
    context["products"] = {
        row["_code"]: {
            "id": row["_id"],
            "price_on_request": True,
            "price_from": Decimal("800000.00"),
            "published_at": datetime(2026, 1, 1, tzinfo=UTC),
        }
    }
    assert "price_on_request" not in row
    assert "price_from" not in row
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={"modifications": {"modification-1"}},
        mode=ImportMode.FULL_SNAPSHOT,
        context=context,
        issues=issues,
    )

    assert normalized is not None
    assert normalized["values"]["price_on_request"] is True
    assert normalized["values"]["price_from"] == Decimal("800000.00")
    assert issues.error_count == 0


def test_v5_new_product_infers_request_price_when_price_and_flag_are_blank() -> None:
    row, context, category_id = _published_product_case()
    row.update(price=None, price_on_request=None, price_from=None)
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is not None
    assert normalized["values"]["price_on_request"] is True
    assert normalized["values"]["price_from"] is None
    assert issues.error_count == 0


def test_v5_new_product_infers_fixed_mode_when_price_is_filled() -> None:
    row, context, category_id = _published_product_case()
    row.update(price=1_000_000, price_on_request=None, price_from=None)
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is not None
    assert normalized["values"]["price_on_request"] is False
    assert normalized["values"]["price"] == Decimal("1000000.00")
    assert normalized["values"]["price_from"] is None
    assert issues.error_count == 0


def test_v5_patch_can_clear_request_price_bound_without_changing_mode() -> None:
    row, context, category_id = _published_product_case()
    row.update(
        operation="SET",
        price_on_request=None,
        price_from=None,
        _clear_fields=["price_from"],
    )
    context["products"] = {
        row["_code"]: {
            "id": row["_id"],
            "price_on_request": True,
            "price_from": Decimal("800000.00"),
            "published_at": datetime(2026, 1, 1, tzinfo=UTC),
        }
    }
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.PATCH,
        context=context,
        issues=issues,
    )

    assert normalized is not None
    assert normalized["values"]["price_on_request"] is True
    assert normalized["values"]["price_from"] is None
    assert issues.error_count == 0


def test_v5_request_price_without_bound_allows_on_order_product() -> None:
    row, context, category_id = _published_product_case()
    row.update(
        price=None,
        price_on_request=True,
        price_from=None,
        sale_status="on_order",
    )
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is not None
    assert normalized["values"]["price_on_request"] is True
    assert normalized["values"]["price_from"] is None
    assert issues.error_count == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("special_price", "1000000.00", "меньше заданной обычной цены"),
        ("special_price", "0", "больше нуля"),
    ],
)
def test_v3_product_normalizer_rejects_invalid_special_price(
    field: str,
    value: str,
    message: str,
) -> None:
    row, context, category_id = _published_product_case()
    row[field] = value
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is None
    assert message in issues[0].message
    assert issues[0].column_name == "Специальная цена"


def test_v3_product_normalizer_ignores_warehouse_id_column() -> None:
    row, context, category_id = _published_product_case()
    warehouse_id = uuid4()
    context["warehouses"] = {
        str(warehouse_id): {
            "id": warehouse_id,
            "company_id": uuid4(),
            "dealer_id": None,
            "status": "active",
        }
    }
    row["warehouse_id"] = str(warehouse_id)
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is not None
    assert normalized["values"]["warehouse_id"] is None
    assert issues.error_count == 0


def test_v4_color_applicability_narrowing_uses_product_references() -> None:
    color_id = uuid4()
    row = {
        "_code": "black",
        "_id": color_id,
        "_sheet_code": "Цвета",
        "_row_number": 2,
        "operation": "SET",
        "name": None,
        "applicability": "body",
        "is_active": None,
    }
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_color(
        row=row,
        mode=ImportMode.PATCH,
        context={
            "colors": {
                "black": {
                    "id": color_id,
                    "name": "Чёрный",
                    "applicability": "both",
                    "is_active": True,
                }
            },
            "_color_product_references": {color_id: {"body": 0, "interior": 1}},
        },
        issues=issues,
    )

    assert normalized is None
    assert issues[0].column_name == "Применимость"
    assert "нельзя сузить" in issues[0].message.lower()


@pytest.mark.parametrize(
    ("field", "column_name", "applicability"),
    [
        ("body_color_code", "Код цвета кузова", "interior"),
        ("interior_color_code", "Код цвета салона", "body"),
    ],
)
def test_v4_product_rejects_color_with_wrong_applicability(
    field: str,
    column_name: str,
    applicability: str,
) -> None:
    row, context, category_id = _published_product_case()
    color_id = uuid4()
    row[field] = "wrong-color"
    context["colors"] = {
        "wrong-color": {
            "id": color_id,
            "code": "wrong-color",
            "name": "Неподходящий",
            "applicability": applicability,
            "is_active": True,
        }
    }
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is None
    assert issues[0].column_name == column_name
    assert "не может быть выбран" in issues[0].message


def test_v4_product_trim_must_be_active_and_belong_to_modification() -> None:
    row, context, category_id = _published_product_case()
    modification_id = context["modifications"]["modification-1"]["id"]
    row["trim_code"] = "premium"
    context["trims"] = {
        "modification-1:premium": {
            "id": uuid4(),
            "code": "premium",
            "modification_id": modification_id,
            "is_active": False,
        }
    }
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is None
    assert issues[0].column_name == "Код комплектации"
    assert "активной" in issues[0].message


def test_v4_patch_blank_preserves_and_clear_removes_trim_and_colors() -> None:
    modification_id = uuid4()
    trim_id = uuid4()
    body_color_id = uuid4()
    interior_color_id = uuid4()
    current = {
        "trim_id": trim_id,
        "body_color_id": body_color_id,
        "interior_color_id": interior_color_id,
    }
    context: dict[str, Any] = {
        "trims": {},
        "colors": {},
    }
    row: dict[str, Any] = {
        "operation": "SET",
        "trim_code": None,
        "body_color_code": None,
        "interior_color_code": None,
        "_clear_fields": [],
    }

    assert (
        import_v2._resolve_product_trim_id(
            row=row,
            current=current,
            modification_code="modification-1",
            modification_id=modification_id,
            identity={},
            valid_codes={},
            mode=ImportMode.PATCH,
            context=context,
        )
        == trim_id
    )
    assert (
        import_v2._resolve_product_color_id(
            row=row,
            current=current,
            code_field="body_color_code",
            id_field="body_color_id",
            column_name="Код цвета кузова",
            required_applicability="body",
            identity={},
            valid_codes={},
            mode=ImportMode.PATCH,
            context=context,
        )
        == body_color_id
    )
    cleared = {**row, "_clear_fields": ["trim_code", "body_color_code"]}
    assert (
        import_v2._resolve_product_trim_id(
            row=cleared,
            current=current,
            modification_code="modification-1",
            modification_id=modification_id,
            identity={},
            valid_codes={},
            mode=ImportMode.PATCH,
            context=context,
        )
        is None
    )
    assert (
        import_v2._resolve_product_color_id(
            row=cleared,
            current=current,
            code_field="body_color_code",
            id_field="body_color_id",
            column_name="Код цвета кузова",
            required_applicability="body",
            identity={},
            valid_codes={},
            mode=ImportMode.PATCH,
            context=context,
        )
        is None
    )


def test_v3_import_rejects_seventh_effective_card_attribute(
    tmp_path: Path,
) -> None:
    category_id = uuid4()
    modification_id = uuid4()
    attribute_ids = [uuid4() for _ in range(7)]
    plan = create_row_stores(tmp_path / "card-limit-plan", DATA_SHEET_HEADERS)
    plan["category_attributes"].append(
        {
            "operation": "SET",
            "values": {
                "category_id": category_id,
                "attribute_id": attribute_ids[-1],
                "group_id": None,
                "is_required": False,
                "is_filterable": False,
                "is_visible": True,
                "sort_order": 7,
            },
            "_sheet_code": "Характеристики категорий",
            "_row_number": 8,
            "_aggregate_kind": "category",
            "_aggregate_code": "trucks",
        }
    )
    context = {
        "categories": {
            "trucks": {
                "id": category_id,
                "code": "trucks",
                "is_active": True,
            }
        },
        "category_relations": set(),
        "category_attributes": {
            (category_id, attribute_id): {
                "category_id": category_id,
                "attribute_id": attribute_id,
                "group_id": None,
                "is_required": False,
                "is_filterable": False,
                "is_visible": True,
                "sort_order": index,
            }
            for index, attribute_id in enumerate(attribute_ids[:6])
        },
        "_modification_category_details": {
            modification_id: {category_id: {"sort_order": 0, "is_primary": True}}
        },
    }
    issues = import_v2.V2IssueCollector()

    import_v2._validate_card_attribute_limit_plan(
        plan=plan,
        context=context,
        mode=ImportMode.PATCH,
        issues=issues,
    )

    assert [issue.code for issue in issues] == ["CARD_ATTRIBUTE_LIMIT_EXCEEDED"]
    assert list(plan["category_attributes"]) == []


def test_full_snapshot_directory_state_accepts_jsonl_relationship_ids(
    tmp_path: Path,
) -> None:
    mark_id = uuid4()
    model_id = uuid4()
    modification_id = uuid4()
    plan = create_row_stores(
        tmp_path / "full-snapshot-directory-state", DATA_SHEET_HEADERS
    )
    plan["marks"].append(
        {
            "id": mark_id,
            "code": "mark-1",
            "operation": "SET",
            "values": {"name": "Марка", "is_active": True},
        }
    )
    plan["models"].append(
        {
            "id": model_id,
            "code": "model-1",
            "operation": "SET",
            "values": {
                "name": "Модель",
                "mark_id": mark_id,
                "is_active": True,
            },
        }
    )
    plan["modifications"].append(
        {
            "id": modification_id,
            "code": "modification-1",
            "operation": "SET",
            "values": {
                "name": "Модификация",
                "model_id": model_id,
                "is_active": True,
            },
        }
    )

    context = {
        "_effective_catalog_entities": import_v2._effective_catalog_entities(
            context={},
            plan=plan,
            mode=ImportMode.FULL_SNAPSHOT,
        )
    }

    is_active, modification = import_v2._product_directory_state(
        context=context,
        modification_id=modification_id,
    )

    assert is_active is True
    assert modification is not None


@pytest.mark.parametrize(
    ("family", "code"),
    [
        ("marks", "mark-1"),
        ("models", "model-1"),
        ("modifications", "modification-1"),
    ],
)
def test_published_product_rejects_inactive_directory_chain(
    family: str,
    code: str,
) -> None:
    row, context, category_id = _published_product_case()
    context[family][code]["is_active"] = False
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is None
    assert issues.error_count == 1
    assert "цепочка марки, модели и модификации неактивна" in issues[0].message


def test_published_product_rejects_inactive_factual_category() -> None:
    row, context, category_id = _published_product_case()
    context["categories"]["category-1"]["is_active"] = False
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is None
    assert issues.error_count == 1
    assert "выбрана неактивная категория" in issues[0].message


@pytest.mark.parametrize("manufacture_year", [2019, 2027])
def test_product_year_must_fit_modification_production_period(
    manufacture_year: int,
) -> None:
    row, context, category_id = _published_product_case()
    row["publication_status"] = "draft"
    row["published_at"] = None
    row["manufacture_year"] = manufacture_year
    issues = import_v2.V2IssueCollector()

    normalized = import_v2._normalize_product(
        row=row,
        categories=[category_id],
        identity={},
        valid_codes={},
        mode=ImportMode.APPEND,
        context=context,
        issues=issues,
    )

    assert normalized is None
    assert issues.error_count == 1
    assert (
        "год выпуска не входит в период выпуска модификации"
        in issues[0].message.lower()
    )


@pytest.mark.asyncio
async def test_import_context_expands_existing_modification_chain(
    db_session: AsyncSession,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="Марка импорта",
        model_name="Модель импорта",
        modification_name="Модификация импорта",
    )
    mark.is_active = False
    modification.year_from = 2020
    modification.year_to = 2026
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    context = await import_repository.get_v2_import_context(
        db_session,
        requested_codes={"modifications_codes": {modification.code}},
        seller_inns=set(),
    )

    assert context["modifications"][modification.code]["model_id"] == model.id
    assert context["models"][model.code]["mark_id"] == mark.id
    assert context["marks"][mark.code]["is_active"] is False


@pytest.mark.asyncio
async def test_v2_plan_uses_code_identity_and_product_usage_metric(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "catalog.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.APPEND))
    workbook = load_workbook(source)

    def append(sheet_name: str, values: Mapping[str, Any]) -> None:
        sheet = workbook[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        row: list[Any] = [None] * len(headers)
        for header, value in values.items():
            if header in headers:
                row[headers.index(header)] = value
        sheet.append(row)

    append("Марки", {"Код": "kamaz", "Название": "КамАЗ", "Активность": "Да"})
    append("Модели", {"Код": "kamaz-65115", "Название": "65115", "Код марки": "kamaz", "Активность": "Да"})
    append("Модификации", {"Код": "kamaz-65115-crane", "Название": "Кран", "Код модели": "kamaz-65115", "Год начала": 2020, "Год окончания": 2026, "Активность": "Да"})
    append("Категории", {"Код": "trucks", "Название": "Грузовики", "Показатель эксплуатации": "Пробег", "Категория надстроек": "Нет", "Порядок": 10, "Активность": "Да"})
    append("Группы характеристик", {"Код": "engine", "Название": "Двигатель", "Порядок": 10, "Активность": "Да"})
    append("Характеристики", {"Код": "power", "Название": "Мощность", "Код группы по умолчанию": "engine", "Тип данных": "Число", "Тип фильтра": "Диапазон", "Активность": "Да"})
    append("Категории модификаций", {"Код модификации": "kamaz-65115-crane", "Код категории": "trucks", "Порядок": 0, "Основная": "Да"})
    append("Характеристики модификаций", {"Код модификации": "kamaz-65115-crane", "Код характеристики": "power", "Значение": 300})
    append("Характеристики категорий", {"Код категории": "trucks", "Код характеристики": "power", "Код группы": "engine", "Обязательная": "Да", "В фильтре": "Да", "В карточке": "Да", "Порядок": 10})
    append("Объявления", {
        "Код": "truck-1",
        "Код модификации": "kamaz-65115-crane",
        "Состояние": "С пробегом",
        "Год выпуска": 2024,
        "Описание": "Автокран",
        "Цена": 10_000_000,
        "Валюта": "RUB",
        "Количество владельцев": 1,
        "Нет VIN": "Да",
        "Пробег, км": 50_000,
        "Статус публикации": "Черновик",
        "Статус продажи": "Доступно",
    })
    append("Категории объявлений", {"Код объявления": "truck-1", "Код категории": "trucks"})
    workbook.save(source)
    workbook.close()
    parsed = parse_xlsx(source, expected_mode=ImportMode.APPEND)

    async def context(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "marks": {},
            "models": {},
            "modifications": {},
            "categories": {},
            "attribute_groups": {},
            "attributes": {},
            "attribute_options": {},
            "products": {},
            "category_relations": set(),
            "modification_categories": set(),
            "product_categories": set(),
            "companies": {},
        }

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", context)
    plan, issues, summary, versions, sellers = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.APPEND.value},
        workbook=parsed,
        plan_spool_dir=tmp_path / "plan",
    )

    assert issues.error_count == 0
    assert summary["acceptedRows"] == 11
    assert versions == {}
    assert sellers == set()
    product = next(iter(plan["products"]))
    assert product["code"] == "truck-1"
    assert product["values"]["mileage_km"] == 50_000
    assert product["values"]["engine_hours"] is None
    assert product["_aggregate_kind"] == "product"
    attribute = next(iter(plan["attributes"]))
    group = next(iter(plan["attribute_groups"]))
    assert attribute["values"]["attribute_group_id"] == group["id"]
    modification_category = next(iter(plan["modification_categories"]))
    assert modification_category["values"]["sort_order"] == 0
    assert modification_category["values"]["is_primary"] is True
    assert (
        next(iter(plan["modification_attribute_values"]))["_aggregate_code"]
        == "kamaz-65115-crane"
    )


def test_v7_template_omits_mode_and_warehouse_id_column() -> None:
    workbook = load_workbook(BytesIO(build_template_v7()), read_only=True)
    try:
        parameters = dict(workbook["Параметры"].iter_rows(min_row=2, values_only=True))
        assert parameters["Версия шаблона"] == "9"
        assert "Режим" not in parameters

        product_headers = tuple(
            cell.value for cell in next(workbook["Объявления"].iter_rows())
        )
        assert "ID склада" not in product_headers
        assert "Действие" not in product_headers

        instruction_sections = {
            row[0]
            for row in workbook["Инструкция"].iter_rows(values_only=True)
            if row[0]
        }
        assert "Режим" not in instruction_sections
        assert "Склад и специальная цена" not in instruction_sections
        assert "Специальная цена" in instruction_sections

        instruction_values = {
            str(cell.value)
            for row in workbook["Инструкция"].iter_rows()
            for cell in row
            if cell.value is not None
        }
        assert not any("ID склада" in val for val in instruction_values)
    finally:
        workbook.close()


def test_v7_template_artifact_filename_has_no_mode() -> None:
    artifact = import_service.request_import_template(version=8)
    assert artifact.filename == "special-equipment-v8.xlsx"
    artifact_patch = import_service.request_import_template(
        version=8, mode=ImportMode.PATCH
    )
    assert artifact_patch.filename == "special-equipment-v8.xlsx"


def test_v7_parser_ignores_legacy_warehouse_id_column(tmp_path: Path) -> None:
    source = tmp_path / "special-equipment-v7-legacy-warehouse.xlsx"
    source.write_bytes(build_template_v7())
    wb = load_workbook(source)
    sheet = wb["Объявления"]
    headers = [cell.value for cell in next(sheet.iter_rows())]
    headers.insert(4, "ID склада")
    sheet.delete_rows(1)
    sheet.insert_rows(1)
    for col_idx, h in enumerate(headers, start=1):
        sheet.cell(row=1, column=col_idx, value=h)

    fake_warehouse = str(uuid4())
    row_values: list[Any] = [None] * len(headers)
    row_values[headers.index("Код")] = "prod-legacy-1"
    row_values[headers.index("Код модификации")] = "mod-1"
    row_values[headers.index("ID склада")] = fake_warehouse
    row_values[headers.index("Состояние")] = "Новое"
    row_values[headers.index("Год выпуска")] = 2024
    row_values[headers.index("Цена")] = 1000000
    row_values[headers.index("Валюта")] = "RUB"
    row_values[headers.index("Нет VIN")] = "Да"
    row_values[headers.index("Статус публикации")] = "Опубликовано"
    row_values[headers.index("Статус продажи")] = "Доступно"
    sheet.append(row_values)
    wb.save(source)
    wb.close()

    parsed = parse_xlsx(
        source,
        expected_mode=ImportMode.APPEND,
        expected_template_version=9,
    )
    products = list(parsed.rows["products"])
    assert len(products) == 1
    assert products[0]["code"] == "prod-legacy-1"
    assert products[0]["condition"] == "new"
    assert "warehouse_id" not in products[0] or products[0].get("warehouse_id") is None


def test_v7_manifest_allows_optional_or_different_mode(tmp_path: Path) -> None:
    source = tmp_path / "special-equipment-v7-modes.xlsx"
    source.write_bytes(build_template_v7())
    wb = load_workbook(source)
    manifest = wb["Параметры"]
    manifest.append(("Режим", "Добавление и изменение"))
    wb.save(source)
    wb.close()

    parsed = parse_xlsx(
        source,
        expected_mode=ImportMode.APPEND,
        expected_template_version=9,
    )
    assert parsed.manifest["schema_version"] == "9"
    assert parsed.manifest["mode"] == ImportMode.APPEND.value
    assert parsed.manifest["mode"] == ImportMode.APPEND.value


@pytest.mark.asyncio
async def test_full_snapshot_ignores_persisted_modification_value_for_incoming_trim_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Class A1: In S0 modification has value X, in FULL_SNAPSHOT file trim has value X.

    In FULL_SNAPSHOT mode this must pass with 0 errors (effective baseline is empty).
    In PATCH mode this fails with ATTRIBUTE_ALREADY_USED_IN_MODIFICATION.
    """
    mod_id = uuid4()
    trim_id = uuid4()
    attr_id = uuid4()
    cat_id = uuid4()

    source = tmp_path / "a1_snapshot.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.FULL_SNAPSHOT))
    wb = load_workbook(source)

    def append(sheet_name: str, values: Mapping[str, Any]) -> None:
        sheet = wb[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        row: list[Any] = [None] * len(headers)
        for header, value in values.items():
            if header in headers:
                row[headers.index(header)] = value
        sheet.append(row)

    append("Марки", {"Действие": "Задать", "Код": "kamaz", "Название": "КамАЗ", "Активность": "Да"})
    append("Модели", {"Действие": "Задать", "Код": "65115", "Название": "65115", "Код марки": "kamaz", "Активность": "Да"})
    append("Модификации", {"Действие": "Задать", "Код": "mod-1", "Название": "mod-1", "Код модели": "65115", "Активность": "Да"})
    append("Комплектации", {"Действие": "Задать", "Код": "trim-1", "Название": "trim-1", "Код модификации": "mod-1", "Порядок": 0, "Активность": "Да"})
    append("Категории", {"Действие": "Задать", "Код": "trucks", "Название": "Самосвалы", "Показатель эксплуатации": "Пробег", "Порядок": 0, "Активность": "Да"})
    append("Категории модификаций", {"Действие": "Задать", "Код модификации": "mod-1", "Код категории": "trucks", "Порядок": 0, "Основная": "Да"})
    append("Группы характеристик", {"Действие": "Задать", "Код": "engine", "Название": "Двигатель", "Порядок": 0, "Активность": "Да"})
    append("Характеристики", {"Действие": "Задать", "Код": "power", "Название": "Мощность", "Тип данных": "Число", "Тип фильтра": "Диапазон", "Код группы по умолчанию": "engine", "Активность": "Да"})
    append("Характеристики категорий", {"Действие": "Задать", "Код категории": "trucks", "Код характеристики": "power", "Код группы": "engine", "Обязательная": "Нет", "В фильтре": "Нет", "В карточке": "Да", "Порядок": 0})
    append("Характеристики комплектаций", {"Действие": "Задать", "Код модификации": "mod-1", "Код комплектации": "trim-1", "Код характеристики": "power", "Код группы": "engine", "Обязательная": "Нет", "В фильтре": "Нет", "Порядок": 0})
    append("Значения комплектаций", {"Действие": "Задать", "Код модификации": "mod-1", "Код комплектации": "trim-1", "Код характеристики": "power", "Значение": "300"})
    wb.save(source)
    wb.close()

    async def mock_context(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "categories": {"trucks": {"id": cat_id, "name": "Самосвалы", "is_active": True}},
            "marks": {"kamaz": {"id": uuid4(), "name": "КамАЗ", "is_active": True}},
            "models": {"65115": {"id": uuid4(), "name": "65115", "is_active": True}},
            "modifications": {"mod-1": {"id": mod_id, "name": "mod-1", "is_active": True}},
            "trims": {"mod-1:trim-1": {"id": trim_id, "modification_id": mod_id, "name": "trim-1", "is_active": True}},
            "attribute_groups": {"engine": {"id": uuid4(), "name": "Двигатель", "is_active": True}},
            "attributes": {"power": {"id": attr_id, "name": "Мощность", "data_type": "number", "is_active": True}},
            "attribute_options": {},
            "colors": {},
            "products": {},
            "category_relations": set(),
            "modification_categories": {(mod_id, cat_id)},
            "_modification_category_details": {mod_id: {cat_id: {"sort_order": 0, "is_primary": True}}},
            "category_attributes": {(cat_id, attr_id): {"is_required": False, "is_filterable": False, "is_visible": True, "sort_order": 0}},
            "modification_attribute_values": {(mod_id, attr_id)},
            "trim_attributes": {},
            "trim_attribute_values": set(),
            "product_categories": set(),
            "product_attachments": set(),
            "_product_component_details": {},
            "companies": {},
            "warehouses": {},
        }

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", mock_context)

    # 1. FULL_SNAPSHOT -> Should pass with 0 errors
    parsed_snapshot = parse_xlsx(source, expected_mode=ImportMode.FULL_SNAPSHOT, expected_template_version=9)
    _plan, issues_snapshot, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.FULL_SNAPSHOT.value},
        workbook=parsed_snapshot,
        plan_spool_dir=tmp_path / "plan-a1-snapshot",
    )
    assert issues_snapshot.error_count == 0, f"Expected 0 errors, got: {[i.as_dict() for i in issues_snapshot]}"

    # 2. PATCH -> Should fail with ATTRIBUTE_ALREADY_USED_IN_MODIFICATION
    parsed_patch = parse_xlsx(source, expected_mode=ImportMode.PATCH, expected_template_version=9)
    _plan_patch, issues_patch, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.PATCH.value},
        workbook=parsed_patch,
        plan_spool_dir=tmp_path / "plan-a1-patch",
    )
    assert any(i.code == "ATTRIBUTE_ALREADY_USED_IN_MODIFICATION" for i in issues_patch)


@pytest.mark.asyncio
async def test_full_snapshot_ignores_persisted_trim_value_for_incoming_modification_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Class A2: In S0 trim has value X, in FULL_SNAPSHOT file modification has value X.

    In FULL_SNAPSHOT mode this must pass with 0 errors.
    In PATCH mode this fails with ATTRIBUTE_ALREADY_ASSIGNED_IN_TRIM.
    """
    mod_id = uuid4()
    trim_id = uuid4()
    attr_id = uuid4()
    cat_id = uuid4()

    source = tmp_path / "a2_snapshot.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.FULL_SNAPSHOT))
    wb = load_workbook(source)

    def append(sheet_name: str, values: Mapping[str, Any]) -> None:
        sheet = wb[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        row: list[Any] = [None] * len(headers)
        for header, value in values.items():
            if header in headers:
                row[headers.index(header)] = value
        sheet.append(row)

    append("Марки", {"Действие": "Задать", "Код": "kamaz", "Название": "КамАЗ", "Активность": "Да"})
    append("Модели", {"Действие": "Задать", "Код": "65115", "Название": "65115", "Код марки": "kamaz", "Активность": "Да"})
    append("Модификации", {"Действие": "Задать", "Код": "mod-1", "Название": "mod-1", "Код модели": "65115", "Активность": "Да"})
    append("Категории", {"Действие": "Задать", "Код": "trucks", "Название": "Самосвалы", "Показатель эксплуатации": "Пробег", "Порядок": 0, "Активность": "Да"})
    append("Категории модификаций", {"Действие": "Задать", "Код модификации": "mod-1", "Код категории": "trucks", "Порядок": 0, "Основная": "Да"})
    append("Группы характеристик", {"Действие": "Задать", "Код": "engine", "Название": "Двигатель", "Порядок": 0, "Активность": "Да"})
    append("Характеристики", {"Действие": "Задать", "Код": "power", "Название": "Мощность", "Тип данных": "Число", "Тип фильтра": "Диапазон", "Код группы по умолчанию": "engine", "Активность": "Да"})
    append("Характеристики категорий", {"Действие": "Задать", "Код категории": "trucks", "Код характеристики": "power", "Код группы": "engine", "Обязательная": "Нет", "В фильтре": "Нет", "В карточке": "Да", "Порядок": 0})
    append("Характеристики модификаций", {"Действие": "Задать", "Код модификации": "mod-1", "Код характеристики": "power", "Значение": "300"})
    wb.save(source)
    wb.close()

    async def mock_context(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "categories": {"trucks": {"id": cat_id, "name": "Самосвалы", "is_active": True}},
            "marks": {"kamaz": {"id": uuid4(), "name": "КамАЗ", "is_active": True}},
            "models": {"65115": {"id": uuid4(), "name": "65115", "is_active": True}},
            "modifications": {"mod-1": {"id": mod_id, "name": "mod-1", "is_active": True}},
            "trims": {"mod-1:trim-1": {"id": trim_id, "modification_id": mod_id, "name": "trim-1", "is_active": True}},
            "attribute_groups": {"engine": {"id": uuid4(), "name": "Двигатель", "is_active": True}},
            "attributes": {"power": {"id": attr_id, "name": "Мощность", "data_type": "number", "is_active": True}},
            "attribute_options": {},
            "colors": {},
            "products": {},
            "category_relations": set(),
            "modification_categories": {(mod_id, cat_id)},
            "_modification_category_details": {mod_id: {cat_id: {"sort_order": 0, "is_primary": True}}},
            "category_attributes": {(cat_id, attr_id): {"is_required": False, "is_filterable": False, "is_visible": True, "sort_order": 0}},
            "modification_attribute_values": set(),
            "trim_attributes": {},
            "trim_attribute_values": {(trim_id, attr_id)},  # S0 has trim value!
            "product_categories": set(),
            "product_attachments": set(),
            "_product_component_details": {},
            "companies": {},
            "warehouses": {},
        }

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", mock_context)

    # 1. FULL_SNAPSHOT -> Should pass with 0 errors
    parsed_snapshot = parse_xlsx(source, expected_mode=ImportMode.FULL_SNAPSHOT, expected_template_version=9)
    _plan, issues_snapshot, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.FULL_SNAPSHOT.value},
        workbook=parsed_snapshot,
        plan_spool_dir=tmp_path / "plan-a2-snapshot",
    )
    assert issues_snapshot.error_count == 0, f"Expected 0 errors, got: {[i.as_dict() for i in issues_snapshot]}"

    # 2. PATCH -> Should fail with ATTRIBUTE_ALREADY_ASSIGNED_IN_TRIM
    parsed_patch = parse_xlsx(source, expected_mode=ImportMode.PATCH, expected_template_version=9)
    _plan_patch, issues_patch, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.PATCH.value},
        workbook=parsed_patch,
        plan_spool_dir=tmp_path / "plan-a2-patch",
    )
    assert any(i.code == "ATTRIBUTE_ALREADY_ASSIGNED_IN_TRIM" for i in issues_patch)


@pytest.mark.asyncio
async def test_full_snapshot_rejects_in_file_invariant_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invariant regression: file contains same attribute for both modification and trim.

    Both FULL_SNAPSHOT and PATCH must reject with ATTRIBUTE_ALREADY_USED_IN_MODIFICATION.
    """
    source = tmp_path / "invariant_conflict.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.FULL_SNAPSHOT))
    wb = load_workbook(source)

    def append(sheet_name: str, values: Mapping[str, Any]) -> None:
        sheet = wb[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        row: list[Any] = [None] * len(headers)
        for header, value in values.items():
            if header in headers:
                row[headers.index(header)] = value
        sheet.append(row)

    append("Марки", {"Действие": "Добавить", "Код": "kamaz", "Название": "КамАЗ", "Активность": "Да"})
    append("Модели", {"Действие": "Добавить", "Код": "65115", "Название": "65115", "Код марки": "kamaz", "Активность": "Да"})
    append("Модификации", {"Действие": "Добавить", "Код": "mod-1", "Название": "mod-1", "Код модели": "65115", "Активность": "Да"})
    append("Комплектации", {"Действие": "Добавить", "Код": "trim-1", "Название": "trim-1", "Код модификации": "mod-1", "Порядок": 0, "Активность": "Да"})
    append("Категории", {"Действие": "Добавить", "Код": "trucks", "Название": "Самосвалы", "Показатель эксплуатации": "Пробег", "Порядок": 0, "Активность": "Да"})
    append("Категории модификаций", {"Действие": "Добавить", "Код модификации": "mod-1", "Код категории": "trucks", "Порядок": 0, "Основная": "Да"})
    append("Группы характеристик", {"Действие": "Добавить", "Код": "engine", "Название": "Двигатель", "Порядок": 0, "Активность": "Да"})
    append("Характеристики", {"Действие": "Добавить", "Код": "power", "Название": "Мощность", "Тип данных": "Число", "Тип фильтра": "Диапазон", "Код группы по умолчанию": "engine", "Активность": "Да"})
    append("Характеристики категорий", {"Действие": "Добавить", "Код категории": "trucks", "Код характеристики": "power", "Код группы": "engine", "Обязательная": "Нет", "В фильтре": "Нет", "В карточке": "Да", "Порядок": 0})
    append("Характеристики модификаций", {"Действие": "Задать", "Код модификации": "mod-1", "Код характеристики": "power", "Значение": "300"})
    append("Характеристики комплектаций", {"Действие": "Добавить", "Код модификации": "mod-1", "Код комплектации": "trim-1", "Код характеристики": "power", "Код группы": "engine", "Обязательная": "Нет", "В фильтре": "Нет", "Порядок": 0})
    append("Значения комплектаций", {"Действие": "Задать", "Код модификации": "mod-1", "Код комплектации": "trim-1", "Код характеристики": "power", "Значение": "350"})
    wb.save(source)
    wb.close()

    async def mock_context(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "categories": {},
            "marks": {},
            "models": {},
            "modifications": {},
            "trims": {},
            "attribute_groups": {},
            "attributes": {},
            "attribute_options": {},
            "colors": {},
            "products": {},
            "category_relations": set(),
            "modification_categories": set(),
            "_modification_category_details": {},
            "category_attributes": {},
            "modification_attribute_values": set(),
            "trim_attributes": {},
            "trim_attribute_values": set(),
            "product_categories": set(),
            "product_attachments": set(),
            "_product_component_details": {},
            "companies": {},
            "warehouses": {},
        }

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", mock_context)

    parsed_snapshot = parse_xlsx(source, expected_mode=ImportMode.FULL_SNAPSHOT, expected_template_version=9)
    _plan, issues_snapshot, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.FULL_SNAPSHOT.value},
        workbook=parsed_snapshot,
        plan_spool_dir=tmp_path / "plan-conflict-snapshot",
    )
    assert any(i.code == "ATTRIBUTE_ALREADY_USED_IN_MODIFICATION" for i in issues_snapshot)

    parsed_patch = parse_xlsx(source, expected_mode=ImportMode.PATCH, expected_template_version=9)
    _plan_p, issues_patch, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.PATCH.value},
        workbook=parsed_patch,
        plan_spool_dir=tmp_path / "plan-conflict-patch",
    )
    assert any(i.code == "ATTRIBUTE_ALREADY_USED_IN_MODIFICATION" for i in issues_patch)


@pytest.mark.asyncio
async def test_full_snapshot_reference_not_in_snapshot_for_missing_s0_entities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Class B1/B2: In FULL_SNAPSHOT referencing an entity that exists in S0 but omitted from file

    Emits REFERENCE_NOT_IN_SNAPSHOT with expected message.
    In PATCH mode resolves to S0 entity without error.
    """
    old_mark_id = uuid4()
    old_attr_id = uuid4()
    old_group_id = uuid4()
    old_option_id = uuid4()

    source = tmp_path / "class_b.xlsx"
    source.write_bytes(build_template_v7(mode=ImportMode.FULL_SNAPSHOT))
    wb = load_workbook(source)

    def append(sheet_name: str, values: Mapping[str, Any]) -> None:
        sheet = wb[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        row: list[Any] = [None] * len(headers)
        for header, value in values.items():
            if header in headers:
                row[headers.index(header)] = value
        sheet.append(row)

    # Note: "Марки" sheet does NOT contain "kamaz-old"
    append("Модели", {"Действие": "Добавить", "Код": "model-1", "Название": "Model 1", "Код марки": "kamaz-old", "Активность": "Да"})
    wb.save(source)
    wb.close()

    async def mock_context(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "categories": {},
            "marks": {"kamaz-old": {"id": old_mark_id, "name": "Старый КамАЗ", "is_active": True}},
            "models": {},
            "modifications": {},
            "trims": {},
            "attribute_groups": {"group-old": {"id": old_group_id, "name": "Старая группа", "is_active": True}},
            "attributes": {"attr-old": {"id": old_attr_id, "name": "Старая характеристика", "data_type": "select", "is_active": True}},
            "attribute_options": {"attr-old:opt-old": {"id": old_option_id, "attribute_id": old_attr_id, "code": "opt-old", "is_active": True}},
            "colors": {},
            "products": {},
            "category_relations": set(),
            "modification_categories": set(),
            "_modification_category_details": {},
            "category_attributes": {},
            "modification_attribute_values": set(),
            "trim_attributes": {},
            "trim_attribute_values": set(),
            "product_categories": set(),
            "product_attachments": set(),
            "_product_component_details": {},
            "companies": {},
            "warehouses": {},
        }

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", mock_context)

    # 1. FULL_SNAPSHOT -> REFERENCE_NOT_IN_SNAPSHOT
    parsed_snapshot = parse_xlsx(source, expected_mode=ImportMode.FULL_SNAPSHOT, expected_template_version=9)
    _plan_snapshot, issues_snapshot, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.FULL_SNAPSHOT.value},
        workbook=parsed_snapshot,
        plan_spool_dir=tmp_path / "plan-b-snapshot",
    )
    b_issues = [i for i in issues_snapshot if i.code == REFERENCE_NOT_IN_SNAPSHOT]
    assert len(b_issues) >= 1
    assert "Сущность отсутствует в файле полной замены и будет деактивирована" in b_issues[0].message

    # 2. Unknown code (not in S0 either) -> standard MARK_NOT_FOUND
    source_unknown = tmp_path / "class_b_unknown.xlsx"
    source_unknown.write_bytes(build_template_v7(mode=ImportMode.FULL_SNAPSHOT))
    wb_u = load_workbook(source_unknown)
    sheet_u = wb_u["Модели"]
    headers_u = [cell.value for cell in next(sheet_u.iter_rows())]
    row_u: list[Any] = [None] * len(headers_u)
    for header, value in {"Действие": "Добавить", "Код": "model-2", "Название": "Model 2", "Код марки": "completely-unknown", "Активность": "Да"}.items():
        if header in headers_u:
            row_u[headers_u.index(header)] = value
    sheet_u.append(row_u)
    wb_u.save(source_unknown)
    wb_u.close()

    parsed_unknown = parse_xlsx(source_unknown, expected_mode=ImportMode.FULL_SNAPSHOT, expected_template_version=9)
    _plan_u, issues_u, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.FULL_SNAPSHOT.value},
        workbook=parsed_unknown,
        plan_spool_dir=tmp_path / "plan-b-unknown",
    )
    assert any(i.code == "MARK_NOT_FOUND" for i in issues_u)
    assert not any(i.code == REFERENCE_NOT_IN_SNAPSHOT for i in issues_u)

    # 3. In PATCH mode -> resolves kamaz-old from S0 without error
    parsed_patch = parse_xlsx(source, expected_mode=ImportMode.PATCH, expected_template_version=9)
    plan_patch, issues_patch, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.PATCH.value},
        workbook=parsed_patch,
        plan_spool_dir=tmp_path / "plan-b-patch",
    )
    assert issues_patch.error_count == 0
    assert UUID(str(next(iter(plan_patch["models"]))["values"]["mark_id"])) == old_mark_id


def test_special_equipment_column_title() -> None:
    assert special_equipment_column_title("categories", "is_attachment_category") == "Категория надстроек"
    assert special_equipment_column_title("category", "is_attachment_category") == "Категория надстроек"
    assert special_equipment_column_title("categories", "usage_metric") == "Показатель эксплуатации"
    assert special_equipment_column_title("categories", "name") == "Название"
    assert special_equipment_column_title("categories", "image_key") == "Картинка"
    assert special_equipment_column_title("models", "mark_id") == "Код марки"
    assert special_equipment_column_title("products", "modification_id") == "Код модификации"
    assert special_equipment_column_title("category_attributes", "is_visible") == "В карточке"
    assert special_equipment_column_title("category_relations", "parent_id") == "Код родительской категории"
    assert special_equipment_column_title("products", "operation") == "Действие"
    assert special_equipment_column_title("unknown", "unknown") is None


def test_import_contract_error_column_name() -> None:
    err = ImportContractError("Test message", column_name="Колонка")
    assert err.column_name == "Колонка"
    assert str(err) == "Test message"


def test_v7_template_documents_attachment_category() -> None:
    workbook = load_workbook(BytesIO(build_template_v7()), read_only=True)
    try:
        instructions = workbook["Инструкция"]
        values = list(instructions.iter_rows(values_only=True))
        attachment_rows = [r for r in values if r and r[0] == "Категория надстроек"]
        assert len(attachment_rows) == 1
        desc = attachment_rows[0][1]
        assert "Категория надстроек — «Да» или «Нет»." in desc
        assert "Пустая ячейка у новой категории означает «Нет», у существующей — сохраняет текущее значение." in desc
    finally:
        workbook.close()


def test_normalize_directory_category_attachment_defaults() -> None:
    # 1. ADD with blank is_attachment_category -> defaults to False
    res_add = import_v2._merge_values(
        row={"operation": "ADD", "name": "Экскаваторы", "is_attachment_category": None},
        current={},
        mode=ImportMode.APPEND,
        fields=("name", "is_attachment_category", "is_active"),
        required={"name"},
        family="categories",
        defaults=import_v2._DIRECTORY_FIELD_DEFAULTS["categories"],
    )
    assert res_add["is_attachment_category"] is False
    assert res_add["is_active"] is True

    # 2. PATCH SET with blank is_attachment_category -> retains current
    res_patch = import_v2._merge_values(
        row={"operation": "SET", "name": "Экскаваторы", "is_attachment_category": None},
        current={"is_attachment_category": True, "is_active": True},
        mode=ImportMode.PATCH,
        fields=("name", "is_attachment_category", "is_active"),
        required={"name"},
        family="categories",
        defaults=import_v2._DIRECTORY_FIELD_DEFAULTS["categories"],
    )
    assert res_patch["is_attachment_category"] is True

    # 3. PATCH SET with clear_fields -> resets to default False
    res_clear = import_v2._merge_values(
        row={"operation": "SET", "name": "Экскаваторы", "is_attachment_category": None, "_clear_fields": ["is_attachment_category"]},
        current={"is_attachment_category": True, "is_active": True},
        mode=ImportMode.PATCH,
        fields=("name", "is_attachment_category", "is_active"),
        required={"name"},
        family="categories",
        defaults=import_v2._DIRECTORY_FIELD_DEFAULTS["categories"],
    )
    assert res_clear["is_attachment_category"] is False

    # 4. FULL_SNAPSHOT SET with blank -> retains current, or defaults if not present
    res_snapshot = import_v2._merge_values(
        row={"operation": "SET", "name": "Экскаваторы", "is_attachment_category": None, "is_active": None},
        current={"is_attachment_category": True, "is_active": False},
        mode=ImportMode.FULL_SNAPSHOT,
        fields=("name", "is_attachment_category", "is_active"),
        required={"name"},
        family="categories",
        defaults=import_v2._DIRECTORY_FIELD_DEFAULTS["categories"],
    )
    assert res_snapshot["is_attachment_category"] is True
    assert res_snapshot["is_active"] is False


def test_invalid_boolean_in_attachment_category_raises_category_invalid(tmp_path: Path) -> None:
    collector = import_v2.V2IssueCollector()
    row = {
        "_code": "cat-invalid-bool",
        "_sheet_code": "Категории",
        "_row_number": 2,
        "operation": "ADD",
        "name": "Некорректная категория",
        "usage_metric": "mileage_km",
        "is_attachment_category": "Может быть",
    }
    normalized = import_v2._normalize_directory_entity(
        family="categories",
        row=row,
        mode=ImportMode.APPEND,
        context={},
        identity={},
        valid_codes=defaultdict(set),
        issues=collector,
    )
    assert normalized is None
    assert len(collector) == 1
    issue = collector[0]
    assert issue.code == "CATEGORY_INVALID"
    assert issue.column_name == "Категория надстроек"
    assert "Значение должно быть «Да» или «Нет»" in issue.message


def test_preflight_required_columns_without_default(tmp_path: Path) -> None:
    plan = create_row_stores(tmp_path / "plan-preflight", DATA_SHEET_HEADERS)
    plan["categories"].append({
        "id": uuid4(),
        "code": "cat-missing-usage",
        "operation": "ADD",
        "values": {
            "name": "Тест",
            "slug": "test",
            "usage_metric": None,  # NOT NULL without default!
        },
        "_sheet_code": "Категории",
        "_row_number": 5,
        "_aggregate_kind": "category",
        "_aggregate_code": "cat-missing-usage",
    })
    issues = import_v2.V2IssueCollector()
    valid_codes = {"categories": {"cat-missing-usage"}}

    import_v2._preflight_required_columns(
        plan=plan,
        issues=issues,
        valid_codes=valid_codes,
    )

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == "REQUIRED_FIELD_MISSING"
    assert issue.sheet_code == "Категории"
    assert issue.row_number == 5
    assert issue.column_name == "Показатель эксплуатации"
    assert "Не заполнено обязательное поле «Показатель эксплуатации»" in issue.message
    assert "cat-missing-usage" not in valid_codes["categories"]
    assert len(list(plan["categories"])) == 0


def test_v8_superstructure_and_product_headers_and_template() -> None:
    assert DATA_SHEET_HEADERS["superstructures"] == ("Код", "Название", "Активность")
    assert "Код модели надстройки" in DATA_SHEET_HEADERS["products"]
    assert "Код объявления надстройки" in DATA_SHEET_HEADERS["products"]

    workbook = load_workbook(BytesIO(build_template_v8()), read_only=True)
    try:
        parameters = dict(workbook["Параметры"].iter_rows(min_row=2, values_only=True))
        assert parameters["Версия шаблона"] == "8"
        superstructure_headers = tuple(
            cell.value for cell in next(workbook["Надстройки"].iter_rows())
        )
        assert superstructure_headers == ("Код", "Название", "Активность")
        product_headers = tuple(
            cell.value for cell in next(workbook["Объявления"].iter_rows())
        )
        assert "Код модели надстройки" in product_headers
        assert "Код объявления надстройки" in product_headers
    finally:
        workbook.close()


def test_export_product_row_v8_manual_and_source_linked() -> None:
    # 1. Ordinary product: all kit/superstructure columns are None
    ordinary = {
        "id": uuid4(),
        "code": "ord-1",
        "model_code": "kamaz-65115",
        "price": Decimal("5000000.00"),
    }
    row_ord = export_product_row(ordinary)
    assert row_ord["superstructure_code"] is None
    assert row_ord["superstructure_model_code"] is None
    assert row_ord["superstructure_modification_code"] is None
    assert row_ord["superstructure_source_code"] is None
    assert row_ord["superstructure_name"] is None
    assert row_ord["superstructure_manufacturer"] is None

    # 2. Kit with manual superstructure
    kit_manual = {
        "id": uuid4(),
        "code": "kit-m",
        "superstructure_id": uuid4(),
        "superstructure_code": "crane-sup",
        "superstructure_model_code": "crane-model-1",
        "superstructure_modification_code": "crane-mod-1",
        "superstructure_name": "Кран-манипулятор",
        "superstructure_manufacturer": "Завод Инмаш",
    }
    row_manual = export_product_row(kit_manual)
    assert row_manual["superstructure_code"] == "crane-sup"
    assert row_manual["superstructure_model_code"] == "crane-model-1"
    assert row_manual["superstructure_modification_code"] == "crane-mod-1"
    assert row_manual["superstructure_name"] == "Кран-манипулятор"
    assert row_manual["superstructure_manufacturer"] == "Завод Инмаш"
    assert row_manual["superstructure_source_code"] is None

    # 3. Kit with source-linked superstructure
    kit_source = {
        "id": uuid4(),
        "code": "kit-s",
        "superstructure_id": uuid4(),
        "superstructure_code": "crane-sup",
        "superstructure_source_product_id": uuid4(),
        "superstructure_source_code": "source-ad-123",
        # Stored manual fields might still exist or be empty, but must NOT be exported
        "superstructure_model_code": "ignored-model",
        "superstructure_name": "Ignored Name",
    }
    row_source = export_product_row(kit_source)
    assert row_source["superstructure_code"] == "crane-sup"
    assert row_source["superstructure_source_code"] == "source-ad-123"
    assert row_source["superstructure_model_code"] is None
    assert row_source["superstructure_modification_code"] is None
    assert row_source["superstructure_name"] is None
    assert row_source["superstructure_manufacturer"] is None

    # 4. format_product_export_cells produces tuple matching fields
    cells = format_product_export_cells(kit_source)
    assert isinstance(cells, tuple)
    src_idx = DATA_SHEET_FIELDS["products"].index("superstructure_source_code")
    assert cells[src_idx] == "source-ad-123"


def test_v9_template_headers_and_sheets() -> None:
    content = build_template_v9()
    workbook = load_workbook(BytesIO(content), read_only=True)
    assert "Категории надстроек" in workbook.sheetnames
    superstructure_categories_sheet = workbook["Категории надстроек"]
    headers = [cell.value for cell in next(superstructure_categories_sheet.iter_rows())]
    assert headers == ["Код надстройки", "Код категории"]

    models_sheet = workbook["Модели"]
    model_headers = [cell.value for cell in next(models_sheet.iter_rows())]
    assert "Код категории" in model_headers

    categories_sheet = workbook["Категории"]
    category_headers = [cell.value for cell in next(categories_sheet.iter_rows())]
    assert "Отображать в каталоге" in category_headers

    products_sheet = workbook["Объявления"]
    product_headers = [cell.value for cell in next(products_sheet.iter_rows())]
    assert "VIN транспортного средства" in product_headers
    assert "VIN шасси" in product_headers
    assert "VIN надстройки" in product_headers
    workbook.close()


@pytest.mark.asyncio
async def test_v9_models_category_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "models_cat.xlsx"
    source.write_bytes(build_template_v9(mode=ImportMode.APPEND))
    workbook = load_workbook(source)

    def append(sheet_name: str, values: Mapping[str, Any]) -> None:
        sheet = workbook[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        row: list[Any] = [None] * len(headers)
        for header, value in values.items():
            if header in headers:
                row[headers.index(header)] = value
        sheet.append(row)

    cat_id = uuid4()
    mark_id = uuid4()
    append("Модели", {"Код": "kamaz-65115", "Название": "65115", "Код марки": "kamaz", "Код категории": "trucks", "Активность": "Да"})
    workbook.save(source)
    workbook.close()

    parsed = parse_xlsx(source, expected_mode=ImportMode.APPEND)

    async def mock_context(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "marks": {"kamaz": {"id": mark_id, "name": "КамАЗ", "is_active": True}},
            "models": {},
            "categories": {"trucks": {"id": cat_id, "name": "Грузовики", "is_active": True}},
            "modifications": {},
            "superstructures": {},
            "superstructure_categories": set(),
            "attribute_groups": {},
            "attributes": {},
            "attribute_options": {},
            "products": {},
            "category_relations": set(),
            "modification_categories": set(),
            "product_categories": set(),
            "companies": {},
        }

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", mock_context)

    plan, issues, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.APPEND.value},
        workbook=parsed,
        plan_spool_dir=tmp_path / "plan-models",
    )
    assert issues.error_count == 0
    model_row = next(iter(plan["models"]))
    assert model_row["values"]["category_id"] == str(cat_id)


@pytest.mark.asyncio
async def test_v9_superstructure_categories_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sup_cat.xlsx"
    source.write_bytes(build_template_v9(mode=ImportMode.APPEND))
    workbook = load_workbook(source)

    def append(sheet_name: str, values: Mapping[str, Any]) -> None:
        sheet = workbook[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        row: list[Any] = [None] * len(headers)
        for header, value in values.items():
            if header in headers:
                row[headers.index(header)] = value
        sheet.append(row)

    sup_id = uuid4()
    cat_id = uuid4()
    append("Категории надстроек", {"Код надстройки": "crane", "Код категории": "trucks"})
    workbook.save(source)
    workbook.close()

    parsed = parse_xlsx(source, expected_mode=ImportMode.APPEND)

    async def mock_context(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "marks": {},
            "models": {},
            "categories": {"trucks": {"id": cat_id, "name": "Грузовики", "is_active": True}},
            "superstructures": {"crane": {"id": sup_id, "name": "Кран-манипулятор", "is_active": True}},
            "superstructure_categories": set(),
            "modifications": {},
            "attribute_groups": {},
            "attributes": {},
            "attribute_options": {},
            "products": {},
            "category_relations": set(),
            "modification_categories": set(),
            "product_categories": set(),
            "companies": {},
        }

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", mock_context)

    plan, issues, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.APPEND.value},
        workbook=parsed,
        plan_spool_dir=tmp_path / "plan-sup-cat",
    )
    assert issues.error_count == 0
    link = next(iter(plan["superstructure_categories"]))
    assert link["values"]["superstructure_id"] == str(sup_id)
    assert link["values"]["category_id"] == str(cat_id)


@pytest.mark.asyncio
async def test_v9_standalone_superstructure_and_kit_vin_validations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "products_v9.xlsx"
    source.write_bytes(build_template_v9(mode=ImportMode.APPEND))
    workbook = load_workbook(source)

    def append(sheet_name: str, values: Mapping[str, Any]) -> None:
        sheet = workbook[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        row: list[Any] = [None] * len(headers)
        for header, value in values.items():
            if header in headers:
                row[headers.index(header)] = value
        sheet.append(row)

    sup_id = uuid4()
    mod_id = uuid4()
    model_id = uuid4()

    # 1. Standalone superstructure with chassis_vin should FAIL (PRODUCT_KIND_CONFLICT)
    append("Объявления", {
        "Код": "sup-invalid",
        "Код модификации": "mod-1",
        "Код надстройки": "crane",
        "VIN транспортного средства": "VIN12345678901234",
        "VIN шасси": "CHASSIS1234567890",
        "Состояние": "Новое",
        "Год выпуска": 2024,
        "Цена": 1_000_000,
        "Валюта": "RUB",
        "Статус публикации": "Черновик",
        "Статус продажи": "Доступно",
    })

    # 2. Kit without chassis_vin when no_vin=False should FAIL (CHASSIS_VIN_REQUIRED_FOR_KIT)
    append("Объявления", {
        "Код": "kit-invalid",
        "Код модели": "model-1",
        "Код модификации": "mod-1",
        "Код надстройки": "crane",
        "Код модели надстройки": "sup-model-1",
        "Название надстройки": "Манипулятор",
        "Производитель надстройки": "Инмаш",
        "VIN транспортного средства": "VIN12345678901235",
        "Состояние": "Новое",
        "Год выпуска": 2024,
        "Цена": 2_000_000,
        "Валюта": "RUB",
        "Статус публикации": "Черновик",
        "Статус продажи": "Доступно",
    })

    # 3. Product with no_vin=True but vin or chassis_vin populated should FAIL (VIN_MUST_BE_EMPTY)
    append("Объявления", {
        "Код": "no-vin-invalid",
        "Код модификации": "mod-1",
        "Нет VIN": "Да",
        "VIN надстройки": "SUPVIN12345",
        "Состояние": "Новое",
        "Год выпуска": 2024,
        "Цена": 3_000_000,
        "Валюта": "RUB",
        "Статус публикации": "Черновик",
        "Статус продажи": "Доступно",
    })

    # 4. Valid standalone superstructure
    append("Объявления", {
        "Код": "sup-valid",
        "Код модификации": "mod-1",
        "Код надстройки": "crane",
        "VIN транспортного средства": "VIN12345678901236",
        "Состояние": "Новое",
        "Год выпуска": 2024,
        "Цена": 1_500_000,
        "Валюта": "RUB",
        "Статус публикации": "Черновик",
        "Статус продажи": "Доступно",
    })
    append("Категории объявлений", {"Код объявления": "sup-valid", "Код категории": "trucks"})

    workbook.save(source)
    workbook.close()

    parsed = parse_xlsx(source, expected_mode=ImportMode.APPEND)

    sup_model_id = uuid4()
    cat_id = uuid4()

    async def mock_context(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "marks": {},
            "models": {
                "model-1": {"id": model_id, "name": "Модель 1", "is_active": True},
                "sup-model-1": {"id": sup_model_id, "name": "Модель надстройки 1", "is_active": True},
            },
            "categories": {"trucks": {"id": cat_id, "name": "Грузовики", "is_active": True, "usage_metric": "mileage"}},
            "superstructures": {"crane": {"id": sup_id, "name": "Кран", "is_active": True}},
            "superstructure_categories": {(sup_id, cat_id)},
            "modifications": {"mod-1": {"id": mod_id, "name": "Модификация 1", "model_id": model_id, "is_active": True}},
            "attribute_groups": {},
            "attributes": {},
            "attribute_options": {},
            "products": {},
            "category_relations": set(),
            "modification_categories": {(mod_id, cat_id)},
            "product_categories": set(),
            "companies": {},
        }

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", mock_context)

    plan, issues, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": ImportMode.APPEND.value},
        workbook=parsed,
        plan_spool_dir=tmp_path / "plan-vin-val",
    )

    issue_codes = {i.code for i in issues}
    assert "PRODUCT_KIND_CONFLICT" in issue_codes
    assert "CHASSIS_VIN_REQUIRED_FOR_KIT" in issue_codes
    assert "VIN_MUST_BE_EMPTY" in issue_codes

    # Check that sup-valid was accepted
    valid_products = [p for p in plan["products"] if p["code"] == "sup-valid"]
    assert len(valid_products) == 1
    assert valid_products[0]["values"]["superstructure_id"] == str(sup_id)
    assert valid_products[0]["values"]["model_id"] is None


def test_v9_export_product_row_vin_and_standalone() -> None:
    # 1. Standalone superstructure product export retains superstructure_code
    sup_prod = {
        "id": uuid4(),
        "code": "sup-prod-1",
        "superstructure_id": uuid4(),
        "superstructure_code": "crane-sup",
        "vin": "VIN12345678901234",
    }
    row_sup = export_product_row(sup_prod, version=9)
    assert row_sup["superstructure_code"] == "crane-sup"
    assert row_sup["chassis_vin"] is None
    assert row_sup["superstructure_vin"] is None
    assert row_sup["vin"] == "VIN12345678901234"

    # 2. Kit export includes chassis_vin and superstructure_vin
    kit_prod = {
        "id": uuid4(),
        "code": "kit-prod-1",
        "model_id": uuid4(),
        "model_code": "kamaz-65115",
        "superstructure_id": uuid4(),
        "superstructure_code": "crane-sup",
        "vin": "VIN12345678901234",
        "chassis_vin": "CHASSIS123456789",
        "superstructure_vin": "SUP1234567890123",
        "superstructure_name": "Манипулятор",
        "superstructure_manufacturer": "Инмаш",
    }
    row_kit = export_product_row(kit_prod, version=9)
    assert row_kit["vin"] == "VIN12345678901234"
    assert row_kit["chassis_vin"] == "CHASSIS123456789"
    assert row_kit["superstructure_vin"] == "SUP1234567890123"
    assert row_kit["superstructure_code"] == "crane-sup"
