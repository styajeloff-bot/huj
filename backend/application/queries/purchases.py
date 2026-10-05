"""Purchase queries and handlers."""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.purchase_order import PurchaseOrder
from domain.errors import AccessDeniedError, OrderNotFoundError, PaymentNotFoundError
from infrastructure.repositories import purchase_repository as repo
from infrastructure.services import payment_gateway
from infrastructure.services.payment_models import PaymentStatusDetails

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass
class GetUserOrdersQuery:
    user_id: UUID
    status_filter: str | None = None


@dataclass
class GetActiveVehicleIdsQuery:
    user_id: UUID


@dataclass
class GetOrderDetailsQuery:
    user_id: UUID
    order_id: UUID


@dataclass
class GetOrderPaymentsQuery:
    user_id: UUID
    order_id: UUID


@dataclass
class GetOrderScheduleQuery:
    user_id: UUID
    order_id: UUID


@dataclass
class GetPaymentReceiptQuery:
    user_id: UUID
    payment_id: UUID


@dataclass
class GetPaymentStatusQuery:
    payment_id: UUID


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_get_user_orders(
    query: GetUserOrdersQuery,
    session: AsyncSession,
) -> list[Any]:
    return await repo.get_by_user_id(session, query.user_id, query.status_filter)  # type: ignore[no-any-return]


async def handle_get_active_vehicle_ids(
    query: GetActiveVehicleIdsQuery,
    session: AsyncSession,
) -> list[Any]:
    return await repo.get_active_vehicle_ids_by_user(session, query.user_id)  # type: ignore[no-any-return]


async def handle_get_order_details(
    query: GetOrderDetailsQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    order_dict = await repo.get_by_id_with_details(session, query.order_id)
    if order_dict is None:
        raise OrderNotFoundError()
    PurchaseOrder.from_dict(order_dict).ensure_owned_by(query.user_id)
    return order_dict  # type: ignore[no-any-return]


async def handle_get_order_payments(
    query: GetOrderPaymentsQuery,
    session: AsyncSession,
) -> list[Any]:
    order_dict = await repo.get_by_id_with_details(session, query.order_id)
    if order_dict is None:
        raise OrderNotFoundError()
    PurchaseOrder.from_dict(order_dict).ensure_owned_by(query.user_id)
    return await repo.get_payments_by_order_id(session, query.order_id)  # type: ignore[no-any-return]


async def handle_get_order_schedule(
    query: GetOrderScheduleQuery,
    session: AsyncSession,
) -> list[Any]:
    order_dict = await repo.get_by_id_with_details(session, query.order_id)
    if order_dict is None:
        raise OrderNotFoundError()
    order = PurchaseOrder.from_dict(order_dict)
    order.ensure_owned_by(query.user_id)
    order.ensure_has_schedule()
    return await repo.get_schedule_by_order_id(session, query.order_id)  # type: ignore[no-any-return]


async def handle_get_payment_receipt(
    query: GetPaymentReceiptQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    payment = await repo.get_payment_by_id(session, query.payment_id)
    if not payment:
        raise PaymentNotFoundError()
    if payment.get("order_user_id") != query.user_id and payment.get("user_id") != query.user_id:
        raise AccessDeniedError("Нет доступа к данному платежу")

    order = await repo.get_by_id_with_details(session, payment["purchase_order_id"])
    if not order:
        raise OrderNotFoundError()

    return {
        "payment": payment,
        "order": {
            "id": order["id"],
            "total_price": order["total_price"],
            "mark_name": order.get("mark_name"),
            "model_name": order.get("model_name"),
            "vin": order.get("vin"),
            "vehicle_year": order.get("vehicle_year"),
        },
    }


async def handle_get_payment_status(
    query: GetPaymentStatusQuery,
    session: AsyncSession,
) -> PaymentStatusDetails | None:
    return await payment_gateway.get_payment_status(query.payment_id, session)
