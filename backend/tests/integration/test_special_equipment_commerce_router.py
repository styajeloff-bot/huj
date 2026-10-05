"""PostgreSQL-backed authorization tests for special-equipment commerce."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from application.special_equipment_commerce import CreateOrderCommand, create_order
from domain.special_equipment_commerce import (
    SpecialEquipmentCartConfigurationConflictError,
    SpecialEquipmentPurchaseType,
)
from infrastructure.database import get_db
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct,
    SpecialEquipmentProductAttachment,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentCartItem,
    SpecialEquipmentOrderItem,
    SpecialEquipmentPayment,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.models.storefronts import Storefront
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories import (
    special_equipment_commerce_repository as commerce_repository,
)
from presentation.routers import special_equipment_commerce as commerce_router_module
from presentation.routers.special_equipment_commerce import router
from tests.application_create_assertions import assert_create_idempotency
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


async def test_mixed_available_and_on_order_cart_group_creates_preorder(
    db_session: AsyncSession,
) -> None:
    seller = Company(name="Дилер смешанного предзаказа", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name="КамАЗ Mixed preorder",
        model_name="65115",
        modification_name="Шасси с надстройкой",
    )
    user = User(
        phone="+375291000229",
        email="special-mixed-preorder@example.test",
        name="Mixed preorder owner",
        role="client",
        is_active=True,
    )
    db_session.add_all([seller, mark, model, modification, user])
    await db_session.flush()
    parent_product = SpecialEquipmentProduct(
        code="mixed-preorder-parent",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="mixed-preorder-parent",
        condition="new",
        vin=None,
        no_vin=True,
        price=Decimal("100.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    attachment_product = SpecialEquipmentProduct(
        code="mixed-preorder-attachment",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="mixed-preorder-attachment",
        condition="new",
        vin=None,
        no_vin=True,
        price=Decimal("20.00"),
        publication_status="published",
        sale_status="on_order",
        published_at=datetime.now(UTC),
    )
    db_session.add_all([parent_product, attachment_product])
    await db_session.flush()
    db_session.add(
        SpecialEquipmentProductAttachment(
            product_id=parent_product.id,
            attachment_product_id=attachment_product.id,
            position=0,
        )
    )
    parent_cart_item = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=parent_product.id,
        quantity=1,
    )
    db_session.add(parent_cart_item)
    await db_session.flush()
    attachment_cart_item = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=attachment_product.id,
        parent_item_id=parent_cart_item.id,
        quantity=1,
    )
    db_session.add(attachment_cart_item)
    await db_session.flush()

    result = await create_order(
        CreateOrderCommand(
            user_id=user.id,
            purchase_type=SpecialEquipmentPurchaseType.PREORDER,
            idempotency_key="mixed-preorder-integration",
            payment_method="bank_transfer",
            down_payment_percent=Decimal("10.00"),
            cart_item_ids=(parent_cart_item.id, attachment_cart_item.id),
        ),
        db_session,
    )
    await db_session.flush()

    await db_session.refresh(parent_product)
    await db_session.refresh(attachment_product)
    assert result["order"]["status"] == "preordered"
    assert result["order"]["total_price"] == Decimal("120.00")
    assert parent_product.sale_status == "reserved"
    assert attachment_product.sale_status == "on_order"
    assert [item["item_role"] for item in result["order"]["items"]] == [
        "offer",
        "attachment",
    ]


async def test_delete_parent_cart_item_merges_detached_child_with_standalone(
    db_session: AsyncSession,
) -> None:
    seller = Company(name="Дилер удаления группы", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name="КамАЗ Cart detach",
        model_name="65115",
        modification_name="Самосвал",
    )
    user = User(
        phone="+375291000221",
        email="special-cart-detach@example.test",
        name="Cart detach owner",
        role="client",
        is_active=True,
    )
    db_session.add_all([seller, mark, model, modification, user])
    await db_session.flush()
    parent_product = SpecialEquipmentProduct(
        code="kamaz-cart-detach-parent",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="kamaz-cart-detach-parent",
        condition="new",
        vin=None,
        no_vin=True,
        price=Decimal("100.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    attachment_product = SpecialEquipmentProduct(
        code="kamaz-cart-detach-attachment",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="kamaz-cart-detach-attachment",
        condition="new",
        vin=None,
        no_vin=True,
        price=Decimal("20.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add_all([parent_product, attachment_product])
    await db_session.flush()
    parent = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=parent_product.id,
        quantity=1,
    )
    standalone = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=attachment_product.id,
        quantity=2,
        custom_price=Decimal("15.00"),
    )
    db_session.add_all([parent, standalone])
    await db_session.flush()
    child = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=attachment_product.id,
        parent_item_id=parent.id,
        quantity=3,
        custom_price=Decimal("15.00"),
    )
    db_session.add(child)
    await db_session.flush()

    updated_child = await commerce_repository.patch_cart_item(
        db_session,
        user_id=user.id,
        cart_item_id=child.id,
        changes={
            "comment": "Единая комплектация",
            "equipments": [{"code": "bucket"}],
            "services": [{"code": "delivery"}],
        },
    )
    await db_session.refresh(standalone)
    assert updated_child is not None
    assert standalone.comment == "Единая комплектация"
    assert standalone.equipments == [{"code": "bucket"}]
    assert standalone.services == [{"code": "delivery"}]

    deleted = await commerce_repository.delete_cart_item(
        db_session,
        user.id,
        parent.id,
    )
    await db_session.flush()

    rows = list(
        (
            await db_session.execute(
                sa.select(SpecialEquipmentCartItem).where(
                    SpecialEquipmentCartItem.user_id == user.id
                )
            )
        ).scalars()
    )
    assert deleted is True
    assert len(rows) == 1
    assert rows[0].id == standalone.id
    assert rows[0].parent_item_id is None
    assert rows[0].quantity == 5
    assert rows[0].custom_price == Decimal("15.00")
    assert rows[0].comment == "Единая комплектация"

    second_parent = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=parent_product.id,
        quantity=1,
    )
    db_session.add(second_parent)
    await db_session.flush()
    with pytest.raises(SpecialEquipmentCartConfigurationConflictError):
        await commerce_repository.put_cart_item(
            db_session,
            user_id=user.id,
            product_id=attachment_product.id,
            quantity=1,
            parent_item_id=second_parent.id,
            transfer_id=None,
            is_selected=True,
            comment="Другая комплектация",
            equipments=[],
            services=[],
        )
    conflicting_child = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=attachment_product.id,
        parent_item_id=second_parent.id,
        quantity=1,
        custom_price=Decimal("17.00"),
        comment="Индивидуальная комплектация",
        equipments=[{"code": "bucket"}],
        services=[{"code": "delivery"}],
    )
    db_session.add(conflicting_child)
    await db_session.flush()

    with pytest.raises(SpecialEquipmentCartConfigurationConflictError):
        await commerce_repository.delete_cart_item(
            db_session,
            user.id,
            second_parent.id,
        )


async def test_checkout_cleanup_merges_unselected_child_with_standalone(
    db_session: AsyncSession,
) -> None:
    seller = Company(name="Дилер checkout cleanup", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name="КамАЗ Checkout cleanup",
        model_name="65115",
        modification_name="Самосвал",
    )
    user = User(
        phone="+375291000230",
        email="special-checkout-cleanup@example.test",
        name="Checkout cleanup owner",
        role="client",
        is_active=True,
    )
    db_session.add_all([seller, mark, model, modification, user])
    await db_session.flush()
    parent_product = SpecialEquipmentProduct(
        code="checkout-cleanup-parent",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="checkout-cleanup-parent",
        condition="new",
        vin=None,
        no_vin=True,
        price=Decimal("100.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    attachment_product = SpecialEquipmentProduct(
        code="checkout-cleanup-attachment",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="checkout-cleanup-attachment",
        condition="new",
        vin=None,
        no_vin=True,
        price=Decimal("20.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add_all([parent_product, attachment_product])
    await db_session.flush()
    parent = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=parent_product.id,
        quantity=1,
        is_selected=True,
    )
    standalone = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=attachment_product.id,
        quantity=2,
        is_selected=False,
    )
    db_session.add_all([parent, standalone])
    await db_session.flush()
    child = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=attachment_product.id,
        parent_item_id=parent.id,
        quantity=3,
        is_selected=False,
    )
    db_session.add(child)
    await db_session.flush()

    deleted = await commerce_repository.delete_cart_items_by_ids(
        db_session,
        user_id=user.id,
        cart_item_ids=(parent.id,),
    )
    await db_session.flush()

    rows = list(
        (
            await db_session.execute(
                sa.select(SpecialEquipmentCartItem).where(
                    SpecialEquipmentCartItem.user_id == user.id
                )
            )
        ).scalars()
    )
    assert deleted == 1
    assert len(rows) == 1
    assert rows[0].id == standalone.id
    assert rows[0].parent_item_id is None
    assert rows[0].quantity == 5
    assert rows[0].is_selected is False


async def test_leasing_application_company_scope_and_employee_override(  # noqa: PLR0915
    db_session: AsyncSession,
) -> None:
    linked_company = Company(
        name="Компания клиента", company_type="other", inn="7707083893"
    )
    foreign_company = Company(name="Чужая компания", company_type="other")
    seller = Company(name="Дилер спецтехники", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name="Амкодор",
        model_name="352C",
        modification_name="Погрузчик",
    )
    user = User(
        phone="+375291000218",
        email="special-commerce-idor@example.test",
        name="Commerce client",
        role="client",
        is_active=True,
    )
    storefront = Storefront(
        slug=f"special-commerce-{uuid4()}",
        is_default=False,
        is_active=True,
        version=1,
    )
    db_session.add_all(
        [
            linked_company,
            foreign_company,
            seller,
            mark,
            model,
            modification,
            user,
            storefront,
        ]
    )
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=user.id,
            company_id=linked_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    product = SpecialEquipmentProduct(
        code="amkodor-352c-commerce-idor",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="amkodor-352c-commerce-idor",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("12500000.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()
    linked_cart_item = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=product.id,
        quantity=1,
    )
    db_session.add(linked_cart_item)
    await db_session.flush()

    actor: dict[str, Any] = {
        "id": user.id,
        "role": "client",
        "scopes": ["applications:write"],
    }
    app = FastAPI()
    app.include_router(
        router,
        prefix="/api/v1/special-equipment",
        tags=["special-equipment-commerce"],
    )
    app.include_router(
        router,
        prefix="/api/v1/storefronts/{storefront_slug}/special-equipment",
        tags=["storefront-special-equipment-commerce"],
    )

    async def _db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[
        commerce_router_module._applications_write
    ] = _actor_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.post(
            "/api/v1/special-equipment/leasing-applications",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "source_type": "platform",
                "company_id": str(foreign_company.id),
                "cart_item_ids": [str(linked_cart_item.id)],
            },
        )
        assert denied.status_code == 403
        assert denied.json()["detail"] == "Нет доступа к выбранной компании"

        linked = await client.post(
            "/api/v1/special-equipment/leasing-applications",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "source_type": "platform",
                "company_id": str(linked_company.id),
                "cart_item_ids": [str(linked_cart_item.id)],
            },
        )
        assert linked.status_code == 201
        assert linked.headers["location"].startswith("/api/v1/applications/")
        assert re.match(r"^7707083893-\d{6}-\d{3}$", linked.json()["display_number"])
        await assert_create_idempotency(client, linked, change_field="comment")

        override_cart_item = SpecialEquipmentCartItem(
            user_id=user.id,
            product_id=product.id,
            quantity=1,
        )
        db_session.add(override_cart_item)
        await db_session.flush()
        actor["role"] = "carcraft_employee"
        overridden = await client.post(
            "/api/v1/special-equipment/leasing-applications",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "source_type": "platform",
                "company_id": str(foreign_company.id),
                "cart_item_ids": [str(override_cart_item.id)],
            },
        )
        assert overridden.status_code == 201
        assert overridden.json()["display_number"] is None

        scoped_cart_item = SpecialEquipmentCartItem(
            user_id=user.id,
            product_id=product.id,
            quantity=1,
        )
        db_session.add(scoped_cart_item)
        await db_session.flush()
        actor["role"] = "client"
        scoped = await client.post(
            "/api/v1/storefronts/"
            f"{storefront.slug}/special-equipment/leasing-applications",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "source_type": "platform",
                "company_id": str(linked_company.id),
                "cart_item_ids": [str(scoped_cart_item.id)],
            },
        )
        assert scoped.status_code == 201

    scoped_application_id = scoped.json()["application_id"]
    scoped_storefront_id = await db_session.scalar(
        sa.select(LeasingApplication.storefront_id).where(
            LeasingApplication.id == scoped_application_id
        )
    )
    assert scoped_storefront_id == storefront.id

    item_count = await db_session.scalar(
        sa.select(sa.func.count(SpecialEquipmentApplicationItem.id))
    )
    assert item_count == 3


async def test_paid_order_refund_flow_is_transactional_and_idempotent(
    db_session: AsyncSession,
) -> None:
    seller = Company(name="Дилер возвратов спецтехники", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name="МТЗ Refund",
        model_name="82.1",
        modification_name="Трактор",
    )
    owner = User(
        phone="+375291000219",
        email="special-refund-owner@example.test",
        name="Refund owner",
        role="client",
        is_active=True,
    )
    employee = User(
        phone="+375291000220",
        email="special-refund-employee@example.test",
        name="Refund employee",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add_all([seller, mark, model, modification, owner, employee])
    await db_session.flush()
    product = SpecialEquipmentProduct(
        code="mtz-82-refund-integration",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug="mtz-82-refund-integration",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("100.00"),
        publication_status="published",
        sale_status="reserved",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()
    order = SpecialEquipmentPurchaseOrder(
        user_id=owner.id,
        product_id=product.id,
        seller_company_id=seller.id,
        purchase_type="reservation",
        status="reserved",
        unit_price=Decimal("100.00"),
        total_price=Decimal("100.00"),
        paid_amount=Decimal("20.00"),
        remaining_amount=Decimal("80.00"),
        currency_code="RUB",
        down_payment_percent=Decimal("20.00"),
        item_snapshot={
            "mark": "МТЗ Refund",
            "model": "82.1",
            "modification": "Трактор",
        },
        idempotency_key="refund-integration-order",
        request_hash="0" * 64,
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add(
        SpecialEquipmentOrderItem(
            purchase_order_id=order.id,
            product_id=product.id,
            group_id=uuid4(),
            item_role="offer",
            position=0,
            unit_price=Decimal("100.00"),
            item_snapshot=dict(order.item_snapshot),
        )
    )
    payment = SpecialEquipmentPayment(
        purchase_order_id=order.id,
        user_id=owner.id,
        payment_type="reservation",
        amount=Decimal("20.00"),
        status="completed",
        payment_method="card",
        gateway_transaction_id=f"CARCRAFT-SE-{order.id}",
        idempotency_key="refund-integration-payment",
        request_hash="1" * 64,
        paid_at=datetime.now(UTC),
    )
    db_session.add(payment)
    await db_session.flush()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/special-equipment")

    async def _db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _owner_override() -> dict[str, Any]:
        return {
            "id": owner.id,
            "role": "client",
            "scopes": ["purchases:write"],
        }

    async def _employee_override() -> dict[str, Any]:
        return {
            "id": employee.id,
            "role": "carcraft_employee",
            "scopes": ["purchases:admin"],
        }

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[commerce_router_module._purchases_write] = (
        _owner_override
    )
    app.dependency_overrides[commerce_router_module._purchases_admin] = (
        _employee_override
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        requested = await client.put(
            f"/api/v1/special-equipment/purchase-orders/{order.id}/cancellation",
            json={"reason": "Возврат согласован"},
        )
        assert requested.status_code == 200
        assert requested.json()["order"]["status"] == "cancellation_requested"
        await db_session.refresh(product)
        assert product.sale_status == "reserved"

        confirmed = await client.put(
            f"/api/v1/special-equipment/purchase-orders/{order.id}/refund-confirmation",
            json={"external_reference": "provider-refund-21808"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["replayed"] is False
        assert confirmed.json()["refunded_amount"] == "20.00"
        assert "provider-refund-21808" not in confirmed.text

        replayed = await client.put(
            f"/api/v1/special-equipment/purchase-orders/{order.id}/refund-confirmation",
            json={"external_reference": "provider-refund-21808"},
        )
        assert replayed.status_code == 200
        assert replayed.json()["replayed"] is True

        mismatch = await client.put(
            f"/api/v1/special-equipment/purchase-orders/{order.id}/refund-confirmation",
            json={"external_reference": "different-provider-reference"},
        )
        assert mismatch.status_code == 409

    await db_session.refresh(order)
    await db_session.refresh(payment)
    await db_session.refresh(product)
    assert (order.status, order.paid_amount, order.remaining_amount) == (
        "cancelled",
        Decimal("0.00"),
        Decimal("100.00"),
    )
    assert order.refund_external_reference == "provider-refund-21808"
    assert order.refund_confirmed_by == employee.id
    assert payment.status == "refunded"
    assert payment.refunded_at is not None
    assert product.sale_status == "available"
