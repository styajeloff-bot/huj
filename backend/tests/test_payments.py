
"""Integration tests for payment-related endpoints.

Covers payment status, receipts, webhook callbacks, and gateway payment
creation flows. All tests use bank_transfer (no real gateway calls) unless
specifically testing gateway error handling.

Each test runs inside a rolled-back transaction (see conftest.py).
"""
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from domain.commerce import VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE
from infrastructure.models.payments import (
    LeasingPaymentSchedule,
    Payment,
)
from infrastructure.models.payments import (
    PurchaseOrder as PurchaseOrderModel,
)
from infrastructure.models.users import User
from infrastructure.services import payment_gateway as payment_gateway_service
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures: order + payment already in DB
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def reservation_with_payment(
    db_session: AsyncSession, client_user: User, test_vehicle: Vehicle
) -> dict[str, Any]:
    """Create a reserved order with a completed reservation payment."""
    order = PurchaseOrderModel(
        user_id=client_user.id,
        vehicle_id=test_vehicle.id,
        purchase_type="reservation",
        status="reserved",
        total_price=Decimal("2000000.00"),
        paid_amount=Decimal("200000.00"),
        remaining_amount=Decimal("1800000.00"),
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)

    payment = Payment(
        purchase_order_id=order.id,
        user_id=client_user.id,
        payment_type="reservation",
        amount=Decimal("200000.00"),
        status="completed",
        payment_method="bank_transfer",
        paid_at=datetime.now(UTC),
    )
    db_session.add(payment)
    await db_session.flush()
    await db_session.refresh(payment)

    return {"order": order, "payment": payment}


@pytest_asyncio.fixture
async def pending_gateway_payment(
    db_session: AsyncSession, client_user: User, test_vehicle: Vehicle
) -> dict[str, Any]:
    """Order with a pending payment (simulating gateway-initiated payment)."""
    order = PurchaseOrderModel(
        user_id=client_user.id,
        vehicle_id=test_vehicle.id,
        purchase_type="full_purchase",
        status="reserved",
        total_price=Decimal("2000000.00"),
        paid_amount=Decimal("0"),
        remaining_amount=Decimal("2000000.00"),
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)

    payment = Payment(
        purchase_order_id=order.id,
        user_id=client_user.id,
        payment_type="full_purchase",
        amount=Decimal("2000000.00"),
        status="pending_payment",
        payment_method="card",
        gateway_transaction_id=f"CARCRAFT-{order.id}",
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    db_session.add(payment)
    await db_session.flush()
    await db_session.refresh(payment)

    return {"order": order, "payment": payment}


@pytest_asyncio.fixture
async def leasing_order_with_schedule(
    db_session: AsyncSession, client_user: User, test_vehicle: Vehicle
) -> dict[str, Any]:
    """Leasing order with a payment schedule."""
    order = PurchaseOrderModel(
        user_id=client_user.id,
        vehicle_id=test_vehicle.id,
        purchase_type="reservation",
        status="leasing_active",
        total_price=Decimal("2000000.00"),
        paid_amount=Decimal("200000.00"),
        remaining_amount=Decimal("1800000.00"),
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)

    items = []
    for i in range(1, 4):
        item = LeasingPaymentSchedule(
            purchase_order_id=order.id,
            payment_number=i,
            due_date=date(2026, i + 3, 1),
            amount=Decimal("600000.00"),
            is_paid=False,
        )
        db_session.add(item)
        items.append(item)
    await db_session.flush()
    for item in items:
        await db_session.refresh(item)

    return {"order": order, "schedule": items}


# ===========================================================================
# GET /api/v1/purchases/payments/{payment_id}/status
# ===========================================================================


async def test_payment_status_completed(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
) -> None:
    """Payment status for a completed payment — 200."""
    pid = reservation_with_payment["payment"].id
    resp = await client.get(
        f"/api/v1/purchases/payments/{pid}/status",
        headers=_auth(client_token),
    )
    assert resp.status_code == 200
    data = resp.json()["payment"]
    assert data["id"] == str(pid)
    assert data["status"] == "completed"


async def test_payment_status_pending(
    client: AsyncClient,
    client_token: str,
    pending_gateway_payment: dict,
) -> None:
    """Payment status for a pending payment — 200."""
    pid = pending_gateway_payment["payment"].id
    resp = await client.get(
        f"/api/v1/purchases/payments/{pid}/status",
        headers=_auth(client_token),
    )
    assert resp.status_code == 200
    assert resp.json()["payment"]["status"] == "pending_payment"


async def test_payment_status_not_found(
    client: AsyncClient,
    client_token: str,
    client_user: User,
) -> None:
    """Payment status for nonexistent payment — 404."""
    resp = await client.get(
        "/api/v1/purchases/payments/736ce387-8b3d-4ef4-a83d-b55b9c4b0fde/status",
        headers=_auth(client_token),
    )
    assert resp.status_code == 404


async def test_payment_status_no_auth(client: AsyncClient) -> None:
    """Payment status without auth — 401."""
    resp = await client.get("/api/v1/purchases/payments/1/status")
    assert resp.status_code == 401


# ===========================================================================
# GET /api/v1/purchases/payments/{payment_id}/receipt
# ===========================================================================


async def test_payment_receipt_success(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
) -> None:
    """Receipt for own payment — 200."""
    pid = reservation_with_payment["payment"].id
    resp = await client.get(
        f"/api/v1/purchases/payments/{pid}/receipt",
        headers=_auth(client_token),
    )
    assert resp.status_code == 200
    data = resp.json()["receipt"]
    assert data["payment"]["id"] == str(pid)
    assert "order" in data


async def test_legacy_payment_reads_hide_vehicle_commerce_receipt(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
    db_session: AsyncSession,
) -> None:
    order = reservation_with_payment["order"]
    payment = reservation_with_payment["payment"]
    payment.gateway_response = {
        "provider_status": "accepted",
        VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE: {
            "key": "must-not-leak",
            "handoff": {"sbpData": {"sbpLink": "must-not-leak"}},
        },
    }
    await db_session.flush()

    payments_response = await client.get(
        f"/api/v1/purchases/{order.id}/payments",
        headers=_auth(client_token),
    )
    receipt_response = await client.get(
        f"/api/v1/purchases/payments/{payment.id}/receipt",
        headers=_auth(client_token),
    )

    assert payments_response.status_code == 200
    assert receipt_response.status_code == 200
    listed_gateway = payments_response.json()["payments"][0]["gateway_response"]
    receipt_gateway = receipt_response.json()["receipt"]["payment"][
        "gateway_response"
    ]
    assert listed_gateway == {"provider_status": "accepted"}
    assert receipt_gateway == {"provider_status": "accepted"}
    assert VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE not in payments_response.text
    assert VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE not in receipt_response.text
    assert "must-not-leak" not in payments_response.text
    assert "must-not-leak" not in receipt_response.text


async def test_payment_receipt_not_found(
    client: AsyncClient,
    client_token: str,
    client_user: User,
) -> None:
    """Receipt for nonexistent payment — 404."""
    resp = await client.get(
        "/api/v1/purchases/payments/736ce387-8b3d-4ef4-a83d-b55b9c4b0fde/receipt",
        headers=_auth(client_token),
    )
    assert resp.status_code == 404


async def test_payment_receipt_wrong_owner(
    client: AsyncClient,
    other_token: str,
    reservation_with_payment: dict,
) -> None:
    """Receipt for another user's payment — 403."""
    pid = reservation_with_payment["payment"].id
    resp = await client.get(
        f"/api/v1/purchases/payments/{pid}/receipt",
        headers=_auth(other_token),
    )
    assert resp.status_code == 403


async def test_payment_receipt_no_auth(client: AsyncClient) -> None:
    """Receipt without auth — 401."""
    resp = await client.get("/api/v1/purchases/payments/1/receipt")
    assert resp.status_code == 401


# ===========================================================================
# POST /api/v1/purchases/{order_id}/payments — scope=remaining
# ===========================================================================


async def test_pay_remaining_creates_payment(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
) -> None:
    """Pay remaining with bank_transfer — completes immediately."""
    oid = reservation_with_payment["order"].id
    resp = await client.post(
        f"/api/v1/purchases/{oid}/payments",
        headers=_auth(client_token),
        json={"scope": "remaining", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["order"]["status"] == "purchased"
    assert float(data["order"]["paid_amount"]) == pytest.approx(2_000_000.0)
    assert float(data["order"]["remaining_amount"]) == pytest.approx(0.0)
    assert data["payment"]["payment_type"] == "remaining_balance"
    assert data["payment"]["status"] == "completed"


async def test_pay_remaining_already_purchased(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
    client_user: User,
    test_vehicle: Vehicle,
) -> None:
    """Cannot pay remaining on a fully purchased order — 400."""
    order = PurchaseOrderModel(
        user_id=client_user.id,
        vehicle_id=test_vehicle.id,
        purchase_type="full_purchase",
        status="purchased",
        total_price=Decimal("2000000"),
        paid_amount=Decimal("2000000"),
        remaining_amount=Decimal("0"),
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)

    resp = await client.post(
        f"/api/v1/purchases/{order.id}/payments",
        headers=_auth(client_token),
        json={"scope": "remaining", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 400


async def test_pay_remaining_wrong_owner(
    client: AsyncClient,
    other_token: str,
    reservation_with_payment: dict,
) -> None:
    """Cannot pay remaining on another user's order — 403."""
    oid = reservation_with_payment["order"].id
    resp = await client.post(
        f"/api/v1/purchases/{oid}/payments",
        headers=_auth(other_token),
        json={"scope": "remaining", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 403


async def test_pay_remaining_order_not_found(
    client: AsyncClient,
    client_token: str,
) -> None:
    """Pay remaining on nonexistent order — 404."""
    resp = await client.post(
        "/api/v1/purchases/736ce387-8b3d-4ef4-a83d-b55b9c4b0fde/payments",
        headers=_auth(client_token),
        json={"scope": "remaining", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 404


# ===========================================================================
# POST /api/v1/purchases — card payment (gateway error, not 500)
# ===========================================================================


async def test_create_order_card_gateway_domain_error(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    """Card payment with PaymentGatewayError — returns 502, not 500."""
    from domain.errors import PaymentGatewayError

    with patch(
        "application.commands.purchases.payment_gateway.prepare_payment",
        new_callable=AsyncMock,
        side_effect=PaymentGatewayError("ModulBank secret key not configured"),
    ):
        resp = await client.post(
            "/api/v1/purchases",
            headers=_auth(client_token),
            json={
                "items": [{"vehicle_id": test_vehicle.id, "quantity": 1}],
                "purchase_type": "full_purchase",
                "payment_method": "card",
            },
        )
        assert resp.status_code == 502


async def test_create_order_sbp_gateway_domain_error(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    """SBP payment with PaymentGatewayError — returns 502, not 500."""
    from domain.errors import PaymentGatewayError

    with patch(
        "application.commands.purchases.payment_gateway.request_sbp_link",
        new_callable=AsyncMock,
        side_effect=PaymentGatewayError("SBP API error"),
    ):
        resp = await client.post(
            "/api/v1/purchases",
            headers=_auth(client_token),
            json={
                "items": [{"vehicle_id": test_vehicle.id, "quantity": 1}],
                "purchase_type": "reservation",
                "payment_method": "sbp",
            },
        )
        assert resp.status_code == 502


# ===========================================================================
# POST /api/v1/purchases/{order_id}/payments — card (gateway mock)
# ===========================================================================


async def test_pay_remaining_card_returns_widget(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
) -> None:
    """Pay remaining with card — returns widget data from gateway mock."""
    oid = reservation_with_payment["order"].id
    mock_widget = {
        "formUrl": "https://pay.modulbank.ru/pay",
        "formParams": {"merchant": "test"},
        "orderId": f"CARCRAFT-{oid}",
        "amount": 1800000.0,
        "expiresAt": "2099-01-01T00:00:00+00:00",
    }

    with patch(
        "application.commands.purchases.payment_gateway.prepare_payment",
        new_callable=AsyncMock,
        return_value=mock_widget,
    ):
        resp = await client.post(
            f"/api/v1/purchases/{oid}/payments",
            headers=_auth(client_token),
            json={"scope": "remaining", "payment_method": "card"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["widgetData"]["formUrl"] == "https://pay.modulbank.ru/pay"
        assert data["order"]["id"] == str(oid)


async def test_legacy_remaining_payment_rejects_second_active_provider_attempt(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
    db_session: AsyncSession,
) -> None:
    oid = reservation_with_payment["order"].id
    mock_widget = {
        "formUrl": "https://pay.modulbank.ru/pay",
        "formParams": {"merchant": "test"},
        "orderId": f"CARCRAFT-{oid}",
        "amount": 1800000.0,
        "expiresAt": "2099-01-01T00:00:00+00:00",
    }

    with patch(
        "application.commands.purchases.payment_gateway.prepare_payment",
        new_callable=AsyncMock,
        return_value=mock_widget,
    ):
        first = await client.post(
            f"/api/v1/purchases/{oid}/payments",
            headers=_auth(client_token),
            json={"scope": "remaining", "payment_method": "card"},
        )
        second = await client.post(
            f"/api/v1/purchases/{oid}/payments",
            headers=_auth(client_token),
            json={"scope": "remaining", "payment_method": "card"},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "уже выполняется платёж" in second.text
    count = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(Payment)
        .where(
            Payment.purchase_order_id == oid,
            Payment.payment_type == "remaining_balance",
        )
    )
    assert count == 1


async def test_pay_remaining_sbp_returns_sbp_data(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
) -> None:
    """Pay remaining with sbp — returns sbpData (SBP QR URL)."""
    oid = reservation_with_payment["order"].id
    mock_sbp = {
        "sbpLink": "https://qr.nspk.ru/ABC123",
        "orderId": f"CARCRAFT-{oid}",
        "amount": 1800000.0,
        "description": "Доплата по заказу",
        "expiresAt": "2099-01-01T00:00:00+00:00",
    }

    with patch(
        "application.commands.purchases.payment_gateway.request_sbp_link",
        new_callable=AsyncMock,
        return_value=mock_sbp,
    ):
        resp = await client.post(
            f"/api/v1/purchases/{oid}/payments",
            headers=_auth(client_token),
            json={"scope": "remaining", "payment_method": "sbp"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["sbpData"]["sbpLink"] == "https://qr.nspk.ru/ABC123"
        assert data["payment"]["id"] is not None


async def test_create_payment_invalid_scope(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
) -> None:
    """Unknown scope value — 422."""
    oid = reservation_with_payment["order"].id
    resp = await client.post(
        f"/api/v1/purchases/{oid}/payments",
        headers=_auth(client_token),
        json={"scope": "invalid", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 422


async def test_create_payment_scheduled_without_schedule_id(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
) -> None:
    """scope=scheduled without schedule_id — 422."""
    oid = reservation_with_payment["order"].id
    resp = await client.post(
        f"/api/v1/purchases/{oid}/payments",
        headers=_auth(client_token),
        json={"scope": "scheduled", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 422


# ===========================================================================
# POST /api/v1/payments/webhook/modulbank
# ===========================================================================


async def test_vehicle_callback_locks_vehicle_order_payment_in_global_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_id = uuid4()
    payment_id = uuid4()
    vehicle_id = uuid4()
    transaction_id = f"CARCRAFT-{payment_id}"
    calls: list[str] = []
    payment = {
        "id": payment_id,
        "purchase_order_id": order_id,
        "order_vehicle_id": vehicle_id,
    }

    async def find_payment(
        _session: object,
        requested_transaction_id: str,
    ) -> dict[str, Any]:
        assert requested_transaction_id == transaction_id
        return payment

    async def lock_vehicle(
        _session: object,
        requested_vehicle_id: object,
    ) -> dict[str, Any]:
        assert requested_vehicle_id == vehicle_id
        calls.append("vehicle")
        return {"id": vehicle_id, "status": "reserved"}

    async def lock_order(
        _session: object,
        requested_order_id: object,
    ) -> dict[str, Any]:
        assert requested_order_id == order_id
        calls.append("order")
        return {"id": order_id, "vehicle_id": vehicle_id}

    async def lock_payment(
        _session: object,
        requested_transaction_id: str,
    ) -> dict[str, Any]:
        assert requested_transaction_id == transaction_id
        calls.append("payment")
        return payment

    monkeypatch.setattr(
        payment_gateway_service.repo,
        "get_payment_by_gateway_id",
        find_payment,
    )
    monkeypatch.setattr(
        payment_gateway_service.repo,
        "get_vehicle_for_update",
        lock_vehicle,
    )
    monkeypatch.setattr(
        payment_gateway_service.repo,
        "get_order_for_update",
        lock_order,
    )
    monkeypatch.setattr(
        payment_gateway_service.repo,
        "get_payment_by_gateway_id_for_update",
        lock_payment,
    )

    locked = await payment_gateway_service._lock_vehicle_payment_callback_context(
        transaction_id,
        object(),  # type: ignore[arg-type]
    )

    assert locked == payment
    assert calls == ["vehicle", "order", "payment"]


async def test_vehicle_expiry_rechecks_payment_under_global_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_id = uuid4()
    payment_id = uuid4()
    vehicle_id = uuid4()
    calls: list[str] = []
    candidate = {
        "id": payment_id,
        "purchase_order_id": order_id,
        "vehicle_id": vehicle_id,
        "payment_type": "full_purchase",
        "status": "pending_payment",
    }

    async def find_candidates(_session: object) -> list[dict[str, Any]]:
        return [candidate]

    async def lock_order(
        _session: object,
        requested_order_id: object,
    ) -> dict[str, Any]:
        assert requested_order_id == order_id
        calls.append("order")
        return {"id": order_id, "vehicle_id": vehicle_id}

    async def lock_vehicle(
        _session: object,
        requested_vehicle_id: object,
    ) -> dict[str, Any]:
        assert requested_vehicle_id == vehicle_id
        calls.append("vehicle")
        return {"id": vehicle_id, "status": "reserved"}

    async def lock_payment(
        _session: object,
        requested_payment_id: object,
    ) -> dict[str, Any]:
        assert requested_payment_id == payment_id
        calls.append("payment")
        return {
            **candidate,
            "status": "completed",
            "expires_at": datetime(2020, 1, 1, tzinfo=UTC),
        }

    update_payment = AsyncMock()
    expire_special = AsyncMock()
    monkeypatch.setattr(
        payment_gateway_service.repo,
        "find_pending_expired_payments",
        find_candidates,
    )
    monkeypatch.setattr(
        payment_gateway_service.repo,
        "get_vehicle_for_update",
        lock_vehicle,
    )
    monkeypatch.setattr(
        payment_gateway_service.repo,
        "get_order_for_update",
        lock_order,
    )
    monkeypatch.setattr(
        payment_gateway_service.repo,
        "get_payment_by_id_for_update",
        lock_payment,
    )
    monkeypatch.setattr(
        payment_gateway_service.repo,
        "update_payment",
        update_payment,
    )
    monkeypatch.setattr(
        payment_gateway_service,
        "_expire_stale_special_equipment_payments",
        expire_special,
    )

    await payment_gateway_service.expire_stale_payments(object())  # type: ignore[arg-type]

    assert calls == ["vehicle", "order", "payment"]
    update_payment.assert_not_awaited()
    expire_special.assert_awaited_once()


async def test_webhook_modulbank_invalid_signature(
    client: AsyncClient,
) -> None:
    """Webhook with invalid signature — should return 200 with ok=false (not 500)."""
    resp = await client.post(
        "/api/v1/payments/webhook/modulbank",
        json={
            "order_id": "CARCRAFT-9999",
            "status": "success",
            "signature": "badsig",
        },
    )
    # ModulBank webhooks always return 200 to prevent retries
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False


async def test_webhook_modulbank_no_signature(
    client: AsyncClient,
) -> None:
    """Webhook without signature — should return 200 with ok=false."""
    resp = await client.post(
        "/api/v1/payments/webhook/modulbank",
        json={"order_id": "CARCRAFT-1", "status": "success"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


async def test_webhook_modulbank_form_data(
    client: AsyncClient,
) -> None:
    """Webhook with form-encoded data — should not 500."""
    resp = await client.post(
        "/api/v1/payments/webhook/modulbank",
        data={"order_id": "CARCRAFT-1", "status": "success", "signature": "test"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


async def test_webhook_modulbank_marks_exact_schedule_item_paid(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    leasing_order_with_schedule: dict,
) -> None:
    order = leasing_order_with_schedule["order"]
    target_schedule = leasing_order_with_schedule["schedule"][1]
    untouched_schedule = leasing_order_with_schedule["schedule"][0]

    payment = Payment(
        purchase_order_id=order.id,
        user_id=client_user.id,
        payment_type="leasing_monthly",
        amount=Decimal("600000.00"),
        status="pending_payment",
        payment_method="card",
        gateway_transaction_id="CARCRAFT-SCHEDULE-2",
        gateway_response={"schedule_id": str(target_schedule.id)},
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    db_session.add(payment)
    await db_session.flush()
    await db_session.refresh(payment)

    with (
        patch(
            "infrastructure.services.payment_gateway.verify_modulbank_signature",
            return_value=True,
        ),
        patch(
            "presentation.routers.payments.payment_gateway.start_fiscalization_task",
        ) as start_fiscalization_task,
    ):
        resp = await client.post(
            "/api/v1/payments/webhook/modulbank",
            json={
                "order_id": "CARCRAFT-SCHEDULE-2",
                "status": "success",
                "signature": "valid",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    start_fiscalization_task.assert_called_once_with(payment.id)

    await db_session.refresh(target_schedule)
    await db_session.refresh(untouched_schedule)
    assert target_schedule.is_paid is True
    assert target_schedule.payment_id == payment.id
    assert untouched_schedule.is_paid is False


async def test_vehicle_success_callback_preserves_server_commerce_receipt(
    client: AsyncClient,
    db_session: AsyncSession,
    pending_gateway_payment: dict,
) -> None:
    payment = pending_gateway_payment["payment"]
    trusted_receipt = {
        "version": 1,
        "key": "server-generated-key",
        "request_hash": "trusted-request-hash",
    }
    payment.gateway_response = {
        VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE: trusted_receipt,
        "server_marker": "keep-me",
    }
    await db_session.flush()

    with (
        patch(
            "infrastructure.services.payment_gateway.verify_modulbank_signature",
            return_value=True,
        ),
        patch(
            "presentation.routers.payments.payment_gateway.start_fiscalization_task",
        ),
    ):
        response = await client.post(
            "/api/v1/payments/webhook/modulbank",
            json={
                "order_id": payment.gateway_transaction_id,
                "status": "success",
                "signature": "valid",
                "provider_marker": "accepted",
                VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE: {
                    "key": "attacker-controlled-key",
                    "request_hash": "spoofed-request-hash",
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    await db_session.refresh(payment)
    assert payment.status == "completed"
    assert payment.gateway_response is not None
    assert (
        payment.gateway_response[VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE]
        == trusted_receipt
    )
    assert payment.gateway_response["server_marker"] == "keep-me"
    assert payment.gateway_response["provider_marker"] == "accepted"


async def test_vehicle_failure_callback_preserves_server_commerce_receipt(
    client: AsyncClient,
    db_session: AsyncSession,
    pending_gateway_payment: dict,
) -> None:
    payment = pending_gateway_payment["payment"]
    trusted_receipt = {
        "version": 1,
        "key": "server-generated-key",
        "request_hash": "trusted-request-hash",
    }
    payment.gateway_response = {
        VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE: trusted_receipt,
        "server_marker": "keep-me",
    }
    await db_session.flush()

    with patch(
        "infrastructure.services.payment_gateway.verify_modulbank_signature",
        return_value=True,
    ):
        response = await client.post(
            "/api/v1/payments/webhook/modulbank",
            json={
                "order_id": payment.gateway_transaction_id,
                "status": "failed",
                "error": "declined",
                "signature": "valid",
                "provider_marker": "accepted",
                VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE: {
                    "key": "attacker-controlled-key",
                    "request_hash": "spoofed-request-hash",
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    await db_session.refresh(payment)
    assert payment.status == "failed"
    assert payment.gateway_response is not None
    assert (
        payment.gateway_response[VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE]
        == trusted_receipt
    )
    assert payment.gateway_response["server_marker"] == "keep-me"
    assert payment.gateway_response["provider_marker"] == "accepted"


# ===========================================================================
# POST /api/v1/payments/webhook/modulkassa
# ===========================================================================


async def test_webhook_modulkassa_unknown_receipt(
    client: AsyncClient,
) -> None:
    """Fiscal webhook for unknown receipt — 200, no crash."""
    resp = await client.post(
        "/api/v1/payments/webhook/modulkassa",
        json={"id": "nonexistent-receipt-id", "status": "COMPLETED"},
    )
    assert resp.status_code == 200


async def test_webhook_modulkassa_empty_body(
    client: AsyncClient,
) -> None:
    """Fiscal webhook with minimal data — should not 500."""
    resp = await client.post(
        "/api/v1/payments/webhook/modulkassa",
        json={},
    )
    assert resp.status_code == 200


# ===========================================================================
# GET /api/v1/purchases/{order_id}/schedule
# ===========================================================================


async def test_get_schedule_leasing_active(
    client: AsyncClient,
    client_token: str,
    leasing_order_with_schedule: dict,
) -> None:
    """Schedule for leasing_active order — 200 with items."""
    oid = leasing_order_with_schedule["order"].id
    resp = await client.get(
        f"/api/v1/purchases/{oid}/schedule",
        headers=_auth(client_token),
    )
    assert resp.status_code == 200
    schedule = resp.json()["schedule"]
    assert len(schedule) == 3
    assert schedule[0]["payment_number"] == 1
    assert not schedule[0]["is_paid"]


async def test_get_schedule_not_leasing(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
) -> None:
    """Schedule for non-leasing order — 400."""
    oid = reservation_with_payment["order"].id
    resp = await client.get(
        f"/api/v1/purchases/{oid}/schedule",
        headers=_auth(client_token),
    )
    assert resp.status_code == 400


async def test_get_schedule_wrong_owner(
    client: AsyncClient,
    other_token: str,
    leasing_order_with_schedule: dict,
) -> None:
    """Schedule for another user's order — 403."""
    oid = leasing_order_with_schedule["order"].id
    resp = await client.get(
        f"/api/v1/purchases/{oid}/schedule",
        headers=_auth(other_token),
    )
    assert resp.status_code == 403


# ===========================================================================
# POST /api/v1/purchases/{order_id}/payments — scope=scheduled
# ===========================================================================


async def test_pay_schedule_item_bank_transfer(
    client: AsyncClient,
    client_token: str,
    leasing_order_with_schedule: dict,
) -> None:
    """Pay a leasing installment via bank_transfer — completes immediately."""
    oid = leasing_order_with_schedule["order"].id
    sid = leasing_order_with_schedule["schedule"][0].id
    resp = await client.post(
        f"/api/v1/purchases/{oid}/payments",
        headers=_auth(client_token),
        json={
            "scope": "scheduled",
            "schedule_id": sid,
            "payment_method": "bank_transfer",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["scheduleItem"]["is_paid"] is True
    assert data["payment"]["payment_type"] == "leasing_monthly"


async def test_legacy_schedule_payment_rejects_second_active_provider_attempt(
    client: AsyncClient,
    client_token: str,
    leasing_order_with_schedule: dict,
    db_session: AsyncSession,
) -> None:
    oid = leasing_order_with_schedule["order"].id
    sid = leasing_order_with_schedule["schedule"][0].id
    mock_widget = {
        "formUrl": "https://pay.modulbank.ru/pay",
        "formParams": {"merchant": "test"},
        "orderId": f"CARCRAFT-{oid}",
        "amount": 100000.0,
        "expiresAt": "2099-01-01T00:00:00+00:00",
    }

    with patch(
        "application.commands.purchases.payment_gateway.prepare_payment",
        new_callable=AsyncMock,
        return_value=mock_widget,
    ):
        body = {
            "scope": "scheduled",
            "schedule_id": str(sid),
            "payment_method": "card",
        }
        first = await client.post(
            f"/api/v1/purchases/{oid}/payments",
            headers=_auth(client_token),
            json=body,
        )
        second = await client.post(
            f"/api/v1/purchases/{oid}/payments",
            headers=_auth(client_token),
            json=body,
        )

    assert first.status_code == 201
    first_body = first.json()
    schedule_after_start = await client.get(
        f"/api/v1/purchases/{oid}/schedule",
        headers=_auth(client_token),
    )
    assert schedule_after_start.status_code == 200
    pending_item = schedule_after_start.json()["schedule"][0]
    assert pending_item["is_paid"] is False
    assert pending_item["payment_id"] == first_body["payment"]["id"]
    assert pending_item["payment_status"] == "pending_payment"
    assert second.status_code == 409
    assert "уже выполняется платёж" in second.text
    count = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(Payment)
        .where(
            Payment.purchase_order_id == oid,
            Payment.payment_type == "leasing_monthly",
        )
    )
    assert count == 1


async def test_pay_schedule_item_not_leasing(
    client: AsyncClient,
    client_token: str,
    reservation_with_payment: dict,
) -> None:
    """Pay schedule item on non-leasing order — 400."""
    oid = reservation_with_payment["order"].id
    resp = await client.post(
        f"/api/v1/purchases/{oid}/payments",
        headers=_auth(client_token),
        json={
            "scope": "scheduled",
            "schedule_id": "736ce387-8b3d-4ef4-a83d-b55b9c4b0fde",
            "payment_method": "bank_transfer",
        },
    )
    assert resp.status_code == 400


async def test_pay_schedule_item_wrong_owner(
    client: AsyncClient,
    other_token: str,
    leasing_order_with_schedule: dict,
) -> None:
    """Pay schedule on another user's order — 403."""
    oid = leasing_order_with_schedule["order"].id
    sid = leasing_order_with_schedule["schedule"][0].id
    resp = await client.post(
        f"/api/v1/purchases/{oid}/payments",
        headers=_auth(other_token),
        json={
            "scope": "scheduled",
            "schedule_id": sid,
            "payment_method": "bank_transfer",
        },
    )
    assert resp.status_code == 403


# ===========================================================================
# Full workflow: reserve → pay remaining → verify final state
# ===========================================================================


async def test_full_payment_workflow(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    """reserve (bank_transfer) → pay remaining → verify payments list = 2 completed."""
    # 1. Create reservation
    create = await client.post(
        "/api/v1/purchases",
        headers=_auth(client_token),
        json={
            "items": [{"vehicle_id": test_vehicle.id, "quantity": 1}],
            "purchase_type": "reservation",
            "payment_method": "bank_transfer",
            "down_payment_percent": 10.0,
        },
    )
    assert create.status_code == 201
    order_id = create.json()["orders"][0]["id"]

    # 2. Pay remaining
    pay = await client.post(
        f"/api/v1/purchases/{order_id}/payments",
        headers=_auth(client_token),
        json={"scope": "remaining", "payment_method": "bank_transfer"},
    )
    assert pay.status_code == 201
    assert pay.json()["order"]["status"] == "purchased"

    # 3. Check both payments exist and are completed
    payments_resp = await client.get(
        f"/api/v1/purchases/{order_id}/payments",
        headers=_auth(client_token),
    )
    assert payments_resp.status_code == 200
    payments = payments_resp.json()["payments"]
    assert len(payments) == 2
    assert all(p["status"] == "completed" for p in payments)
    types = {p["payment_type"] for p in payments}
    assert types == {"reservation", "remaining_balance"}

    # 4. Check payment status endpoint for each
    for p in payments:
        status_resp = await client.get(
            f"/api/v1/purchases/payments/{p['id']}/status",
            headers=_auth(client_token),
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["payment"]["status"] == "completed"

    # 5. Check receipt endpoint for each
    for p in payments:
        receipt_resp = await client.get(
            f"/api/v1/purchases/payments/{p['id']}/receipt",
            headers=_auth(client_token),
        )
        assert receipt_resp.status_code == 200
        assert receipt_resp.json()["receipt"]["payment"]["id"] == p["id"]
