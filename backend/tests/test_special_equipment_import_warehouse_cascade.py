"""Tests for warehouse cascade purge and warehouse-scoped FULL_SNAPSHOT import."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from domain.special_equipment_import import ImportMode
from infrastructure.models.applications import (
    ApplicationVehicle,
    ApplicationVehicleAllocation,
    LeasingApplication,
)
from infrastructure.models.companies import Company
from infrastructure.models.exchange import (
    ExchangeCartItem,
    ExchangeRequest,
)
from infrastructure.models.payments import (
    LeasingPaymentSchedule,
    Payment,
    PurchaseOrder,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentCategory,
    SpecialEquipmentColor,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
    SpecialEquipmentProductAttachment,
    SpecialEquipmentProductCategory,
    SpecialEquipmentProductImage,
    SpecialEquipmentTrim,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentCartItem,
    SpecialEquipmentFavorite,
    SpecialEquipmentLeasingPaymentSchedule,
    SpecialEquipmentOrderItem,
    SpecialEquipmentPayment,
    SpecialEquipmentPaymentCallbackInbox,
    SpecialEquipmentPriceChangeLog,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.models.users import User, UserFavorite
from infrastructure.models.vehicles import City, VehicleWarehouseTransfer, Warehouse
from infrastructure.repositories import special_equipment_import_repository as repo

pytestmark = pytest.mark.asyncio


async def _create_test_entities(
    db_session: AsyncSession,
) -> tuple[Warehouse, Warehouse, SpecialEquipmentProduct, SpecialEquipmentProduct, SpecialEquipmentProduct, User, Company]:
    suffix = uuid.uuid4().hex[:8]
    city = City(name=f"City-{suffix}")
    company = Company(
        name=f"Seller Company-{suffix}",
        company_type="dealer",
        inn=f"77{uuid.uuid4().int % 100000000:08d}",
        is_active=True,
    )
    db_session.add_all([city, company])
    await db_session.flush()

    user = User(
        phone=f"+7999{uuid.uuid4().int % 10000000:07d}",
        email=f"user-{suffix}@example.com",
        name=f"User-{suffix}",
        role="client",
        is_active=True,
        company_id=company.id,
    )
    warehouse_target = Warehouse(
        name=f"Target Warehouse-{suffix}",
        address=f"Target Address-{suffix}",
        city_id=city.id,
        owner_company_id=company.id,
        owner_company_type="dealer",
        is_active=True,
    )
    warehouse_other = Warehouse(
        name=f"Other Warehouse-{suffix}",
        address=f"Other Address-{suffix}",
        city_id=city.id,
        owner_company_id=company.id,
        owner_company_type="dealer",
        is_active=True,
    )
    db_session.add_all([user, warehouse_target, warehouse_other])
    await db_session.flush()

    mark = SpecialEquipmentMark(
        code=f"mark-{suffix}",
        name=f"Mark-{suffix}",
        slug=f"mark-{suffix}",
    )
    db_session.add(mark)
    await db_session.flush()

    model = SpecialEquipmentModel(
        mark_id=mark.id,
        code=f"model-{suffix}",
        name=f"Model-{suffix}",
        slug=f"model-{suffix}",
    )
    db_session.add(model)
    await db_session.flush()

    modification = SpecialEquipmentModification(
        model_id=model.id,
        code=f"mod-{suffix}",
        name=f"Mod-{suffix}",
        slug=f"mod-{suffix}",
    )
    db_session.add(modification)
    await db_session.flush()

    trim = SpecialEquipmentTrim(
        modification_id=modification.id,
        code=f"trim-{suffix}",
        name=f"Trim-{suffix}",
        slug=f"trim-{suffix}",
    )
    color = SpecialEquipmentColor(
        code=f"color-{suffix}",
        name=f"Color-{suffix}",
        applicability="body",
    )
    category = SpecialEquipmentCategory(
        code=f"cat-{suffix}",
        name=f"Cat-{suffix}",
        slug=f"cat-{suffix}",
        usage_metric="mileage_km",
    )
    db_session.add_all([trim, color, category])
    await db_session.flush()

    # Product 1 on target warehouse
    product_1 = SpecialEquipmentProduct(
        code=f"prod1-{suffix}",
        slug=f"prod1-{suffix}",
        modification_id=modification.id,
        trim_id=trim.id,
        body_color_id=color.id,
        seller_company_id=company.id,
        warehouse_id=warehouse_target.id,
        condition="new",
        manufacture_year=2024,
        price=Decimal("1000000.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
        no_vin=False,
        vin=f"VIN1{suffix.upper():0>13}",
    )
    # Product 2 on target warehouse
    product_2 = SpecialEquipmentProduct(
        code=f"prod2-{suffix}",
        slug=f"prod2-{suffix}",
        modification_id=modification.id,
        trim_id=trim.id,
        body_color_id=color.id,
        seller_company_id=company.id,
        warehouse_id=warehouse_target.id,
        condition="new",
        manufacture_year=2024,
        price=Decimal("1200000.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
        no_vin=False,
        vin=f"VIN2{suffix.upper():0>13}",
    )
    # Product on other warehouse
    product_other = SpecialEquipmentProduct(
        code=f"prodother-{suffix}",
        slug=f"prodother-{suffix}",
        modification_id=modification.id,
        trim_id=trim.id,
        body_color_id=color.id,
        seller_company_id=company.id,
        warehouse_id=warehouse_other.id,
        condition="new",
        manufacture_year=2024,
        price=Decimal("1500000.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
        no_vin=False,
        vin=f"VIN3{suffix.upper():0>13}",
    )
    db_session.add_all([product_1, product_2, product_other])
    await db_session.flush()

    return warehouse_target, warehouse_other, product_1, product_2, product_other, user, company


async def _populate_test_dependencies(
    db_session: AsyncSession,
    *,
    user: User,
    company: Company,
    warehouse_target: Warehouse,
    warehouse_other: Warehouse,
    product_1: SpecialEquipmentProduct,
    product_2: SpecialEquipmentProduct,
) -> ApplicationVehicle:
    # 1. Favorites
    fav_se = SpecialEquipmentFavorite(user_id=user.id, product_id=product_1.id)
    fav_user = UserFavorite(user_id=user.id, product_id=product_1.id)
    db_session.add_all([fav_se, fav_user])

    # 2. Carts: parent cart item for product_1, child cart item for product_2
    cart_parent = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=product_1.id,
        quantity=1,
    )
    db_session.add(cart_parent)
    await db_session.flush()

    cart_child = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=product_2.id,
        parent_item_id=cart_parent.id,
        quantity=1,
    )
    db_session.add(cart_child)

    # 3. Leasing Application and items
    leasing_app = LeasingApplication(
        company_id=company.id,
        created_by=user.id,
        status="active",
    )
    db_session.add(leasing_app)
    await db_session.flush()

    app_item = SpecialEquipmentApplicationItem(
        application_id=leasing_app.id,
        product_id=product_1.id,
        item_snapshot={"code": product_1.code},
    )
    db_session.add(app_item)
    await db_session.flush()

    price_log = SpecialEquipmentPriceChangeLog(
        item_id=app_item.id,
        old_price=Decimal("1000000.00"),
        new_price=Decimal("950000.00"),
        changed_by=user.id,
        source="api",
    )
    db_session.add(price_log)

    app_vehicle = ApplicationVehicle(
        application_id=leasing_app.id,
        product_id=product_1.id,
    )
    db_session.add(app_vehicle)
    await db_session.flush()

    app_alloc = ApplicationVehicleAllocation(
        application_vehicle_id=app_vehicle.id,
        product_id=product_1.id,
        unit_price=Decimal("1000000.00"),
        reserved_until=datetime.now(UTC),
        created_by=user.id,
    )
    db_session.add(app_alloc)

    # 4. Purchase orders & payments
    se_order = SpecialEquipmentPurchaseOrder(
        user_id=user.id,
        product_id=product_1.id,
        purchase_type="reservation",
        status="reserved",
        unit_price=Decimal("1000000.00"),
        total_price=Decimal("1000000.00"),
        paid_amount=Decimal("0.00"),
        remaining_amount=Decimal("1000000.00"),
        item_snapshot={"code": product_1.code},
        idempotency_key=f"idem-{uuid.uuid4().hex}",
        request_hash="a" * 64,
    )
    db_session.add(se_order)
    await db_session.flush()

    se_order_item = SpecialEquipmentOrderItem(
        purchase_order_id=se_order.id,
        product_id=product_1.id,
        group_id=uuid.uuid4(),
        unit_price=Decimal("1000000.00"),
        item_snapshot={"code": product_1.code},
    )
    se_payment = SpecialEquipmentPayment(
        purchase_order_id=se_order.id,
        user_id=user.id,
        payment_type="reservation",
        amount=Decimal("50000.00"),
        status="pending",
        idempotency_key=f"pay-idem-{uuid.uuid4().hex}",
        request_hash="b" * 64,
    )
    se_schedule = SpecialEquipmentLeasingPaymentSchedule(
        purchase_order_id=se_order.id,
        payment_number=1,
        due_date=date(2025, 1, 1),
        amount=Decimal("50000.00"),
    )
    db_session.add_all([se_order_item, se_payment, se_schedule])
    await db_session.flush()

    callback_inbox = SpecialEquipmentPaymentCallbackInbox(
        event_key="c" * 64,
        gateway_transaction_id="gw-tx-1",
        payment_id=se_payment.id,
        signature_digest="d" * 64,
        payload={"dummy": True},
    )
    db_session.add(callback_inbox)

    # Legacy purchase order
    po = PurchaseOrder(
        user_id=user.id,
        product_id=product_1.id,
        purchase_type="reservation",
        status="reserved",
        total_price=Decimal("1000000.00"),
        paid_amount=Decimal("0.00"),
        remaining_amount=Decimal("1000000.00"),
    )
    db_session.add(po)
    await db_session.flush()

    po_payment = Payment(
        purchase_order_id=po.id,
        user_id=user.id,
        payment_type="reservation",
        amount=Decimal("1000000.00"),
        status="pending_payment",
    )
    po_sched = LeasingPaymentSchedule(
        purchase_order_id=po.id,
        payment_number=1,
        due_date=date(2025, 1, 1),
        amount=Decimal("1000000.00"),
    )
    db_session.add_all([po_payment, po_sched])

    # 5. Attachments
    attachment = SpecialEquipmentProductAttachment(
        product_id=product_1.id,
        attachment_product_id=product_2.id,
        position=0,
    )
    db_session.add(attachment)

    # 6. Images, Categories, Transfers
    image = SpecialEquipmentProductImage(
        product_id=product_1.id,
        storage_key=f"img-{uuid.uuid4().hex}.jpg",
    )
    category_id = (
        await db_session.execute(sa.select(SpecialEquipmentCategory.id))
    ).scalars().first()
    assert category_id is not None
    cat_link = SpecialEquipmentProductCategory(
        product_id=product_1.id,
        category_id=category_id,
    )
    transfer = VehicleWarehouseTransfer(
        product_id=product_1.id,
        source_warehouse_id=warehouse_target.id,
        destination_warehouse_id=warehouse_other.id,
    )
    db_session.add_all([image, cat_link, transfer])

    # 7. Exchange cart & requests
    ex_cart = ExchangeCartItem(
        user_id=user.id,
        product_id=product_1.id,
    )
    ex_req = ExchangeRequest(
        lc_user_id=user.id,
        product_id=product_1.id,
        quantity=1,
    )
    db_session.add_all([ex_cart, ex_req])
    await db_session.flush()
    return app_vehicle


async def test_cascade_purge_warehouse_products_deletes_all_dependencies(
    db_session: AsyncSession,
) -> None:
    """Cascade purge must delete all warehouse products and their dependent entities."""
    (
        warehouse_target,
        warehouse_other,
        product_1,
        product_2,
        product_other,
        user,
        company,
    ) = await _create_test_entities(db_session)

    app_vehicle = await _populate_test_dependencies(
        db_session,
        user=user,
        company=company,
        warehouse_target=warehouse_target,
        warehouse_other=warehouse_other,
        product_1=product_1,
        product_2=product_2,
    )

    # Execute purge of target warehouse
    purged_count = await repo.cascade_purge_warehouse_products(
        db_session, warehouse_target.id
    )
    assert purged_count == 2

    # Verification: products on target warehouse deleted
    p1 = await db_session.get(SpecialEquipmentProduct, product_1.id)
    p2 = await db_session.get(SpecialEquipmentProduct, product_2.id)
    assert p1 is None
    assert p2 is None

    # Product on other warehouse untouched
    p_other = await db_session.get(SpecialEquipmentProduct, product_other.id)
    assert p_other is not None

    # Users and companies untouched
    u = await db_session.get(User, user.id)
    w_target = await db_session.get(Warehouse, warehouse_target.id)
    w_other = await db_session.get(Warehouse, warehouse_other.id)
    assert u is not None
    assert w_target is not None
    assert w_other is not None

    # Dependent entities cleanly removed
    assert (
        await db_session.execute(
            sa.select(SpecialEquipmentCartItem).where(
                SpecialEquipmentCartItem.product_id.in_([product_1.id, product_2.id])
            )
        )
    ).scalars().first() is None

    assert (
        await db_session.execute(
            sa.select(SpecialEquipmentApplicationItem).where(
                SpecialEquipmentApplicationItem.product_id == product_1.id
            )
        )
    ).scalars().first() is None

    assert (
        await db_session.execute(
            sa.select(SpecialEquipmentPurchaseOrder).where(
                SpecialEquipmentPurchaseOrder.product_id == product_1.id
            )
        )
    ).scalars().first() is None

    # Application vehicle product_id set to null
    refreshed_av = await db_session.get(ApplicationVehicle, app_vehicle.id)
    assert refreshed_av is not None
    assert refreshed_av.product_id is None


async def test_cascade_purge_empty_warehouse_returns_zero(
    db_session: AsyncSession,
) -> None:
    empty_warehouse_id = uuid.uuid4()
    count = await repo.cascade_purge_warehouse_products(db_session, empty_warehouse_id)
    assert count == 0


async def test_lock_import_archive_targets_warehouse_scoped(
    db_session: AsyncSession,
) -> None:
    (
        warehouse_target,
        _warehouse_other,
        product_1,
        _product_2,
        _product_other,
        _user,
        _company,
    ) = await _create_test_entities(db_session)

    # In FULL_SNAPSHOT with target_warehouse_id, plan contains product_1, but not product_2
    plan = {
        "products": [
            {"id": product_1.id, "operation": "SET"},
        ]
    }
    # product_2 belongs to warehouse_target -> should be locked as archive target
    # product_other belongs to warehouse_other -> must NOT be included in archive targets
    result = await repo.lock_import_archive_targets(
        db_session,
        mode="FULL_SNAPSHOT",
        plan=plan,
        target_warehouse_id=warehouse_target.id,
    )
    assert result is True


async def test_get_v2_import_context_excludes_target_warehouse_products_in_full_snapshot(
    db_session: AsyncSession,
) -> None:
    (
        warehouse_target,
        _warehouse_other,
        product_1,
        _product_2,
        product_other,
        _user,
        _company,
    ) = await _create_test_entities(db_session)

    # When mode == FULL_SNAPSHOT and target_warehouse_id is set:
    context = await repo.get_v2_import_context(
        db_session,
        requested_codes={
            "products_codes": {product_1.code, product_other.code},
        },
        seller_inns=set(),
        target_warehouse_id=warehouse_target.id,
        mode=ImportMode.FULL_SNAPSHOT,
    )
    # product_1 belongs to warehouse_target, so it is excluded from context["products"]
    assert product_1.code not in context.get("products", {})
    # product_other belongs to warehouse_other, so it remains in context["products"]
    assert product_other.code in context.get("products", {})
