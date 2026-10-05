"""Regression contracts for the admin product category cascade in task 22090."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.special_equipment_management import (
    ListRegistryQuery,
    handle_list,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryRelation,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
    SpecialEquipmentProductCategory,
)
from main import app
from presentation.routers import special_equipment_management as management_router


def _category(name: str) -> SpecialEquipmentCategory:
    suffix = uuid4().hex
    return SpecialEquipmentCategory(
        code=f"product-filter-category-{suffix}",
        name=name,
        slug=f"product-filter-category-{suffix}",
        usage_metric="engine_hours",
    )


def _product(
    modification: SpecialEquipmentModification,
    code: str,
) -> SpecialEquipmentProduct:
    return SpecialEquipmentProduct(
        code=code,
        slug=f"{code}-{uuid4().hex}",
        modification_id=modification.id,
        no_vin=True,
        condition="new",
        publication_status="draft",
        sale_status="unavailable",
    )


def test_product_list_exposes_five_category_level_parameters() -> None:
    operation = app.openapi()["paths"][
        "/api/v1/admin/special-equipment/products"
    ]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}

    for level in range(1, 6):
        parameter = parameters[f"level_{level}_id"]
        uuid_schema = next(
            item for item in parameter["schema"]["anyOf"]
            if item.get("format") == "uuid"
        )
        assert uuid_schema["type"] == "string"


@pytest.mark.asyncio
async def test_product_route_forwards_the_complete_category_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    levels = tuple(uuid4() for _ in range(5))
    list_registry = AsyncMock(return_value=object())
    monkeypatch.setattr(management_router, "_list", list_registry)

    response = await management_router.products(
        _user={},  # type: ignore[arg-type]
        session=AsyncMock(),
        level_1_id=levels[0],
        level_2_id=levels[1],
        level_3_id=levels[2],
        level_4_id=levels[3],
        level_5_id=levels[4],
    )

    assert response is list_registry.return_value
    awaited = list_registry.await_args
    assert awaited is not None
    assert awaited.kwargs["category_level_ids"] == levels


@pytest.mark.asyncio
async def test_product_category_chain_scopes_direct_and_modification_categories_before_pagination(
    db_session: AsyncSession,
) -> None:
    root = _category("Техника")
    direct_leaf = _category("Прямая категория")
    inherited_branch = _category("Ветка модификации")
    inherited_leaf = _category("Категория модификации")
    outside_root = _category("Другая техника")
    suffix = uuid4().hex
    mark = SpecialEquipmentMark(
        id=uuid4(),
        code=f"product-filter-mark-{suffix}",
        name=f"Марка {suffix}",
        slug=f"product-filter-mark-{suffix}",
    )
    model = SpecialEquipmentModel(
        id=uuid4(),
        mark_id=mark.id,
        code=f"product-filter-model-{suffix}",
        name=f"Модель {suffix}",
        slug=f"product-filter-model-{suffix}",
    )
    direct_modification = SpecialEquipmentModification(
        id=uuid4(),
        model_id=model.id,
        code=f"product-filter-direct-mod-{suffix}",
        name=f"Прямая модификация {suffix}",
        slug=f"product-filter-direct-mod-{suffix}",
    )
    inherited_modification = SpecialEquipmentModification(
        id=uuid4(),
        model_id=model.id,
        code=f"product-filter-inherited-mod-{suffix}",
        name=f"Наследуемая модификация {suffix}",
        slug=f"product-filter-inherited-mod-{suffix}",
    )
    outside_modification = SpecialEquipmentModification(
        id=uuid4(),
        model_id=model.id,
        code=f"product-filter-outside-mod-{suffix}",
        name=f"Внешняя модификация {suffix}",
        slug=f"product-filter-outside-mod-{suffix}",
    )
    db_session.add_all(
        (
            root,
            direct_leaf,
            inherited_branch,
            inherited_leaf,
            outside_root,
            mark,
            model,
            direct_modification,
            inherited_modification,
            outside_modification,
        )
    )
    await db_session.flush()
    db_session.add_all(
        (
            SpecialEquipmentCategoryRelation(
                parent_id=root.id,
                child_id=direct_leaf.id,
                sort_order=0,
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=root.id,
                child_id=inherited_branch.id,
                sort_order=1,
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=inherited_branch.id,
                child_id=inherited_leaf.id,
                sort_order=0,
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=outside_root.id,
                child_id=inherited_leaf.id,
                sort_order=1,
            ),
            SpecialEquipmentModificationCategory(
                modification_id=direct_modification.id,
                category_id=outside_root.id,
                sort_order=0,
                is_primary=True,
            ),
            SpecialEquipmentModificationCategory(
                modification_id=inherited_modification.id,
                category_id=inherited_leaf.id,
                sort_order=0,
                is_primary=True,
            ),
            SpecialEquipmentModificationCategory(
                modification_id=outside_modification.id,
                category_id=outside_root.id,
                sort_order=0,
                is_primary=True,
            ),
        )
    )
    direct_product = _product(
        direct_modification,
        f"category-target-direct-{suffix}",
    )
    inherited_product = _product(
        inherited_modification,
        f"category-target-inherited-{suffix}",
    )
    outside_product = _product(
        outside_modification,
        f"category-target-outside-{suffix}",
    )
    nonmatching_product = _product(
        direct_modification,
        f"category-other-direct-{suffix}",
    )
    db_session.add_all(
        (direct_product, inherited_product, outside_product, nonmatching_product)
    )
    await db_session.flush()
    db_session.add_all(
        (
            SpecialEquipmentProductCategory(
                product_id=direct_product.id,
                category_id=direct_leaf.id,
            ),
            SpecialEquipmentProductCategory(
                product_id=nonmatching_product.id,
                category_id=direct_leaf.id,
            ),
        )
    )
    await db_session.flush()

    result = await handle_list(
        ListRegistryQuery(
            "product",
            page=2,
            page_size=1,
            search="category-target",
            normalization_state="normalized",
            category_level_ids=(root.id,),
        ),
        db_session,
    )

    assert result["pagination"] == {
        "page": 2,
        "page_size": 1,
        "total": 2,
        "pages": 2,
    }
    assert result["items"][0]["id"] in {
        direct_product.id,
        inherited_product.id,
    }

    direct_result = await handle_list(
        ListRegistryQuery(
            "product",
            search="category-target",
            category_level_ids=(root.id, direct_leaf.id),
        ),
        db_session,
    )
    inherited_result = await handle_list(
        ListRegistryQuery(
            "product",
            search="category-target",
            category_level_ids=(root.id, inherited_branch.id),
        ),
        db_session,
    )

    assert [item["id"] for item in direct_result["items"]] == [direct_product.id]
    assert [item["id"] for item in inherited_result["items"]] == [
        inherited_product.id
    ]

    combined_result = await handle_list(
        ListRegistryQuery(
            "product",
            category_id=inherited_leaf.id,
            category_level_ids=(root.id,),
        ),
        db_session,
    )
    assert [item["id"] for item in combined_result["items"]] == [
        inherited_product.id
    ]

    legacy_result = await handle_list(
        ListRegistryQuery(
            "product",
            normalization_state="legacy",
            category_level_ids=(root.id,),
        ),
        db_session,
    )
    assert legacy_result["items"] == []
    assert legacy_result["pagination"]["total"] == 0

    for invalid_levels in (
        (root.id, outside_root.id),
        (root.id, None, inherited_leaf.id),
        (uuid4(),),
    ):
        invalid = await handle_list(
            ListRegistryQuery(
                "product",
                category_level_ids=invalid_levels,
            ),
            db_session,
        )
        assert invalid["items"] == []
        assert invalid["pagination"]["total"] == 0
        assert invalid["pagination"]["pages"] == 0
