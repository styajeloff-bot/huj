"""Purchase repository — SQLAlchemy ORM."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, TypedDict, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from domain.commerce import VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE
from domain.values import OrderStatus, PaymentStatus
from infrastructure.models.applications import ShoppingCart
from infrastructure.models.payments import (
    LeasingPaymentSchedule,
    Payment,
    PurchaseOrder,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.users import User
from infrastructure.models.vehicles import City, Warehouse
from infrastructure.repository_timing import timed_repository

# ---------------------------------------------------------------------------
# TypedDicts — repository return contracts
# ---------------------------------------------------------------------------

class OrderDict(TypedDict, total=False):
    id: UUID
    user_id: UUID
    product_id: UUID
    vehicle_id: UUID
    purchase_type: str
    status: str
    total_price: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    leasing_application_id: uuid.UUID | None
    cancellation_reason: str | None
    cancellation_requested_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OrderLockRoute(TypedDict, total=False):
    """Immutable identifiers needed to acquire commerce locks in order."""

    id: UUID
    user_id: UUID
    product_id: UUID
    vehicle_id: UUID


class OrderDetailDict(OrderDict):
    vin: str | None
    color: str | None
    vehicle_year: int | None
    images: Any
    vehicle_status: str | None
    vehicle_base_price: Decimal | None
    vehicle_discount_price: Decimal | None
    mark_name: str | None
    mark_cyrillic: str | None
    model_name: str | None
    model_cyrillic: str | None
    generation_name: str | None
    configuration_name: str | None
    modification_name: str | None
    warehouse_name: str | None
    warehouse_address: str | None
    warehouse_brand: str | None

class OrderSummaryDict(OrderDict):
    vin: str | None
    color: str | None
    vehicle_year: int | None
    images: Any
    vehicle_status: str | None
    mark_name: str | None
    mark_cyrillic: str | None
    model_name: str | None
    model_cyrillic: str | None
    generation_name: str | None
    configuration_name: str | None
    modification_name: str | None
    warehouse_name: str | None
    warehouse_address: str | None
    warehouse_brand: str | None
    base_price: Decimal | None
    discount_price: Decimal | None

class PaymentDict(TypedDict, total=False):
    id: UUID
    purchase_order_id: UUID
    user_id: UUID
    payment_type: str
    amount: Decimal
    status: str
    gateway_transaction_id: str | None
    gateway_response: dict[str, Any] | None
    receipt_url: str | None
    receipt_s3_key: str | None
    error_message: str | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime
    payment_method: str | None
    fiscal_status: str | None
    fiscal_receipt_id: str | None
    fiscal_response: dict[str, Any] | None
    fiscal_retry_count: int | None
    fiscal_error_message: str | None
    expires_at: datetime | None
    order_user_id: UUID


class PaymentWithOrderDict(PaymentDict):
    order_product_id: UUID
    order_vehicle_id: UUID


class ScheduleItemDict(TypedDict):
    id: UUID
    purchase_order_id: UUID
    payment_number: int
    due_date: date
    amount: Decimal
    principal: Decimal | None
    interest: Decimal | None
    payment_id: UUID | None
    is_paid: bool
    created_at: datetime

class ScheduleItemWithPaymentDict(ScheduleItemDict):
    payment_status: str | None
    payment_paid_at: datetime | None
    receipt_url: str | None

class VehicleLockDict(TypedDict):
    id: UUID
    status: str | None
    complectation_id: str | None

class VehiclePriceDict(TypedDict):
    id: UUID
    effective_price: Decimal | None

class ActiveVehicleDict(TypedDict, total=False):
    product_id: UUID
    vehicle_id: UUID
    status: str
    purchase_type: str

class ExpiredPaymentDict(PaymentDict):
    product_id: UUID
    vehicle_id: UUID
    order_status: str

class UserInfoDict(TypedDict, total=False):
    phone: str | None
    email: str | None
    name: str | None

# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _to_dict(obj: Any) -> Any:
    """Convert an ORM instance to a plain dict of column values."""
    if obj is None:
        return None
    d = {c.key: getattr(obj, c.key) for c in sa_inspect(obj).mapper.column_attrs}
    if "product_id" in d and "vehicle_id" not in d:
        d["vehicle_id"] = d["product_id"]
    return d

def _rows(result: Any) -> Any:
    """Convert a mapped select() result to a list of plain dicts."""
    return [dict(row._mapping) for row in result.all()]

# ---------------------------------------------------------------------------
# Reusable column lists for complex JOINs
# ---------------------------------------------------------------------------

_ORDER_COLS = [
    PurchaseOrder.id,
    PurchaseOrder.user_id,
    PurchaseOrder.product_id,
    PurchaseOrder.product_id.label("vehicle_id"),
    PurchaseOrder.purchase_type,
    PurchaseOrder.status,
    PurchaseOrder.total_price,
    PurchaseOrder.paid_amount,
    PurchaseOrder.remaining_amount,
    PurchaseOrder.leasing_application_id,
    PurchaseOrder.cancellation_reason,
    PurchaseOrder.cancellation_requested_at,
    PurchaseOrder.cancelled_at,
    PurchaseOrder.created_at,
    PurchaseOrder.updated_at,
]

_CATALOG_JOIN_COLS = [
    SpecialEquipmentProduct.vin,
    sa.cast(None, sa.String).label("color"),
    SpecialEquipmentProduct.manufacture_year.label("vehicle_year"),
    sa.cast(None, sa.dialects.postgresql.JSONB).label("images"),
    SpecialEquipmentProduct.sale_status.label("vehicle_status"),
    SpecialEquipmentMark.name.label("mark_name"),
    sa.cast(None, sa.String).label("mark_cyrillic"),
    SpecialEquipmentModel.name.label("model_name"),
    sa.cast(None, sa.String).label("model_cyrillic"),
    sa.cast(None, sa.String).label("generation_name"),
    sa.func.coalesce(
        SpecialEquipmentModification.name,
        SpecialEquipmentProduct.superstructure_name,
    ).label("configuration_name"),
    SpecialEquipmentModification.name.label("modification_name"),
    SpecialEquipmentProduct.superstructure_name,
    SpecialEquipmentProduct.superstructure_manufacturer,
    City.name.label("warehouse_name"),
    Warehouse.address.label("warehouse_address"),
    Warehouse.brand.label("warehouse_brand"),
]

_PAYMENT_COLS = [
    Payment.id,
    Payment.purchase_order_id,
    Payment.user_id,
    Payment.payment_type,
    Payment.amount,
    Payment.status,
    Payment.gateway_transaction_id,
    Payment.gateway_response,
    Payment.receipt_url,
    Payment.receipt_s3_key,
    Payment.error_message,
    Payment.paid_at,
    Payment.created_at,
    Payment.updated_at,
    Payment.payment_method,
    Payment.fiscal_status,
    Payment.fiscal_receipt_id,
    Payment.fiscal_response,
    Payment.fiscal_retry_count,
    Payment.fiscal_error_message,
    Payment.expires_at,
]

_SCHEDULE_COLS = [
    LeasingPaymentSchedule.id,
    LeasingPaymentSchedule.purchase_order_id,
    LeasingPaymentSchedule.payment_number,
    LeasingPaymentSchedule.due_date,
    LeasingPaymentSchedule.amount,
    LeasingPaymentSchedule.principal,
    LeasingPaymentSchedule.interest,
    LeasingPaymentSchedule.payment_id,
    LeasingPaymentSchedule.is_paid,
    LeasingPaymentSchedule.created_at,
]

def _with_catalog_joins(stmt: Any) -> Any:
    """Apply the standard catalog + warehouse LEFT JOINs to a purchase_orders stmt."""
    return (
        stmt
        .join(SpecialEquipmentProduct, PurchaseOrder.product_id == SpecialEquipmentProduct.id)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentProduct.modification_id == SpecialEquipmentModification.id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentModel.mark_id == SpecialEquipmentMark.id,
        )
        .outerjoin(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .outerjoin(City, City.id == Warehouse.city_id)
    )

# ---------------------------------------------------------------------------
# Read — purchase orders
# ---------------------------------------------------------------------------

@timed_repository
async def get_by_user_id(
    session: AsyncSession,
    user_id: UUID,
    status_filter: str | None = None,
) -> list[OrderSummaryDict]:
    stmt = select(
        *_ORDER_COLS,
        *_CATALOG_JOIN_COLS,
        SpecialEquipmentProduct.price.label("base_price"),
        SpecialEquipmentProduct.special_price.label("discount_price"),
    )
    stmt = _with_catalog_joins(stmt).where(PurchaseOrder.user_id == user_id)

    if status_filter:
        stmt = stmt.where(PurchaseOrder.status == status_filter)

    stmt = stmt.order_by(PurchaseOrder.created_at.desc())
    result = await session.execute(stmt)
    return _rows(result)

@timed_repository
async def get_by_id_with_details(
    session: AsyncSession,
    order_id: UUID,
) -> OrderDetailDict | None:
    stmt = select(
        *_ORDER_COLS,
        SpecialEquipmentProduct.vin,
        sa.cast(None, sa.String).label("color"),
        SpecialEquipmentProduct.manufacture_year.label("vehicle_year"),
        sa.cast(None, sa.dialects.postgresql.JSONB).label("images"),
        SpecialEquipmentProduct.sale_status.label("vehicle_status"),
        SpecialEquipmentProduct.price.label("vehicle_base_price"),
        SpecialEquipmentProduct.special_price.label("vehicle_discount_price"),
        SpecialEquipmentMark.name.label("mark_name"),
        sa.cast(None, sa.String).label("mark_cyrillic"),
        SpecialEquipmentModel.name.label("model_name"),
        sa.cast(None, sa.String).label("model_cyrillic"),
        sa.cast(None, sa.String).label("generation_name"),
        sa.func.coalesce(
            SpecialEquipmentModification.name,
            SpecialEquipmentProduct.superstructure_name,
        ).label("configuration_name"),
        SpecialEquipmentModification.name.label("modification_name"),
        SpecialEquipmentProduct.superstructure_name,
        SpecialEquipmentProduct.superstructure_manufacturer,
        City.name.label("warehouse_name"),
        Warehouse.address.label("warehouse_address"),
        Warehouse.brand.label("warehouse_brand"),
    )
    stmt = _with_catalog_joins(stmt).where(PurchaseOrder.id == order_id)
    result = await session.execute(stmt)
    row = result.first()
    return dict(row._mapping) if row else None  # type: ignore[return-value]

@timed_repository
async def get_order_by_id(session: AsyncSession, order_id: UUID) -> OrderDict | None:
    order = await session.get(PurchaseOrder, order_id)
    return _to_dict(order)

@timed_repository
async def get_order_by_id_for_update(
    session: AsyncSession,
    order_id: UUID,
) -> OrderDict | None:
    stmt = (
        select(PurchaseOrder)
        .where(PurchaseOrder.id == order_id)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return _to_dict(result.scalar_one_or_none())


@timed_repository
async def get_order_for_update(
    session: AsyncSession, order_id: UUID
) -> OrderDict | None:
    """Serialize payment attempts for one product order."""
    result = await session.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return _to_dict(result.scalar_one_or_none())


@timed_repository
async def get_order_lock_route(
    session: AsyncSession,
    order_id: UUID,
) -> OrderLockRoute | None:
    """Load order routing keys without holding a row lock."""

    stmt = select(
        PurchaseOrder.id,
        PurchaseOrder.user_id,
        PurchaseOrder.product_id,
        PurchaseOrder.product_id.label("vehicle_id"),
    ).where(PurchaseOrder.id == order_id)
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("Any", dict(row)) if row else None


@timed_repository
async def list_active_orders_by_product_ids(
    session: AsyncSession,
    product_ids: list[UUID] | None = None,
    *,
    vehicle_ids: list[UUID] | None = None,
) -> list[ActiveVehicleDict]:
    target_ids = product_ids or vehicle_ids or []
    if not target_ids:
        return []
    stmt = (
        select(
            PurchaseOrder.product_id,
            PurchaseOrder.product_id.label("vehicle_id"),
            PurchaseOrder.status,
            PurchaseOrder.purchase_type,
        )
        .where(
            and_(
                PurchaseOrder.product_id.in_(target_ids),
                PurchaseOrder.status.not_in([OrderStatus.CANCELLED]),
            )
        )
    )
    result = await session.execute(stmt)
    return _rows(result)


list_active_orders_by_vehicle_ids = list_active_orders_by_product_ids


@timed_repository
async def find_active_orders_by_user(
    session: AsyncSession,
    user_id: UUID,
) -> list[OrderDict]:
    stmt = (
        select(PurchaseOrder)
        .where(
            and_(
                PurchaseOrder.user_id == user_id,
                PurchaseOrder.status.not_in([OrderStatus.CANCELLED]),
            )
        )
        .order_by(PurchaseOrder.created_at.desc())
    )
    result = await session.execute(stmt)
    return _rows(result)


@timed_repository
async def get_active_vehicle_ids_by_user(
    session: AsyncSession,
    user_id: UUID,
) -> list[ActiveVehicleDict]:
    stmt = (
        select(
            PurchaseOrder.product_id.label("vehicle_id"),
            PurchaseOrder.status,
            PurchaseOrder.purchase_type,
        )
        .where(
            and_(
                PurchaseOrder.user_id == user_id,
                PurchaseOrder.status.not_in([OrderStatus.CANCELLED]),
            )
        )
        .order_by(PurchaseOrder.created_at.desc())
    )
    result = await session.execute(stmt)
    return _rows(result)

@timed_repository
async def has_active_order(
    session: AsyncSession,
    product_id: UUID | None = None,
    *,
    vehicle_id: UUID | None = None,
) -> bool:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return False
    stmt = (
        select(func.count())
        .select_from(PurchaseOrder)
        .where(
            and_(
                PurchaseOrder.product_id == target_id,
                PurchaseOrder.status.not_in([OrderStatus.CANCELLED]),
            )
        )
    )
    result = await session.execute(stmt)
    return (result.scalar() or 0) > 0

@timed_repository
async def find_active_order_by_product_and_user(
    session: AsyncSession,
    product_id: UUID | None = None,
    user_id: UUID | None = None,
    *,
    vehicle_id: UUID | None = None,
) -> OrderDict | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None or user_id is None:
        return None
    stmt = (
        select(PurchaseOrder)
        .where(
            and_(
                PurchaseOrder.product_id == target_id,
                PurchaseOrder.user_id == user_id,
                PurchaseOrder.status.not_in([OrderStatus.CANCELLED]),
            )
        )
        .order_by(PurchaseOrder.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return _to_dict(result.scalar_one_or_none())


find_active_order_by_vehicle_and_user = find_active_order_by_product_and_user

@timed_repository
async def find_order_by_application_and_product(
    session: AsyncSession,
    leasing_application_id: uuid.UUID,
    product_id: UUID | None = None,
    *,
    vehicle_id: UUID | None = None,
) -> OrderDict | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    stmt = (
        select(PurchaseOrder)
        .where(
            and_(
                PurchaseOrder.leasing_application_id == leasing_application_id,
                PurchaseOrder.product_id == target_id,
            )
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return _to_dict(result.scalar_one_or_none())


find_order_by_application_and_vehicle = find_order_by_application_and_product

# ---------------------------------------------------------------------------
# Write — purchase orders
# ---------------------------------------------------------------------------

@timed_repository
async def create_in_transaction(session: AsyncSession, data: dict[str, Any]) -> OrderDict:
    order_data = dict(data)
    if "vehicle_id" in order_data and "product_id" not in order_data:
        order_data["product_id"] = order_data.pop("vehicle_id")
    order = PurchaseOrder(**order_data)
    session.add(order)
    await session.flush()
    await session.refresh(order)
    return _to_dict(order)

@timed_repository
async def update_order(session: AsyncSession, order_id: UUID, data: dict[str, Any]) -> OrderDict:
    order = await session.get(PurchaseOrder, order_id)
    if order is None:
        raise ValueError(f"Purchase order {order_id} not found")
    for key, value in data.items():
        setattr(order, key, value)
    order.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(order)
    return _to_dict(order)

# ---------------------------------------------------------------------------
# Products / Units
# ---------------------------------------------------------------------------

@timed_repository
async def get_product_for_update(
    session: AsyncSession,
    product_id: UUID | None = None,
    *,
    vehicle_id: UUID | None = None,
) -> VehicleLockDict | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    stmt = (
        select(
            SpecialEquipmentProduct.id,
            SpecialEquipmentProduct.sale_status.label("status"),
            SpecialEquipmentProduct.modification_id.label("complectation_id"),
        )
        .where(SpecialEquipmentProduct.id == target_id)
        .with_for_update()
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("Any", dict(row)) if row else None


get_vehicle_for_update = get_product_for_update

@timed_repository
async def get_product_price(
    session: AsyncSession,
    product_id: UUID | None = None,
    *,
    vehicle_id: UUID | None = None,
) -> VehiclePriceDict | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    stmt = select(
        SpecialEquipmentProduct.id,
        func.coalesce(
            SpecialEquipmentProduct.special_price, SpecialEquipmentProduct.price
        ).label("effective_price"),
    ).where(SpecialEquipmentProduct.id == target_id)
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("Any", dict(row)) if row else None


get_vehicle_price = get_product_price

@timed_repository
async def update_product_status_in_transaction(
    session: AsyncSession,
    product_id: UUID | None = None,
    status: str = "available",
    *,
    vehicle_id: UUID | None = None,
) -> dict[str, Any]:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        raise ValueError("Product id is required")
    product = await session.get(SpecialEquipmentProduct, target_id)
    if product is None:
        raise ValueError(f"Product {target_id} not found")
    product.sale_status = status
    await session.flush()
    return _to_dict(product)


update_vehicle_status_in_transaction = update_product_status_in_transaction

# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@timed_repository
async def lock_vehicle_commerce_idempotency(
    session: AsyncSession,
    user_id: UUID,
    idempotency_key: str,
) -> None:
    """Serialize vehicle-commerce requests for one user-scoped key."""

    lock_key = f"vehicle-commerce:{user_id}:{idempotency_key}"
    await session.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(CAST(:lock_key AS text), 0)"
            ")"
        ),
        {"lock_key": lock_key},
    )


@timed_repository
async def find_vehicle_commerce_payment_by_idempotency(
    session: AsyncSession,
    user_id: UUID,
    idempotency_key: str,
) -> PaymentDict | None:
    """Find a vehicle-commerce payment receipt owned by ``user_id``."""

    receipt = Payment.gateway_response[VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE]
    stmt = (
        select(*_PAYMENT_COLS, PurchaseOrder.user_id.label("order_user_id"))
        .join(PurchaseOrder, Payment.purchase_order_id == PurchaseOrder.id)
        .where(
            Payment.user_id == user_id,
            PurchaseOrder.user_id == user_id,
            receipt["key"].astext == idempotency_key,
        )
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("Any", dict(row)) if row else None


@timed_repository
async def get_payments_by_order_id(session: AsyncSession, order_id: UUID) -> list[PaymentDict]:
    stmt = (
        select(Payment)
        .where(Payment.purchase_order_id == order_id)
        .order_by(Payment.created_at.desc())
    )
    result = await session.execute(stmt)
    return [_to_dict(obj) for obj in result.scalars().all()]

@timed_repository
async def create_payment(session: AsyncSession, data: dict[str, Any]) -> PaymentDict:
    payment = Payment(**data)
    session.add(payment)
    await session.flush()
    await session.refresh(payment)
    return _to_dict(payment)

@timed_repository
async def update_payment(session: AsyncSession, payment_id: UUID, data: dict[str, Any]) -> PaymentDict:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise ValueError(f"Payment {payment_id} not found")
    for key, value in data.items():
        setattr(payment, key, value)
    await session.flush()
    await session.refresh(payment)
    return _to_dict(payment)

@timed_repository
async def get_payment_by_id(session: AsyncSession, payment_id: UUID) -> PaymentDict | None:
    stmt = (
        select(*_PAYMENT_COLS, PurchaseOrder.user_id.label("order_user_id"))
        .join(PurchaseOrder, Payment.purchase_order_id == PurchaseOrder.id)
        .where(Payment.id == payment_id)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("Any", dict(row)) if row else None


@timed_repository
async def get_payment_by_id_for_update(
    session: AsyncSession,
    payment_id: UUID,
) -> PaymentDict | None:
    """Lock one vehicle payment after its purchase order has been locked."""

    stmt = (
        select(*_PAYMENT_COLS, PurchaseOrder.user_id.label("order_user_id"))
        .join(PurchaseOrder, Payment.purchase_order_id == PurchaseOrder.id)
        .where(Payment.id == payment_id)
        .with_for_update(of=Payment)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("Any", dict(row)) if row else None


@timed_repository
async def get_payment_by_gateway_id(
    session: AsyncSession,
    transaction_id: str,
) -> PaymentWithOrderDict | None:
    stmt = (
        select(
            *_PAYMENT_COLS,
            PurchaseOrder.user_id.label("order_user_id"),
            PurchaseOrder.product_id.label("order_product_id"),
            PurchaseOrder.product_id.label("order_vehicle_id"),
        )
        .join(PurchaseOrder, Payment.purchase_order_id == PurchaseOrder.id)
        .where(Payment.gateway_transaction_id == transaction_id)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("Any", dict(row)) if row else None

@timed_repository
async def get_payment_by_gateway_id_for_update(
    session: AsyncSession,
    transaction_id: str,
) -> PaymentWithOrderDict | None:
    stmt = (
        select(
            *_PAYMENT_COLS,
            PurchaseOrder.user_id.label("order_user_id"),
            PurchaseOrder.product_id.label("order_product_id"),
            PurchaseOrder.product_id.label("order_vehicle_id"),
        )
        .join(PurchaseOrder, Payment.purchase_order_id == PurchaseOrder.id)
        .where(Payment.gateway_transaction_id == transaction_id)
        .with_for_update(of=Payment)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("Any", dict(row)) if row else None

@timed_repository
async def find_pending_expired_payments(session: AsyncSession) -> list[ExpiredPaymentDict]:
    stmt = (
        select(
            *_PAYMENT_COLS,
            PurchaseOrder.product_id.label("product_id"),
            PurchaseOrder.product_id.label("vehicle_id"),
            PurchaseOrder.status.label("order_status"),
        )
        .join(PurchaseOrder, Payment.purchase_order_id == PurchaseOrder.id)
        .where(
            and_(
                Payment.status == PaymentStatus.PENDING,
                Payment.expires_at.isnot(None),
                Payment.expires_at < func.now(),
            )
        )
    )
    result = await session.execute(stmt)
    return _rows(result)


# ---------------------------------------------------------------------------
# Leasing schedule
# ---------------------------------------------------------------------------

@timed_repository
async def get_schedule_by_order_id(session: AsyncSession, order_id: UUID) -> list[ScheduleItemWithPaymentDict]:
    stmt = (
        select(
            *_SCHEDULE_COLS,
            Payment.status.label("payment_status"),
            Payment.paid_at.label("payment_paid_at"),
            Payment.receipt_url,
        )
        .outerjoin(Payment, Payment.id == LeasingPaymentSchedule.payment_id)
        .where(LeasingPaymentSchedule.purchase_order_id == order_id)
        .order_by(LeasingPaymentSchedule.payment_number.asc())
    )
    result = await session.execute(stmt)
    return _rows(result)

@timed_repository
async def get_schedule_item(session: AsyncSession, schedule_id: UUID) -> ScheduleItemDict | None:
    obj = await session.get(LeasingPaymentSchedule, schedule_id)
    return _to_dict(obj)

@timed_repository
async def mark_schedule_item_paid(
    session: AsyncSession,
    schedule_id: UUID,
    payment_id: UUID,
) -> ScheduleItemDict:
    item = await session.get(LeasingPaymentSchedule, schedule_id)
    assert item is not None
    item.is_paid = True
    item.payment_id = payment_id
    await session.flush()
    return _to_dict(item)


@timed_repository
async def link_schedule_item_payment(
    session: AsyncSession,
    schedule_id: UUID,
    payment_id: UUID,
) -> ScheduleItemDict:
    """Attach an in-flight provider payment without marking the installment paid."""

    item = await session.get(LeasingPaymentSchedule, schedule_id)
    assert item is not None
    item.payment_id = payment_id
    await session.flush()
    return _to_dict(item)

@timed_repository
async def create_schedule_entries(
    session: AsyncSession,
    entries: list[dict[str, Any]],
) -> list[ScheduleItemDict]:
    if not entries:
        return []
    objs = [LeasingPaymentSchedule(**entry) for entry in entries]
    session.add_all(objs)
    await session.flush()
    for obj in objs:
        await session.refresh(obj)
    return [_to_dict(obj) for obj in objs]

# ---------------------------------------------------------------------------
# Products — additional helpers
# ---------------------------------------------------------------------------

@timed_repository
async def get_additional_available_product_ids(
    session: AsyncSession,
    complectation_id: Any,
    exclude_id: UUID,
    limit: int,
) -> list[UUID]:
    stmt = (
        select(SpecialEquipmentProduct.id)
        .where(
            and_(
                SpecialEquipmentProduct.modification_id == complectation_id,
                SpecialEquipmentProduct.sale_status == "available",
                SpecialEquipmentProduct.publication_status == "published",
                SpecialEquipmentProduct.id != exclude_id,
            )
        )
        .order_by(SpecialEquipmentProduct.id)
        .limit(limit)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


get_additional_available_vehicle_ids = get_additional_available_product_ids

@timed_repository
async def get_payment_by_fiscal_receipt_id(
    session: AsyncSession,
    receipt_id: str | None,
) -> PaymentDict | None:
    stmt = (
        select(*_PAYMENT_COLS, PurchaseOrder.user_id.label("order_user_id"))
        .join(PurchaseOrder, Payment.purchase_order_id == PurchaseOrder.id)
        .where(Payment.fiscal_receipt_id == receipt_id)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("Any", dict(row)) if row else None

@timed_repository
async def get_user_info(session: AsyncSession, user_id: UUID) -> UserInfoDict:
    stmt = select(User.phone, User.email, User.name).where(User.id == user_id)
    result = await session.execute(stmt)
    row = result.mappings().first()
    return cast("UserInfoDict", dict(row)) if row else {}

# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------

@timed_repository
async def remove_from_cart_in_transaction(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    *,
    vehicle_id: UUID | None = None,
) -> None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return
    await session.execute(
        delete(ShoppingCart).where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.product_id == target_id,
        )
    )
