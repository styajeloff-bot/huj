"""Regression tests for Warehouse.brand subquery correlation.

Verifies that Warehouse._brand_expression explicitly correlates only the warehouse
table, avoiding SQLAlchemy auto-correlation failures when SpecialEquipmentMark
is also joined in the outer query (as in list_application_vehicles_with_catalog
and purchase_repository.get_by_user_id / get_by_id_with_details).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from application.commerce import commerce_facade
from application.queries.applications.get_application import (
    GetApplicationQuery,
    handle_get_application,
)
from application.queries.purchases import (
    GetUserOrdersQuery,
    handle_get_user_orders,
)
from domain.commerce import CommerceItemType
from infrastructure.models.applications import ApplicationVehicle, LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.payments import PurchaseOrder
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import City, Warehouse, WarehouseMark
from infrastructure.repositories import purchase_repository as purchase_repo
from presentation.schemas.applications import ApplicationDetailResponse
from presentation.schemas.commerce import CommerceOrderListResponse
from tests.special_equipment_factories import special_equipment_directory


def test_warehouse_brand_expression_compilation_with_mark_join() -> None:
    """Warehouse.brand must compile when SpecialEquipmentMark is also in outer FROM."""
    app_id = uuid4()
    stmt = (
        sa.select(
            ApplicationVehicle.id,
            SpecialEquipmentMark.name.label("mark_name"),
            Warehouse.brand.label("warehouse_brand"),
        )
        .select_from(ApplicationVehicle)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
            isouter=True,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id == SpecialEquipmentModification.model_id,
            isouter=True,
        )
        .join(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
            isouter=True,
        )
        .join(
            Warehouse,
            Warehouse.id == SpecialEquipmentProduct.warehouse_id,
            isouter=True,
        )
        .where(ApplicationVehicle.application_id == app_id)
    )

    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "warehouse_marks.warehouse_id = warehouses.id" in compiled
    assert "string_agg(special_equipment_marks.name" in compiled


def test_aliased_warehouse_brand_expression_compilation() -> None:
    """Warehouse.brand must also compile when Warehouse is aliased."""
    wh = aliased(Warehouse, name="wh_alias")
    stmt = (
        sa.select(wh.id, wh.brand.label("brand_name"))
        .select_from(wh)
        .join(
            WarehouseMark,
            WarehouseMark.warehouse_id == wh.id,
            isouter=True,
        )
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "warehouse_marks.warehouse_id = wh_alias.id" in compiled


def test_purchase_repository_queries_compilation() -> None:
    """Purchase queries joining SpecialEquipmentMark and selecting Warehouse.brand must compile."""
    user_id = uuid4()
    order_id = uuid4()

    # get_by_user_id query
    stmt_list = sa.select(
        *purchase_repo._ORDER_COLS,
        *purchase_repo._CATALOG_JOIN_COLS,
        SpecialEquipmentProduct.price.label("base_price"),
        SpecialEquipmentProduct.special_price.label("discount_price"),
    )
    stmt_list = purchase_repo._with_catalog_joins(stmt_list).where(
        PurchaseOrder.user_id == user_id
    )
    compiled_list = str(stmt_list.compile(dialect=postgresql.dialect()))
    assert "warehouse_brand" in compiled_list

    # get_by_id_with_details query
    stmt_detail = sa.select(
        *purchase_repo._ORDER_COLS,
        Warehouse.brand.label("warehouse_brand"),
    )
    stmt_detail = purchase_repo._with_catalog_joins(stmt_detail).where(
        PurchaseOrder.id == order_id
    )
    compiled_detail = str(stmt_detail.compile(dialect=postgresql.dialect()))
    assert "warehouse_brand" in compiled_detail


@pytest.mark.asyncio
async def test_get_application_detail_with_warehouse_brand(
    db_session: AsyncSession,
) -> None:
    """handle_get_application must successfully resolve vehicles with warehouse_brand."""
    client_co = Company(name=f"Client Co {uuid4().hex[:6]}", company_type="other")
    dealer_co = Company(name=f"Dealer Co {uuid4().hex[:6]}", company_type="dealer")
    db_session.add_all([client_co, dealer_co])
    await db_session.flush()

    user = User(
        phone=f"+7999{uuid4().int % 10000000:07d}",
        email=f"u-{uuid4().hex[:6]}@test.local",
        name="Test User",
        role="client",
        company_id=client_co.id,
    )
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        UserCompany(
            user_id=user.id,
            company_id=client_co.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )

    mark, model, modification = special_equipment_directory(
        mark_name=f"Brand-{uuid4().hex[:6]}",
        model_name=f"Model-{uuid4().hex[:6]}",
        modification_name=f"Mod-{uuid4().hex[:6]}",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    city = City(name=f"City-{uuid4().hex[:6]}")
    db_session.add(city)
    await db_session.flush()

    warehouse = Warehouse(
        name=f"WH-{uuid4().hex[:6]}",
        owner_company_id=dealer_co.id,
        owner_company_type="dealer",
        city_id=city.id,
        address="ул. Складская, 1",
        is_active=True,
    )
    db_session.add(warehouse)
    await db_session.flush()
    db_session.add(WarehouseMark(warehouse_id=warehouse.id, mark_id=mark.id))
    await db_session.flush()

    product = SpecialEquipmentProduct(
        code=f"prd-{uuid4().hex[:6]}",
        modification_id=modification.id,
        seller_company_id=dealer_co.id,
        warehouse_id=warehouse.id,
        slug=f"prd-{uuid4().hex[:6]}",
        condition="new",
        no_vin=True,
        price=Decimal("2500000.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()

    application = LeasingApplication(
        company_id=client_co.id,
        dealer_company_id=dealer_co.id,
        created_by=user.id,
        status="active",
        total_amount=Decimal("2500000.00"),
    )
    db_session.add(application)
    await db_session.flush()

    av = ApplicationVehicle(
        application_id=application.id,
        product_id=product.id,
        modification_id=str(modification.id),
        quantity=1,
        unit_price=Decimal("2500000.00"),
        total_price=Decimal("2500000.00"),
    )
    db_session.add(av)
    await db_session.flush()

    # Query details
    query = GetApplicationQuery(
        application_id=application.id,
        actor_id=user.id,
        actor_role="client",
        actor_company_id=client_co.id,
    )
    detail = await handle_get_application(query, db_session)
    assert detail is not None
    assert len(detail["vehicles"]) == 1
    assert detail["vehicles"][0]["warehouse"]["brand"] == mark.name

    # Validate against presentation response schema
    validated = ApplicationDetailResponse.model_validate(detail)
    assert validated.id == application.id
    assert validated.vehicles[0].warehouse is not None
    assert validated.vehicles[0].warehouse.brand == mark.name


@pytest.mark.asyncio
async def test_get_commerce_orders_vehicle_type_with_warehouse_brand(
    db_session: AsyncSession,
) -> None:
    """handle_get_user_orders and commerce_facade.list_orders must resolve vehicle orders without error."""
    client_co = Company(name=f"Client Co {uuid4().hex[:6]}", company_type="other")
    dealer_co = Company(name=f"Dealer Co {uuid4().hex[:6]}", company_type="dealer")
    db_session.add_all([client_co, dealer_co])
    await db_session.flush()

    user = User(
        phone=f"+7999{uuid4().int % 10000000:07d}",
        email=f"u-{uuid4().hex[:6]}@test.local",
        name="Test User",
        role="client",
        company_id=client_co.id,
    )
    db_session.add(user)
    await db_session.flush()

    mark, model, modification = special_equipment_directory(
        mark_name=f"Brand-{uuid4().hex[:6]}",
        model_name=f"Model-{uuid4().hex[:6]}",
        modification_name=f"Mod-{uuid4().hex[:6]}",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    city = City(name=f"City-{uuid4().hex[:6]}")
    db_session.add(city)
    await db_session.flush()

    warehouse = Warehouse(
        name=f"WH-{uuid4().hex[:6]}",
        owner_company_id=dealer_co.id,
        owner_company_type="dealer",
        city_id=city.id,
        address="ул. Складская, 2",
        is_active=True,
    )
    db_session.add(warehouse)
    await db_session.flush()
    db_session.add(WarehouseMark(warehouse_id=warehouse.id, mark_id=mark.id))
    await db_session.flush()

    product = SpecialEquipmentProduct(
        code=f"prd-{uuid4().hex[:6]}",
        modification_id=modification.id,
        seller_company_id=dealer_co.id,
        warehouse_id=warehouse.id,
        slug=f"prd-{uuid4().hex[:6]}",
        condition="new",
        no_vin=True,
        price=Decimal("1800000.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()

    order = PurchaseOrder(
        user_id=user.id,
        product_id=product.id,
        purchase_type="full_purchase",
        status="purchased",
        total_price=Decimal("1800000.00"),
        paid_amount=Decimal("0.00"),
    )
    db_session.add(order)
    await db_session.flush()

    # 1. Test repository / application handler
    rows = await handle_get_user_orders(
        GetUserOrdersQuery(user_id=user.id),
        db_session,
    )
    assert len(rows) == 1
    assert rows[0]["id"] == order.id
    assert rows[0]["warehouse_brand"] == mark.name

    # 2. Test commerce facade list_orders for type=vehicle
    orders = await commerce_facade.list_orders(
        user.id,
        db_session,
        CommerceItemType.VEHICLE,
    )
    assert len(orders) == 1
    assert orders[0]["id"] == order.id
    assert orders[0]["item"]["type"] == CommerceItemType.VEHICLE.value
    validated = CommerceOrderListResponse.model_validate({"items": orders})
    assert len(validated.items) == 1
    assert validated.items[0].id == order.id
    assert validated.items[0].item.type == CommerceItemType.VEHICLE.value
