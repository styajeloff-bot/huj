"""Tests for domain/special_equipment_kits.py."""

from uuid import uuid4

import pytest

from domain.special_equipment_kits import (
    KitInvariantError,
    ensure_kit_categories,
    ensure_superstructure_card_limit,
    kit_title,
)


def test_kit_title_formats_correctly() -> None:
    # Rule К4: «{Название надстройки} на базе {Марка шасси} {Модель шасси}»
    assert (
        kit_title(
            superstructure_name="АТЗ-10",
            chassis_mark_name="FOTON",
            chassis_model_name="D18",
        )
        == "АТЗ-10 на базе FOTON D18"
    )


def test_ensure_kit_categories_rejects_empty_and_attachment_branches() -> None:
    # Rule Ш1: Категории — хотя бы одна, только обычные (не ветка надстроек) -> KIT_ATTACHMENT_CATEGORY
    cat_normal = uuid4()
    cat_attachment = uuid4()
    attachment_branch = {cat_attachment}

    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_categories([], attachment_branch)
    assert exc_info.value.code == "KIT_ATTACHMENT_CATEGORY"

    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_categories([cat_normal, cat_attachment], attachment_branch)
    assert exc_info.value.code == "KIT_ATTACHMENT_CATEGORY"

    # Valid ordinary categories pass
    ensure_kit_categories([cat_normal], attachment_branch)


def test_ensure_superstructure_card_limit() -> None:
    # Rule С4: «В карточке» не больше 6 на тип -> SUPERSTRUCTURE_CARD_LIMIT_EXCEEDED
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_superstructure_card_limit(7)
    assert exc_info.value.code == "SUPERSTRUCTURE_CARD_LIMIT_EXCEEDED"

    ensure_superstructure_card_limit(6)
    ensure_superstructure_card_limit(0)


def test_ensure_superstructure_attribute_groups() -> None:
    # Rule С3: Группа у назначения обязательна; если характеристика не входит в группу -> SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH
    from domain.special_equipment_kits import (
        SuperstructureAttributeAssignment,
        ensure_superstructure_attribute_groups,
    )

    attr1, attr2 = uuid4(), uuid4()
    group1, group2 = uuid4(), uuid4()
    attr_to_group = {attr1: group1, attr2: group2}

    # Mismatch group
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_superstructure_attribute_groups(
            [SuperstructureAttributeAssignment(attribute_id=attr1, group_id=group2)],
            attr_to_group,
        )
    assert exc_info.value.code == "SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH"

    # Duplicate attribute
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_superstructure_attribute_groups(
            [
                SuperstructureAttributeAssignment(attribute_id=attr1, group_id=group1),
                SuperstructureAttributeAssignment(attribute_id=attr1, group_id=group1),
            ],
            attr_to_group,
        )
    assert exc_info.value.code == "SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH"

    # Card limit exceeded (> 6 visible)
    visible_assignments = [
        SuperstructureAttributeAssignment(
            attribute_id=uuid4(), group_id=group1, is_visible=True
        )
        for _ in range(7)
    ]
    mapping = {a.attribute_id: group1 for a in visible_assignments}
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_superstructure_attribute_groups(visible_assignments, mapping)
    assert exc_info.value.code == "SUPERSTRUCTURE_CARD_LIMIT_EXCEEDED"

    # Valid
    valid_assignments = [
        SuperstructureAttributeAssignment(attribute_id=attr1, group_id=group1, is_visible=True),
        SuperstructureAttributeAssignment(attribute_id=attr2, group_id=group2, is_visible=False),
    ]
    ensure_superstructure_attribute_groups(valid_assignments, attr_to_group)


def test_ensure_kit_chassis_values() -> None:
    # Rules Ш4–Ш5
    from domain.special_equipment_kits import (
        ChassisAttributeContract,
        ChassisAttributeRule,
        ensure_kit_chassis_values,
    )

    attr_req = uuid4()
    attr_opt = uuid4()
    group = uuid4()

    contract = ChassisAttributeContract(
        rules_by_attribute_id={
            attr_req: ChassisAttributeRule(
                attribute_id=attr_req,
                group_id=group,
                is_required=True,
                is_visible=True,
                is_filterable=True,
                sort_order=1,
            ),
            attr_opt: ChassisAttributeRule(
                attribute_id=attr_opt,
                group_id=group,
                is_required=False,
                is_visible=False,
                is_filterable=False,
                sort_order=2,
            ),
        }
    )

    # Ш4: When modification is chosen, own chassis values must NOT be provided
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_chassis_values(
            contract=contract,
            provided_attribute_ids=[attr_req],
            filled_attribute_ids=[attr_req],
            has_modification=True,
        )
    assert exc_info.value.code == "KIT_CHASSIS_VALUES_WITH_MODIFICATION"

    # Without modification: missing required value
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_chassis_values(
            contract=contract,
            provided_attribute_ids=[attr_opt],
            filled_attribute_ids=[attr_opt],
            has_modification=False,
        )
    assert exc_info.value.code == "KIT_REQUIRED_VALUE_MISSING"

    # Foreign attribute not in category rules
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_chassis_values(
            contract=contract,
            provided_attribute_ids=[attr_req, uuid4()],
            filled_attribute_ids=[attr_req],
            has_modification=False,
        )
    assert exc_info.value.code == "KIT_CHASSIS_ATTRIBUTE_NOT_IN_CATEGORY"

    # Valid values without modification
    ensure_kit_chassis_values(
        contract=contract,
        provided_attribute_ids=[attr_req, attr_opt],
        filled_attribute_ids=[attr_req],
        has_modification=False,
    )


def test_ensure_kit_superstructure() -> None:
    # Rule Н1–Н5
    from domain.special_equipment_kits import ensure_kit_superstructure

    model1 = uuid4()
    model2 = uuid4()

    # Inactive
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_superstructure(
            superstructure_is_active=False,
            superstructure_model_id=model1,
            superstructure_name="Kamaz",
            superstructure_manufacturer="Kamaz Corp",
        )
    assert exc_info.value.code == "SUPERSTRUCTURE_NOT_FOUND"

    # Name required for manual kit
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_superstructure(
            superstructure_is_active=True,
            superstructure_model_id=None,
            superstructure_name="",
            superstructure_manufacturer="Kamaz Corp",
        )
    assert exc_info.value.code == "KIT_REQUIRED_VALUE_MISSING"

    # Manufacturer required for manual kit
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_superstructure(
            superstructure_is_active=True,
            superstructure_model_id=None,
            superstructure_name="Kamaz",
            superstructure_manufacturer="",
        )
    assert exc_info.value.code == "KIT_REQUIRED_VALUE_MISSING"

    # Manual kit without model is valid when name & manufacturer provided
    ensure_kit_superstructure(
        superstructure_is_active=True,
        superstructure_model_id=None,
        superstructure_name="Kamaz",
        superstructure_manufacturer="Kamaz Corp",
    )

    # Modification model mismatch
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_superstructure(
            superstructure_is_active=True,
            superstructure_model_id=model1,
            superstructure_modification_model_id=model2,
            superstructure_name="Kamaz",
            superstructure_manufacturer="Kamaz Corp",
        )
    assert exc_info.value.code == "KIT_SUPERSTRUCTURE_MODIFICATION_MODEL_MISMATCH"

    # Source product: self-reference
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_superstructure(
            superstructure_is_active=True,
            superstructure_source_product_id=model1,
            source_product={"id": model1, "publication_status": "published"},
            current_product_id=model1,
            source_is_attachment=True,
        )
    assert exc_info.value.code == "KIT_SUPERSTRUCTURE_SOURCE_INVALID"

    # Source product: not attachment
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_superstructure(
            superstructure_is_active=True,
            superstructure_source_product_id=model1,
            source_product={"id": model1, "publication_status": "published"},
            current_product_id=model2,
            source_is_attachment=False,
        )
    assert exc_info.value.code == "KIT_SUPERSTRUCTURE_SOURCE_INVALID"

    # Source product: valid
    ensure_kit_superstructure(
        superstructure_is_active=True,
        superstructure_source_product_id=model1,
        source_product={"id": model1, "publication_status": "published"},
        current_product_id=model2,
        source_is_attachment=True,
    )

    # Manual superstructure: valid
    ensure_kit_superstructure(
        superstructure_is_active=True,
        superstructure_model_id=model1,
        superstructure_modification_model_id=model1,
        superstructure_name="Kamaz",
        superstructure_manufacturer="Kamaz Corp",
    )


def test_values_kept_after_change() -> None:
    # Rules Ш6 / Н6
    from domain.special_equipment_kits import values_kept_after_change

    a1, a2, a3 = uuid4(), uuid4(), uuid4()
    old = {a1: "val1", a2: "val2", a3: "val3"}
    allowed = {a1, a3}
    assert values_kept_after_change(old, allowed) == {a1: "val1", a3: "val3"}


def test_kit_card_attributes() -> None:
    # Rule К6: up to 6 attributes: superstructure first, then chassis
    from domain.special_equipment_kits import kit_card_attributes

    sup_rows = [
        {"name": f"sup_{i}", "is_visible": True, "value": f"v_{i}"}
        for i in range(4)
    ]
    chassis_rows = [
        {"name": f"chassis_{i}", "is_visible": True, "value": f"cv_{i}"}
        for i in range(4)
    ]
    res = kit_card_attributes(sup_rows, chassis_rows, limit=6)
    assert len(res) == 6
    assert [r["name"] for r in res] == [
        "sup_0", "sup_1", "sup_2", "sup_3", "chassis_0", "chassis_1"
    ]


def test_ensure_kit_vins() -> None:
    from domain.special_equipment_kits import ensure_kit_vins

    # no_vin is True: all VINs must be empty
    ensure_kit_vins(vin=None, chassis_vin=None, superstructure_vin=None, no_vin=True)
    ensure_kit_vins(vin="", chassis_vin="", superstructure_vin="", no_vin=True)

    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_vins(vin="ABC12345678901234", chassis_vin=None, superstructure_vin=None, no_vin=True)
    assert exc_info.value.code == "KIT_VIN_NOT_EMPTY"

    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_vins(vin=None, chassis_vin="CHASSIS123", superstructure_vin=None, no_vin=True)
    assert exc_info.value.code == "KIT_VIN_NOT_EMPTY"

    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_vins(vin=None, chassis_vin=None, superstructure_vin="SUPER123", no_vin=True)
    assert exc_info.value.code == "KIT_VIN_NOT_EMPTY"

    # no_vin is False: chassis_vin is required
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_vins(vin="ABC12345678901234", chassis_vin="", superstructure_vin=None, no_vin=False)
    assert exc_info.value.code == "KIT_CHASSIS_VIN_REQUIRED"

    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_vins(vin="ABC12345678901234", chassis_vin="A" * 33, superstructure_vin=None, no_vin=False)
    assert exc_info.value.code == "KIT_CHASSIS_VIN_TOO_LONG"

    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_vins(vin="ABC12345678901234", chassis_vin="CHASSIS123", superstructure_vin="S" * 33, no_vin=False)
    assert exc_info.value.code == "KIT_SUPERSTRUCTURE_VIN_TOO_LONG"

    # Valid kit VINs
    ensure_kit_vins(vin="ABC12345678901234", chassis_vin="CHASSIS123", superstructure_vin=None, no_vin=False)
    ensure_kit_vins(vin="ABC12345678901234", chassis_vin="CHASSIS123", superstructure_vin="SUPER123", no_vin=False)


def test_ensure_standalone_superstructure() -> None:
    from domain.special_equipment_kits import ensure_standalone_superstructure

    # None superstructure_id -> ok
    ensure_standalone_superstructure(superstructure_is_active=True, superstructure_id=None)

    # Inactive superstructure -> error
    s_id = uuid4()
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_standalone_superstructure(superstructure_is_active=False, superstructure_id=s_id)
    assert exc_info.value.code == "SUPERSTRUCTURE_NOT_FOUND"

    # Category not allowed
    cat1, cat2 = uuid4(), uuid4()
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_standalone_superstructure(
            superstructure_is_active=True,
            superstructure_id=s_id,
            allowed_category_ids=[cat1],
            category_ids=[cat2],
        )
    assert exc_info.value.code == "SUPERSTRUCTURE_CATEGORY_NOT_ALLOWED"

    # Category allowed
    ensure_standalone_superstructure(
        superstructure_is_active=True,
        superstructure_id=s_id,
        allowed_category_ids=[cat1],
        category_ids=[cat1],
    )


def test_kit_source_standalone_superstructure() -> None:
    from domain.special_equipment_kits import ensure_kit_superstructure

    source_id = uuid4()
    kit_id = uuid4()
    standalone_source = {
        "id": source_id,
        "model_id": None,
        "superstructure_id": uuid4(),
        "publication_status": "published",
    }
    ensure_kit_superstructure(
        superstructure_is_active=True,
        superstructure_source_product_id=source_id,
        source_product=standalone_source,
        current_product_id=kit_id,
        source_is_attachment=True,
    )

    kit_source = {
        "id": source_id,
        "model_id": uuid4(),
        "superstructure_id": uuid4(),
        "publication_status": "published",
    }
    with pytest.raises(KitInvariantError) as exc_info:
        ensure_kit_superstructure(
            superstructure_is_active=True,
            superstructure_source_product_id=source_id,
            source_product=kit_source,
            current_product_id=kit_id,
            source_is_attachment=True,
        )
    assert exc_info.value.code == "KIT_SUPERSTRUCTURE_SOURCE_INVALID"


