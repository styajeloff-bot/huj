
"""Purchase commands and handlers."""
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.errors import ServiceError
from domain.entities.payment import Payment, validate_schedule_item
from domain.entities.purchase_order import PurchaseOrder
from domain.errors import (
    InsufficientVehiclesError,
    OrderNotFoundError,
    PriceUnavailableError,
    VehicleNotAvailableError,
    VehicleNotFoundError,
)
from domain.values import OrderStatus, PaymentMethod, PaymentStatus, VehicleStatus
from infrastructure.repositories import purchase_repository as repo
from infrastructure.services import payment_gateway
from infrastructure.services.payment_models import (
    ModulbankPaymentResponse,
    ModulbankSbpResponse,
)

logger = logging.getLogger("carcraft-backend")
_ACTIVE_PAYMENT_STATUSES = frozenset(
    {PaymentStatus.PENDING.value, PaymentStatus.PROCESSING.value}
)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass
class CreatePurchaseOrdersCommand:
    user_id: UUID
    items: list[dict]
    purchase_type: str
    payment_method: str | None = None
    down_payment_percent: float | None = None


@dataclass
class PayRemainingCommand:
    user_id: UUID
    order_id: UUID
    payment_method: str | None = None


@dataclass
class RequestCancellationCommand:
    user_id: UUID
    order_id: UUID
    reason: str | None = None


@dataclass
class ApproveCancellationCommand:
    order_id: UUID
    user_id: UUID | None = None


@dataclass
class PayScheduleItemCommand:
    user_id: UUID
    order_id: UUID
    schedule_id: UUID
    payment_method: str | None = None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_create_purchase_orders(
    cmd: CreatePurchaseOrdersCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Create purchase orders for the given items."""
    use_gateway = Payment.uses_gateway(cmd.payment_method)
    expires_at = Payment.compute_expiry(use_gateway)
    created_orders: list[dict] = []

    for item in cmd.items:
        quantity = max(1, item.get("quantity", 1))
        vehicle_id = item["vehicle_id"]

        vehicle = await repo.get_vehicle_for_update(session, vehicle_id)
        if not vehicle:
            raise VehicleNotFoundError(vehicle_id)

        if vehicle["status"] != VehicleStatus.AVAILABLE:
            await _try_reclaim_vehicle(session, vehicle_id, cmd.user_id)

        assert vehicle is not None
        vehicle_ids = await _resolve_vehicle_ids(
            session, vehicle_id, vehicle, quantity
        )

        for vid in vehicle_ids:
            order, payment = await _create_single_order(
                session, cmd, vid, use_gateway, expires_at
            )
            created_orders.append({**order, "payment_id": payment["id"]})

        await repo.remove_from_cart_in_transaction(session, cmd.user_id, vehicle_id)

    # Flush before gateway calls — router will commit
    await session.flush()

    # Outside transaction: request gateway payment data
    widget_data = None
    sbp_data = None
    if use_gateway and created_orders:
        pid = created_orders[0]["payment_id"]
        widget_data, sbp_data = await _request_gateway_data(
            pid, cmd.payment_method, session
        )

    logger.info(
        "Created %d purchase orders for user %s, type: %s",
        len(created_orders), cmd.user_id, cmd.purchase_type,
    )
    return {"orders": created_orders, "widgetData": widget_data, "sbpData": sbp_data}


async def handle_pay_remaining(
    cmd: PayRemainingCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Pay remaining balance on a reserved order."""
    order, order_dict = await _load_order_for_payment_attempt(
        session, cmd.order_id, cmd.user_id
    )
    amount = order.ensure_can_pay_remaining()

    use_gateway = Payment.uses_gateway(cmd.payment_method)
    expires_at = Payment.compute_expiry(use_gateway)

    payment_data: dict = {
        "purchase_order_id": cmd.order_id,
        "user_id": cmd.user_id,
        "payment_type": "remaining_balance",
        "amount": amount,
        "status": Payment.initial_status(use_gateway),
        "payment_method": cmd.payment_method,
    }
    if expires_at:
        payment_data["expires_at"] = expires_at

    payment = await repo.create_payment(session, payment_data)

    if use_gateway:
        payment = await repo.update_payment(
            session,
            payment["id"],
            {"gateway_transaction_id": f"CARCRAFT-{payment['id']}"},
        )
        logger.info(
            "User %s initiated remaining payment %.2f on order %s",
            cmd.user_id, amount, cmd.order_id,
        )
        widget_data, sbp_data = await _request_gateway_data(
            payment["id"], cmd.payment_method, session
        )
        result: dict = {"order": order_dict, "payment": payment}
        if sbp_data:
            result["sbpData"] = sbp_data
        else:
            result["widgetData"] = widget_data
        return result

    updated_order = await repo.update_order(
        session,
        cmd.order_id,
        {
            "paid_amount": order.paid_amount + amount,
            "remaining_amount": Decimal("0.00"),
            "status": OrderStatus.PURCHASED,
        },
    )
    await repo.update_vehicle_status_in_transaction(session, order.vehicle_id, VehicleStatus.SOLD)
    from infrastructure.messaging.status_events import emit_vehicle_status_changed
    emit_vehicle_status_changed(
        vehicle_id=order.vehicle_id,
        old_status="reserved",
        new_status=VehicleStatus.SOLD,
        changed_by=cmd.user_id,
    )
    updated_payment = await repo.update_payment(
        session, payment["id"],
        {"status": PaymentStatus.COMPLETED, "paid_at": datetime.now(UTC)},
    )

    from infrastructure.messaging.dwh_events import emit_purchase_order_changed
    emit_purchase_order_changed({
        "order_id": cmd.order_id,
        "user_id": cmd.user_id,
        "vehicle_id": order.vehicle_id,
        "purchase_type": order.purchase_type,
        "status": updated_order.get("status"),
        "total_price": str(updated_order.get("total_price")) if updated_order.get("total_price") else None,
        "paid_amount": str(updated_order.get("paid_amount")) if updated_order.get("paid_amount") else "0",
        "remaining_amount": str(updated_order.get("remaining_amount")) if updated_order.get("remaining_amount") else "0",
        "leasing_application_id": None,
        "cancellation_reason": None,
        "cancellation_requested_at": None,
        "cancelled_at": None,
        "created_at": None,
        "updated_at": None,
        "_deleted": False,
    })
    logger.info("User %s paid remaining %.2f on order %s", cmd.user_id, amount, cmd.order_id)
    return {"order": updated_order, "payment": updated_payment}


async def handle_request_cancellation(
    cmd: RequestCancellationCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Request cancellation of an order."""
    order, _locked_order = await _lock_vehicle_order(
        session,
        cmd.order_id,
        user_id=cmd.user_id,
    )
    order.ensure_can_request_cancellation()

    # Vehicle financial mutations use one global lock order: vehicle, purchase
    # order, then its payments. A pending provider callback therefore either
    # wins before this cancellation (and the paid order enters cancellation
    # review) or observes the failed payment afterwards; it can never
    # resurrect the order by overwriting ``cancellation_requested``.
    payments = await repo.get_payments_by_order_id(session, cmd.order_id)
    for candidate in sorted(payments, key=lambda payment: str(payment["id"])):
        if candidate.get("status") not in _ACTIVE_PAYMENT_STATUSES:
            continue
        payment = await repo.get_payment_by_id_for_update(
            session,
            candidate["id"],
        )
        if payment is None or payment.get("status") not in _ACTIVE_PAYMENT_STATUSES:
            continue
        await repo.update_payment(
            session,
            payment["id"],
            {
                "status": PaymentStatus.FAILED,
                "error_message": (
                    "Order cancellation requested before payment completion"
                ),
            },
        )

    updated = await repo.update_order(
        session,
        cmd.order_id,
        {
            "status": OrderStatus.CANCELLATION_REQUESTED,
            "cancellation_reason": cmd.reason,
            "cancellation_requested_at": datetime.now(UTC),
        },
    )
    from infrastructure.messaging.dwh_events import emit_purchase_order_changed
    emit_purchase_order_changed({
        "order_id": cmd.order_id,
        "user_id": cmd.user_id,
        "vehicle_id": order.vehicle_id,
        "purchase_type": order.purchase_type,
        "status": updated.get("status"),
        "total_price": str(updated.get("total_price")) if updated.get("total_price") else None,
        "paid_amount": str(updated.get("paid_amount")) if updated.get("paid_amount") else "0",
        "remaining_amount": str(updated.get("remaining_amount")) if updated.get("remaining_amount") else "0",
        "leasing_application_id": None,
        "cancellation_reason": updated.get("cancellation_reason"),
        "cancellation_requested_at": _isoformat(updated.get("cancellation_requested_at")),
        "cancelled_at": None,
        "created_at": None,
        "updated_at": None,
        "_deleted": False,
    })
    logger.info("User %s requested cancellation of order %s", cmd.user_id, cmd.order_id)
    return {"order": updated}


async def handle_approve_cancellation(
    cmd: ApproveCancellationCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Approve a pending cancellation."""
    order, _locked_order = await _lock_vehicle_order(session, cmd.order_id)
    order.ensure_can_approve_cancellation()

    updated = await repo.update_order(
        session,
        cmd.order_id,
        {"status": OrderStatus.CANCELLED, "cancelled_at": datetime.now(UTC)},
    )
    await repo.update_vehicle_status_in_transaction(session, order.vehicle_id, VehicleStatus.AVAILABLE)
    from infrastructure.messaging.status_events import emit_vehicle_status_changed
    emit_vehicle_status_changed(
        vehicle_id=order.vehicle_id,
        old_status="reserved",
        new_status=VehicleStatus.AVAILABLE,
        changed_by=cmd.user_id,
    )
    from infrastructure.messaging.dwh_events import emit_purchase_order_changed
    emit_purchase_order_changed({
        "order_id": cmd.order_id,
        "user_id": order.user_id,
        "vehicle_id": order.vehicle_id,
        "purchase_type": order.purchase_type,
        "status": updated.get("status"),
        "total_price": str(updated.get("total_price")) if updated.get("total_price") else None,
        "paid_amount": str(updated.get("paid_amount")) if updated.get("paid_amount") else "0",
        "remaining_amount": str(updated.get("remaining_amount")) if updated.get("remaining_amount") else "0",
        "leasing_application_id": None,
        "cancellation_reason": updated.get("cancellation_reason"),
        "cancellation_requested_at": _isoformat(updated.get("cancellation_requested_at")),
        "cancelled_at": _isoformat(updated.get("cancelled_at")),
        "created_at": None,
        "updated_at": None,
        "_deleted": False,
    })
    logger.info(
        "Cancellation approved for order %s, vehicle %s returned to available",
        cmd.order_id, order.vehicle_id,
    )
    return {"order": updated}


async def handle_pay_schedule_item(
    cmd: PayScheduleItemCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Pay a leasing schedule installment."""
    order, _order_dict = await _load_order_for_payment_attempt(
        session, cmd.order_id, cmd.user_id
    )
    order.ensure_can_pay_schedule()

    schedule_item = await repo.get_schedule_item(session, cmd.schedule_id)
    schedule_item = validate_schedule_item(schedule_item, cmd.order_id)

    use_gateway = Payment.uses_gateway(cmd.payment_method)
    amount = Decimal(str(schedule_item["amount"]))
    expires_at = Payment.compute_expiry(use_gateway)

    payment_data: dict = {
        "purchase_order_id": cmd.order_id,
        "user_id": cmd.user_id,
        "payment_type": "leasing_monthly",
        "amount": amount,
        "status": Payment.initial_status(use_gateway),
        "payment_method": cmd.payment_method,
        "gateway_response": {"schedule_id": str(cmd.schedule_id)} if cmd.schedule_id else None,
    }
    if expires_at:
        payment_data["expires_at"] = expires_at

    payment = await repo.create_payment(session, payment_data)

    if use_gateway:
        schedule_item = await repo.link_schedule_item_payment(
            session,
            cmd.schedule_id,
            payment["id"],
        )
        payment = await repo.update_payment(
            session,
            payment["id"],
            {"gateway_transaction_id": f"CARCRAFT-{payment['id']}"},
        )
        logger.info(
            "User %s initiated leasing payment #%d for order %s",
            cmd.user_id, schedule_item["payment_number"], cmd.order_id,
        )
        widget_data, sbp_data = await _request_gateway_data(
            payment["id"], cmd.payment_method, session
        )
        result: dict = {"payment": payment, "scheduleItem": schedule_item}
        if sbp_data:
            result["sbpData"] = sbp_data
        else:
            result["widgetData"] = widget_data
        return result

    await repo.update_payment(
        session, payment["id"],
        {"status": PaymentStatus.COMPLETED, "paid_at": datetime.now(UTC)},
    )
    await repo.mark_schedule_item_paid(session, cmd.schedule_id, payment["id"])
    updated_order = await repo.update_order(
        session,
        cmd.order_id,
        {"paid_amount": order.paid_amount + amount},
    )
    from infrastructure.messaging.dwh_events import emit_purchase_order_changed
    emit_purchase_order_changed({
        "order_id": cmd.order_id,
        "user_id": cmd.user_id,
        "vehicle_id": order.vehicle_id,
        "purchase_type": order.purchase_type,
        "status": updated_order.get("status"),
        "total_price": str(updated_order.get("total_price")) if updated_order.get("total_price") else None,
        "paid_amount": str(updated_order.get("paid_amount")) if updated_order.get("paid_amount") else "0",
        "remaining_amount": str(updated_order.get("remaining_amount")) if updated_order.get("remaining_amount") else "0",
        "leasing_application_id": None,
        "cancellation_reason": updated_order.get("cancellation_reason"),
        "cancellation_requested_at": _isoformat(updated_order.get("cancellation_requested_at")),
        "cancelled_at": _isoformat(updated_order.get("cancelled_at")),
        "created_at": None,
        "updated_at": None,
        "_deleted": False,
    })

    logger.info(
        "User %s paid leasing installment #%d for order %s",
        cmd.user_id, schedule_item["payment_number"], cmd.order_id,
    )
    return {
        "payment": payment,
        "scheduleItem": {**schedule_item, "is_paid": True, "payment_id": payment["id"]},
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _lock_vehicle_order(
    session: AsyncSession,
    order_id: UUID,
    *,
    user_id: UUID | None = None,
) -> tuple[PurchaseOrder, dict[str, Any]]:
    """Lock a vehicle and its order in the global commerce lock order."""

    route = await repo.get_order_lock_route(session, order_id)
    if route is None:
        raise OrderNotFoundError()
    if user_id is not None:
        PurchaseOrder.from_dict(route).ensure_owned_by(user_id)

    vehicle = await repo.get_vehicle_for_update(session, route["vehicle_id"])
    if vehicle is None:
        raise VehicleNotFoundError(route["vehicle_id"])

    locked = await repo.get_order_for_update(session, order_id)
    if locked is None:
        raise OrderNotFoundError()
    if locked["vehicle_id"] != route["vehicle_id"]:
        raise ServiceError("Заказ был изменён, повторите операцию", 409)

    order = PurchaseOrder.from_dict(locked)
    if user_id is not None:
        order.ensure_owned_by(user_id)
    return order, locked  # type: ignore[return-value]


async def _load_order_for_payment_attempt(
    session: AsyncSession,
    order_id: UUID,
    user_id: UUID,
) -> tuple[PurchaseOrder, dict[str, Any]]:
    """Lock vehicle/order and fail closed while a provider payment is active."""

    order, locked = await _lock_vehicle_order(
        session,
        order_id,
        user_id=user_id,
    )
    payments = await repo.get_payments_by_order_id(session, order_id)
    if any(payment.get("status") in _ACTIVE_PAYMENT_STATUSES for payment in payments):
        raise ServiceError(
            "Для заказа уже выполняется платёж. Проверьте его статус перед "
            "повторной попыткой",
            409,
        )
    details = await repo.get_by_id_with_details(session, order_id)
    return order, details or locked


async def _try_reclaim_vehicle(
    session: AsyncSession, vehicle_id: UUID, user_id: UUID
) -> None:
    """If user has a stale unpaid order for this vehicle, cancel it."""
    existing = await repo.find_active_order_by_vehicle_and_user(
        session, vehicle_id, user_id
    )
    if not existing:
        raise VehicleNotAvailableError(vehicle_id)

    payments = await repo.get_payments_by_order_id(
        session, existing["id"]
    )
    if any(p["status"] == PaymentStatus.COMPLETED for p in payments):
        raise VehicleNotAvailableError(vehicle_id)

    for p in payments:
        if p["status"] == PaymentStatus.PENDING:
            await repo.update_payment(
                session, p["id"],
                {"status": PaymentStatus.FAILED, "error_message": "Replaced by new payment attempt"},
            )
    await repo.update_order(session, existing["id"], {"status": OrderStatus.CANCELLED})
    await repo.update_vehicle_status_in_transaction(session, vehicle_id, VehicleStatus.AVAILABLE)
    from infrastructure.messaging.status_events import emit_vehicle_status_changed
    emit_vehicle_status_changed(
        vehicle_id=vehicle_id,
        old_status="reserved",
        new_status=VehicleStatus.AVAILABLE,
        changed_by=user_id,
    )


async def _resolve_vehicle_ids(
    session: AsyncSession,
    primary_id: UUID,
    vehicle: dict[str, Any],
    quantity: int,
) -> list[UUID]:
    """Build a list of vehicle IDs honouring quantity."""
    ids: list[UUID] = [primary_id]
    if quantity == 1:
        return ids
    complectation_id = vehicle.get("complectation_id")
    if not complectation_id:
        raise InsufficientVehiclesError(requested=quantity, available=1)
    extra = await repo.get_additional_available_vehicle_ids(
        session, complectation_id, primary_id, quantity - 1
    )
    if len(extra) < quantity - 1:
        raise InsufficientVehiclesError(
            requested=quantity, available=1 + len(extra)
        )
    ids.extend(extra)
    return ids


async def _create_single_order(
    session: AsyncSession,
    cmd: CreatePurchaseOrdersCommand,
    vehicle_id: UUID,
    use_gateway: bool,
    expires_at: datetime | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create one order + its first payment inside a running transaction."""
    price_data = await repo.get_vehicle_price(session, vehicle_id)
    effective_price = price_data["effective_price"] if price_data else None
    if not effective_price:
        raise PriceUnavailableError(vehicle_id)

    total_price = Decimal(str(effective_price))
    payment_amount, initial_paid, initial_remaining, order_status, payment_type = (
        PurchaseOrder.compute_amounts(cmd.purchase_type, total_price, use_gateway, cmd.down_payment_percent)
    )

    order = await repo.create_in_transaction(
        session,
        {
            "user_id": cmd.user_id,
            "vehicle_id": vehicle_id,
            "purchase_type": cmd.purchase_type,
            "status": order_status,
            "total_price": total_price,
            "paid_amount": initial_paid,
            "remaining_amount": initial_remaining,
        },
    )

    payment_data: dict = {
        "purchase_order_id": order["id"],
        "user_id": cmd.user_id,
        "payment_type": payment_type,
        "amount": payment_amount,
        "status": Payment.initial_status(use_gateway),
        "payment_method": cmd.payment_method,
    }
    if expires_at:
        payment_data["expires_at"] = expires_at

    payment = await repo.create_payment(session, payment_data)

    if use_gateway:
        payment = await repo.update_payment(
            session,
            payment["id"],
            {"gateway_transaction_id": f"CARCRAFT-{payment['id']}"},
        )

    if not use_gateway:
        await repo.update_payment(
            session, payment["id"],
            {"status": PaymentStatus.COMPLETED, "paid_at": datetime.now(UTC)},
        )

    target_status = PurchaseOrder.target_vehicle_status(cmd.purchase_type)
    await repo.update_vehicle_status_in_transaction(session, vehicle_id, target_status)

    from infrastructure.messaging.dwh_events import emit_purchase_order_changed
    emit_purchase_order_changed({
        "order_id": order["id"],
        "user_id": cmd.user_id,
        "vehicle_id": vehicle_id,
        "purchase_type": cmd.purchase_type,
        "status": order["status"],
        "total_price": str(order["total_price"]) if order.get("total_price") else None,
        "paid_amount": str(order["paid_amount"]) if order.get("paid_amount") else "0",
        "remaining_amount": str(order["remaining_amount"]) if order.get("remaining_amount") else "0",
        "leasing_application_id": None,
        "cancellation_reason": None,
        "cancellation_requested_at": None,
        "cancelled_at": None,
        "created_at": None,
        "updated_at": None,
        "_deleted": False,
    })

    return order, payment  # type: ignore[return-value]


async def _request_gateway_data(
    payment_id: UUID,
    payment_method: str | None,
    session: AsyncSession,
) -> tuple[ModulbankPaymentResponse | None, ModulbankSbpResponse | None]:
    """Call payment gateway and return (widget_data, sbp_data)."""
    if payment_method == PaymentMethod.SBP:
        return None, await payment_gateway.request_sbp_link(payment_id, session)
    return await payment_gateway.prepare_payment(payment_id, session), None
