"""Storefront and commerce snapshot tests for special equipment kits."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from application.queries.special_equipment import (
    _attribute_groups_resource,
    _product_resource,
)
from domain.special_equipment_commerce import ProductCommerceState
from infrastructure.repositories.special_equipment_repository import (
    SpecialEquipmentFilters,
    _filtered_product_ids,
    _product_projection,
)


def _compile(stmt: sa.sql.ClauseElement) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_product_projection_selects_superstructure_details() -> None:
    stmt = _product_projection()
    sql = _compile(stmt)
    assert "superstructure_type_name" in sql
    assert "superstructure_model_name" in sql
    assert "superstructure_mark_name" in sql
    assert "superstructure_mod_name" in sql


def test_filtered_product_ids_search_includes_superstructure_mark_and_model() -> None:
    stmt = _filtered_product_ids(SpecialEquipmentFilters(search="Вектор"))
    sql = _compile(stmt)
    assert "filter_super_model" in sql or "se_filter_super_model" in sql or "superstructure" in sql


def test_product_resource_for_kit_product() -> None:
    chassis_model_id = uuid4()
    chassis_mark_id = uuid4()
    super_type_id = uuid4()
    super_model_id = uuid4()
    super_mark_id = uuid4()

    row = {
        "id": uuid4(),
        "code": "SE-KIT-1",
        "slug": "se-kit-1",
        "modification_id": None,
        "modification_code": None,
        "modification_name": None,
        "modification_slug": None,
        "year_from": None,
        "year_to": None,
        "model_id": chassis_model_id,
        "model_code": "D18",
        "model_name": "D18",
        "model_slug": "d18",
        "mark_id": chassis_mark_id,
        "mark_code": "FOTON",
        "mark_name": "FOTON",
        "mark_slug": "foton",
        "trim_id": None,
        "trim_name": None,
        "condition": "new",
        "owners_count": 0,
        "mileage_km": None,
        "engine_hours": None,
        "price": Decimal("5000000.00"),
        "base_price": Decimal("5000000.00"),
        "special_price": None,
        "price_on_request": False,
        "price_from": None,
        "currency_code": "RUB",
        "manufacture_year": 2026,
        "sale_status": "available",
        "body_color_id": None,
        "body_color_name": None,
        "interior_color_id": None,
        "interior_color_name": None,
        "available_count": 1,
        "categories": [],
        "superstructure_id": super_type_id,
        "superstructure_type_code": "ATZ_10",
        "superstructure_type_name": "Автотопливозаправщик",
        "superstructure_model_id": super_model_id,
        "superstructure_model_code": "ATZ10",
        "superstructure_model_name": "АТЗ-10",
        "superstructure_model_slug": "atz-10",
        "superstructure_mark_id": super_mark_id,
        "superstructure_mark_code": "VEKTOR",
        "superstructure_mark_name": "Вектор",
        "superstructure_mark_slug": "vektor",
        "superstructure_mod_id": None,
        "superstructure_mod_code": None,
        "superstructure_mod_name": None,
        "superstructure_mod_slug": None,
        "superstructure_name": "АТЗ-10",
        "superstructure_manufacturer": "НПО Вектор",
    }
    resource = _product_resource(row)
    assert resource["modification"] is None
    assert resource["model"]["id"] == chassis_model_id
    assert resource["model"]["name"] == "D18"
    assert resource["model"]["mark"]["name"] == "FOTON"
    assert resource["title"] == "АТЗ-10 на базе FOTON D18"
    assert resource["superstructure"] is not None
    assert resource["superstructure"]["name"] == "АТЗ-10"
    assert resource["superstructure"]["manufacturer"] == "НПО Вектор"
    assert resource["superstructure"]["type"]["name"] == "Автотопливозаправщик"
    assert resource["superstructure"]["mark"]["name"] == "Вектор"
    assert resource["superstructure"]["model"]["name"] == "АТЗ-10"


def test_product_resource_for_standard_product() -> None:
    model_id = uuid4()
    mark_id = uuid4()
    mod_id = uuid4()

    row = {
        "id": uuid4(),
        "code": "SE-STD-1",
        "slug": "se-std-1",
        "modification_id": mod_id,
        "modification_code": "M1",
        "modification_name": "Standard Mod",
        "modification_slug": "standard-mod",
        "year_from": 2020,
        "year_to": None,
        "model_id": model_id,
        "model_code": "MOD1",
        "model_name": "Model 1",
        "model_slug": "model-1",
        "mark_id": mark_id,
        "mark_code": "MARK1",
        "mark_name": "Mark 1",
        "mark_slug": "mark-1",
        "trim_id": None,
        "trim_name": None,
        "condition": "new",
        "owners_count": 0,
        "mileage_km": None,
        "engine_hours": None,
        "price": Decimal("1000000.00"),
        "base_price": Decimal("1000000.00"),
        "special_price": None,
        "price_on_request": False,
        "price_from": None,
        "currency_code": "RUB",
        "manufacture_year": 2025,
        "sale_status": "available",
        "body_color_id": None,
        "body_color_name": None,
        "interior_color_id": None,
        "interior_color_name": None,
        "available_count": 1,
        "categories": [],
        "superstructure_id": None,
    }
    resource = _product_resource(row)
    assert resource["modification"] is not None
    assert resource["modification"]["name"] == "Standard Mod"
    assert resource["model"]["name"] == "Model 1"
    assert resource["model"]["mark"]["name"] == "Mark 1"
    assert resource["title"] == "Mark 1 Model 1"
    assert resource["superstructure"] is None


def test_attribute_groups_resource_preserves_section_and_orders_chassis_first() -> None:
    chassis_group_id = uuid4()
    super_group_id = uuid4()

    rows = [
        {
            "id": uuid4(),
            "code": "SUPER_VOL",
            "name": "Объем цистерны",
            "data_type": "number",
            "unit": "м³",
            "group_id": super_group_id,
            "group_name": "Параметры цистерны",
            "group_sort_order": 1,
            "section": "superstructure",
            "value_number": Decimal("10"),
            "value_text": None,
            "value_boolean": None,
            "option_id": None,
            "option_name": None,
        },
        {
            "id": uuid4(),
            "code": "CHASSIS_WHEEL_FORMULA",
            "name": "Колесная формула",
            "data_type": "text",
            "unit": None,
            "group_id": chassis_group_id,
            "group_name": "Ходовая часть",
            "group_sort_order": 1,
            "section": "chassis",
            "value_number": None,
            "value_text": "4x2",
            "value_boolean": None,
            "option_id": None,
            "option_name": None,
        },
    ]

    _flat, groups = _attribute_groups_resource(rows)
    assert len(groups) == 2
    assert groups[0]["name"] == "Ходовая часть"
    assert groups[0]["section"] == "chassis"
    assert groups[1]["name"] == "Параметры цистерны"
    assert groups[1]["section"] == "superstructure"


def test_product_commerce_state_snapshot_kit_fields() -> None:
    prod_id = uuid4()
    super_id = uuid4()
    seller_id = uuid4()

    data = {
        "id": prod_id,
        "mark_name": "FOTON",
        "model_name": "D18",
        "modification_name": None,
        "manufacture_year": 2026,
        "vin": "X991234567890ABCD",
        "price": Decimal("6000000.00"),
        "currency_code": "RUB",
        "seller_company_id": seller_id,
        "publication_status": "published",
        "sale_status": "available",
        "superstructure_id": super_id,
        "superstructure_name": "АТЗ-10",
        "superstructure_type_name": "Автотопливозаправщик",
        "superstructure_manufacturer": "НПО Вектор",
    }
    state = ProductCommerceState.from_dict(data)
    snapshot = state.snapshot()

    assert snapshot["product_id"] == str(prod_id)
    assert snapshot["title"] == "АТЗ-10 на базе FOTON D18"
    assert snapshot["superstructure_name"] == "АТЗ-10"
    assert snapshot["superstructure_type_name"] == "Автотопливозаправщик"
    assert snapshot["superstructure_manufacturer"] == "НПО Вектор"
    assert snapshot["chassis_mark_name"] == "FOTON"
    assert snapshot["chassis_model_name"] == "D18"
    assert snapshot["chassis_modification_name"] is None
