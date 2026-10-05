
"""Integration tests for the purchases API.

All tests use bank_transfer as the payment method — no external gateway calls.
Each test runs inside a rolled-back transaction (see conftest.py).
"""
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from application.commands import purchases as purchase_commands
from domain.entities.purchase_order import PurchaseOrder
from infrastructure.models.users import User
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_reservation(
    client: AsyncClient,
    token: str,
    vehicle_id: UUID,
    *,
    down_payment_percent: float = 10.0,
) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/purchases",
        headers=_auth(token),
        json={
            "items": [{"vehicle_id": vehicle_id, "quantity": 1}],
            "purchase_type": "reservation",
            "payment_method": "bank_transfer",
            "down_payment_percent": down_payment_percent,
        },
    )
    assert resp.status_code == 201, resp.text
    return cast("dict[str, Any]", resp.json())


async def _create_full_purchase(
    client: AsyncClient,
    token: str,
    vehicle_id: UUID,
) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/purchases",
        headers=_auth(token),
        json={
            "items": [{"vehicle_id": vehicle_id, "quantity": 1}],
            "purchase_type": "full_purchase",
            "payment_method": "bank_transfer",
        },
    )
    assert resp.status_code == 201, resp.text
    return cast("dict[str, Any]", resp.json())


# ===========================================================================
# POST /api/v1/purchases — create orders
# ===========================================================================


async def test_create_reservation_bank_transfer(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_reservation(client, client_token, test_vehicle.id)

    assert len(data["orders"]) == 1
    order = data["orders"][0]

    assert order["status"] == "reserved"
    assert order["purchase_type"] == "reservation"
    assert order["user_id"] == str(client_user.id)
    assert order["vehicle_id"] == str(test_vehicle.id)
    assert float(order["total_price"]) == pytest.approx(2_000_000.0)
    assert float(order["paid_amount"]) == pytest.approx(200_000.0)   # 10 %
    assert float(order["remaining_amount"]) == pytest.approx(1_800_000.0)
    assert data["widgetData"] is None
    assert data["sbpData"] is None


async def test_create_reservation_custom_percent(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_reservation(
        client, client_token, test_vehicle.id, down_payment_percent=25.0
    )
    order = data["orders"][0]
    assert float(order["paid_amount"]) == pytest.approx(500_000.0)    # 25 %
    assert float(order["remaining_amount"]) == pytest.approx(1_500_000.0)


async def test_create_full_purchase_bank_transfer(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_full_purchase(client, client_token, test_vehicle.id)

    order = data["orders"][0]
    assert order["status"] == "purchased"
    assert order["purchase_type"] == "full_purchase"
    assert float(order["paid_amount"]) == pytest.approx(2_000_000.0)
    assert float(order["remaining_amount"]) == pytest.approx(0.0)


async def test_create_order_vehicle_not_found(
    client: AsyncClient,
    client_token: str,
) -> None:
    resp = await client.post(
        "/api/v1/purchases",
        headers=_auth(client_token),
        json={
            "items": [{"vehicle_id": "736ce387-8b3d-4ef4-a83d-b55b9c4b0fde"}],
            "purchase_type": "reservation",
            "payment_method": "bank_transfer",
        },
    )
    assert resp.status_code == 404


async def test_create_order_no_auth(
    client: AsyncClient,
    test_vehicle: Vehicle,
) -> None:
    resp = await client.post(
        "/api/v1/purchases",
        json={
            "items": [{"vehicle_id": test_vehicle.id}],
            "purchase_type": "reservation",
        },
    )
    assert resp.status_code == 401


async def test_create_order_employee_allowed(
    client: AsyncClient,
    employee_token: str,
    employee_user: User,
    test_vehicle: Vehicle,
) -> None:
    """carcraft_employee role is allowed to create orders."""
    resp = await client.post(
        "/api/v1/purchases",
        headers=_auth(employee_token),
        json={
            "items": [{"vehicle_id": test_vehicle.id, "quantity": 1}],
            "purchase_type": "reservation",
            "payment_method": "bank_transfer",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["orders"][0]["user_id"] == str(employee_user.id)


async def test_create_order_quantity_without_complectation_fails(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    resp = await client.post(
        "/api/v1/purchases",
        headers=_auth(client_token),
        json={
            "items": [{"vehicle_id": test_vehicle.id, "quantity": 2}],
            "purchase_type": "reservation",
            "payment_method": "bank_transfer",
        },
    )
    assert resp.status_code == 409


async def test_compute_amounts_preserves_zero_down_payment() -> None:
    payment_amount, initial_paid, initial_remaining, order_status, payment_type = (
        PurchaseOrder.compute_amounts(
            purchase_type="reservation",
            total_price=2_000_000.0,
            use_gateway=False,
            down_payment_percent=0,
        )
    )

    assert payment_amount == pytest.approx(0.0)
    assert initial_paid == pytest.approx(0.0)
    assert initial_remaining == pytest.approx(2_000_000.0)
    assert order_status == "reserved"
    assert payment_type == "reservation"


# ===========================================================================
# GET /api/v1/purchases — list orders
# ===========================================================================


async def test_list_orders_empty(
    client: AsyncClient,
    client_token: str,
    client_user: User,
) -> None:
    resp = await client.get("/api/v1/purchases", headers=_auth(client_token))
    assert resp.status_code == 200
    assert resp.json()["orders"] == []


async def test_list_orders_after_creation(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    await _create_reservation(client, client_token, test_vehicle.id)

    resp = await client.get("/api/v1/purchases", headers=_auth(client_token))
    assert resp.status_code == 200
    orders = resp.json()["orders"]
    assert len(orders) == 1
    assert orders[0]["status"] == "reserved"


async def test_list_orders_status_filter(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    await _create_reservation(client, client_token, test_vehicle.id)

    resp = await client.get(
        "/api/v1/purchases?status=purchased", headers=_auth(client_token)
    )
    assert resp.status_code == 200
    assert resp.json()["orders"] == []


async def test_list_orders_no_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/purchases")
    assert resp.status_code == 401


# ===========================================================================
# GET /api/v1/purchases/my-vehicle-ids
# ===========================================================================


async def test_my_vehicle_ids_empty(
    client: AsyncClient,
    client_token: str,
    client_user: User,
) -> None:
    resp = await client.get(
        "/api/v1/purchases/my-vehicle-ids", headers=_auth(client_token)
    )
    assert resp.status_code == 200
    assert resp.json()["vehicles"] == []


async def test_my_vehicle_ids_after_reservation(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    await _create_reservation(client, client_token, test_vehicle.id)

    resp = await client.get(
        "/api/v1/purchases/my-vehicle-ids", headers=_auth(client_token)
    )
    assert resp.status_code == 200
    vehicles = resp.json()["vehicles"]
    assert len(vehicles) == 1
    assert vehicles[0]["vehicle_id"] == str(test_vehicle.id)
    assert vehicles[0]["status"] == "reserved"
    assert vehicles[0]["purchase_type"] == "reservation"


# ===========================================================================
# GET /api/v1/purchases/{order_id} — order details
# ===========================================================================


async def test_get_order_details(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.get(
        f"/api/v1/purchases/{order_id}", headers=_auth(client_token)
    )
    assert resp.status_code == 200
    order = resp.json()["order"]
    assert order["id"] == order_id
    assert order["status"] == "reserved"
    assert float(order["total_price"]) == pytest.approx(2_000_000.0)


async def test_get_order_details_not_found(
    client: AsyncClient,
    client_token: str,
    client_user: User,
) -> None:
    resp = await client.get(
        "/api/v1/purchases/736ce387-8b3d-4ef4-a83d-b55b9c4b0fde", headers=_auth(client_token)
    )
    assert resp.status_code == 404


async def test_get_order_details_wrong_owner(
    client: AsyncClient,
    client_token: str,
    other_token: str,
    test_vehicle: Vehicle,
) -> None:
    """A different client should get 403 when accessing another user's order."""
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.get(
        f"/api/v1/purchases/{order_id}", headers=_auth(other_token)
    )
    assert resp.status_code == 403


# ===========================================================================
# GET /api/v1/purchases/{order_id}/payments
# ===========================================================================


async def test_list_payments_after_creation(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.get(
        f"/api/v1/purchases/{order_id}/payments", headers=_auth(client_token)
    )
    assert resp.status_code == 200
    payments = resp.json()["payments"]
    assert len(payments) == 1
    assert payments[0]["payment_type"] == "reservation"
    assert payments[0]["status"] == "completed"
    assert float(payments[0]["amount"]) == pytest.approx(200_000.0)


async def test_list_payments_full_purchase(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_full_purchase(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.get(
        f"/api/v1/purchases/{order_id}/payments", headers=_auth(client_token)
    )
    assert resp.status_code == 200
    payments = resp.json()["payments"]
    assert len(payments) == 1
    assert payments[0]["payment_type"] == "full_purchase"
    assert payments[0]["status"] == "completed"
    assert float(payments[0]["amount"]) == pytest.approx(2_000_000.0)


# ===========================================================================
# POST /api/v1/purchases/{order_id}/payments — scope=remaining
# ===========================================================================


async def test_pay_remaining_bank_transfer(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchases/{order_id}/payments",
        headers=_auth(client_token),
        json={"scope": "remaining", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 201
    result = resp.json()
    assert result["order"]["status"] == "purchased"
    assert float(result["order"]["paid_amount"]) == pytest.approx(2_000_000.0)
    assert float(result["order"]["remaining_amount"]) == pytest.approx(0.0)
    assert result["payment"]["payment_type"] == "remaining_balance"
    assert result["payment"]["status"] == "completed"


async def test_pay_remaining_wrong_status(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    """Paying remaining on an already-purchased order should fail."""
    data = await _create_full_purchase(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchases/{order_id}/payments",
        headers=_auth(client_token),
        json={"scope": "remaining", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 400


async def test_pay_remaining_employee_forbidden(
    client: AsyncClient,
    client_token: str,
    employee_token: str,
    test_vehicle: Vehicle,
) -> None:
    """carcraft_employee cannot pay remaining — only client role is allowed."""
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchases/{order_id}/payments",
        headers=_auth(employee_token),
        json={"scope": "remaining", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 403


async def test_create_payment_invalid_scope(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    """Invalid scope value — 422."""
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchases/{order_id}/payments",
        headers=_auth(client_token),
        json={"scope": "invalid", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 422


async def test_create_payment_scheduled_without_schedule_id(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    """scope=scheduled without schedule_id — 422."""
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchases/{order_id}/payments",
        headers=_auth(client_token),
        json={"scope": "scheduled", "payment_method": "bank_transfer"},
    )
    assert resp.status_code == 422


# ===========================================================================
# POST /api/v1/purchases/{order_id}/request-cancellation
# ===========================================================================


async def test_vehicle_order_helper_uses_global_lock_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_id = uuid4()
    user_id = uuid4()
    vehicle_id = uuid4()
    calls: list[str] = []
    locked_order = {
        "id": order_id,
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "status": "reserved",
    }

    async def get_route(
        _session: object,
        requested_order_id: UUID,
    ) -> dict[str, UUID]:
        assert requested_order_id == order_id
        calls.append("route")
        return {
            "id": order_id,
            "user_id": user_id,
            "vehicle_id": vehicle_id,
        }

    async def lock_vehicle(
        _session: object,
        requested_vehicle_id: UUID,
    ) -> dict[str, Any]:
        assert requested_vehicle_id == vehicle_id
        calls.append("vehicle")
        return {"id": vehicle_id, "status": "reserved"}

    async def lock_order(
        _session: object,
        requested_order_id: UUID,
    ) -> dict[str, Any]:
        assert requested_order_id == order_id
        calls.append("order")
        return locked_order

    monkeypatch.setattr(
        purchase_commands.repo,
        "get_order_lock_route",
        get_route,
    )
    monkeypatch.setattr(
        purchase_commands.repo,
        "get_vehicle_for_update",
        lock_vehicle,
    )
    monkeypatch.setattr(
        purchase_commands.repo,
        "get_order_for_update",
        lock_order,
    )

    order, raw = await purchase_commands._lock_vehicle_order(
        object(),  # type: ignore[arg-type]
        order_id,
        user_id=user_id,
    )

    assert order.id == order_id
    assert raw == locked_order
    assert calls == ["route", "vehicle", "order"]


async def test_request_cancellation(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchases/{order_id}/request-cancellation",
        headers=_auth(client_token),
        json={"reason": "Передумал"},
    )
    assert resp.status_code == 200
    order = resp.json()["order"]
    assert order["status"] == "cancellation_requested"
    assert order["cancellation_reason"] == "Передумал"
    assert order["cancellation_requested_at"] is not None


async def test_request_cancellation_already_cancelled(
    client: AsyncClient,
    client_token: str,
    employee_token: str,
    test_vehicle: Vehicle,
) -> None:
    """Cannot request cancellation when already in cancellation_requested state."""
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    # First request
    resp = await client.post(
        f"/api/v1/purchases/{order_id}/request-cancellation",
        headers=_auth(client_token),
        json={"reason": "Первый раз"},
    )
    assert resp.status_code == 200

    # Second request should fail
    resp2 = await client.post(
        f"/api/v1/purchases/{order_id}/request-cancellation",
        headers=_auth(client_token),
        json={"reason": "Второй раз"},
    )
    assert resp2.status_code == 400


async def test_request_cancellation_employee_forbidden(
    client: AsyncClient,
    client_token: str,
    employee_token: str,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchases/{order_id}/request-cancellation",
        headers=_auth(employee_token),
        json={"reason": "test"},
    )
    assert resp.status_code == 403


# ===========================================================================
# POST /api/v1/purchases/{order_id}/cancel — approve cancellation
# ===========================================================================


async def test_approve_cancellation(
    client: AsyncClient,
    client_token: str,
    employee_token: str,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    # Client requests cancellation
    await client.post(
        f"/api/v1/purchases/{order_id}/request-cancellation",
        headers=_auth(client_token),
        json={"reason": "test"},
    )

    # Employee approves
    resp = await client.post(
        f"/api/v1/purchases/{order_id}/cancel",
        headers=_auth(employee_token),
    )
    assert resp.status_code == 200
    order = resp.json()["order"]
    assert order["status"] == "cancelled"
    assert order["cancelled_at"] is not None


async def test_approve_cancellation_wrong_status(
    client: AsyncClient,
    client_token: str,
    employee_token: str,
    test_vehicle: Vehicle,
) -> None:
    """Cannot approve cancellation on a plain reserved order."""
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchases/{order_id}/cancel",
        headers=_auth(employee_token),
    )
    assert resp.status_code == 400


async def test_approve_cancellation_client_forbidden(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    resp = await client.post(
        f"/api/v1/purchases/{order_id}/cancel",
        headers=_auth(client_token),
    )
    assert resp.status_code == 403


# ===========================================================================
# Full workflow: reserve → pay remaining → verify payments list
# ===========================================================================


async def test_full_reservation_to_purchase_workflow(
    client: AsyncClient,
    client_token: str,
    test_vehicle: Vehicle,
) -> None:
    # 1. Create reservation
    data = await _create_reservation(
        client, client_token, test_vehicle.id, down_payment_percent=20.0
    )
    order_id = data["orders"][0]["id"]
    assert data["orders"][0]["status"] == "reserved"
    assert float(data["orders"][0]["paid_amount"]) == pytest.approx(400_000.0)

    # 2. Pay remaining
    pay_resp = await client.post(
        f"/api/v1/purchases/{order_id}/payments",
        headers=_auth(client_token),
        json={"scope": "remaining", "payment_method": "bank_transfer"},
    )
    assert pay_resp.status_code == 201
    assert pay_resp.json()["order"]["status"] == "purchased"

    # 3. Verify payment history
    payments_resp = await client.get(
        f"/api/v1/purchases/{order_id}/payments", headers=_auth(client_token)
    )
    payments = payments_resp.json()["payments"]
    assert len(payments) == 2
    types = {p["payment_type"] for p in payments}
    assert types == {"reservation", "remaining_balance"}
    assert all(p["status"] == "completed" for p in payments)

    # 4. Order appears with status=purchased in list
    list_resp = await client.get(
        "/api/v1/purchases?status=purchased", headers=_auth(client_token)
    )
    orders = list_resp.json()["orders"]
    assert len(orders) == 1
    assert orders[0]["id"] == order_id


# ===========================================================================
# Full workflow: reserve → request cancellation → approve
# ===========================================================================


async def test_full_cancellation_workflow(
    client: AsyncClient,
    client_token: str,
    employee_token: str,
    test_vehicle: Vehicle,
) -> None:
    # 1. Reserve
    data = await _create_reservation(client, client_token, test_vehicle.id)
    order_id = data["orders"][0]["id"]

    # 2. Vehicle now reserved — should appear in my-vehicle-ids
    ids_resp = await client.get(
        "/api/v1/purchases/my-vehicle-ids", headers=_auth(client_token)
    )
    assert len(ids_resp.json()["vehicles"]) == 1

    # 3. Client requests cancellation
    cancel_req = await client.post(
        f"/api/v1/purchases/{order_id}/request-cancellation",
        headers=_auth(client_token),
        json={"reason": "Нашел дешевле"},
    )
    assert cancel_req.json()["order"]["status"] == "cancellation_requested"

    # 4. Employee approves
    approve = await client.post(
        f"/api/v1/purchases/{order_id}/cancel",
        headers=_auth(employee_token),
    )
    assert approve.json()["order"]["status"] == "cancelled"

    # 5. Cancelled order no longer in active vehicle ids
    ids_after = await client.get(
        "/api/v1/purchases/my-vehicle-ids", headers=_auth(client_token)
    )
    assert ids_after.json()["vehicles"] == []
