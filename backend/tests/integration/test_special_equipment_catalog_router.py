"""PostgreSQL-backed public catalog contract for task 21808 correction."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, QueryParams
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_db
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentAttribute,
    SpecialEquipmentAttributeGroup,
    SpecialEquipmentAttributeOption,
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryAttribute,
    SpecialEquipmentCategoryRelation,
    SpecialEquipmentModification,
    SpecialEquipmentModificationAttributeValue,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
    SpecialEquipmentProductCategory,
)
from presentation.routers.special_equipment import router
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


async def test_multi_value_exact_attributes_use_or_within_one_attribute(
    db_session: AsyncSession,
) -> None:
    seller = Company(name="Дилер фильтров", company_type="dealer")
    mark, model, first_modification = special_equipment_directory(
        mark_name="Тестовая марка",
        model_name="Тестовая модель",
        modification_name="Первая модификация",
    )
    second_modification = SpecialEquipmentModification(
        model_id=model.id,
        code="filter-second-modification",
        name="Вторая модификация",
        slug="filter-second-modification",
    )
    excluded_modification = SpecialEquipmentModification(
        model_id=model.id,
        code="filter-excluded-modification",
        name="Исключённая модификация",
        slug="filter-excluded-modification",
    )
    category = SpecialEquipmentCategory(
        code="multi-value-filters",
        name="Техника с составными фильтрами",
        slug="multi-value-filters",
        usage_metric="engine_hours",
    )
    drive = SpecialEquipmentAttribute(
        code="filter-drive",
        name="Привод",
        data_type="select",
        filter_kind="exact",
    )
    equipment_class = SpecialEquipmentAttribute(
        code="filter-class",
        name="Класс",
        data_type="select",
        filter_kind="exact",
    )
    power = SpecialEquipmentAttribute(
        code="filter-power",
        name="Мощность",
        data_type="number",
        filter_kind="range",
    )
    note = SpecialEquipmentAttribute(
        code="filter-note",
        name="Описание характеристики",
        data_type="text",
        filter_kind="search",
    )
    db_session.add_all(
        [
            seller,
            mark,
            model,
            first_modification,
            second_modification,
            excluded_modification,
            category,
            drive,
            equipment_class,
            power,
            note,
        ]
    )
    await db_session.flush()

    drive_left = SpecialEquipmentAttributeOption(
        attribute_id=drive.id, code="left", name="Левый", sort_order=1
    )
    drive_right = SpecialEquipmentAttributeOption(
        attribute_id=drive.id, code="right", name="Правый", sort_order=2
    )
    class_allowed = SpecialEquipmentAttributeOption(
        attribute_id=equipment_class.id,
        code="allowed",
        name="Разрешённый",
        sort_order=1,
    )
    class_excluded = SpecialEquipmentAttributeOption(
        attribute_id=equipment_class.id,
        code="excluded",
        name="Исключённый",
        sort_order=2,
    )
    db_session.add_all(
        [
            drive_left,
            drive_right,
            class_allowed,
            class_excluded,
        ]
    )
    await db_session.flush()

    modifications = (
        (first_modification, drive_left, class_allowed),
        (second_modification, drive_right, class_allowed),
        (excluded_modification, drive_left, class_excluded),
    )
    for index, (modification, drive_option, class_option) in enumerate(
        modifications, start=1
    ):
        db_session.add_all(
            [
                SpecialEquipmentModificationAttributeValue(
                    modification_id=modification.id,
                    attribute_id=drive.id,
                    option_id=drive_option.id,
                ),
                SpecialEquipmentModificationAttributeValue(
                    modification_id=modification.id,
                    attribute_id=equipment_class.id,
                    option_id=class_option.id,
                ),
                SpecialEquipmentModificationAttributeValue(
                    modification_id=modification.id,
                    attribute_id=power.id,
                    value_number=Decimal(200 + index),
                ),
                SpecialEquipmentModificationAttributeValue(
                    modification_id=modification.id,
                    attribute_id=note.id,
                    value_text="Гидравлическая система",
                ),
            ]
        )

    for index, attribute in enumerate(
        (drive, equipment_class, power, note), start=1
    ):
        db_session.add(
            SpecialEquipmentCategoryAttribute(
                category_id=category.id,
                attribute_id=attribute.id,
                is_filterable=True,
                is_visible=True,
                sort_order=index,
            )
        )

    products: list[SpecialEquipmentProduct] = []
    for index, (modification, _drive_option, _class_option) in enumerate(
        modifications, start=1
    ):
        product = SpecialEquipmentProduct(
            code=f"multi-value-product-{index}",
            modification_id=modification.id,
            seller_company_id=seller.id,
            slug=f"multi-value-product-{index}",
            description=f"Товар {index}",
            price=Decimal("1000000.00"),
            manufacture_year=2024,
            condition="used",
            vin=None,
            no_vin=True,
            owners_count=1,
            engine_hours=100,
            publication_status="published",
            sale_status="available",
            published_at=datetime.now(UTC),
        )
        products.append(product)
        db_session.add(product)
    await db_session.flush()
    db_session.add_all(
        [
            SpecialEquipmentProductCategory(
                product_id=product.id, category_id=category.id
            )
            for product in products
        ]
    )
    await db_session.flush()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/special-equipment")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = db_override
    params = QueryParams([
        ("category_path", category.slug),
        ("attribute", f"{drive.id}:eq:left"),
        ("attribute", f"{drive.id}:eq:right"),
        ("attribute", f"{equipment_class.id}:eq:allowed"),
        ("attribute", f"{power.id}:gte:200"),
        ("attribute", f"{power.id}:lte:210"),
        ("attribute", f"{note.id}:search:гидравлическая"),
    ])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/special-equipment/products", params=params
        )
        facets_response = await client.get(
            "/api/v1/special-equipment/facets", params=params
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"]["total"] == 2
    assert {
        item["modification"]["id"] for item in body["items"]
    } == {str(first_modification.id), str(second_modification.id)}
    assert facets_response.status_code == 200, facets_response.text
    assert facets_response.json()["availability"] == {
        "available": 2,
        "on_order": 0,
    }


async def test_public_category_graph_exposes_ordered_dag_placements(
    db_session: AsyncSession,
) -> None:
    root_a = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        code="root-a",
        name="Первый тип",
        slug="root-a",
        usage_metric="engine_hours",
        sort_order=10,
    )
    root_b = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        code="root-b",
        name="Второй тип",
        slug="root-b",
        usage_metric="engine_hours",
        sort_order=20,
    )
    standard = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        code="standard",
        name="Обычная категория",
        slug="standard",
        usage_metric="engine_hours",
        sort_order=30,
    )
    attachment = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000004"),
        code="attachment",
        name="Надстройка",
        slug="attachment",
        usage_metric="engine_hours",
        is_attachment_category=True,
        sort_order=40,
    )
    db_session.add_all([root_a, root_b, standard, attachment])
    await db_session.flush()
    db_session.add_all(
        [
            SpecialEquipmentCategoryRelation(
                parent_id=root_a.id, child_id=standard.id, sort_order=20
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=root_a.id, child_id=attachment.id, sort_order=10
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=root_b.id, child_id=attachment.id, sort_order=5
            ),
        ]
    )
    await db_session.flush()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/special-equipment")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = db_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/special-equipment/categories")

    assert response.status_code == 200
    body = response.json()
    categories = {item["code"]: item for item in body["items"]}
    assert categories["attachment"]["is_attachment_category"] is True
    assert categories["attachment"]["parent_ids"] == [
        str(root_a.id),
        str(root_b.id),
    ]
    assert categories["root-a"]["child_ids"] == [
        str(attachment.id),
        str(standard.id),
    ]
    assert [item["id"] for item in body["root_items"]] == [
        str(root_b.id),
        str(root_a.id),
    ]
    assert body["placements"] == [
        {
            "parent_id": str(root_a.id),
            "category_id": str(attachment.id),
            "sort_order": 10,
        },
        {
            "parent_id": str(root_a.id),
            "category_id": str(standard.id),
            "sort_order": 20,
        },
        {
            "parent_id": str(root_b.id),
            "category_id": str(attachment.id),
            "sort_order": 5,
        },
    ]


async def test_public_category_graph_orders_roots_by_russian_name_not_sort_order(
    db_session: AsyncSession,
) -> None:
    """Only returned active parents prevent a category from being a root."""
    lower_case_first = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        code="lower-case-first",
        name="арбуз",
        slug="lower-case-first",
        usage_metric="engine_hours",
        sort_order=999,
    )
    upper_case_second = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        code="upper-case-second",
        name="Арбуз",
        slug="upper-case-second",
        usage_metric="engine_hours",
        sort_order=1,
    )
    bulldozer = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        code="bulldozer",
        name="Бульдозеры",
        slug="bulldozer",
        usage_metric="engine_hours",
        sort_order=0,
    )
    orphaned_by_inactive_parent = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000004"),
        code="orphaned-by-inactive-parent",
        name="Ямобуры",
        slug="orphaned-by-inactive-parent",
        usage_metric="engine_hours",
        sort_order=2,
    )
    inactive_parent = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000005"),
        code="inactive-parent",
        name="Не должна вернуться",
        slug="inactive-parent",
        usage_metric="engine_hours",
        is_active=False,
    )
    db_session.add_all(
        [
            lower_case_first,
            upper_case_second,
            bulldozer,
            orphaned_by_inactive_parent,
            inactive_parent,
        ]
    )
    await db_session.flush()
    db_session.add(
        SpecialEquipmentCategoryRelation(
            parent_id=inactive_parent.id,
            child_id=orphaned_by_inactive_parent.id,
            sort_order=1,
        )
    )
    await db_session.flush()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/special-equipment")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = db_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/special-equipment/categories")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["root_items"]] == [
        str(lower_case_first.id),
        str(upper_case_second.id),
        str(bulldozer.id),
        str(orphaned_by_inactive_parent.id),
    ]


async def test_public_category_graph_inherits_attachment_flag_to_descendants(
    db_session: AsyncSession,
) -> None:
    attachment_root = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000011"),
        code="attachment-root",
        name="Корень надстроек",
        slug="attachment-root",
        usage_metric="engine_hours",
        is_attachment_category=True,
        sort_order=10,
    )
    attachment_child = SpecialEquipmentCategory(
        id=UUID("00000000-0000-0000-0000-000000000012"),
        code="attachment-child",
        name="Потомок надстройки",
        slug="attachment-child",
        usage_metric="engine_hours",
        is_attachment_category=False,
        sort_order=20,
    )
    db_session.add_all([attachment_root, attachment_child])
    await db_session.flush()
    db_session.add(
        SpecialEquipmentCategoryRelation(
            parent_id=attachment_root.id,
            child_id=attachment_child.id,
            sort_order=10,
        )
    )
    await db_session.flush()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/special-equipment")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = db_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/special-equipment/categories")

    assert response.status_code == 200, response.text
    categories = {item["code"]: item for item in response.json()["items"]}
    assert categories["attachment-root"]["is_attachment_category"] is True
    assert categories["attachment-child"]["is_attachment_category"] is True


async def test_contextual_catalog_uses_dag_and_live_modification_values(  # noqa: PLR0915
    db_session: AsyncSession,
) -> None:
    seller = Company(name="Дилер спецтехники", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name="Ивановец",
        model_name="КС",
        modification_name="КС-45717",
    )
    root = SpecialEquipmentCategory(
        code="lifting",
        name="Подъёмная техника",
        slug="lifting",
        usage_metric="engine_hours",
        sort_order=1,
    )
    leaf = SpecialEquipmentCategory(
        code="mobile-cranes",
        name="Автокраны",
        slug="mobile-cranes",
        usage_metric="engine_hours",
        sort_order=1,
    )
    second_actual_category = SpecialEquipmentCategory(
        code="crawler-cranes",
        name="Гусеничные краны",
        slug="crawler-cranes",
        usage_metric="engine_hours",
        sort_order=2,
    )
    group = SpecialEquipmentAttributeGroup(
        code="engine",
        name="Двигатель",
        slug="engine",
        sort_order=1,
    )
    second_group = SpecialEquipmentAttributeGroup(
        code="boom",
        name="Стрела",
        slug="boom",
        sort_order=2,
    )
    inactive_group = SpecialEquipmentAttributeGroup(
        code="hidden",
        name="Скрытая группа",
        slug="hidden",
        sort_order=3,
        is_active=False,
    )
    power = SpecialEquipmentAttribute(
        code="engine_power",
        name="Мощность",
        data_type="number",
        unit="л.с.",
        filter_kind="range",
    )
    drive = SpecialEquipmentAttribute(
        code="drive",
        name="Привод",
        data_type="select",
        filter_kind="exact",
    )
    boom_length = SpecialEquipmentAttribute(
        code="boom_length",
        name="Длина стрелы",
        data_type="number",
        unit="м",
        filter_kind="range",
    )
    inactive_attribute = SpecialEquipmentAttribute(
        code="deprecated_value",
        name="Устаревшее значение",
        data_type="number",
        filter_kind="range",
        is_active=False,
    )
    hidden_group_attribute = SpecialEquipmentAttribute(
        code="hidden_group_value",
        name="Значение скрытой группы",
        data_type="number",
        filter_kind="range",
    )
    db_session.add_all(
        [
            seller,
            mark,
            model,
            modification,
            root,
            leaf,
            second_actual_category,
            group,
            second_group,
            inactive_group,
            power,
            drive,
            boom_length,
            inactive_attribute,
            hidden_group_attribute,
        ]
    )
    await db_session.flush()
    option = SpecialEquipmentAttributeOption(
        attribute_id=drive.id,
        code="all-wheel",
        name="Полный",
        sort_order=1,
    )
    db_session.add(option)
    await db_session.flush()
    db_session.add_all(
        [
            SpecialEquipmentCategoryRelation(
                parent_id=root.id, child_id=leaf.id, sort_order=1
            ),
            SpecialEquipmentModificationCategory(
                modification_id=modification.id,
                category_id=leaf.id,
                is_primary=True,
            ),
            SpecialEquipmentCategoryAttribute(
                category_id=root.id,
                attribute_id=power.id,
                group_id=group.id,
                is_filterable=True,
                is_visible=True,
                sort_order=1,
            ),
            SpecialEquipmentCategoryAttribute(
                category_id=leaf.id,
                attribute_id=drive.id,
                group_id=group.id,
                is_filterable=True,
                is_visible=True,
                sort_order=2,
            ),
            SpecialEquipmentCategoryAttribute(
                category_id=second_actual_category.id,
                attribute_id=boom_length.id,
                group_id=second_group.id,
                is_filterable=True,
                is_visible=True,
                sort_order=1,
            ),
            SpecialEquipmentCategoryAttribute(
                category_id=leaf.id,
                attribute_id=inactive_attribute.id,
                group_id=group.id,
                is_filterable=True,
                is_visible=True,
                sort_order=3,
            ),
            SpecialEquipmentCategoryAttribute(
                category_id=leaf.id,
                attribute_id=hidden_group_attribute.id,
                group_id=inactive_group.id,
                is_filterable=True,
                is_visible=True,
                sort_order=4,
            ),
            SpecialEquipmentModificationAttributeValue(
                modification_id=modification.id,
                attribute_id=power.id,
                value_number=Decimal("240.0000"),
            ),
            SpecialEquipmentModificationAttributeValue(
                modification_id=modification.id,
                attribute_id=drive.id,
                option_id=option.id,
            ),
            SpecialEquipmentModificationAttributeValue(
                modification_id=modification.id,
                attribute_id=boom_length.id,
                value_number=Decimal("32.0000"),
            ),
            SpecialEquipmentModificationAttributeValue(
                modification_id=modification.id,
                attribute_id=inactive_attribute.id,
                value_number=Decimal("1.0000"),
            ),
            SpecialEquipmentModificationAttributeValue(
                modification_id=modification.id,
                attribute_id=hidden_group_attribute.id,
                value_number=Decimal("2.0000"),
            ),
        ]
    )
    product = SpecialEquipmentProduct(
        code="crane-001",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="ivanovets-ks-45717",
        description="Автокран",
        price=Decimal("12500000.00"),
        manufacture_year=2022,
        condition="used",
        vin=None,
        no_vin=True,
        owners_count=1,
        engine_hours=1200,
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    outside_product = SpecialEquipmentProduct(
        code="crane-outside",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="ivanovets-outside-branch",
        description="Техника другой ветки",
        price=Decimal("15000000.00"),
        manufacture_year=2021,
        condition="used",
        vin=None,
        no_vin=True,
        owners_count=2,
        engine_hours=3500,
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add_all([product, outside_product])
    await db_session.flush()
    db_session.add_all(
        [
            SpecialEquipmentProductCategory(
                product_id=product.id, category_id=leaf.id
            ),
            SpecialEquipmentProductCategory(
                product_id=product.id,
                category_id=second_actual_category.id,
            ),
            SpecialEquipmentProductCategory(
                product_id=outside_product.id,
                category_id=second_actual_category.id,
            ),
        ]
    )
    await db_session.flush()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/special-equipment")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = db_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        graph_response = await client.get("/api/v1/special-equipment/categories")
        assert graph_response.status_code == 200
        graph = {item["code"]: item for item in graph_response.json()["items"]}
        assert graph["lifting"]["child_ids"] == [str(leaf.id)]
        assert graph["mobile-cranes"]["parent_ids"] == [str(root.id)]
        assert graph["lifting"]["product_count"] == 1
        assert graph["mobile-cranes"]["product_count"] == 1

        resolved = await client.get(
            "/api/v1/special-equipment/categories/resolve",
            params={"path": "lifting/mobile-cranes"},
        )
        assert resolved.status_code == 200
        assert [item["code"] for item in resolved.json()["items"]] == [
            "lifting",
            "mobile-cranes",
        ]

        listing = await client.get(
            "/api/v1/special-equipment/products",
            params=[
                ("category_path", "lifting/mobile-cranes"),
                ("mark_id", str(mark.id)),
                ("condition", "used"),
                ("engine_hours_min", "1000"),
                ("attribute", f"{power.id}:gte:200"),
                ("attribute", f"{drive.id}:eq:all-wheel"),
            ],
        )
        assert listing.status_code == 200, listing.text
        body = listing.json()
        assert body["pagination"]["total"] == 1
        assert body["items"][0]["modification"]["model"]["mark"]["name"] == "Ивановец"
        assert body["items"][0]["engine_hours"] == 1200
        assert body["facets"]["usage"]["metric"] == "engine_hours"
        assert body["facets"]["conditions"]["used"] == 1
        assert body["facets"]["attribute_groups"][0]["name"] == "Двигатель"
        facet_codes = {
            attribute["code"]
            for group_resource in body["facets"]["attribute_groups"]
            for attribute in group_resource["attributes"]
        }
        assert facet_codes == {"engine_power", "drive"}

        descendant_listing = await client.get(
            "/api/v1/special-equipment/products",
            params={"category_path": "lifting"},
        )
        assert descendant_listing.status_code == 200, descendant_listing.text
        assert descendant_listing.json()["pagination"]["total"] == 1
        assert descendant_listing.json()["items"][0]["id"] == str(product.id)

        descendant_facets = await client.get(
            "/api/v1/special-equipment/facets",
            params={"category_path": "lifting"},
        )
        assert descendant_facets.status_code == 200, descendant_facets.text
        descendant_facets_body = descendant_facets.json()
        assert descendant_facets_body["availability"] == {
            "available": 1,
            "on_order": 0,
        }
        assert {
            attribute["code"]
            for group_resource in descendant_facets_body["attribute_groups"]
            for attribute in group_resource["attributes"]
        } == {"engine_power", "drive"}

        descendant_filter = await client.get(
            "/api/v1/special-equipment/products",
            params=[
                ("category_path", "lifting"),
                ("attribute", f"{drive.id}:eq:all-wheel"),
            ],
        )
        assert descendant_filter.status_code == 200, descendant_filter.text
        assert descendant_filter.json()["pagination"]["total"] == 1

        implicit_listing = await client.get(
            "/api/v1/special-equipment/products",
            params=[
                ("modification_id", str(modification.id)),
                ("engine_hours_min", "1000"),
                ("attribute", f"{drive.id}:eq:all-wheel"),
            ],
        )
        assert implicit_listing.status_code == 200, implicit_listing.text
        implicit_body = implicit_listing.json()
        assert implicit_body["pagination"]["total"] == 1
        assert implicit_body["facets"]["usage"]["metric"] == "engine_hours"
        assert {
            attribute["code"]
            for group_resource in implicit_body["facets"]["attribute_groups"]
            for attribute in group_resource["attributes"]
        } == {"engine_power", "drive"}

        implicit_facets = await client.get(
            "/api/v1/special-equipment/facets",
            params={"modification_id": str(modification.id)},
        )
        assert implicit_facets.status_code == 200, implicit_facets.text
        assert implicit_facets.json()["usage"]["metric"] == "engine_hours"
        assert {
            attribute["code"]
            for group_resource in implicit_facets.json()["attribute_groups"]
            for attribute in group_resource["attributes"]
        } == {"engine_power", "drive"}

        explicit_with_multiple_modifications = await client.get(
            "/api/v1/special-equipment/products",
            params=[
                ("category_path", "lifting/mobile-cranes"),
                ("modification_id", str(modification.id)),
                ("modification_id", str(UUID(int=999))),
                ("attribute", f"{drive.id}:eq:all-wheel"),
            ],
        )
        assert explicit_with_multiple_modifications.status_code == 200, (
            explicit_with_multiple_modifications.text
        )
        assert explicit_with_multiple_modifications.json()["pagination"]["total"] == 1

        missing_context = await client.get(
            "/api/v1/special-equipment/facets",
            params={"engine_hours_min": "1"},
        )
        assert missing_context.status_code == 422
        assert missing_context.headers["content-type"].startswith(
            "application/problem+json"
        )
        assert missing_context.json()["code"] == "CATEGORY_CONTEXT_REQUIRED"

        ambiguous_context = await client.get(
            "/api/v1/special-equipment/products",
            params=[
                ("modification_id", str(modification.id)),
                ("modification_id", str(UUID(int=999))),
                ("engine_hours_min", "1"),
            ],
        )
        assert ambiguous_context.status_code == 422
        assert ambiguous_context.json()["code"] == "CATEGORY_CONTEXT_REQUIRED"

        detail = await client.get(
            f"/api/v1/special-equipment/products/{product.id}",
            params={"category_path": "lifting/mobile-cranes"},
        )
        assert detail.status_code == 200, detail.text
        detail_body = detail.json()
        detail_attribute_codes = {
            attribute["code"]
            for group_resource in detail_body["attribute_groups"]
            for attribute in group_resource["attributes"]
        }
        assert detail_attribute_codes == {
            "engine_power",
            "drive",
            "boom_length",
        }

        contextless = await client.get(
            f"/api/v1/special-equipment/products/{product.id}"
        )
        assert contextless.status_code == 200
