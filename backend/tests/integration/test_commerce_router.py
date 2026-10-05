"""PostgreSQL-backed proof that the facade keeps special equipment FK-safe."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from application.special_equipment_commerce import (
    ConfirmOfflinePaymentCommand,
    ConfirmOrderRefundCommand,
    confirm_offline_payment,
    confirm_order_refund,
)
from domain.commerce import VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE
from infrastructure.database import get_db
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingApplicationCalculation,
)
from infrastructure.models.companies import Company
from infrastructure.models.payments import (
    LeasingPaymentSchedule,
    Payment,
    PurchaseOrder,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentCartItem,
    SpecialEquipmentOrderItem,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse
from infrastructure.services import payment_gateway
from infrastructure.services.payment_models import ModulbankWebhookPayload
from presentation.dependencies.auth import get_current_user
from presentation.routers import applications as applications_router_module
from presentation.routers import commerce as commerce_router_module
from presentation.routers.applications import router as applications_router
from presentation.routers.commerce import router
from tests.application_create_assertions import assert_create_idempotency
from tests.legacy_compat import Vehicle
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


async def test_special_order_uses_unified_api_but_not_vehicle_tables(  # noqa: PLR0915
    db_session: AsyncSession,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="Амкодор",
        model_name="352C",
        modification_name="Погрузчик",
    )
    user = User(
        phone=f"+37529{str(uuid4().int)[-7:]}",
        email=f"commerce-{uuid4()}@example.test",
        name="Commerce client",
        role="client",
        is_active=True,
    )
    other_user = User(
        phone=f"+37533{str(uuid4().int)[-7:]}",
        email=f"commerce-other-{uuid4()}@example.test",
        name="Other commerce client",
        role="client",
        is_active=True,
    )
    seller = Company(name="Дилер спецтехники", company_type="dealer")
    db_session.add_all([mark, model, modification, user, other_user, seller])
    await db_session.flush()
    product = SpecialEquipmentProduct(
        code=f"amkodor-352c-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug=f"amkodor-352c-{uuid4()}",
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
    cart_item = SpecialEquipmentCartItem(
        user_id=user.id,
        product_id=product.id,
        quantity=1,
    )
    db_session.add(cart_item)
    await db_session.flush()

    actor: dict[str, Any] = {
        "id": user.id,
        "role": "client",
        "company_id": None,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    for dependency in (
        commerce_router_module._read,
        commerce_router_module._item_read,
        commerce_router_module._write,
        commerce_router_module._self_pay,
    ):
        app.dependency_overrides[dependency] = actor_override

    idempotency_key = f"unified-{uuid4()}"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        item = await client.get(
            f"/api/v1/commerce/items/special_equipment/{product.id}"
        )
        assert item.status_code == 200
        assert item.json()["item"]["ref"] == {
            "type": "special_equipment",
            "id": str(product.id),
        }

        body = {
            "item": {"type": "special_equipment", "id": str(product.id)},
            "purchase_type": "full_purchase",
            "payment_method": "bank_transfer",
            "cart_item_ids": [str(cart_item.id)],
        }
        created = await client.post(
            "/api/v1/commerce/orders",
            headers={"Idempotency-Key": idempotency_key},
            json=body,
        )
        assert created.status_code == 201
        created_body = created.json()
        order_id = created_body["orders"][0]["id"]
        payment_id = created_body["payments"][0]["id"]
        assert created_body["orders"][0]["item"]["type"] == "special_equipment"
        assert created_body["orders"][0]["status"] == "payment_pending"
        assert created_body["payments"][0]["amount"] == "12500000.00"
        assert created_body["payments"][0]["status"] == "processing"
        assert created_body["payments"][0]["order"] == {
            "type": "special_equipment",
            "id": order_id,
        }

        replay = await client.post(
            "/api/v1/commerce/orders",
            headers={"Idempotency-Key": idempotency_key},
            json=body,
        )
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        assert replay.json()["orders"][0]["id"] == order_id

        listed = await client.get("/api/v1/commerce/orders")
        assert listed.status_code == 200
        assert [(row["item"]["type"], row["id"]) for row in listed.json()["items"]] == [
            ("special_equipment", order_id)
        ]

        actor["id"] = other_user.id
        foreign_detail = await client.get(
            f"/api/v1/commerce/orders/special_equipment/{order_id}"
        )
        foreign_payments = await client.get(
            f"/api/v1/commerce/orders/special_equipment/{order_id}/payments"
        )
        foreign_status = await client.get(
            f"/api/v1/commerce/orders/special_equipment/{order_id}/payments/"
            f"{payment_id}/status"
        )
        foreign_cancel = await client.put(
            f"/api/v1/commerce/orders/special_equipment/{order_id}/cancellation",
            json={"reason": "IDOR"},
        )
        assert {
            foreign_detail.status_code,
            foreign_payments.status_code,
            foreign_status.status_code,
            foreign_cancel.status_code,
        } == {403}

        actor["id"] = user.id
        wrong_domain = await client.get(f"/api/v1/commerce/orders/vehicle/{order_id}")
        assert wrong_domain.status_code == 404

        await confirm_offline_payment(
            ConfirmOfflinePaymentCommand(
                actor_role="carcraft_employee",
                order_id=UUID(order_id),
                payment_id=UUID(payment_id),
            ),
            db_session,
        )
        await db_session.refresh(product)
        assert product.sale_status == "sold"

        cancelled = await client.put(
            f"/api/v1/commerce/orders/special_equipment/{order_id}/cancellation",
            json={"reason": "Проверка единого flow"},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["order"]["status"] == "cancellation_requested"

        await confirm_order_refund(
            ConfirmOrderRefundCommand(
                actor_id=user.id,
                actor_role="carcraft_employee",
                order_id=UUID(order_id),
                external_reference=f"refund-{order_id}",
            ),
            db_session,
        )

    order_items = list(
        await db_session.scalars(
            sa.select(SpecialEquipmentOrderItem)
            .where(SpecialEquipmentOrderItem.purchase_order_id == UUID(order_id))
            .order_by(SpecialEquipmentOrderItem.position)
        )
    )
    assert [item.item_role for item in order_items] == ["offer"]
    await db_session.refresh(product)
    assert product.sale_status == "available"

    special_count = await db_session.scalar(
        sa.select(sa.func.count()).select_from(SpecialEquipmentPurchaseOrder)
    )
    vehicle_count = await db_session.scalar(
        sa.select(sa.func.count()).select_from(PurchaseOrder)
    )
    assert special_count == 1
    assert vehicle_count == 0


async def test_vehicle_unified_api_rejects_batch_and_legacy_offline_payment(
    db_session: AsyncSession,
    test_vehicle: Any,
) -> None:
    user = User(
        phone=f"+37544{str(uuid4().int)[-7:]}",
        email=f"vehicle-commerce-{uuid4()}@example.test",
        name="Vehicle commerce client",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    actor: dict[str, Any] = {
        "id": user.id,
        "role": "client",
        "company_id": None,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[commerce_router_module._write] = actor_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        batch = await client.post(
            "/api/v1/commerce/orders",
            headers={"Idempotency-Key": f"vehicle-{uuid4()}"},
            json={
                "item": {"type": "vehicle", "id": str(test_vehicle.id)},
                "quantity": 2,
                "purchase_type": "reservation",
                "payment_method": "card",
                "down_payment_percent": "10.00",
            },
        )
        offline = await client.post(
            "/api/v1/commerce/orders",
            headers={"Idempotency-Key": f"vehicle-{uuid4()}"},
            json={
                "item": {"type": "vehicle", "id": str(test_vehicle.id)},
                "purchase_type": "reservation",
                "payment_method": "bank_transfer",
                "down_payment_percent": "10.00",
            },
        )

    assert batch.status_code == 422
    assert "Пакетное оформление" in batch.text
    assert offline.status_code == 422
    assert "Безналичный перевод" in offline.text
    vehicle_count = await db_session.scalar(
        sa.select(sa.func.count()).select_from(PurchaseOrder)
    )
    special_count = await db_session.scalar(
        sa.select(sa.func.count()).select_from(SpecialEquipmentPurchaseOrder)
    )
    assert vehicle_count == 0
    assert special_count == 0


async def test_vehicle_unified_order_replays_durable_idempotency_receipt(
    db_session: AsyncSession,
    test_vehicle: Vehicle,
) -> None:
    user = User(
        phone=f"+37544{str(uuid4().int)[-7:]}",
        email=f"vehicle-replay-{uuid4()}@example.test",
        name="Vehicle replay client",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    actor: dict[str, Any] = {
        "id": user.id,
        "role": "client",
        "company_id": None,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[commerce_router_module._write] = actor_override

    idempotency_key = f"vehicle-replay-{uuid4()}"
    body = {
        "item": {"type": "vehicle", "id": str(test_vehicle.id)},
        "purchase_type": "reservation",
        "payment_method": "card",
        "down_payment_percent": "10.00",
    }
    widget = {
        "formUrl": "https://pay.modulbank.ru/pay",
        "formParams": {"merchant": "idempotency-test"},
        "orderId": "CARCRAFT-IDEMPOTENCY-TEST",
        "amount": "200000.00",
        "expiresAt": "2099-01-01T00:00:00+00:00",
    }

    with patch(
        "application.commands.purchases.payment_gateway.prepare_payment",
        new_callable=AsyncMock,
        return_value=widget,
    ) as prepare_payment:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/api/v1/commerce/orders",
                headers={"Idempotency-Key": idempotency_key},
                json=body,
            )
            replay = await client.post(
                "/api/v1/commerce/orders",
                headers={"Idempotency-Key": idempotency_key},
                json=body,
            )
            conflict = await client.post(
                "/api/v1/commerce/orders",
                headers={"Idempotency-Key": idempotency_key},
                json={**body, "down_payment_percent": "15.00"},
            )

    assert created.status_code == 201
    assert replay.status_code == 200
    assert conflict.status_code == 409
    assert "Idempotency-Key" in conflict.text
    assert prepare_payment.await_count == 1

    created_body = created.json()
    replay_body = replay.json()
    order_id = created_body["orders"][0]["id"]
    payment_id = created_body["payments"][0]["id"]
    assert created_body["replayed"] is False
    assert replay_body["replayed"] is True
    assert replay_body["orders"][0]["id"] == order_id
    assert replay_body["payments"][0]["id"] == payment_id
    assert replay_body["widgetData"] == created_body["widgetData"]

    reserved_namespace = VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE
    assert reserved_namespace not in created.text
    assert reserved_namespace not in replay.text
    payment = await db_session.get(Payment, UUID(payment_id))
    assert payment is not None
    assert payment.gateway_response is not None
    receipt = payment.gateway_response[reserved_namespace]
    assert receipt["key"] == idempotency_key
    assert receipt["operation"] == "initial"
    assert receipt["request_hash"]
    assert receipt["handoff"]["widgetData"] == widget

    order_count = await db_session.scalar(
        sa.select(sa.func.count()).select_from(PurchaseOrder)
    )
    payment_count = await db_session.scalar(
        sa.select(sa.func.count()).select_from(Payment)
    )
    assert order_count == 1
    assert payment_count == 1


async def test_vehicle_cancellation_invalidates_pending_checkout_before_late_callback(
    db_session: AsyncSession,
    test_vehicle: Vehicle,
) -> None:
    user = User(
        phone=f"+37544{str(uuid4().int)[-7:]}",
        email=f"vehicle-cancel-race-{uuid4()}@example.test",
        name="Vehicle cancellation client",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    actor: dict[str, Any] = {
        "id": user.id,
        "role": "client",
        "company_id": None,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[commerce_router_module._write] = actor_override
    app.dependency_overrides[commerce_router_module._self_pay] = actor_override

    idempotency_key = f"vehicle-cancel-race-{uuid4()}"
    body = {
        "item": {"type": "vehicle", "id": str(test_vehicle.id)},
        "purchase_type": "full_purchase",
        "payment_method": "card",
    }
    widget = {
        "formUrl": "https://pay.modulbank.ru/pay",
        "formParams": {"merchant": "cancel-race-test"},
        "orderId": "CARCRAFT-CANCEL-RACE",
        "amount": "2000000.00",
        "expiresAt": "2099-01-01T00:00:00+00:00",
    }

    with patch(
        "application.commands.purchases.payment_gateway.prepare_payment",
        new_callable=AsyncMock,
        return_value=widget,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/api/v1/commerce/orders",
                headers={"Idempotency-Key": idempotency_key},
                json=body,
            )
            assert created.status_code == 201
            order_id = UUID(created.json()["orders"][0]["id"])
            payment_id = UUID(created.json()["payments"][0]["id"])

            cancelled = await client.put(
                f"/api/v1/commerce/orders/vehicle/{order_id}/cancellation",
                json={"reason": "Отмена до завершения оплаты"},
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["order"]["status"] == "cancellation_requested"

            replay = await client.post(
                "/api/v1/commerce/orders",
                headers={"Idempotency-Key": idempotency_key},
                json=body,
            )
            assert replay.status_code == 200
            assert replay.json()["replayed"] is True
            assert replay.json()["widgetData"] is None
            assert replay.json()["payments"][0]["status"] == "failed"

    payment = await db_session.get(Payment, payment_id)
    assert payment is not None
    await db_session.refresh(payment)
    assert payment.status == "failed"
    assert payment.gateway_response is not None
    receipt = payment.gateway_response[VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE]
    assert receipt["key"] == idempotency_key

    with (
        patch.object(payment_gateway, "verify_modulbank_signature", return_value=True),
        patch.object(payment_gateway.settings, "webhook_replay_enabled", False),
    ):
        (
            callback_result,
            fiscalization_ids,
        ) = await payment_gateway.handle_payment_callback(
            ModulbankWebhookPayload(
                order_id=payment.gateway_transaction_id,
                status="success",
                signature="valid-late-success",
            ),
            db_session,
        )

    assert callback_result == {"processed": False}
    assert fiscalization_ids == []
    order = await db_session.get(PurchaseOrder, order_id)
    assert order is not None
    await db_session.refresh(order)
    await db_session.refresh(payment)
    assert order.status == "cancellation_requested"
    assert payment.status == "failed"
    assert payment.gateway_response[VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE] == receipt


async def test_vehicle_idempotency_key_is_owner_scoped(
    db_session: AsyncSession,
    test_vehicle: Vehicle,
) -> None:
    first_user = User(
        phone=f"+37544{str(uuid4().int)[-7:]}",
        email=f"vehicle-owner-a-{uuid4()}@example.test",
        name="Vehicle owner A",
        role="client",
        is_active=True,
    )
    second_user = User(
        phone=f"+37544{str(uuid4().int)[-7:]}",
        email=f"vehicle-owner-b-{uuid4()}@example.test",
        name="Vehicle owner B",
        role="client",
        is_active=True,
    )
    second_vehicle = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("2500000.00"),
    )
    db_session.add_all([first_user, second_user, second_vehicle])
    await db_session.flush()
    actor: dict[str, Any] = {
        "id": first_user.id,
        "role": "client",
        "company_id": None,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[commerce_router_module._write] = actor_override

    idempotency_key = f"vehicle-owner-scope-{uuid4()}"
    widget = {
        "formUrl": "https://pay.modulbank.ru/pay",
        "formParams": {"merchant": "owner-scope-test"},
        "orderId": "CARCRAFT-OWNER-SCOPE-TEST",
        "amount": "200000.00",
        "expiresAt": "2099-01-01T00:00:00+00:00",
    }
    with patch(
        "application.commands.purchases.payment_gateway.prepare_payment",
        new_callable=AsyncMock,
        return_value=widget,
    ) as prepare_payment:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post(
                "/api/v1/commerce/orders",
                headers={"Idempotency-Key": idempotency_key},
                json={
                    "item": {"type": "vehicle", "id": str(test_vehicle.id)},
                    "purchase_type": "reservation",
                    "payment_method": "card",
                    "down_payment_percent": "10.00",
                },
            )
            actor["id"] = second_user.id
            second = await client.post(
                "/api/v1/commerce/orders",
                headers={"Idempotency-Key": idempotency_key},
                json={
                    "item": {"type": "vehicle", "id": str(second_vehicle.id)},
                    "purchase_type": "reservation",
                    "payment_method": "card",
                    "down_payment_percent": "10.00",
                },
            )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["orders"][0]["id"] != second.json()["orders"][0]["id"]
    assert prepare_payment.await_count == 2
    owner_ids = set(await db_session.scalars(sa.select(PurchaseOrder.user_id)))
    assert owner_ids == {first_user.id, second_user.id}


async def test_vehicle_remaining_payment_replays_without_new_gateway_attempt(  # noqa: PLR0915
    db_session: AsyncSession,
    test_vehicle: Vehicle,
) -> None:
    user = User(
        phone=f"+37544{str(uuid4().int)[-7:]}",
        email=f"vehicle-remaining-replay-{uuid4()}@example.test",
        name="Vehicle remaining replay client",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    order = PurchaseOrder(
        user_id=user.id,
        vehicle_id=test_vehicle.id,
        purchase_type="reservation",
        status="reserved",
        total_price=Decimal("2000000.00"),
        paid_amount=Decimal("200000.00"),
        remaining_amount=Decimal("1800000.00"),
    )
    db_session.add(order)
    await db_session.flush()

    actor: dict[str, Any] = {
        "id": user.id,
        "role": "client",
        "company_id": None,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[commerce_router_module._self_pay] = actor_override

    idempotency_key = f"vehicle-remaining-{uuid4()}"
    body = {"scope": "remaining", "payment_method": "card"}
    widget = {
        "formUrl": "https://pay.modulbank.ru/pay",
        "formParams": {"merchant": "remaining-idempotency-test"},
        "orderId": "CARCRAFT-REMAINING-IDEMPOTENCY-TEST",
        "amount": "1800000.00",
        "expiresAt": "2099-01-01T00:00:00+00:00",
    }

    with patch(
        "application.commands.purchases.payment_gateway.prepare_payment",
        new_callable=AsyncMock,
        return_value=widget,
    ) as prepare_payment:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                f"/api/v1/commerce/orders/vehicle/{order.id}/payments",
                headers={"Idempotency-Key": idempotency_key},
                json=body,
            )
            replay = await client.post(
                f"/api/v1/commerce/orders/vehicle/{order.id}/payments",
                headers={"Idempotency-Key": idempotency_key},
                json=body,
            )

            assert created.status_code == 201
            assert replay.status_code == 200
            created_body = created.json()
            replay_body = replay.json()
            payment_id = created_body["payment"]["id"]
            assert replay_body["replayed"] is True
            assert replay_body["order"]["id"] == created_body["order"]["id"]
            assert replay_body["payment"]["id"] == payment_id
            assert replay_body["widgetData"] == created_body["widgetData"]
            assert VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE not in created.text
            assert VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE not in replay.text

            payment = await db_session.get(Payment, UUID(payment_id))
            assert payment is not None
            assert payment.gateway_response is not None
            receipt = payment.gateway_response[VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE]
            assert receipt["key"] == idempotency_key
            assert receipt["operation"] == "remaining"
            assert receipt["handoff"]["widgetData"] == widget

            payment.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db_session.flush()
            expired_replay = await client.post(
                f"/api/v1/commerce/orders/vehicle/{order.id}/payments",
                headers={"Idempotency-Key": idempotency_key},
                json=body,
            )

    assert expired_replay.status_code == 200
    expired_body = expired_replay.json()
    assert expired_body["replayed"] is True
    assert expired_body["payment"]["id"] == payment_id
    assert expired_body["widgetData"] is None
    assert expired_body["sbpData"] is None
    assert prepare_payment.await_count == 1
    payment_count = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(Payment)
        .where(Payment.purchase_order_id == order.id)
    )
    assert payment_count == 1


async def test_vehicle_scheduled_payment_replays_and_keeps_schedule_link(
    db_session: AsyncSession,
    test_vehicle: Vehicle,
) -> None:
    user = User(
        phone=f"+37544{str(uuid4().int)[-7:]}",
        email=f"vehicle-scheduled-replay-{uuid4()}@example.test",
        name="Vehicle scheduled replay client",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    order = PurchaseOrder(
        user_id=user.id,
        vehicle_id=test_vehicle.id,
        purchase_type="reservation",
        status="leasing_active",
        total_price=Decimal("2000000.00"),
        paid_amount=Decimal("200000.00"),
        remaining_amount=Decimal("1800000.00"),
    )
    db_session.add(order)
    await db_session.flush()
    schedule = LeasingPaymentSchedule(
        purchase_order_id=order.id,
        payment_number=1,
        due_date=date(2026, 8, 1),
        amount=Decimal("600000.00"),
        principal=Decimal("550000.00"),
        interest=Decimal("50000.00"),
        is_paid=False,
    )
    db_session.add(schedule)
    await db_session.flush()

    actor: dict[str, Any] = {
        "id": user.id,
        "role": "client",
        "company_id": None,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[commerce_router_module._self_pay] = actor_override

    idempotency_key = f"vehicle-scheduled-{uuid4()}"
    body = {
        "scope": "scheduled",
        "schedule_id": str(schedule.id),
        "payment_method": "card",
    }
    widget = {
        "formUrl": "https://pay.modulbank.ru/pay",
        "formParams": {"merchant": "scheduled-idempotency-test"},
        "orderId": "CARCRAFT-SCHEDULED-IDEMPOTENCY-TEST",
        "amount": "600000.00",
        "expiresAt": "2099-01-01T00:00:00+00:00",
    }

    with patch(
        "application.commands.purchases.payment_gateway.prepare_payment",
        new_callable=AsyncMock,
        return_value=widget,
    ) as prepare_payment:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                f"/api/v1/commerce/orders/vehicle/{order.id}/payments",
                headers={"Idempotency-Key": idempotency_key},
                json=body,
            )
            replay = await client.post(
                f"/api/v1/commerce/orders/vehicle/{order.id}/payments",
                headers={"Idempotency-Key": idempotency_key},
                json=body,
            )

    assert created.status_code == 201
    assert replay.status_code == 200
    created_body = created.json()
    replay_body = replay.json()
    payment_id = created_body["payment"]["id"]
    assert replay_body["replayed"] is True
    assert replay_body["order"]["id"] == created_body["order"]["id"]
    assert replay_body["payment"]["id"] == payment_id
    assert replay_body["schedule_item"]["id"] == created_body["schedule_item"]["id"]
    assert created_body["schedule_item"]["payment_id"] == payment_id
    assert replay_body["schedule_item"]["payment_id"] == payment_id
    assert replay_body["widgetData"] == created_body["widgetData"]
    assert prepare_payment.await_count == 1

    await db_session.refresh(schedule)
    assert schedule.payment_id == UUID(payment_id)
    assert schedule.is_paid is False
    payment = await db_session.get(Payment, UUID(payment_id))
    assert payment is not None
    assert payment.gateway_response is not None
    assert payment.gateway_response["schedule_id"] == str(schedule.id)
    receipt = payment.gateway_response[VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE]
    assert receipt["operation"] == "scheduled"
    assert receipt["schedule_id"] == str(schedule.id)
    assert receipt["handoff"]["widgetData"] == widget
    payment_count = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(Payment)
        .where(Payment.purchase_order_id == order.id)
    )
    assert payment_count == 1


async def test_special_leasing_application_bridges_to_common_application_read_model(  # noqa: PLR0915
    db_session: AsyncSession,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="Ростсельмаш",
        model_name="RSM 161",
        modification_name="Комбайн",
    )
    actor_user = User(
        phone=f"+37525{str(uuid4().int)[-7:]}",
        email=f"employee-commerce-{uuid4()}@example.test",
        name="Commerce employee",
        role="carcraft_employee",
        is_active=True,
    )
    applicant_company = Company(name="Лизингополучатель", company_type="other")
    seller = Company(name="Дилер Ростсельмаш", company_type="dealer")
    db_session.add_all(
        [mark, model, modification, actor_user, applicant_company, seller]
    )
    await db_session.flush()
    product = SpecialEquipmentProduct(
        code=f"rostselmash-rsm-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug=f"rostselmash-rsm-{uuid4()}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("28500000.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()
    cart_item = SpecialEquipmentCartItem(
        user_id=actor_user.id,
        product_id=product.id,
        quantity=1,
    )
    db_session.add(cart_item)
    await db_session.flush()

    actor: dict[str, Any] = {
        "id": actor_user.id,
        "role": "carcraft_employee",
        "company_id": None,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")
    app.include_router(applications_router, prefix="/api/v1/applications")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[commerce_router_module._applications_write] = (
        actor_override
    )
    app.dependency_overrides[applications_router_module._read_access] = actor_override
    app.dependency_overrides[get_current_user] = actor_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/commerce/leasing-applications",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "items": [
                    {
                        "item": {
                            "type": "special_equipment",
                            "id": str(product.id),
                        },
                        "leasing_purpose": "other",
                        "leasing_purpose_comment": (
                            "  Для сельскохозяйственных работ  "
                        ),
                        "regions": ["Минская область"],
                        "cart_item_ids": [str(cart_item.id)],
                    }
                ],
                "company_id": str(applicant_company.id),
                "down_payment_percent": "20.00",
                "lease_term_months": 36,
            },
        )
        assert created.status_code == 201
        application_id = created.json()["application_id"]
        assert created.json()["items"][0]["item"] == {
            "type": "special_equipment",
            "id": str(product.id),
        }
        await assert_create_idempotency(client, created, change_field="name")

        detail = await client.get(f"/api/v1/applications/{application_id}")
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["vehicles"] == []
        assert len(detail_body["items"]) == 1
        assert detail_body["items"][0]["type"] == "special_equipment"
        assert detail_body["items"][0]["item_id"] == str(product.id)
        assert isinstance(detail_body["items"][0]["unit_price"], str)
        assert isinstance(detail_body["items"][0]["total_price"], str)
        assert detail_body["items_count"] == 1
        assert isinstance(detail_body["total_items_price"], str)
        assert isinstance(detail_body["total_amount"], int | float)
        assert Decimal(str(detail_body["total_items_price"])) == Decimal("28500000.00")

        listed = await client.get("/api/v1/applications")
        assert listed.status_code == 200
        listed_application = next(
            row for row in listed.json()["applications"] if row["id"] == application_id
        )
        assert isinstance(listed_application["items"][0]["unit_price"], str)
        assert isinstance(listed_application["items"][0]["total_price"], str)
        assert isinstance(listed_application["total_items_price"], str)
        assert isinstance(listed_application["total_amount"], int | float)

    application_uuid = UUID(application_id)
    assert await db_session.get(LeasingApplication, application_uuid) is not None
    special_lines = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(SpecialEquipmentApplicationItem)
        .where(SpecialEquipmentApplicationItem.application_id == application_uuid)
    )
    vehicle_lines = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ApplicationVehicle)
        .where(ApplicationVehicle.application_id == application_uuid)
    )
    assert special_lines == 1
    assert vehicle_lines == 0
    special_line = await db_session.scalar(
        sa.select(SpecialEquipmentApplicationItem).where(
            SpecialEquipmentApplicationItem.application_id == application_uuid
        )
    )
    assert special_line is not None
    assert special_line.leasing_purpose == "Для сельскохозяйственных работ"


async def test_dealer_special_application_binds_payload_client_and_product_seller(  # noqa: PLR0915
    db_session: AsyncSession,
) -> None:
    dealer_company = Company(
        name="Дилер для unified commerce",
        company_type="dealer",
    )
    mark, model, modification = special_equipment_directory(
        mark_name="МТЗ",
        model_name="82.1",
        modification_name="Трактор",
    )
    dealer_user = User(
        phone=f"+37529{str(uuid4().int)[-7:]}",
        email=f"dealer-commerce-{uuid4()}@example.test",
        name="Dealer commerce user",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    dealer_viewer = User(
        phone=f"+37544{str(uuid4().int)[-7:]}",
        email=f"dealer-viewer-{uuid4()}@example.test",
        name="Dealer application viewer",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    foreign_company = Company(
        name="Посторонний дилер unified commerce",
        company_type="dealer",
    )
    foreign_viewer = User(
        phone=f"+37533{str(uuid4().int)[-7:]}",
        email=f"foreign-viewer-{uuid4()}@example.test",
        name="Foreign dealer application viewer",
        role="dealer",
        is_active=True,
        company_id=foreign_company.id,
    )
    warehouse = Warehouse(
        address="Склад дилера unified commerce",
        brand="UNIFIED-DEALER",
        company_id=dealer_company.id,
        status="active",
    )
    db_session.add_all(
        [
            dealer_company,
            foreign_company,
            mark,
            model,
            modification,
            warehouse,
        ]
    )
    await db_session.flush()
    dealer_user.company_id = dealer_company.id
    warehouse.company_id = dealer_company.id
    db_session.add_all([dealer_user, dealer_viewer, foreign_viewer])
    await db_session.flush()
    db_session.add_all(
        [
            UserCompany(
                user_id=dealer_viewer.id,
                company_id=dealer_company.id,
                can_view_applications=True,
            ),
            UserCompany(
                user_id=foreign_viewer.id,
                company_id=foreign_company.id,
                can_view_applications=True,
            ),
        ]
    )
    await db_session.flush()
    product = SpecialEquipmentProduct(
        code=f"mtz-82-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=dealer_company.id,
        warehouse_id=warehouse.id,
        slug=f"mtz-82-{uuid4()}",
        condition="new",
        vin=f"MTZ{str(uuid4().int)[-12:]}",
        no_vin=False,
        owners_count=None,
        price=Decimal("5100000.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()
    cart_item = SpecialEquipmentCartItem(
        user_id=dealer_user.id,
        product_id=product.id,
        quantity=1,
    )
    db_session.add(cart_item)
    await db_session.flush()

    actor: dict[str, Any] = {
        "id": dealer_user.id,
        "role": "dealer",
        "company_id": dealer_company.id,
        "scopes": ["applications:write"],
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")
    app.include_router(applications_router, prefix="/api/v1/applications")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = actor_override
    app.dependency_overrides[commerce_router_module._applications_write] = (
        actor_override
    )
    app.dependency_overrides[applications_router_module._read_access] = actor_override

    client_inn = str(uuid4().int)[-10:]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        item = await client.get(
            f"/api/v1/commerce/items/special_equipment/{product.id}"
        )
        assert item.status_code == 200
        assert item.json()["item"]["ref"] == {
            "type": "special_equipment",
            "id": str(product.id),
        }

        actor["scopes"] = ["applications:read"]
        forbidden_item = await client.get(
            f"/api/v1/commerce/items/special_equipment/{product.id}"
        )
        assert forbidden_item.status_code == 403
        actor["scopes"] = ["applications:write"]

        created = await client.post(
            "/api/v1/commerce/leasing-applications",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "items": [
                    {
                        "item": {
                            "type": "special_equipment",
                            "id": str(product.id),
                        },
                        "cart_item_ids": [str(cart_item.id)],
                    }
                ],
                # This is the dealer's currently selected company. As in the
                # vehicle flow, the client payload below is the applicant.
                "company_id": str(dealer_company.id),
                "company": {
                    "name": "ООО Клиент спецтехники",
                    "full_name": "Общество с ограниченной ответственностью Клиент",
                    "inn": client_inn,
                    "kpp": "770101001",
                    "ogrn": "1027700000001",
                    "legal_address": "Москва, ул. Тестовая, 1",
                    "entity_type": "LEGAL",
                },
                "down_payment_percent": "15.00",
                "lease_term_months": 24,
            },
        )

        assert created.status_code == 201
        application_id = created.json()["application_id"]
        actor.update(
            {
                "id": dealer_viewer.id,
                "company_id": dealer_company.id,
                "scopes": ["applications:read"],
            }
        )
        dealer_list = await client.get("/api/v1/applications")
        dealer_detail = await client.get(
            f"/api/v1/applications/{application_id}"
        )
        assert dealer_list.status_code == 200
        assert application_id in {
            row["id"] for row in dealer_list.json()["applications"]
        }
        assert dealer_detail.status_code == 200

        actor.update(
            {
                "id": foreign_viewer.id,
                "company_id": foreign_company.id,
                "scopes": ["applications:read"],
            }
        )
        foreign_list = await client.get("/api/v1/applications")
        foreign_detail = await client.get(
            f"/api/v1/applications/{application_id}"
        )
        assert foreign_list.status_code == 200
        assert application_id not in {
            row["id"] for row in foreign_list.json()["applications"]
        }
        assert foreign_detail.status_code == 403

    application_id = UUID(application_id)
    application = await db_session.get(LeasingApplication, application_id)
    assert application is not None
    assert application.company_id != dealer_company.id
    assert application.dealer_company_id == dealer_company.id
    client_company = await db_session.get(Company, application.company_id)
    assert client_company is not None
    assert client_company.inn == client_inn
    item = await db_session.scalar(
        sa.select(SpecialEquipmentApplicationItem).where(
            SpecialEquipmentApplicationItem.application_id == application_id
        )
    )
    assert item is not None
    assert item.product_id == product.id
    assert item.seller_company_id == dealer_company.id
    assert product.warehouse_id == warehouse.id
    assert warehouse.company_id == dealer_company.id


async def test_mixed_items_create_one_atomic_leasing_application(  # noqa: PLR0915
    db_session: AsyncSession,
    test_vehicle: Vehicle,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="МАЗ mixed",
        model_name="6312C9",
        modification_name="Шасси",
    )
    actor_user = User(
        phone=f"+37525{str(uuid4().int)[-7:]}",
        email=f"mixed-application-{uuid4()}@example.test",
        name="Mixed application employee",
        role="carcraft_employee",
        is_active=True,
    )
    applicant_company = Company(
        name="ООО Единая заявка",
        company_type="other",
    )
    seller_company = Company(
        name="ООО Продавец mixed",
        company_type="dealer",
    )
    db_session.add_all(
        [
            mark,
            model,
            modification,
            actor_user,
            applicant_company,
            seller_company,
        ]
    )
    await db_session.flush()
    product = SpecialEquipmentProduct(
        code=f"maz-6312-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=seller_company.id,
        slug=f"maz-6312-{uuid4()}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("15300000.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    unavailable_product = SpecialEquipmentProduct(
        code=f"maz-unavailable-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=seller_company.id,
        slug=f"maz-unavailable-{uuid4()}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("1000000.00"),
        publication_status="published",
        sale_status="reserved",
        published_at=datetime.now(UTC),
    )
    db_session.add_all([product, unavailable_product])
    await db_session.flush()
    product_cart_item = SpecialEquipmentCartItem(
        user_id=actor_user.id,
        product_id=product.id,
        quantity=1,
        custom_price=Decimal("15000000.00"),
    )
    unavailable_cart_item = SpecialEquipmentCartItem(
        user_id=actor_user.id,
        product_id=unavailable_product.id,
        quantity=1,
    )
    db_session.add_all([product_cart_item, unavailable_cart_item])
    await db_session.flush()

    actor: dict[str, Any] = {
        "id": actor_user.id,
        "role": "carcraft_employee",
        "company_id": None,
    }
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")

    async def db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def actor_override() -> dict[str, Any]:
        return actor

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[commerce_router_module._applications_write] = (
        actor_override
    )

    request_body: dict[str, Any] = {
        "items": [
            {
                "item": {"type": "vehicle", "id": str(test_vehicle.id)},
                "quantity": 1,
                "comment": "Автомобиль",
            },
            {
                "item": {
                    "type": "special_equipment",
                    "id": str(product.id),
                },
                "quantity": 1,
                "custom_price": "15000000.00",
                "comment": "Спецтехника",
                "cart_item_ids": [str(product_cart_item.id)],
            },
        ],
        "company_id": str(applicant_company.id),
        "down_payment_percent": "20.00",
        "lease_term_months": 36,
        # Simulate a calculation made before the second item/price appeared.
        "calculation": {
            "total_amount": "2000000.00",
            # Derived browser fields are untrusted and must never be persisted.
            "down_payment": "-500.00",
            "monthly_payment": "-999.00",
            "total_cost": "1.00",
            "rate": "-42.00",
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        application_count_before_stale = int(
            await db_session.scalar(sa.select(sa.func.count(LeasingApplication.id)))
            or 0
        )
        # The calculator saw the old catalog price, then the product changed
        # before submission. No parent or child rows may be written.
        product.price = Decimal("15400000.00")
        await db_session.flush()
        changed_catalog_price = await client.post(
            "/api/v1/commerce/leasing-applications",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "items": [
                    {
                        "item": {
                            "type": "special_equipment",
                            "id": str(product.id),
                        },
                        "cart_item_ids": [str(product_cart_item.id)],
                    }
                ],
                "company_id": str(applicant_company.id),
                "down_payment_percent": "20.00",
                "lease_term_months": 36,
                "calculation": {"total_amount": "15300000.00"},
            },
        )
        assert changed_catalog_price.status_code == 409

        stale = await client.post(
            "/api/v1/commerce/leasing-applications",
            headers={"Idempotency-Key": str(uuid4())},
            json=request_body,
        )
        assert stale.status_code == 409
        assert "Стоимость товаров изменилась" in stale.json()["detail"]
        application_count_after_stale = int(
            await db_session.scalar(sa.select(sa.func.count(LeasingApplication.id)))
            or 0
        )
        assert application_count_after_stale == application_count_before_stale

        request_body["calculation"] = {
            "total_amount": "17000000.00",
            "down_payment": "-500.00",
            "monthly_payment": "-999.00",
            "total_cost": "1.00",
            "rate": "-42.00",
        }
        created = await client.post(
            "/api/v1/commerce/leasing-applications",
            json=request_body,
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert [line["item"]["type"] for line in body["items"]] == [
            "vehicle",
            "special_equipment",
        ]

        application_id = UUID(body["application_id"])
        application = await db_session.get(LeasingApplication, application_id)
        assert application is not None
        assert application.total_amount == Decimal("17000000.00")
        assert application.down_payment == Decimal("3400000.00")
        assert application.monthly_payment is not None
        assert application.total_cost is not None
        assert application.rate is not None
        monthly_payment = cast("Decimal", application.monthly_payment)
        total_cost = cast("Decimal", application.total_cost)
        total_amount = cast("Decimal", application.total_amount)
        rate = cast("Decimal", application.rate)
        assert monthly_payment > Decimal("0")
        assert monthly_payment != Decimal("-999.00")
        assert total_cost > total_amount
        assert rate >= Decimal("0")
        calculation_row = await db_session.get(
            LeasingApplicationCalculation,
            application_id,
        )
        assert calculation_row is not None
        assert calculation_row.monthly_payment == application.monthly_payment
        assert calculation_row.rate == application.rate

        vehicle_lines = (
            (
                await db_session.execute(
                    sa.select(ApplicationVehicle).where(
                        ApplicationVehicle.application_id == application_id
                    )
                )
            )
            .scalars()
            .all()
        )
        special_lines = (
            (
                await db_session.execute(
                    sa.select(SpecialEquipmentApplicationItem).where(
                        SpecialEquipmentApplicationItem.application_id == application_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(vehicle_lines) == 1
        assert len(special_lines) == 1
        assert vehicle_lines[0].vehicle_id == test_vehicle.id
        assert special_lines[0].product_id == product.id
        assert special_lines[0].unit_price == Decimal("15000000.00")
        assert {UUID(line["line_id"]) for line in body["items"]} == {
            vehicle_lines[0].id,
            special_lines[0].id,
        }

        application_count_before = int(
            await db_session.scalar(sa.select(sa.func.count(LeasingApplication.id)))
            or 0
        )
        failed_body = {
            **request_body,
            "items": [
                request_body["items"][0],
                {
                    "item": {
                        "type": "special_equipment",
                        "id": str(unavailable_product.id),
                    },
                    "cart_item_ids": [str(unavailable_cart_item.id)],
                },
            ],
        }
        failed = await client.post(
            "/api/v1/commerce/leasing-applications",
            json=failed_body,
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert failed.status_code == 409
        application_count_after = int(
            await db_session.scalar(sa.select(sa.func.count(LeasingApplication.id)))
            or 0
        )
        assert application_count_after == application_count_before
