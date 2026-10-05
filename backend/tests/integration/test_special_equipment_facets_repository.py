"""Facet/query compiler contracts for modification-owned values."""

from uuid import uuid4

from infrastructure.repositories.special_equipment_repository import (
    AttributePredicate,
    SpecialEquipmentFilters,
)


def test_filter_contract_keeps_dynamic_predicates_and_usage_exclusive() -> None:
    attribute_id = uuid4()
    filters = SpecialEquipmentFilters(
        category_id=uuid4(),
        engine_hours_min=100,
        engine_hours_max=500,
        attributes=(
            AttributePredicate(attribute_id, "gte", "200"),
            AttributePredicate(attribute_id, "lte", "400"),
        ),
    )
    assert filters.mileage_min is None
    assert [item.operator for item in filters.attributes] == ["gte", "lte"]
