"""Query and projection tests for special equipment kit products."""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct,
)
from infrastructure.repositories.special_equipment_repository import (
    AttributePredicate,
    SpecialEquipmentFilters,
    _attribute_filter_clauses,
    _filtered_product_ids,
    _product_projection,
)


def _compile(stmt: sa.sql.ClauseElement) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_product_projection_uses_coalesce_for_model() -> None:
    """_product_projection must outer-join modification and coalesce model_id."""
    stmt = _product_projection()
    sql = _compile(stmt)
    assert "LEFT OUTER JOIN special_equipment_modifications" in sql
    assert "coalesce(special_equipment_modifications.model_id, special_equipment_products.model_id)" in sql.lower()


def test_filtered_product_ids_uses_coalesce_and_supports_kits() -> None:
    """_filtered_product_ids must allow kit products without modification."""
    stmt = _filtered_product_ids(SpecialEquipmentFilters())
    sql = _compile(stmt)
    assert "LEFT OUTER JOIN special_equipment_modifications" in sql
    assert "coalesce(special_equipment_modifications.model_id, special_equipment_products.model_id)" in sql.lower()
    assert "special_equipment_modifications.id is null or special_equipment_modifications.is_active is true" in sql.lower()


def test_attribute_filter_clauses_includes_chassis_and_superstructure_values() -> None:
    """Attribute filtering must query chassis and superstructure values by product_id."""
    attr_id = uuid4()
    clauses = _attribute_filter_clauses(
        [AttributePredicate(attribute_id=attr_id, operator="eq", value="test_val")],
        modification_id=SpecialEquipmentProduct.modification_id,
        trim_id=SpecialEquipmentProduct.trim_id,
        product_id=SpecialEquipmentProduct.id,
    )
    assert len(clauses) == 1
    sql = _compile(sa.select(SpecialEquipmentProduct.id).where(*clauses))
    assert "special_equipment_product_chassis_values" in sql
    assert "special_equipment_product_superstructure_values" in sql


def test_effective_filtered_product_ids_uses_coalesce_for_model() -> None:
    """_effective_filtered_product_ids must outer-join modification and coalesce model_id."""
    from infrastructure.repositories.special_equipment_repository import (
        _effective_filtered_product_ids,
    )

    stmt = _effective_filtered_product_ids(SpecialEquipmentFilters())
    sql = _compile(stmt)
    assert "LEFT OUTER JOIN special_equipment_modifications" in sql
    assert "coalesce(se_filter_modification.model_id, special_equipment_products.model_id)" in sql.lower()


def test_public_offering_group_rows_includes_kit_fields() -> None:
    """_public_offering_group_rows must include superstructure fields in base_rows and base_key."""
    from infrastructure.repositories.special_equipment_repository import (
        _public_offering_group_rows,
    )

    base_rows, _grouped_rows = _public_offering_group_rows(SpecialEquipmentFilters())
    base_sql = _compile(sa.select(base_rows))
    assert "superstructure_id" in base_sql
    assert "superstructure_name" in base_sql
    assert "LEFT OUTER JOIN special_equipment_modifications" in base_sql

