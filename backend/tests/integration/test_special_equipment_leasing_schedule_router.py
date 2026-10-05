"""HTTP integration for owner-scoped special-equipment leasing installments."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_db
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentLeasingPaymentSchedule,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.models.users import User
from presentation.routers import special_equipment_commerce as router_module
from presentation.routers.special_equipment_commerce import router
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


async def _seed_schedule(
    db_session: AsyncSession,
) -> tuple[User, User, SpecialEquipmentPurchaseOrder, SpecialEquipmentLeasingPaymentSchedule, str]:
    suffix = uuid4().hex
    seller = Company(name=f"Leasing schedule seller {suffix}", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name=f"Leasing schedule maker {suffix}",
        model_name="Schedule test excavator",
        modification_name="Schedule modification",
    )
    owner = User(
        phone=f"+37529{suffix[:7]}",
        email=f"leasing-owner-{suffix}@example.test",
        name="Leasing owner",
        role="client",
        is_active=True,
    )
    employee = User(
        phone=f"+37533{suffix[7:14]}",
        email=f"leasing-employee-{suffix}@example.test",
        name="Leasing employee",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add_all([seller, mark, model, modification, owner, employee])
    await db_session.flush()
    product = SpecialEquipmentProduct(
        code=f"leasing-schedule-product-{suffix}",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug=f"leasing-schedule-product-{suffix}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("1000.00"),
        publication_status="published",
        sale_status="sold",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()
    order = SpecialEquipmentPurchaseOrder(
        user_id=owner.id,
        product_id=product.id,
        seller_company_id=seller.id,
        purchase_type="leasing",
        status="leasing_active",
        unit_price=Decimal("800.00"),
        total_price=Decimal("1000.00"),
        paid_amount=Decimal("0.00"),
        remaining_amount=Decimal("1000.00"),
        currency_code="RUB",
        item_snapshot={
            "mark": mark.name,
            "model": model.name,
            "modification": modification.name,
        },
        idempotency_key=f"leasing-order-{suffix}",
        request_hash="0" * 64,
    )
    db_session.add(order)
    await db_session.flush()
    installment = SpecialEquipmentLeasingPaymentSchedule(
        purchase_order_id=order.id,
        payment_number=1,
        due_date=date(2026, 8, 17),
        amount=Decimal("100.00"),
        principal=Decimal("80.00"),
        interest=Decimal("20.00"),
        is_paid=False,
    )
    db_session.add(installment)
    await db_session.flush()
    return owner, employee, order, installment, suffix


async def test_schedule_payment_requires_confirmation_and_replays_idempotently(
    db_session: AsyncSession,
) -> None:
    owner, employee, order, installment, suffix = await _seed_schedule(db_session)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/special-equipment")

    async def _db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _owner_override() -> dict[str, Any]:
        return {"id": owner.id, "role": "client"}

    async def _employee_override() -> dict[str, Any]:
        return {"id": employee.id, "role": "carcraft_employee"}

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[router_module._purchases_read] = _owner_override
    app.dependency_overrides[router_module._purchases_write] = _owner_override
    app.dependency_overrides[router_module._purchases_admin] = _employee_override

    payment_path = (
        f"/api/v1/special-equipment/purchase-orders/{order.id}"
        f"/payment-schedule/{installment.id}/payments"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            payment_path,
            headers={"Idempotency-Key": f"schedule-{suffix}"},
            json={"payment_method": "bank_transfer"},
        )
        assert created.status_code == 201, created.text
        created_body = created.json()
        payment_id = created_body["payment"]["id"]
        assert created_body["payment"]["status"] == "processing"
        assert created_body["schedule_item"]["is_paid"] is False
        assert created_body["schedule_item"]["can_pay"] is False
        assert "gateway_response" not in created.text
        assert "request_hash" not in created.text

        replay = await client.post(
            payment_path,
            headers={"Idempotency-Key": f"schedule-{suffix}"},
            json={"payment_method": "bank_transfer"},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["payment"]["id"] == payment_id

        before_confirmation = await client.get(
            f"/api/v1/special-equipment/purchase-orders/{order.id}/payment-schedule"
        )
        assert before_confirmation.status_code == 200
        assert before_confirmation.json()["items"][0]["is_paid"] is False
        assert before_confirmation.json()["items"][0]["payment_status"] == "processing"

        confirmed = await client.put(
            f"/api/v1/special-equipment/purchase-orders/{order.id}"
            f"/payments/{payment_id}/offline-confirmation"
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["order"]["status"] == "leasing_active"
        assert confirmed.json()["order"]["paid_amount"] == "100.00"

        after_confirmation = await client.get(
            f"/api/v1/special-equipment/purchase-orders/{order.id}/payment-schedule"
        )
        item = after_confirmation.json()["items"][0]
        assert item["is_paid"] is True
        assert item["payment_status"] == "completed"
        assert item["can_pay"] is False

    await db_session.refresh(installment)
    assert installment.is_paid is True
    assert str(installment.payment_id) == payment_id
