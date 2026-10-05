"""Regression coverage for published-catalog dependency guards."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands import special_equipment_management as commands
from domain.special_equipment_attachments import AttachmentInvariantError
from domain.special_equipment_management import (
    AttributeTypeConversionBlockedError,
    SpecialEquipmentManagementConflictError,
    SpecialEquipmentManagementValidationError,
)
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentAttributeOption,
    SpecialEquipmentModificationAttributeValue,
)
from infrastructure.repositories import (
    special_equipment_management_repository as repository,
)

pytestmark = pytest.mark.asyncio


async def _create(
    session: AsyncSession,
    *,
    entity_type: repository.EntityType,
    values: dict[str, Any],
) -> dict[str, Any]:
    return await commands.create_entity(
        session,
        entity_type=entity_type,
        values=values,
    )


async def _published_catalog(
    session: AsyncSession,
    *,
    required_attribute: bool = False,
    select_attribute: bool = False,
    text_attribute: bool = False,
) -> dict[str, Any]:
    suffix = uuid4().hex
    seller = Company(
        name=f"Продавец {suffix}",
        inn=suffix[:12],
        company_type="dealer",
        is_active=True,
    )
    session.add(seller)
    await session.flush()
    mark = await _create(
        session,
        entity_type="mark",
        values={
            "code": f"mark-{suffix}",
            "name": f"Марка {suffix}",
            "is_active": True,
        },
    )
    model = await _create(
        session,
        entity_type="model",
        values={
            "code": f"model-{suffix}",
            "name": f"Модель {suffix}",
            "mark_id": mark["id"],
            "is_active": True,
        },
    )
    group = None
    attribute = None
    option = None
    attribute_links: list[dict[str, Any]] = []
    attribute_values: list[dict[str, Any]] = []
    if required_attribute:
        group = await _create(
            session,
            entity_type="attribute_group",
            values={
                "code": f"group-{suffix}",
                "name": f"Группа {suffix}",
                "sort_order": 0,
                "is_active": True,
            },
        )
        attribute = await _create(
            session,
            entity_type="attribute",
            values={
                "code": f"power-{suffix}",
                "name": f"Мощность {suffix}",
                "data_type": (
                    "select"
                    if select_attribute
                    else "text"
                    if text_attribute
                    else "number"
                ),
                "unit": None if select_attribute or text_attribute else "л.с.",
                "filter_kind": (
                    "exact"
                    if select_attribute
                    else "search"
                    if text_attribute
                    else "range"
                ),
                "is_active": True,
                "options": (
                    [
                        {
                            "code": f"diesel-{suffix}",
                            "name": f"Дизель {suffix}",
                            "sort_order": 0,
                            "is_active": True,
                        }
                    ]
                    if select_attribute
                    else []
                ),
            },
        )
        option = attribute["options"][0] if select_attribute else None
        attribute_links = [
            {
                "attribute_id": attribute["id"],
                "group_id": group["id"],
                "is_required": True,
                "is_filterable": True,
                "is_visible": True,
                "sort_order": 0,
            }
        ]
        attribute_values = [
            {
                "attribute_id": attribute["id"],
                "option_id": option["id"] if option is not None else None,
                "value": (
                    None
                    if option is not None
                    else "Белый"
                    if text_attribute
                    else "250"
                ),
            }
        ]
    category = await _create(
        session,
        entity_type="category",
        values={
            "code": f"category-{suffix}",
            "name": f"Категория {suffix}",
            "usage_metric": "engine_hours",
            "sort_order": 0,
            "is_active": True,
            "parent_ids": [],
            "attribute_links": attribute_links,
        },
    )
    modification = await _create(
        session,
        entity_type="modification",
        values={
            "code": f"modification-{suffix}",
            "name": f"Модификация {suffix}",
            "model_id": model["id"],
            "year_from": 2020,
            "year_to": 2026,
            "is_active": True,
            "category_ids": [category["id"]],
            "attribute_values": attribute_values,
        },
    )
    product = await _create(
        session,
        entity_type="product",
        values={
            "code": f"offer-{suffix}",
            "modification_id": modification["id"],
            "seller_company_id": seller.id,
            "description": None,
            "price": None,
            "currency_code": "RUB",
            "manufacture_year": 2024,
            "vin": None,
            "no_vin": True,
            "condition": "used",
            "owners_count": 1,
            "mileage_km": None,
            "engine_hours": 100,
            "publication_status": "published",
            "sale_status": "available",
            "category_ids": [category["id"]],
        },
    )
    return {
        "mark": mark,
        "model": model,
        "group": group,
        "attribute": attribute,
        "option": option,
        "category": category,
        "modification": modification,
        "product": product,
    }


async def test_category_metric_and_deactivation_preserve_published_products(
    db_session: AsyncSession,
) -> None:
    catalog = await _published_catalog(db_session)
    category = catalog["category"]

    with pytest.raises(
        SpecialEquipmentManagementConflictError
    ) as metric_conflict:
        async with db_session.begin_nested():
            await commands.patch_entity(
                db_session,
                entity_type="category",
                entity_id=category["id"],
                values={"usage_metric": "mileage_km"},
                expected_version=category["lock_version"],
            )
    assert metric_conflict.value.entity_type == "category"
    assert metric_conflict.value.entity_id == category["id"]
    assert sum(
        item.count for item in metric_conflict.value.dependencies
    ) == 1

    with pytest.raises(SpecialEquipmentManagementConflictError):
        async with db_session.begin_nested():
            await commands.patch_entity(
                db_session,
                entity_type="category",
                entity_id=category["id"],
                values={"is_active": False},
                expected_version=category["lock_version"],
            )


async def test_product_rejects_mixed_direct_and_modification_classification(
    db_session: AsyncSession,
) -> None:
    catalog = await _published_catalog(db_session)
    suffix = uuid4().hex
    attachment_category = await _create(
        db_session,
        entity_type="category",
        values={
            "code": f"attachment-category-{suffix}",
            "name": f"Надстройка {suffix}",
            "usage_metric": "engine_hours",
            "is_attachment_category": True,
            "sort_order": 0,
            "is_active": True,
            "parent_ids": [],
            "attribute_links": [],
        },
    )

    with pytest.raises(
        AttachmentInvariantError,
        match="одновременно относиться к обычной ветви и надстройкам",
    ):
        async with db_session.begin_nested():
            await _create(
                db_session,
                entity_type="product",
                values={
                    "code": f"mixed-offer-{suffix}",
                    "modification_id": catalog["modification"]["id"],
                    "seller_company_id": None,
                    "description": None,
                    "price": None,
                    "currency_code": "RUB",
                    "manufacture_year": 2024,
                    "vin": None,
                    "no_vin": True,
                    "condition": "used",
                    "owners_count": 1,
                    "mileage_km": None,
                    "engine_hours": 100,
                    "publication_status": "draft",
                    "sale_status": "available",
                    "category_ids": [attachment_category["id"]],
                },
            )


async def test_required_effective_attributes_and_live_values_are_guarded(
    db_session: AsyncSession,
) -> None:
    catalog = await _published_catalog(
        db_session, required_attribute=True
    )
    modification = catalog["modification"]
    category = catalog["category"]
    group = catalog["group"]
    assert group is not None

    with pytest.raises(SpecialEquipmentManagementConflictError):
        async with db_session.begin_nested():
            await commands.patch_entity(
                db_session,
                entity_type="modification",
                entity_id=modification["id"],
                values={"attribute_values": []},
                expected_version=modification["lock_version"],
            )

    suffix = uuid4().hex
    second_attribute = await _create(
        db_session,
        entity_type="attribute",
        values={
            "code": f"capacity-{suffix}",
            "name": f"Грузоподъёмность {suffix}",
            "data_type": "number",
            "unit": "т",
            "filter_kind": "range",
            "is_active": True,
            "options": [],
        },
    )
    current_link = category["attribute_links"][0]
    links = [
        {
            "attribute_id": current_link["attribute_id"],
            "group_id": current_link["group_id"],
            "is_required": True,
            "is_filterable": True,
            "is_visible": True,
            "sort_order": 0,
        },
        {
            "attribute_id": second_attribute["id"],
            "group_id": group["id"],
            "is_required": True,
            "is_filterable": True,
            "is_visible": True,
            "sort_order": 1,
        },
    ]
    with pytest.raises(SpecialEquipmentManagementConflictError):
        async with db_session.begin_nested():
            await commands.replace_category_attributes(
                db_session,
                category_id=category["id"],
                links=links,
                expected_version=category["lock_version"],
            )


async def test_text_attribute_type_conversion_requires_confirmation_and_preserves_links(
    db_session: AsyncSession,
) -> None:
    catalog = await _published_catalog(
        db_session,
        required_attribute=True,
        text_attribute=True,
    )
    attribute = catalog["attribute"]
    category = catalog["category"]
    modification = catalog["modification"]
    assert attribute is not None
    preexisting_option = SpecialEquipmentAttributeOption(
        attribute_id=attribute["id"],
        code="belyy",
        name="Не белый",
        sort_order=0,
    )
    db_session.add(preexisting_option)
    empty_modification = await _create(
        db_session,
        entity_type="modification",
        values={
            "code": f"empty-text-{uuid4().hex}",
            "name": "Модификация с пустым значением",
            "model_id": catalog["model"]["id"],
            "year_from": 2020,
            "year_to": 2026,
            "is_active": True,
            "category_ids": [category["id"]],
            "attribute_values": [],
        },
    )
    db_session.add(
        SpecialEquipmentModificationAttributeValue(
            modification_id=empty_modification["id"],
            attribute_id=attribute["id"],
            value_text="   ",
        )
    )
    await db_session.flush()

    with pytest.raises(SpecialEquipmentManagementConflictError):
        async with db_session.begin_nested():
            await commands.patch_entity(
                db_session,
                entity_type="attribute",
                entity_id=attribute["id"],
                values={"data_type": "select"},
                expected_version=attribute["lock_version"],
            )

    converted = await commands.patch_entity(
        db_session,
        entity_type="attribute",
        entity_id=attribute["id"],
        values={
            "data_type": "select",
            "confirm_type_conversion": True,
            "options": [
                {
                    "code": "krasnyy",
                    "name": "Красный",
                    "sort_order": 10,
                    "is_active": True,
                }
            ],
        },
        expected_version=attribute["lock_version"],
    )

    assert converted["id"] == attribute["id"]
    assert converted["data_type"] == "select"
    assert converted["filter_kind"] == "exact"
    options_by_name = {item["name"]: item for item in converted["options"]}
    assert set(options_by_name) == {"Не белый", "Белый", "Красный"}
    assert options_by_name["Белый"]["code"] == "belyy-2"
    refreshed_attribute = await repository.get_entity(
        db_session, "attribute", attribute["id"]
    )
    refreshed_category = await repository.get_entity(
        db_session, "category", category["id"]
    )
    refreshed_modification = await repository.get_entity(
        db_session, "modification", modification["id"]
    )
    assert refreshed_category is not None
    assert refreshed_modification is not None
    assert refreshed_attribute is not None
    assert {
        (item["code"], item["name"])
        for item in refreshed_attribute["options"]
    } == {
        ("belyy", "Не белый"),
        ("belyy-2", "Белый"),
        ("krasnyy", "Красный"),
    }
    assert refreshed_category["attribute_links"][0]["attribute_id"] == attribute["id"]
    assert refreshed_category["attribute_links"][0]["group_id"] == catalog["group"]["id"]
    assert refreshed_modification["attribute_values"][0]["attribute_id"] == attribute["id"]
    assert refreshed_modification["attribute_values"][0]["option_id"] == (
        options_by_name["Белый"]["id"]
    )
    refreshed_empty_modification = await repository.get_entity(
        db_session, "modification", empty_modification["id"]
    )
    assert refreshed_empty_modification is not None
    assert refreshed_empty_modification["attribute_values"] == []


async def test_non_text_attribute_conversion_with_values_is_blocked(
    db_session: AsyncSession,
) -> None:
    catalog = await _published_catalog(db_session, required_attribute=True)
    attribute = catalog["attribute"]
    assert attribute is not None

    with pytest.raises(AttributeTypeConversionBlockedError) as conflict:
        async with db_session.begin_nested():
            await commands.patch_entity(
                db_session,
                entity_type="attribute",
                entity_id=attribute["id"],
                values={
                    "data_type": "text",
                    "filter_kind": "search",
                    "confirm_type_conversion": True,
                },
                expected_version=attribute["lock_version"],
            )

    assert conflict.value.code == "ATTRIBUTE_TYPE_CONVERSION_BLOCKED"
    unchanged = await repository.get_entity(
        db_session, "attribute", attribute["id"]
    )
    assert unchanged is not None
    assert unchanged["data_type"] == "number"


async def test_attribute_without_values_changes_type_while_links_stay_intact(
    db_session: AsyncSession,
) -> None:
    suffix = uuid4().hex
    group = await _create(
        db_session,
        entity_type="attribute_group",
        values={
            "code": f"empty-group-{suffix}",
            "name": f"Группа {suffix}",
            "sort_order": 0,
            "is_active": True,
        },
    )
    attribute = await _create(
        db_session,
        entity_type="attribute",
        values={
            "code": f"empty-attribute-{suffix}",
            "name": f"Характеристика {suffix}",
            "attribute_group_id": group["id"],
            "data_type": "text",
            "unit": None,
            "filter_kind": "search",
            "is_active": True,
            "options": [],
        },
    )
    category = await _create(
        db_session,
        entity_type="category",
        values={
            "code": f"empty-category-{suffix}",
            "name": f"Категория {suffix}",
            "usage_metric": "engine_hours",
            "sort_order": 0,
            "is_active": True,
            "parent_ids": [],
            "attribute_links": [
                {
                    "attribute_id": attribute["id"],
                    "group_id": group["id"],
                    "is_required": False,
                    "is_filterable": True,
                    "is_visible": True,
                    "sort_order": 0,
                }
            ],
        },
    )

    converted = await commands.patch_entity(
        db_session,
        entity_type="attribute",
        entity_id=attribute["id"],
        values={"data_type": "number"},
        expected_version=attribute["lock_version"],
    )

    assert converted["data_type"] == "number"
    assert converted["filter_kind"] == "exact"
    refreshed_category = await repository.get_entity(
        db_session, "category", category["id"]
    )
    assert refreshed_category is not None
    assert refreshed_category["attribute_links"][0]["attribute_id"] == attribute[
        "id"
    ]
    assert refreshed_category["attribute_links"][0]["group_id"] == group["id"]


async def test_modification_year_narrowing_cannot_exclude_published_unit(
    db_session: AsyncSession,
) -> None:
    catalog = await _published_catalog(db_session)
    modification = catalog["modification"]

    with pytest.raises(
        SpecialEquipmentManagementConflictError
    ) as conflict:
        async with db_session.begin_nested():
            await commands.patch_entity(
                db_session,
                entity_type="modification",
                entity_id=modification["id"],
                values={"year_to": 2023},
                expected_version=modification["lock_version"],
            )

    assert conflict.value.dependencies[0].count == 1
    assert "год выпуска" in conflict.value.dependencies[0].name.casefold()


async def test_published_product_cannot_reference_inactive_category(
    db_session: AsyncSession,
) -> None:
    catalog = await _published_catalog(db_session)
    category = catalog["category"]
    product = catalog["product"]
    await commands.patch_entity(
        db_session,
        entity_type="product",
        entity_id=product["id"],
        values={"publication_status": "draft"},
        expected_version=product["lock_version"],
    )
    current_product = await repository.get_entity(
        db_session, "product", product["id"]
    )
    assert current_product is not None
    await commands.patch_entity(
        db_session,
        entity_type="category",
        entity_id=category["id"],
        values={"is_active": False},
        expected_version=category["lock_version"],
    )

    with pytest.raises(
        SpecialEquipmentManagementValidationError,
        match="неактивная категория",
    ):
        await commands.patch_entity(
            db_session,
            entity_type="product",
            entity_id=product["id"],
            values={"publication_status": "published"},
            expected_version=current_product["lock_version"],
        )


@pytest.mark.parametrize(
    ("entity_type", "dependency_type"),
    [
        ("attribute_group", "category_attributes"),
        ("attribute", "category_attributes"),
        ("attribute_option", "modification_values"),
    ],
)
async def test_used_attribute_directory_cannot_be_deactivated(
    db_session: AsyncSession,
    entity_type: repository.EntityType,
    dependency_type: str,
) -> None:
    catalog = await _published_catalog(
        db_session,
        required_attribute=True,
        select_attribute=True,
    )
    entity = {
        "attribute_group": catalog["group"],
        "attribute": catalog["attribute"],
        "attribute_option": catalog["option"],
    }[entity_type]
    assert entity is not None

    with pytest.raises(
        SpecialEquipmentManagementConflictError
    ) as conflict:
        async with db_session.begin_nested():
            await commands.patch_entity(
                db_session,
                entity_type=entity_type,
                entity_id=entity["id"],
                values={"is_active": False},
                expected_version=entity["lock_version"],
            )

    assert conflict.value.entity_type == entity_type
    assert conflict.value.entity_id == entity["id"]
    assert dependency_type in {
        dependency.entity_type
        for dependency in conflict.value.dependencies
    }


@pytest.mark.parametrize(
    ("entity_type", "message"),
    [
        ("attribute_group", "неактивная группа характеристик"),
        ("attribute", "неактивная характеристика"),
        ("attribute_option", "неактивный вариант характеристики"),
    ],
)
async def test_published_product_rejects_inactive_attribute_directory(
    db_session: AsyncSession,
    entity_type: repository.EntityType,
    message: str,
) -> None:
    catalog = await _published_catalog(
        db_session,
        required_attribute=True,
        select_attribute=True,
    )
    product = catalog["product"]
    entity = {
        "attribute_group": catalog["group"],
        "attribute": catalog["attribute"],
        "attribute_option": catalog["option"],
    }[entity_type]
    assert entity is not None

    await commands.patch_entity(
        db_session,
        entity_type="product",
        entity_id=product["id"],
        values={"publication_status": "draft"},
        expected_version=product["lock_version"],
    )
    current_product = await repository.get_entity(
        db_session, "product", product["id"]
    )
    assert current_product is not None
    await repository.patch_entity(
        db_session,
        entity_type,
        entity["id"],
        {"is_active": False},
    )

    with pytest.raises(
        SpecialEquipmentManagementValidationError,
        match=message,
    ):
        await commands.patch_entity(
            db_session,
            entity_type="product",
            entity_id=product["id"],
            values={"publication_status": "published"},
            expected_version=current_product["lock_version"],
        )
