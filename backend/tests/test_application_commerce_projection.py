"""Regression tests for the unified leasing-application item projection."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.create_application import (
    ApplicationVehiclePayload,
)
from application.commands.applications.update_conditions import (
    UpdateConditionsCommand,
    handle_update_conditions,
)
from application.commands.applications.update_vehicles import (
    UpdateVehiclesCommand,
    handle_update_vehicles,
)
from application.errors import ServiceError
from application.queries.application_vehicles.list_available_vins import (
    ListAvailableVinsQuery,
    handle_list_available_vins,
)
from application.queries.applications import (
    GetApplicationQuery,
    ListApplicationsQuery,
    handle_get_application,
    handle_list_applications,
)
from application.queries.applications.item_projection import (
    group_application_items,
    project_special_equipment_item,
    project_vehicle_item,
)
from application.queries.leasing_response import (
    GetLcResponseStateQuery,
    handle_get_lc_response_state,
)
from domain.errors import ApplicationNotOwnedError
from domain.storefronts import DEFAULT_STOREFRONT_ID
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct,
    SpecialEquipmentProductImage,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
)
from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import dealer_repository as dealer_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import reporting_repository as reporting_repo
from presentation.schemas.applications import (
    ApplicationDetailResponse,
    ApplicationListResponse,
    application_commerce_money_to_wire,
)
from presentation.schemas.leasing import LcResponseStateResponse
from tests.legacy_compat import Vehicle, VehicleWarehouse
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


async def test_vehicle_item_title_prefers_english_catalog_names() -> None:
    item = project_vehicle_item(
        {
            "id": uuid4(),
            "vehicle_id": uuid4(),
            "mark_name": "Haval",
            "mark_cyrillic_name": "Хавейл",
            "model_name": "Jolion",
            "model_cyrillic_name": "Джолион",
            "modification_name": "Premium",
            "quantity": 1,
        }
    )
    assert item["title"] == "Haval Jolion Premium"


async def test_vehicle_item_projects_safe_internal_detail_url() -> None:
    vehicle_id = uuid4()

    item = project_vehicle_item(
        {
            "id": uuid4(),
            "vehicle_id": vehicle_id,
            "quantity": 1,
        }
    )

    assert item["detail_url"] == f"/cars/{vehicle_id}"


async def test_vehicle_item_preserves_purpose_and_regions_for_application_cards() -> None:
    item = project_vehicle_item(
        {
            "id": uuid4(),
            "vehicle_id": uuid4(),
            "quantity": 1,
            "leasing_purpose": "business",
            "regions": ["Москва", "Санкт-Петербург"],
        }
    )

    assert item["leasing_purpose"] == "business"
    assert item["regions"] == ["Москва", "Санкт-Петербург"]


@pytest.mark.parametrize(
    ("detail_product_id", "detail_product_slug", "expected_url"),
    [
        (None, None, None),
        (UUID("c6a9771f-c007-4e39-9c7d-ff83c2ca92e5"), None, None),
        (
            UUID("c6a9771f-c007-4e39-9c7d-ff83c2ca92e5"),
            "amkodor-352c",
            "/special-equipment/products/"
            "c6a9771f-c007-4e39-9c7d-ff83c2ca92e5/amkodor-352c",
        ),
    ],
)
async def test_special_equipment_item_uses_only_repository_safe_detail_target(
    detail_product_id: UUID | None,
    detail_product_slug: str | None,
    expected_url: str | None,
) -> None:
    item = project_special_equipment_item(
        {
            "id": uuid4(),
            "product_id": uuid4(),
            "detail_product_id": detail_product_id,
            "detail_product_slug": detail_product_slug,
            "item_role": "attachment",
            "group_id": uuid4(),
            "parent_group_id": uuid4(),
            "item_snapshot": {
                "is_base": False,
                "composite_product_id": str(uuid4()),
            },
        }
    )

    assert item["detail_url"] == expected_url
    assert item["item_role"] == "attachment"
    assert {
        "group_id",
        "parent_group_id",
        "is_base",
        "composite_product_id",
    }.isdisjoint(item)
    assert "is_base" not in item["snapshot"]
    assert "composite_product_id" not in item["snapshot"]


async def test_vehicle_item_title_keeps_cyrillic_legacy_fallback() -> None:
    item = project_vehicle_item(
        {
            "id": uuid4(),
            "vehicle_id": uuid4(),
            "mark_cyrillic_name": "Хавейл",
            "model_cyrillic_name": "Джолион",
            "quantity": 1,
        }
    )
    assert item["title"] == "Хавейл Джолион"


async def test_vehicle_item_projects_stable_prices_and_normalized_corrections() -> None:
    item = project_vehicle_item(
        {
            "id": uuid4(),
            "vehicle_id": uuid4(),
            "unit_price": Decimal("3000000.00"),
            "catalog_price_from": Decimal("3200000.00"),
            "quantity": 2,
            "total_price": Decimal("6400000.00"),
            "discount_type": "fixed_price",
            "discount_value": Decimal("2850000.00"),
            "markup_type": "percent_up",
            "markup_value": Decimal("5.00"),
            "final_price": Decimal("3000000.00"),
            "dealer_comment": "Индивидуальные условия",
        }
    )

    assert item["catalog_price"] == Decimal("3000000.00")
    assert item["discount_amount"] == Decimal("150000.00")
    assert item["markup_amount"] == Decimal("150000.00")
    assert item["final_price"] == Decimal("3000000.00")
    assert item["total_price"] == Decimal("6400000.00")
    assert item["dealer_comment"] == "Индивидуальные условия"


@pytest.mark.parametrize(
    ("discount_show_catalog_price", "markup_show_catalog_price", "expected"),
    [
        (True, True, True),
        (False, True, False),
        (True, False, False),
        (False, False, False),
    ],
)
async def test_vehicle_item_shows_catalog_price_only_when_both_actions_allow_it(
    discount_show_catalog_price: bool,
    markup_show_catalog_price: bool,
    expected: bool,
) -> None:
    item = project_vehicle_item(
        {
            "id": uuid4(),
            "vehicle_id": uuid4(),
            "unit_price": Decimal("3000000.00"),
            "quantity": 1,
            "discount_show_catalog_price": discount_show_catalog_price,
            "markup_show_catalog_price": markup_show_catalog_price,
        }
    )

    assert item["show_catalog_price"] is expected


async def _seed_mixed_application(
    session: AsyncSession,
) -> tuple[
    LeasingApplication,
    ApplicationVehicle,
    SpecialEquipmentApplicationItem,
    SpecialEquipmentApplicationItem,
]:
    client_company = Company(
        name="Клиент единой заявки",
        company_type="other",
    )
    seller_company = Company(
        name="Продавец спецтехники",
        company_type="dealer",
    )
    mark, model, modification = special_equipment_directory(
        mark_name="Текущее название марки",
        model_name="Текущая модель",
        modification_name="Текущая модификация",
    )
    session.add_all(
        [client_company, seller_company, mark, model, modification]
    )
    await session.flush()

    vehicle = Vehicle(base_price=Decimal("100.00"))
    vehicle.images = cast(
        "Any",
        [
            {
                "filename": "projection-vehicle.png",
                "url": "https://storage.example/private/vehicle.png",
            }
        ],
    )
    product = SpecialEquipmentProduct(
        code=f"projection-product-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=seller_company.id,
        slug=f"projection-product-{uuid4()}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("300.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    removed_product = SpecialEquipmentProduct(
        code=f"projection-removed-product-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=seller_company.id,
        slug=f"projection-removed-product-{uuid4()}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("5000.00"),
    )
    session.add_all([vehicle, product, removed_product])
    await session.flush()
    session.add(
        SpecialEquipmentProductImage(
            product_id=product.id,
            storage_key=f"projection/{product.id}.png",
            sort_order=0,
            is_primary=True,
        )
    )

    application = LeasingApplication(
        company_id=client_company.id,
        status="active",
        total_amount=Decimal("1299.00"),
    )
    session.add(application)
    await session.flush()

    vehicle_line = ApplicationVehicle(
        application_id=application.id,
        vehicle_id=vehicle.id,
        quantity=2,
        unit_price=Decimal("100.00"),
        equipments=[
            {"equipment_code": "option-package", "price": "399.50"}
        ],
        # Persisted total includes additional equipment/services and must win.
        total_price=Decimal("999.00"),
    )
    equipment_line = SpecialEquipmentApplicationItem(
        application_id=application.id,
        product_id=product.id,
        seller_company_id=seller_company.id,
        unit_price=Decimal("300.00"),
        total_price=Decimal("300.00"),
        currency_code="RUB",
        item_snapshot={
            "product_id": str(product.id),
            "mark": "Снимок марки",
            "model": "Снимок модели",
            "modification": "Снимок модификации",
            "price": "300.00",
            "currency_code": "RUB",
        },
        item_status="active",
    )
    removed_line = SpecialEquipmentApplicationItem(
        application_id=application.id,
        product_id=removed_product.id,
        seller_company_id=seller_company.id,
        unit_price=Decimal("5000.00"),
        total_price=Decimal("5000.00"),
        currency_code="RUB",
        item_snapshot={
            "product_id": str(removed_product.id),
            "mark": "Удалённая марка",
            "model": "Удалённая модель",
        },
        item_status="removed",
    )
    session.add_all([vehicle_line, equipment_line, removed_line])
    await session.flush()
    return application, vehicle_line, equipment_line, removed_line


async def _seed_multi_seller_application(
    session: AsyncSession,
) -> dict[str, Any]:
    client_company = Company(name="Клиент нескольких продавцов", company_type="other")
    primary_vehicle_seller = Company(
        name="Первый продавец автомобилей",
        company_type="dealer",
    )
    secondary_vehicle_seller = Company(
        name="Второй продавец автомобилей",
        company_type="dealer",
    )
    equipment_seller = Company(
        name="Продавец спецтехники в общей заявке",
        company_type="dealer",
    )
    unrelated_company = Company(
        name="Посторонний продавец",
        company_type="dealer",
    )
    mark, model, modification = special_equipment_directory(
        mark_name="Марка для проверки доступа",
        model_name="Экскаватор для проверки доступа",
        modification_name="Модификация для проверки доступа",
    )
    session.add_all(
        [
            client_company,
            primary_vehicle_seller,
            secondary_vehicle_seller,
            equipment_seller,
            unrelated_company,
            mark,
            model,
            modification,
        ]
    )
    await session.flush()

    primary_vehicle = Vehicle(
        dealer_id=primary_vehicle_seller.id,
        base_price=Decimal("100.00"),
    )
    # Warehouse ownership is authoritative. The stale vehicles.dealer_id must
    # not accidentally grant access to the unrelated company.
    secondary_vehicle = Vehicle(
        dealer_id=unrelated_company.id,
        base_price=Decimal("200.00"),
    )
    secondary_warehouse = Warehouse(
        address="Склад второго продавца",
        brand="OWNERSHIP",
        company_id=secondary_vehicle_seller.id,
    )
    product = SpecialEquipmentProduct(
        code=f"ownership-product-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=equipment_seller.id,
        slug=f"ownership-product-{uuid4()}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("300.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    session.add_all(
        [primary_vehicle, secondary_vehicle, secondary_warehouse, product]
    )
    await session.flush()
    session.add(
        VehicleWarehouse(
            vehicle_id=secondary_vehicle.id,
            warehouse_id=secondary_warehouse.id,
        )
    )

    application = LeasingApplication(
        company_id=client_company.id,
        dealer_company_id=primary_vehicle_seller.id,
        status="active",
        total_amount=Decimal("600.00"),
    )
    session.add(application)
    await session.flush()
    primary_vehicle_line = ApplicationVehicle(
        application_id=application.id,
        vehicle_id=primary_vehicle.id,
        quantity=1,
        unit_price=Decimal("100.00"),
        total_price=Decimal("100.00"),
    )
    secondary_vehicle_line = ApplicationVehicle(
        application_id=application.id,
        vehicle_id=secondary_vehicle.id,
        quantity=1,
        unit_price=Decimal("200.00"),
        total_price=Decimal("200.00"),
    )
    equipment_line = SpecialEquipmentApplicationItem(
        application_id=application.id,
        product_id=product.id,
        seller_company_id=equipment_seller.id,
        unit_price=Decimal("300.00"),
        total_price=Decimal("300.00"),
        currency_code="RUB",
        item_snapshot={
            "mark": mark.name,
            "model": model.name,
            "modification": modification.name,
        },
        item_status="active",
    )
    session.add_all([primary_vehicle_line, secondary_vehicle_line, equipment_line])

    users: dict[str, User] = {}
    for key, company in {
        "vehicle_seller": secondary_vehicle_seller,
        "equipment_seller": equipment_seller,
        "unrelated": unrelated_company,
    }.items():
        unique = uuid4()
        user = User(
            phone=f"+7{unique.int % 10**10:010d}",
            email=f"{key}-{unique}@test.local",
            name=key,
            role="dealer",
            company_id=company.id,
            is_active=True,
        )
        session.add(user)
        users[key] = user
    await session.flush()
    return {
        "application": application,
        "primary_vehicle": primary_vehicle,
        "secondary_vehicle": secondary_vehicle,
        "primary_vehicle_line": primary_vehicle_line,
        "secondary_vehicle_line": secondary_vehicle_line,
        "equipment_line": equipment_line,
        "vehicle_seller_company": secondary_vehicle_seller,
        "equipment_seller_company": equipment_seller,
        "unrelated_company": unrelated_company,
        **users,
    }


async def test_application_detail_projects_vehicle_and_special_equipment(
    db_session: AsyncSession,
) -> None:
    application, vehicle_line, equipment_line, removed_line = (
        await _seed_mixed_application(db_session)
    )

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=application.id,
            actor_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )

    assert len(result["vehicles"]) == 1
    assert result["vehicles"][0]["id"] == vehicle_line.id
    assert {item["type"] for item in result["items"]} == {
        "vehicle",
        "special_equipment",
    }
    assert len(result["items"]) == 3

    vehicle_item = next(
        item for item in result["items"] if item["type"] == "vehicle"
    )
    assert vehicle_item["id"] == vehicle_line.id
    assert vehicle_item["item_id"] == vehicle_line.vehicle_id
    assert vehicle_item["quantity"] == 2
    assert vehicle_item["total_price"] == Decimal("999.00")
    assert vehicle_item["image_url"] == (
        "/api/v1/cars/images/projection-vehicle.png"
    )

    equipment_item = next(
        item
        for item in result["items"]
        if item["id"] == equipment_line.id
    )
    assert equipment_item["id"] == equipment_line.id
    assert equipment_item["item_id"] == equipment_line.product_id
    assert equipment_item["title"] == (
        "Снимок марки Снимок модели Снимок модификации"
    )
    assert equipment_item["image_url"].startswith(
        "/api/v1/special-equipment/images/"
    )
    assert equipment_item["image_url"].endswith("/content")
    assert "storage.example" not in equipment_item["image_url"]

    removed_item = next(
        item for item in result["items"] if item["id"] == removed_line.id
    )
    assert removed_item["status"] == "removed"
    assert removed_item["snapshot"]["model"] == "Удалённая модель"

    assert result["vehicles_count"] == 2
    assert result["special_equipment_count"] == 1
    assert result["items_count"] == 3
    assert result["total_vehicles_price"] == Decimal("999.00")
    assert result["total_special_equipment_price"] == Decimal("300.00")
    assert result["total_items_price"] == Decimal("1299.00")
    ApplicationDetailResponse.model_validate(result)


async def test_application_special_equipment_detail_url_tracks_persisted_storefront_scope(
    db_session: AsyncSession,
) -> None:
    application, _vehicle_line, equipment_line, _removed_line = (
        await _seed_mixed_application(db_session)
    )
    product = await db_session.get(
        SpecialEquipmentProduct,
        equipment_line.product_id,
    )
    assert product is not None
    warehouse = Warehouse(
        address="Склад scoped ссылки заявки",
        brand="APPLICATION-SCOPE",
        status="active",
    )
    storefront = Storefront(
        slug=f"application-scope-{uuid4()}",
        is_default=False,
        is_active=True,
    )
    db_session.add_all([warehouse, storefront])
    await db_session.flush()
    product.no_vin = False
    product.vin = "APP-SCOPE-VIN"
    product.warehouse_id = warehouse.id
    application.storefront_id = storefront.id
    membership = StorefrontWarehouse(
        storefront_id=storefront.id,
        warehouse_id=warehouse.id,
    )
    db_session.add(membership)
    await db_session.flush()

    visible = await app_repo.list_application_special_equipment_item_rows(
        db_session,
        [application.id],
    )
    visible_item = next(row for row in visible if row["id"] == equipment_line.id)
    assert visible_item["detail_product_id"] == product.id
    assert visible_item["detail_product_slug"] == product.slug

    await db_session.delete(membership)
    await db_session.flush()
    hidden = await app_repo.list_application_special_equipment_item_rows(
        db_session,
        [application.id],
    )
    hidden_item = next(row for row in hidden if row["id"] == equipment_line.id)
    assert hidden_item["detail_product_id"] is None
    assert hidden_item["detail_product_slug"] is None

    application.storefront_id = DEFAULT_STOREFRONT_ID
    await db_session.flush()
    default_visible = await app_repo.list_application_special_equipment_item_rows(
        db_session,
        [application.id],
    )
    default_item = next(
        row for row in default_visible if row["id"] == equipment_line.id
    )
    assert default_item["detail_product_id"] == product.id


async def test_application_detail_exposes_price_visibility_contract(
    db_session: AsyncSession,
) -> None:
    application, vehicle_line, _equipment_line, _removed_line = (
        await _seed_mixed_application(db_session)
    )
    vehicle_line.discount_show_catalog_price = False
    vehicle_line.markup_show_catalog_price = True
    await db_session.flush()

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=application.id,
            actor_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )

    detail_vehicle = result["vehicles"][0]
    assert detail_vehicle["discount_show_catalog_price"] is False
    assert detail_vehicle["markup_show_catalog_price"] is True
    assert detail_vehicle["show_catalog_price"] is False
    projected_vehicle = next(
        item for item in result["items"] if item["type"] == "vehicle"
    )
    assert projected_vehicle["show_catalog_price"] is False
    ApplicationDetailResponse.model_validate(result)


@pytest.mark.parametrize(
    (
        "vehicle_status",
        "projected_status",
        "expected_items_count",
        "expected_items_total",
    ),
    [
        ("not_confirmed", "rejected", 1, Decimal("300.00")),
        ("replacement", "replacement", 3, Decimal("1299.00")),
    ],
)
async def test_application_commerce_totals_apply_vehicle_status_policy(
    db_session: AsyncSession,
    vehicle_status: str,
    projected_status: str,
    expected_items_count: int,
    expected_items_total: Decimal,
) -> None:
    application, vehicle_line, _equipment_line, _removed_line = (
        await _seed_mixed_application(db_session)
    )
    vehicle_line.car_status = vehicle_status
    await db_session.flush()

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=application.id,
            actor_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )

    projected_vehicle = next(
        item for item in result["items"] if item["type"] == "vehicle"
    )
    assert projected_vehicle["status"] == projected_status
    # Vehicle totals also preserve the persisted option-inclusive total.
    assert result["vehicles_count"] == 2
    assert result["total_vehicles_price"] == Decimal("999.00")
    # Common totals describe only the current active composition.
    assert result["items_count"] == expected_items_count
    assert result["total_items_price"] == expected_items_total


@pytest.mark.parametrize("stored_quantity", [None, 0])
async def test_application_commerce_totals_use_projected_vehicle_quantity(
    db_session: AsyncSession,
    stored_quantity: int | None,
) -> None:
    application, vehicle_line, _equipment_line, _removed_line = (
        await _seed_mixed_application(db_session)
    )
    vehicle_line.quantity = stored_quantity
    await db_session.flush()

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=application.id,
            actor_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )

    projected_vehicle = next(
        item for item in result["items"] if item["type"] == "vehicle"
    )
    assert projected_vehicle["quantity"] == 1
    assert projected_vehicle["total_price"] == Decimal("999.00")
    assert result["items_count"] == 2
    assert result["total_items_price"] == Decimal("1299.00")


async def test_application_totals_stay_unknown_for_unpriced_billable_offer(
    db_session: AsyncSession,
) -> None:
    application, _vehicle_line, equipment_line, component_line = (
        await _seed_mixed_application(db_session)
    )
    equipment_line.unit_price = None
    equipment_line.total_price = None
    equipment_line.item_role = "offer"
    component_line.item_status = "active"
    component_line.item_role = "component"
    component_line.unit_price = Decimal("0.00")
    component_line.total_price = Decimal("0.00")
    await db_session.flush()

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=application.id,
            actor_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )

    assert result["total_special_equipment_price"] is None
    assert result["total_items_price"] is None
    assert result["special_equipment_count"] == 2


async def test_application_list_batches_discriminated_items_and_totals(
    db_session: AsyncSession,
) -> None:
    application, vehicle_line, equipment_line, removed_line = (
        await _seed_mixed_application(db_session)
    )
    vehicle_line.leasing_purpose = "business"
    vehicle_line.regions = ["Москва", "Санкт-Петербург"]
    await db_session.flush()

    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )
    listed = next(
        item
        for item in result["applications"]
        if item["id"] == application.id
    )

    vehicle_item = listed["items"][0]
    assert vehicle_item["type"] == "vehicle"
    assert vehicle_item["leasing_purpose"] == "business"
    assert vehicle_item["regions"] == ["Москва", "Санкт-Петербург"]
    assert {item["id"] for item in listed["items"][1:]} == {
        equipment_line.id,
        removed_line.id,
    }
    assert next(
        item for item in listed["items"] if item["id"] == removed_line.id
    )["status"] == "removed"
    # Historical rows are visible, but only active/reserved lines participate
    # in current commerce totals.
    assert listed["items_count"] == 3
    assert listed["special_equipment_count"] == 1
    assert listed["total_items_price"] == Decimal("1299.00")
    assert listed["total_special_equipment_price"] == Decimal("300.00")
    ApplicationListResponse.model_validate(result)


async def test_all_child_sellers_can_list_and_open_one_mixed_application(
    db_session: AsyncSession,
) -> None:
    seeded = await _seed_multi_seller_application(db_session)
    application = seeded["application"]

    for (
        user_key,
        company_key,
        expected_line_key,
        expected_type,
        expected_total,
    ) in (
        (
            "vehicle_seller",
            "vehicle_seller_company",
            "secondary_vehicle_line",
            "vehicle",
            Decimal("200.00"),
        ),
        (
            "equipment_seller",
            "equipment_seller_company",
            "equipment_line",
            "special_equipment",
            Decimal("300.00"),
        ),
    ):
        user = seeded[user_key]
        company = seeded[company_key]
        expected_line = seeded[expected_line_key]
        listing = await handle_list_applications(
            ListApplicationsQuery(
                actor_id=user.id,
                actor_role="dealer",
                actor_company_id=company.id,
            ),
            db_session,
        )
        listed = next(
            item
            for item in listing["applications"]
            if item["id"] == application.id
        )
        assert [item["id"] for item in listed["items"]] == [expected_line.id]
        assert [item["type"] for item in listed["items"]] == [expected_type]
        assert listed["items_count"] == 1
        assert listed["total_amount"] == expected_total
        assert listed["total_items_price"] == expected_total

        detail = await handle_get_application(
            GetApplicationQuery(
                application_id=application.id,
                actor_id=user.id,
                actor_role="dealer",
                actor_company_id=company.id,
            ),
            db_session,
        )
        assert detail["id"] == application.id
        assert [item["id"] for item in detail["items"]] == [expected_line.id]
        assert [item["type"] for item in detail["items"]] == [expected_type]
        assert detail["items_count"] == 1
        assert detail["total_amount"] == expected_total
        assert detail["total_items_price"] == expected_total
        if expected_type == "vehicle":
            assert [row["id"] for row in detail["vehicles"]] == [
                expected_line.id
            ]
        else:
            assert detail["vehicles"] == []


async def test_unrelated_dealer_cannot_list_or_open_mixed_application(
    db_session: AsyncSession,
) -> None:
    seeded = await _seed_multi_seller_application(db_session)
    application = seeded["application"]
    unrelated = seeded["unrelated"]
    unrelated_company = seeded["unrelated_company"]

    listing = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=unrelated.id,
            actor_role="dealer",
            actor_company_id=unrelated_company.id,
        ),
        db_session,
    )
    assert application.id not in {
        item["id"] for item in listing["applications"]
    }

    with pytest.raises(ApplicationNotOwnedError):
        await handle_get_application(
            GetApplicationQuery(
                application_id=application.id,
                actor_id=unrelated.id,
                actor_role="dealer",
                actor_company_id=unrelated_company.id,
            ),
            db_session,
        )


async def test_child_seller_scope_is_reused_by_dealer_and_lca_lists(
    db_session: AsyncSession,
) -> None:
    seeded = await _seed_multi_seller_application(db_session)
    application = seeded["application"]

    for company_key in (
        "vehicle_seller_company",
        "equipment_seller_company",
    ):
        company = seeded[company_key]
        stats = await dealer_repo.dealer_sales_stats(db_session, company.id)
        assert stats["total_applications"] == 1
        report_rows = await reporting_repo.dealer_applications(
            db_session,
            dealer_id=company.id,
            date_from=None,
            date_to=None,
        )
        assert [row["id"] for row in report_rows] == [application.id]

    leasing_owner = Company(
        name="Лизинговая компания для списка продавца",
        company_type="leasing_company",
    )
    db_session.add(leasing_owner)
    await db_session.flush()
    leasing_company = LeasingCompany(
        company_id=leasing_owner.id,
        is_active=True,
    )
    db_session.add(leasing_company)
    await db_session.flush()
    db_session.add(
        LeasingCompanyApplication(
            application_id=application.id,
            leasing_company_id=leasing_company.id,
            status="submitted",
        )
    )
    await db_session.flush()

    seller_company = seeded["equipment_seller_company"]
    lca_rows = await lca_repo.list_lca_rows_for_actor(
        db_session,
        actor_role="dealer",
        actor_company_id=seller_company.id,
        application_id=application.id,
    )
    assert lca_rows["pagination"]["total"] == 1
    assert lca_rows["items"][0]["application_id"] == application.id


async def test_special_equipment_seller_cannot_mutate_parent_application(
    db_session: AsyncSession,
) -> None:
    seeded = await _seed_multi_seller_application(db_session)
    application = seeded["application"]
    seller = seeded["equipment_seller"]
    seller_company = seeded["equipment_seller_company"]

    assert await app_repo.dealer_company_owns_application_item(
        db_session,
        application_id=application.id,
        company_id=seller_company.id,
    )
    with pytest.raises(ServiceError) as conditions_error:
        await handle_update_conditions(
            UpdateConditionsCommand(
                application_id=application.id,
                actor_id=seller.id,
                actor_role="dealer",
                actor_company_id=seller_company.id,
                lease_term_months=48,
            ),
            db_session,
        )
    assert conditions_error.value.status_code == 403

    with pytest.raises(ServiceError) as vehicles_error:
        await handle_update_vehicles(
            UpdateVehiclesCommand(
                application_id=application.id,
                actor_id=seller.id,
                actor_role="dealer",
                actor_company_id=seller_company.id,
                vehicles=[
                    ApplicationVehiclePayload(
                        vehicle_id=seeded["primary_vehicle"].id,
                        custom_price=Decimal("1.00"),
                    )
                ],
            ),
            db_session,
        )
    assert vehicles_error.value.status_code == 403

    await db_session.refresh(application)
    assert application.lease_term_months is None
    assert application.total_amount == Decimal("600.00")
    assert await app_repo.count_application_vehicles(db_session, application.id) == 2


async def test_vehicle_seller_vin_read_is_scoped_to_exact_child(
    db_session: AsyncSession,
) -> None:
    seeded = await _seed_multi_seller_application(db_session)
    vehicle_seller = seeded["vehicle_seller"]
    vehicle_seller_company = seeded["vehicle_seller_company"]
    equipment_seller = seeded["equipment_seller"]
    equipment_seller_company = seeded["equipment_seller_company"]
    target = seeded["secondary_vehicle_line"]

    allowed = await handle_list_available_vins(
        ListAvailableVinsQuery(
            application_vehicle_id=target.id,
            actor_id=vehicle_seller.id,
            actor_role="dealer",
            actor_company_id=vehicle_seller_company.id,
        ),
        db_session,
    )
    assert allowed["application_vehicle_id"] == target.id

    with pytest.raises(ApplicationNotOwnedError):
        await handle_list_available_vins(
            ListAvailableVinsQuery(
                application_vehicle_id=target.id,
                actor_id=equipment_seller.id,
                actor_role="dealer",
                actor_company_id=equipment_seller_company.id,
            ),
            db_session,
        )


async def test_leasing_company_response_state_uses_unified_items(
    db_session: AsyncSession,
) -> None:
    application, _vehicle_line, equipment_line, removed_line = (
        await _seed_mixed_application(db_session)
    )
    application.leasing_company_comments = "Внутренний комментарий платформы"
    application.client_visible_comment = "Комментарий другого канала"
    application.current_stage = "internal-review"
    await db_session.flush()
    leasing_company_owner = Company(
        name="Лизинговая компания единой заявки",
        company_type="leasing_company",
    )
    db_session.add(leasing_company_owner)
    await db_session.flush()
    leasing_company = LeasingCompany(
        company_id=leasing_company_owner.id,
        is_active=True,
    )
    lc_reader = User(
        phone="+79990003535", role="leasing_company",
        company_id=leasing_company_owner.id, is_active=True,
    )
    db_session.add(lc_reader)
    db_session.add(leasing_company)
    await db_session.flush()
    db_session.add(
        LeasingCompanyApplication(
            application_id=application.id,
            leasing_company_id=leasing_company.id,
            status="under_review",
        )
    )
    await db_session.flush()

    result = await handle_get_lc_response_state(
        GetLcResponseStateQuery(
            application_id=application.id,
            actor_leasing_company_id=leasing_company.id,
            actor_user_id=lc_reader.id,
            actor_company_id=leasing_company_owner.id,
        ),
        db_session,
    )

    projected = result["application"]
    assert projected is not None
    assert {item["id"] for item in projected["items"]} >= {
        equipment_line.id,
        removed_line.id,
    }
    assert projected["items_count"] == 3
    assert projected["total_items_price"] == Decimal("1299.00")
    assert projected["special_equipment_count"] == 1
    assert projected["total_special_equipment_price"] == Decimal("300.00")
    assert projected["vehicles_count"] == 2
    assert projected["total_vehicles_price"] == Decimal("999.00")
    hidden_lc_application_fields = {
        "created_by",
        "dealer_company_id",
        "leasing_company_comments",
        "client_visible_comment",
        "comments_updated_at",
        "documents_requested_at",
        "client_comment_updated_at",
        "questionnaire_completed",
        "questionnaire_progress",
        "current_stage",
        "group_id",
        "group_number",
        "group_status",
        "group_status_label",
        "application_status",
        "application_status_label",
        "created_at",
        "updated_at",
    }
    assert hidden_lc_application_fields.isdisjoint(projected)
    LcResponseStateResponse.model_validate(result)
    wire_application = jsonable_encoder(
        application_commerce_money_to_wire(projected)
    )
    assert isinstance(wire_application["items"][0]["unit_price"], str)
    assert isinstance(wire_application["total_items_price"], str)
    assert isinstance(wire_application["total_amount"], int | float)


async def test_group_application_items_groups_by_group_id_and_preserves_overstock() -> None:
    from presentation.schemas.applications import (
        ApplicationSpecialEquipmentItem as SchemaItem,
    )

    app_id = uuid4()
    group_1 = uuid4()
    group_2 = uuid4()

    # 15 items for group 1
    unit_price_1 = Decimal("1500000.00")
    group_1_products = [uuid4() for _ in range(15)]
    rows_group_1 = [
        {
            "id": uuid4(),
            "application_id": app_id,
            "product_id": prod_id,
            "group_id": group_1,
            "item_role": "offer",
            "item_status": "active",
            "unit_price": unit_price_1,
            "total_price": unit_price_1,
            "currency_code": "RUB",
            "overstock_requested_quantity": 5 if idx == 0 else 0,
            "item_snapshot": {"mark": "FAW", "model": "J7"},
            "leasing_purpose": "business",
            "regions": ["77", "50"],
            "comment": "Group 1 comment",
        }
        for idx, prod_id in enumerate(group_1_products)
    ]

    # 8 items for group 2
    unit_price_2 = Decimal("800000.00")
    group_2_products = [uuid4() for _ in range(8)]
    rows_group_2 = [
        {
            "id": uuid4(),
            "application_id": app_id,
            "product_id": prod_id,
            "group_id": group_2,
            "item_role": "offer",
            "item_status": "active",
            "unit_price": unit_price_2,
            "total_price": unit_price_2,
            "currency_code": "RUB",
            "overstock_requested_quantity": 0,
            "item_snapshot": {"mark": "Тонар", "model": "Полуприцеп"},
            "leasing_purpose": "expansion",
            "regions": ["78"],
            "comment": "Group 2 comment",
        }
        for idx, prod_id in enumerate(group_2_products)
    ]

    # 1 legacy item without group_id
    legacy_product = uuid4()
    legacy_id = uuid4()
    legacy_row: dict[str, Any] = {
        "id": legacy_id,
        "application_id": app_id,
        "product_id": legacy_product,
        "group_id": None,
        "item_role": "offer",
        "item_status": "active",
        "unit_price": Decimal("500000.00"),
        "total_price": Decimal("500000.00"),
        "currency_code": "RUB",
        "overstock_requested_quantity": 0,
        "item_snapshot": {"mark": "Legacy", "model": "Old"},
        "leasing_purpose": None,
        "regions": [],
        "comment": None,
    }

    all_rows = rows_group_1 + rows_group_2 + [legacy_row]

    grouped = group_application_items(
        [app_id],
        vehicle_rows=[],
        special_equipment_rows=all_rows,
        actor_role="client",
    )

    items = grouped[app_id]
    assert len(items) == 3

    item_1 = next(item for item in items if item["item_id"] == group_1)
    assert item_1["quantity"] == 15
    assert item_1["unit_price"] == unit_price_1
    assert item_1["total_price"] == unit_price_1 * 15
    assert item_1["overstock_requested_quantity"] == 5
    assert item_1["product_ids"] == group_1_products
    assert item_1["leasing_purpose"] == "business"
    assert item_1["regions"] == ["77", "50"]
    assert item_1["region"] == "77"
    assert item_1["comment"] == "Group 1 comment"

    item_2 = next(item for item in items if item["item_id"] == group_2)
    assert item_2["quantity"] == 8
    assert item_2["unit_price"] == unit_price_2
    assert item_2["total_price"] == unit_price_2 * 8
    assert item_2["overstock_requested_quantity"] == 0
    assert item_2["product_ids"] == group_2_products
    assert item_2["leasing_purpose"] == "expansion"
    assert item_2["regions"] == ["78"]
    assert item_2["region"] == "78"

    item_legacy = next(item for item in items if item["id"] == legacy_id)
    assert item_legacy["item_id"] == legacy_product
    assert item_legacy["quantity"] == 1
    assert item_legacy["product_ids"] == [legacy_product]

    # Validate against Pydantic schema
    for it in items:
        SchemaItem.model_validate(it)
