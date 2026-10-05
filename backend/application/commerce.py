"""Unified commerce facade over the existing vehicle and equipment stores.

The facade deliberately normalizes use-case inputs and outputs only.  Each
adapter keeps writing to its existing FK-safe tables; a special-equipment UUID
is never treated as a ``vehicle_id``.
"""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications import (
    ApplicationSpecialEquipmentPayload,
    ApplicationVehiclePayload,
    CreateDraftCommand,
    handle_create_draft,
)
from application.commands.calculator.calculate import (
    CalculateCommand,
    handle_calculate,
)
from application.commands.purchases import (
    CreatePurchaseOrdersCommand,
    PayRemainingCommand,
    PayScheduleItemCommand,
    RequestCancellationCommand,
    handle_create_purchase_orders,
    handle_pay_remaining,
    handle_pay_schedule_item,
    handle_request_cancellation,
)
from application.errors import ServiceError
from application.queries.purchases import (
    GetOrderDetailsQuery,
    GetOrderPaymentsQuery,
    GetOrderScheduleQuery,
    GetPaymentStatusQuery,
    GetUserOrdersQuery,
    handle_get_order_details,
    handle_get_order_payments,
    handle_get_order_schedule,
    handle_get_payment_status,
    handle_get_user_orders,
)
from application.special_equipment_checkout import (
    CheckoutAllocationError,
    allocate_cart_items,
)
from application.special_equipment_commerce import (
    CancelOrderCommand as CancelSpecialEquipmentOrderCommand,
)
from application.special_equipment_commerce import (
    CreateLeasingApplicationCommand as CreateSpecialEquipmentLeasingApplicationCommand,
)
from application.special_equipment_commerce import (
    CreateOrderCommand as CreateSpecialEquipmentOrderCommand,
)
from application.special_equipment_commerce import (
    CreateRemainingPaymentCommand as CreateSpecialEquipmentRemainingPaymentCommand,
)
from application.special_equipment_commerce import (
    CreateScheduledPaymentCommand as CreateSpecialEquipmentScheduledPaymentCommand,
)
from application.special_equipment_commerce import (
    cancel_order as cancel_special_equipment_order,
)
from application.special_equipment_commerce import (
    create_leasing_application as create_special_equipment_leasing_application,
)
from application.special_equipment_commerce import (
    create_order as create_special_equipment_order,
)
from application.special_equipment_commerce import (
    create_remaining_payment as create_special_equipment_remaining_payment,
)
from application.special_equipment_commerce import (
    create_scheduled_payment as create_special_equipment_scheduled_payment,
)
from application.special_equipment_commerce import (
    get_leasing_payment_schedule as get_special_equipment_schedule,
)
from application.special_equipment_commerce import (
    get_order as get_special_equipment_order,
)
from application.special_equipment_commerce import (
    get_payment_receipt_content as get_special_equipment_payment_receipt_content,
)
from application.special_equipment_commerce import (
    get_payment_status as get_special_equipment_payment_status,
)
from application.special_equipment_commerce import (
    list_orders as list_special_equipment_orders,
)
from application.special_equipment_urls import public_special_equipment_detail_url
from domain.commerce import (
    VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE,
    CommerceItemRef,
    CommerceItemType,
    CommerceOrderRef,
)
from domain.entities.cart_item import CartItem
from domain.errors import (
    OrderNotFoundError,
    PaymentNotFoundError,
    VehicleNotFoundError,
)
from domain.leasing_purposes import selected_purposes
from domain.services.object_storage import ObjectStorage, StoredObject
from domain.special_equipment_commerce import (
    ProductCommerceState,
    SpecialEquipmentPurchaseType,
)
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import (
    company_registration_repository,
    purchase_repository,
    special_equipment_commerce_repository,
)

_SAFE_IMAGE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_ACTIVE_VEHICLE_PAYMENT_STATUSES = frozenset({"pending_payment", "processing"})
_VEHICLE_COMMERCE_IDEMPOTENCY_VERSION = 1


async def _load_special_equipment_product(
    session: AsyncSession,
    product_id: UUID,
) -> tuple[dict[str, Any], ProductCommerceState]:
    row = await special_equipment_commerce_repository.get_product(session, product_id)
    if row is None:
        from domain.special_equipment_commerce import (
            SpecialEquipmentProductNotFoundError,
        )

        raise SpecialEquipmentProductNotFoundError()
    return row, ProductCommerceState.from_dict(row)


@dataclass(frozen=True, slots=True)
class CreateCommerceOrderCommand:
    user_id: UUID
    item: CommerceItemRef
    purchase_type: str
    payment_method: str
    idempotency_key: str
    quantity: int = 1
    down_payment_percent: Decimal | None = None
    cart_item_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class CreateCommercePaymentCommand:
    user_id: UUID
    order: CommerceOrderRef
    scope: str
    payment_method: str
    idempotency_key: str
    schedule_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CreateCommerceLeasingApplicationCommand:
    user_id: UUID
    actor_role: str
    source_type: str
    actor_company_id: UUID | None
    item: CommerceItemRef
    company_id: UUID | None
    company: dict[str, Any] | None = None
    name: str = ""
    email: str = ""
    comment: str | None = None
    leasing_purpose: str | None = None
    leasing_purposes: list[str] | None = None
    leasing_purpose_comment: str | None = None
    regions: list[str] = field(default_factory=list)
    down_payment_percent: Decimal | None = None
    lease_term_months: int | None = None
    calculation: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CommerceLeasingApplicationLineCommand:
    item: CommerceItemRef
    quantity: int = 1
    allow_overstock: bool = False
    custom_price: Decimal | None = None
    comment: str | None = None
    equipments: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)
    leasing_purpose: str | None = None
    leasing_purposes: list[str] | None = None
    leasing_purpose_comment: str | None = None
    regions: list[str] = field(default_factory=list)
    cart_item_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class CreateCommerceLeasingApplicationBatchCommand:
    user_id: UUID
    actor_role: str
    source_type: str
    actor_company_id: UUID | None
    items: list[CommerceLeasingApplicationLineCommand]
    company_id: UUID | None
    company: dict[str, Any] | None = None
    name: str = ""
    email: str = ""
    down_payment_percent: Decimal | None = None
    lease_term_months: int | None = None
    calculation: dict[str, Any] | None = None
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


@dataclass(frozen=True, slots=True)
class _PreparedLeasingBatch:
    vehicles: list[
        tuple[CommerceLeasingApplicationLineCommand, ApplicationVehiclePayload]
    ]
    special_equipment: list[
        tuple[
            CommerceLeasingApplicationLineCommand,
            ApplicationSpecialEquipmentPayload,
        ]
    ]
    total_amount: Decimal | None


def _persisted_leasing_purpose(
    purpose: str | None,
    purpose_comment: str | None,
) -> str | None:
    """Match the established application storage contract without new columns.

    Existing vehicle applications persist the free-form value itself when the
    UI option is ``other``.  The commerce adapters use the same representation
    for both item types so the common form does not discard that text.
    """
    normalized_purpose = (purpose or "").strip()
    if normalized_purpose != "other":
        return normalized_purpose or None
    return (purpose_comment or "").strip() or None


def _money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (ArithmeticError, TypeError, ValueError):
        return Decimal("0.00")


def _custom_price(value: Any) -> Decimal:
    """Return a positive, cent-precision employee/dealer price override."""

    try:
        raw_price = Decimal(str(value))
    except (TypeError, ValueError) as exc:
        raise ServiceError("Некорректная пользовательская цена", 422) from exc
    if not raw_price.is_finite():
        raise ServiceError("Некорректная пользовательская цена", 422)
    try:
        price = raw_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except ArithmeticError as exc:
        raise ServiceError("Некорректная пользовательская цена", 422) from exc
    if price <= 0:
        raise ServiceError(
            "Пользовательская цена должна быть больше нуля",
            422,
        )
    return price


def _requested_calculation_total(
    calculation: Mapping[str, Any] | None,
) -> Decimal | None:
    if not calculation or "total_amount" not in calculation:
        return None
    raw_total = calculation.get("total_amount")
    if raw_total is None:
        return None
    try:
        total = Decimal(str(raw_total))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ServiceError("Некорректная стоимость имущества в расчёте", 422) from exc
    if not total.is_finite() or total < 0:
        raise ServiceError("Некорректная стоимость имущества в расчёте", 422)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _authoritative_calculation_base_total(
    response: Mapping[str, Any],
) -> Decimal | None:
    support = response.get("support")
    if isinstance(support, Mapping):
        return _requested_calculation_total({"total_amount": support.get("base_total")})
    parameters = response.get("calculation_parameters")
    return _requested_calculation_total(
        parameters if isinstance(parameters, Mapping) else None
    )


def _option_total(
    equipments: list[dict[str, Any]],
    services: list[dict[str, Any]],
) -> Decimal:
    total = Decimal("0.00")
    for option in [*equipments, *services]:
        price = _money(option.get("price"))
        if price < 0:
            raise ServiceError(
                "Стоимость дополнительной опции не может быть отрицательной",
                422,
            )
        total += price
    return total


def _vehicle_image_url(images: Any) -> str | None:
    if not isinstance(images, list) or not images:
        return None
    first = images[0]
    filename: Any = first
    if isinstance(first, dict):
        filename = first.get("filename") or first.get("name")
    if not isinstance(filename, str) or not _SAFE_IMAGE_NAME.fullmatch(filename):
        return None
    return f"/api/v1/cars/images/{filename}"


def _title(*parts: Any) -> str:
    return " ".join(str(value).strip() for value in parts if value).strip()


def _facts(*values: tuple[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": label, "value": str(value)}
        for label, value in values
        if value is not None and str(value).strip()
    ]


def _typed_ref(item_type: CommerceItemType, item_id: UUID) -> dict[str, Any]:
    return {"type": item_type.value, "id": item_id}


def _order_sort_key(row: dict[str, Any]) -> str:
    value = row.get("created_at") or row.get("updated_at")
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _decimal_token(value: Decimal | None) -> str | None:
    """Canonicalize semantically equal decimal request values for hashing."""

    if value is None:
        return None
    return format(value.normalize(), "f")


def _request_hash(payload: Mapping[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _json_mapping(value: Any) -> dict[str, Any]:
    """Convert a gateway DTO to JSON-safe data suitable for a JSONB receipt."""

    if hasattr(value, "model_dump"):
        raw = value.model_dump(mode="json", by_alias=True)
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise ServiceError("Платёжный шлюз вернул некорректный ответ", 502)
    return cast(
        "dict[str, Any]",
        json.loads(json.dumps(raw, default=str)),
    )


def _json_safe(value: Any) -> Any:
    """Recursively normalize calculator output before writing JSONB fields."""

    normalized: Any
    if isinstance(value, Mapping):
        normalized = {
            str(key): _json_safe(item) for key, item in value.items()
        }
    elif isinstance(value, (list, tuple, set)):
        normalized = [_json_safe(item) for item in value]
    elif isinstance(value, (UUID, Decimal)):
        normalized = str(value)
    elif isinstance(value, datetime):
        normalized = value.isoformat()
    elif value is None or isinstance(value, (str, int, float, bool)):
        normalized = value
    else:
        normalized = str(value)
    return normalized


def _checkout_handoff(result: Mapping[str, Any]) -> dict[str, Any]:
    if result.get("widgetData") is not None:
        return {"widgetData": _json_mapping(result["widgetData"])}
    if result.get("sbpData") is not None:
        return {"sbpData": _json_mapping(result["sbpData"])}
    return {}


def _normalize_checkout(
    result: dict[str, Any], adapter: CommerceAdapter
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "order": adapter.normalize_order(result["order"]),
        "payment": (
            adapter.normalize_payment(result["payment"])
            if result.get("payment")
            else None
        ),
        "replayed": bool(result.get("replayed", False)),
    }
    if result.get("schedule_item") or result.get("scheduleItem"):
        payload["schedule_item"] = adapter.normalize_schedule_item(
            result.get("schedule_item") or result["scheduleItem"]
        )
    if result.get("widgetData") is not None:
        payload["widgetData"] = result["widgetData"]
    if result.get("sbpData") is not None:
        payload["sbpData"] = result["sbpData"]
    return payload


class CommerceAdapter(ABC):
    """Port implemented once per persistence bounded context."""

    item_type: CommerceItemType

    @abstractmethod
    async def get_item(
        self,
        item_id: UUID,
        session: AsyncSession,
        *,
        scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def create_order(
        self, command: CreateCommerceOrderCommand, session: AsyncSession
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def list_orders(
        self, user_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_order(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def list_payments(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def create_payment(
        self, command: CreateCommercePaymentCommand, session: AsyncSession
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def get_payment_status(
        self,
        user_id: UUID,
        order_id: UUID,
        payment_id: UUID,
        session: AsyncSession,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def get_receipt_content(
        self,
        user_id: UUID,
        order_id: UUID,
        payment_id: UUID,
        session: AsyncSession,
        storage: ObjectStorage,
    ) -> StoredObject: ...

    @abstractmethod
    async def get_schedule(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def cancel_order(
        self,
        user_id: UUID,
        order_id: UUID,
        reason: str | None,
        session: AsyncSession,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def create_leasing_application(
        self,
        command: CreateCommerceLeasingApplicationCommand,
        session: AsyncSession,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def normalize_order(self, row: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def normalize_payment(self, row: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def normalize_schedule_item(self, row: dict[str, Any]) -> dict[str, Any]: ...


class VehicleCommerceAdapter(CommerceAdapter):
    item_type = CommerceItemType.VEHICLE

    @staticmethod
    def _order_request_hash(command: CreateCommerceOrderCommand) -> str:
        return _request_hash(
            {
                "operation": "initial",
                "item_type": command.item.type.value,
                "item_id": str(command.item.id),
                "quantity": command.quantity,
                "purchase_type": command.purchase_type,
                "payment_method": command.payment_method,
                "down_payment_percent": _decimal_token(command.down_payment_percent),
            }
        )

    @staticmethod
    def _payment_request_hash(command: CreateCommercePaymentCommand) -> str:
        return _request_hash(
            {
                "operation": command.scope,
                "order_type": command.order.type.value,
                "order_id": str(command.order.id),
                "scope": command.scope,
                "schedule_id": (
                    str(command.schedule_id) if command.schedule_id else None
                ),
                "payment_method": command.payment_method,
            }
        )

    async def _find_idempotent_payment(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        request_hash: str,
        operation: str,
        session: AsyncSession,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        await purchase_repository.lock_vehicle_commerce_idempotency(
            session,
            user_id,
            idempotency_key,
        )
        payment = (
            await purchase_repository.find_vehicle_commerce_payment_by_idempotency(
                session,
                user_id,
                idempotency_key,
            )
        )
        if payment is None:
            return None
        gateway_response = payment.get("gateway_response")
        receipt = (
            gateway_response.get(VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE)
            if isinstance(gateway_response, Mapping)
            else None
        )
        if not isinstance(receipt, Mapping) or receipt.get("version") != (
            _VEHICLE_COMMERCE_IDEMPOTENCY_VERSION
        ):
            raise ServiceError(
                "Сохранённый результат Idempotency-Key повреждён; "
                "создание нового платежа заблокировано",
                409,
            )
        if (
            receipt.get("operation") != operation
            or receipt.get("request_hash") != request_hash
        ):
            raise ServiceError(
                "Idempotency-Key уже использован с другим набором параметров",
                409,
            )
        return payment, dict(receipt)

    @staticmethod
    def _replay_handoff(
        payment: Mapping[str, Any], receipt: Mapping[str, Any]
    ) -> dict[str, Any]:
        if payment.get("status") not in _ACTIVE_VEHICLE_PAYMENT_STATUSES:
            return {}
        expires_at = payment.get("expires_at")
        if expires_at is not None:
            if not isinstance(expires_at, datetime):
                raise ServiceError("Сохранённый срок действия платежа повреждён", 409)
            comparable = (
                expires_at.replace(tzinfo=UTC)
                if expires_at.tzinfo is None
                else expires_at
            )
            if comparable <= datetime.now(UTC):
                return {}
        handoff = receipt.get("handoff")
        if not isinstance(handoff, Mapping):
            raise ServiceError(
                "Платёж уже создан, но его безопасный результат недоступен; "
                "повторное обращение к шлюзу заблокировано",
                409,
            )
        keys = {key for key in ("widgetData", "sbpData") if key in handoff}
        if len(keys) != 1 or not isinstance(handoff[next(iter(keys))], Mapping):
            raise ServiceError(
                "Платёж уже создан, но его безопасный результат повреждён; "
                "повторное обращение к шлюзу заблокировано",
                409,
            )
        return {key: dict(handoff[key]) for key in keys}

    async def _store_idempotency_receipt(
        self,
        *,
        payment_id: UUID,
        idempotency_key: str,
        request_hash: str,
        operation: str,
        checkout_result: Mapping[str, Any],
        session: AsyncSession,
        schedule_id: UUID | None = None,
    ) -> dict[str, Any]:
        payment = await purchase_repository.get_payment_by_id(session, payment_id)
        if payment is None:
            raise PaymentNotFoundError()
        existing = payment.get("gateway_response")
        gateway_response = dict(existing) if isinstance(existing, Mapping) else {}
        receipt: dict[str, Any] = {
            "version": _VEHICLE_COMMERCE_IDEMPOTENCY_VERSION,
            "key": idempotency_key,
            "request_hash": request_hash,
            "operation": operation,
            "handoff": _checkout_handoff(checkout_result),
        }
        if schedule_id is not None:
            receipt["schedule_id"] = str(schedule_id)
        gateway_response[VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE] = receipt
        return cast(
            "dict[str, Any]",
            await purchase_repository.update_payment(
                session,
                payment_id,
                {"gateway_response": gateway_response},
            ),
        )

    async def _replay_order_checkout(
        self,
        payment: dict[str, Any],
        receipt: dict[str, Any],
        session: AsyncSession,
    ) -> dict[str, Any]:
        order = await purchase_repository.get_by_id_with_details(
            session,
            payment["purchase_order_id"],
        )
        if order is None:
            raise OrderNotFoundError()
        result: dict[str, Any] = {
            "orders": [self.normalize_order(order)],
            "payments": [self.normalize_payment(payment)],
            "replayed": True,
        }
        result.update(self._replay_handoff(payment, receipt))
        return result

    async def _replay_payment_checkout(
        self,
        payment: dict[str, Any],
        receipt: dict[str, Any],
        operation: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        order = await purchase_repository.get_by_id_with_details(
            session,
            payment["purchase_order_id"],
        )
        if order is None:
            raise OrderNotFoundError()
        result: dict[str, Any] = {
            "order": self.normalize_order(order),
            "payment": self.normalize_payment(payment),
            "replayed": True,
        }
        if operation == "scheduled":
            raw_schedule_id = receipt.get("schedule_id")
            try:
                schedule_id = UUID(str(raw_schedule_id))
            except (TypeError, ValueError) as exc:
                raise ServiceError(
                    "Сохранённая связь платежа с графиком повреждена", 409
                ) from exc
            rows = await purchase_repository.get_schedule_by_order_id(
                session,
                payment["purchase_order_id"],
            )
            schedule_item = next(
                (row for row in rows if row["id"] == schedule_id),
                None,
            )
            if schedule_item is None:
                raise ServiceError("Сохранённый платёж из графика не найден", 409)
            result["schedule_item"] = self.normalize_schedule_item(schedule_item)
        result.update(self._replay_handoff(payment, receipt))
        return result

    async def get_item(
        self,
        item_id: UUID,
        session: AsyncSession,
        *,
        scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    ) -> dict[str, Any]:
        row = await special_equipment_commerce_repository.get_product(
            session, item_id
        )
        if row is None:
            raise VehicleNotFoundError(item_id)
        if not scope.is_default:
            visible = await special_equipment_commerce_repository.product_visible_in_scope(
                session, item_id, scope
            )
            if not visible:
                raise VehicleNotFoundError(item_id)
        price = row.get("effective_price") or row.get("price")
        available = row.get("sale_status") == "available"
        has_price = price is not None and Decimal(str(price)) > 0
        title = _title(row.get("mark_name"), row.get("model_name"))
        return {
            "ref": _typed_ref(self.item_type, item_id),
            "title": title or "Техника",
            "subtitle": _title(
                row.get("modification_name"),
                row.get("trim_name"),
                row.get("group_name"),
            )
            or None,
            "image_url": _vehicle_image_url(row.get("images")),
            "detail_url": f"/special-equipment/products/{item_id}",
            "price": price,
            "currency_code": "RUB",
            "availability": str(row.get("sale_status") or "unavailable"),
            "manufacturer": row.get("mark_name"),
            "model": row.get("model_name"),
            "modification": row.get("modification_name") or row.get("group_name"),
            "year": row.get("year"),
            "facts": _facts(
                ("Цвет", row.get("color")),
                ("Двигатель", row.get("engine_type")),
                ("Мощность", row.get("horse_power")),
                ("Коробка передач", row.get("transmission")),
                ("Привод", row.get("drive")),
            ),
            "capabilities": {
                "can_lease": available,
                "can_buy": available and has_price,
                "can_preorder": available and has_price,
            },
        }

    def _item_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": _title(row.get("mark_name"), row.get("model_name"))
            or "Автомобиль",
            "subtitle": _title(
                row.get("generation_name"),
                row.get("configuration_name"),
                row.get("modification_name") or row.get("group_name"),
            )
            or None,
            "image_url": _vehicle_image_url(row.get("images")),
            "manufacturer": row.get("mark_name"),
            "model": row.get("model_name"),
            "modification": row.get("modification_name") or row.get("group_name"),
            "year": row.get("vehicle_year"),
        }

    def normalize_order(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "item": _typed_ref(self.item_type, row["product_id"]),
            "item_snapshot": self._item_snapshot(row),
            "purchase_type": row["purchase_type"],
            "status": row["status"],
            "total_price": row["total_price"],
            "paid_amount": row["paid_amount"],
            "remaining_amount": row["remaining_amount"],
            "currency_code": "RUB",
            "leasing_application_id": row.get("leasing_application_id"),
            "down_payment_percent": None,
            "hold_expires_at": None,
            "cancellation_reason": row.get("cancellation_reason"),
            "cancellation_requested_at": row.get("cancellation_requested_at"),
            "cancelled_at": row.get("cancelled_at"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def normalize_payment(self, row: dict[str, Any]) -> dict[str, Any]:
        order_id = row["purchase_order_id"]
        receipt_content_url = (
            f"/api/v1/commerce/orders/vehicle/{order_id}/payments/"
            f"{row['id']}/receipt/content"
            if row.get("receipt_s3_key")
            else None
        )
        return {
            "id": row["id"],
            "order": _typed_ref(self.item_type, order_id),
            "payment_type": row["payment_type"],
            "amount": row["amount"],
            "status": row["status"],
            "payment_method": row.get("payment_method"),
            "error_message": row.get("error_message"),
            "fiscal_status": row.get("fiscal_status"),
            "expires_at": row.get("expires_at"),
            "paid_at": row.get("paid_at"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "receipt_content_url": receipt_content_url,
        }

    def normalize_schedule_item(self, row: dict[str, Any]) -> dict[str, Any]:
        status = row.get("payment_status")
        return {
            "id": row["id"],
            "order": _typed_ref(self.item_type, row["purchase_order_id"]),
            "payment_number": row["payment_number"],
            "due_date": row["due_date"],
            "amount": row["amount"],
            "principal": row.get("principal"),
            "interest": row.get("interest"),
            "payment_id": row.get("payment_id"),
            "is_paid": bool(row.get("is_paid")),
            "payment_status": status,
            "payment_paid_at": row.get("payment_paid_at"),
            "receipt_content_url": None,
            "can_pay": not bool(row.get("is_paid"))
            and status not in {"pending_payment", "processing", "completed"},
            "created_at": row.get("created_at"),
            "updated_at": None,
        }

    async def create_order(
        self, command: CreateCommerceOrderCommand, session: AsyncSession
    ) -> dict[str, Any]:
        if command.quantity != 1:
            raise ServiceError(
                "Пакетное оформление временно недоступно; оформляйте каждую "
                "единицу отдельным заказом",
                422,
            )
        if command.payment_method == "bank_transfer":
            raise ServiceError(
                "Безналичный перевод для автомобиля временно недоступен; "
                "выберите оплату картой или СБП",
                422,
            )
        request_hash = self._order_request_hash(command)
        replay = await self._find_idempotent_payment(
            user_id=command.user_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            operation="initial",
            session=session,
        )
        if replay is not None:
            replayed_payment, receipt = replay
            return await self._replay_order_checkout(
                replayed_payment,
                receipt,
                session,
            )
        vehicle = await purchase_repository.get_vehicle_for_update(
            session, command.item.id
        )
        if vehicle is not None and vehicle.get("status") != "available":
            active_order = (
                await purchase_repository.find_active_order_by_vehicle_and_user(
                    session, command.item.id, command.user_id
                )
            )
            if active_order is not None:
                active_payments = await purchase_repository.get_payments_by_order_id(
                    session, active_order["id"]
                )
                if any(
                    payment.get("status") in _ACTIVE_VEHICLE_PAYMENT_STATUSES
                    for payment in active_payments
                ):
                    raise ServiceError(
                        "Для автомобиля уже выполняется платёж. Проверьте его "
                        "статус перед повторным оформлением",
                        409,
                    )
        result = await handle_create_purchase_orders(
            CreatePurchaseOrdersCommand(
                user_id=command.user_id,
                items=[
                    {
                        "vehicle_id": command.item.id,
                        "quantity": command.quantity,
                    }
                ],
                purchase_type=command.purchase_type,
                payment_method=command.payment_method,
                down_payment_percent=cast("Any", command.down_payment_percent),
            ),
            session,
        )
        orders: list[dict[str, Any]] = []
        payments: list[dict[str, Any]] = []
        for raw in result["orders"]:
            details = await purchase_repository.get_by_id_with_details(
                session, raw["id"]
            )
            if details is None:
                raise OrderNotFoundError()
            payment = await purchase_repository.get_payment_by_id(
                session, raw["payment_id"]
            )
            if payment is None:
                raise PaymentNotFoundError()
            payment = await self._store_idempotency_receipt(
                payment_id=payment["id"],
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
                operation="initial",
                checkout_result=result,
                session=session,
            )
            orders.append(self.normalize_order(details))
            payments.append(self.normalize_payment(payment))
        return {
            "orders": orders,
            "payments": payments,
            "replayed": False,
            "widgetData": result.get("widgetData"),
            "sbpData": result.get("sbpData"),
        }

    async def list_orders(
        self, user_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        rows = await handle_get_user_orders(
            GetUserOrdersQuery(user_id=user_id), session
        )
        return [self.normalize_order(row) for row in rows]

    async def get_order(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> dict[str, Any]:
        row = await handle_get_order_details(
            GetOrderDetailsQuery(user_id=user_id, order_id=order_id), session
        )
        return self.normalize_order(row)

    async def list_payments(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        rows = await handle_get_order_payments(
            GetOrderPaymentsQuery(user_id=user_id, order_id=order_id), session
        )
        return [self.normalize_payment(row) for row in rows]

    async def create_payment(
        self, command: CreateCommercePaymentCommand, session: AsyncSession
    ) -> dict[str, Any]:
        if command.payment_method == "bank_transfer":
            raise ServiceError(
                "Безналичный перевод для платежей по автомобилю временно "
                "недоступен; выберите оплату картой или СБП",
                422,
            )
        if command.scope == "scheduled" and command.schedule_id is None:
            raise PaymentNotFoundError("Не указан платёж из графика")
        request_hash = self._payment_request_hash(command)
        replay = await self._find_idempotent_payment(
            user_id=command.user_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            operation=command.scope,
            session=session,
        )
        if replay is not None:
            replayed_payment, receipt = replay
            return await self._replay_payment_checkout(
                replayed_payment,
                receipt,
                command.scope,
                session,
            )
        # The legacy use case still owns the order lock and fail-closed
        # active-payment invariant, protecting both HTTP adapters.
        if command.scope == "scheduled":
            assert command.schedule_id is not None
            result = await handle_pay_schedule_item(
                PayScheduleItemCommand(
                    user_id=command.user_id,
                    order_id=command.order.id,
                    schedule_id=command.schedule_id,
                    payment_method=command.payment_method,
                ),
                session,
            )
        else:
            result = await handle_pay_remaining(
                PayRemainingCommand(
                    user_id=command.user_id,
                    order_id=command.order.id,
                    payment_method=command.payment_method,
                ),
                session,
            )
        payment = result.get("payment")
        if not isinstance(payment, Mapping) or not isinstance(payment.get("id"), UUID):
            raise PaymentNotFoundError()
        result["payment"] = await self._store_idempotency_receipt(
            payment_id=payment["id"],
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            operation=command.scope,
            checkout_result=result,
            session=session,
            schedule_id=command.schedule_id,
        )
        if "order" not in result:
            order = await purchase_repository.get_by_id_with_details(
                session, command.order.id
            )
            if order is None:
                raise OrderNotFoundError()
            result["order"] = order
        return _normalize_checkout({**result, "replayed": False}, self)

    async def get_payment_status(
        self,
        user_id: UUID,
        order_id: UUID,
        payment_id: UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        await self.get_order(user_id, order_id, session)
        payment = await purchase_repository.get_payment_by_id(session, payment_id)
        if payment is None or payment["purchase_order_id"] != order_id:
            raise PaymentNotFoundError()
        current = await handle_get_payment_status(
            GetPaymentStatusQuery(payment_id=payment_id), session
        )
        if current is None:
            raise PaymentNotFoundError()
        refreshed = await purchase_repository.get_payment_by_id(session, payment_id)
        if refreshed is None or refreshed["purchase_order_id"] != order_id:
            raise PaymentNotFoundError()
        return self.normalize_payment(refreshed)

    async def get_receipt_content(
        self,
        user_id: UUID,
        order_id: UUID,
        payment_id: UUID,
        session: AsyncSession,
        storage: ObjectStorage,
    ) -> StoredObject:
        await self.get_order(user_id, order_id, session)
        payment = await purchase_repository.get_payment_by_id(session, payment_id)
        if payment is None or payment["purchase_order_id"] != order_id:
            raise PaymentNotFoundError()
        storage_key = payment.get("receipt_s3_key")
        if not storage_key:
            raise ServiceError("Фискальный чек ещё не сохранён", 404)
        obj = await storage.get(str(storage_key))
        if obj is None:
            raise ServiceError("Фискальный чек не найден в хранилище", 404)
        return obj

    async def get_schedule(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        rows = await handle_get_order_schedule(
            GetOrderScheduleQuery(user_id=user_id, order_id=order_id), session
        )
        return [self.normalize_schedule_item(row) for row in rows]

    async def cancel_order(
        self,
        user_id: UUID,
        order_id: UUID,
        reason: str | None,
        session: AsyncSession,
    ) -> dict[str, Any]:
        result = await handle_request_cancellation(
            RequestCancellationCommand(
                user_id=user_id, order_id=order_id, reason=reason
            ),
            session,
        )
        details = await purchase_repository.get_by_id_with_details(session, order_id)
        return self.normalize_order(details or result["order"])

    async def create_leasing_application(
        self,
        command: CreateCommerceLeasingApplicationCommand,
        session: AsyncSession,
    ) -> dict[str, Any]:
        item = await self.get_item(command.item.id, session)
        calculation = dict(command.calculation or {})
        calculation.setdefault("total_amount", item.get("price"))
        calculation.setdefault("down_payment_percent", command.down_payment_percent)
        calculation.setdefault("lease_term_months", command.lease_term_months)
        result = await handle_create_draft(
            CreateDraftCommand(
                source_type=command.source_type,
                actor_id=command.user_id,
                actor_role=command.actor_role,
                actor_company_id=command.actor_company_id,
                company_id=command.company_id,
                company=command.company,
                name=command.name,
                email=command.email,
                vehicles=[
                    ApplicationVehiclePayload(
                        vehicle_id=command.item.id,
                        quantity=1,
                        custom_price=item.get("price"),
                        comment=command.comment,
                        leasing_purpose=_persisted_leasing_purpose(
                            command.leasing_purpose,
                            command.leasing_purpose_comment,
                        ),
                        leasing_purposes=selected_purposes(command.leasing_purposes, command.leasing_purpose, command.leasing_purpose_comment),
                        regions=command.regions,
                    )
                ],
                calculation=calculation,
            ),
            session,
        )
        return {
            "application_id": result["application_id"],
            **({"source_type": result["source_type"]} if "source_type" in result else {}),
            "item": command.item.as_dict(),
            "line_id": None,
            "status": result["status"],
        }


class SpecialEquipmentCommerceAdapter(CommerceAdapter):
    item_type = CommerceItemType.SPECIAL_EQUIPMENT

    async def get_item(
        self,
        item_id: UUID,
        session: AsyncSession,
        *,
        scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    ) -> dict[str, Any]:
        row = await special_equipment_commerce_repository.get_product(session, item_id)
        if row is None:
            from domain.special_equipment_commerce import (
                SpecialEquipmentProductNotFoundError,
            )

            raise SpecialEquipmentProductNotFoundError()
        price = row.get("price")
        available = (
            row.get("publication_status") == "published"
            and row.get("sale_status") == "available"
        )
        on_order = (
            row.get("publication_status") == "published"
            and row.get("sale_status") == "on_order"
        )
        has_price = (
            not bool(row.get("price_on_request"))
            and price is not None
            and Decimal(str(price)) > 0
        )
        image_id = row.get("primary_image_id")
        in_catalog_scope = (
            await special_equipment_commerce_repository.product_visible_in_scope(
                session,
                item_id,
                scope,
            )
        )
        detail_url = (
            public_special_equipment_detail_url(
                item_id,
                row.get("slug"),
                publication_status=row.get("publication_status"),
                sale_status=row.get("sale_status"),
            )
            if in_catalog_scope
            else None
        )
        return {
            "ref": _typed_ref(self.item_type, item_id),
            "title": _title(row.get("mark_name"), row.get("model_name"))
            or "Спецтехника",
            "subtitle": row.get("modification_name"),
            "image_url": (
                f"/api/v1/special-equipment/images/{image_id}/content"
                if image_id
                else None
            ),
            "detail_url": detail_url,
            "price": price,
            "price_on_request": bool(row.get("price_on_request")),
            "price_from": row.get("price_from"),
            "currency_code": row.get("currency_code") or "RUB",
            "availability": str(row.get("sale_status") or "unavailable"),
            # The unified commerce DTO keeps the cross-domain field name
            # ``manufacturer``; for special equipment its value is the mark.
            "manufacturer": row.get("mark_name"),
            "model": row.get("model_name"),
            "modification": row.get("modification_name"),
            "year": row.get("manufacture_year"),
            "facts": _facts(
                ("Модификация", row.get("modification_name")),
                ("Год выпуска", row.get("manufacture_year")),
            ),
            "capabilities": {
                "can_lease": available or on_order,
                "can_buy": available and has_price,
                "can_preorder": (available or on_order) and has_price,
            },
        }

    def _item_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        snapshot = row.get("item_snapshot") or {}
        title: str
        subtitle: str | None
        if snapshot.get("superstructure_name"):
            from domain.special_equipment_kits import kit_title

            title = str(
                snapshot.get("title")
                or kit_title(
                    superstructure_name=str(snapshot["superstructure_name"]),
                    chassis_mark_name=str(
                        snapshot.get("chassis_mark_name")
                        or snapshot.get("mark")
                        or ""
                    ),
                    chassis_model_name=str(
                        snapshot.get("chassis_model_name")
                        or snapshot.get("model")
                        or ""
                    ),
                )
            )
            subtitle_parts = [
                snapshot.get("chassis_modification_name") or snapshot.get("modification"),
                snapshot.get("superstructure_type_name"),
            ]
            if snapshot.get("superstructure_manufacturer"):
                subtitle_parts.append(f"Производитель: {snapshot['superstructure_manufacturer']}")
            subtitle = " · ".join(str(p).strip() for p in subtitle_parts if p)
        else:
            title = _title(snapshot.get("mark"), snapshot.get("model")) or "Спецтехника"
            raw_sub = snapshot.get("modification")
            subtitle = str(raw_sub) if raw_sub is not None else None

        return {
            "title": title,
            "subtitle": subtitle,
            "image_url": None,
            "manufacturer": snapshot.get("mark"),
            "model": snapshot.get("model"),
            "modification": snapshot.get("modification"),
            "year": snapshot.get("manufacture_year"),
            "superstructure_name": snapshot.get("superstructure_name"),
            "superstructure_type_name": snapshot.get("superstructure_type_name"),
            "superstructure_manufacturer": snapshot.get("superstructure_manufacturer"),
            "chassis_mark_name": snapshot.get("chassis_mark_name") or snapshot.get("mark"),
            "chassis_model_name": snapshot.get("chassis_model_name") or snapshot.get("model"),
            "chassis_modification_name": snapshot.get("chassis_modification_name") or snapshot.get("modification"),
        }

    def normalize_order(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "item": _typed_ref(self.item_type, row["product_id"]),
            "item_snapshot": self._item_snapshot(row),
            "purchase_type": row["purchase_type"],
            "status": row["status"],
            "total_price": row["total_price"],
            "paid_amount": row["paid_amount"],
            "remaining_amount": row["remaining_amount"],
            "currency_code": row.get("currency_code") or "RUB",
            "leasing_application_id": row.get("leasing_application_id"),
            "down_payment_percent": row.get("down_payment_percent"),
            "hold_expires_at": row.get("hold_expires_at"),
            "cancellation_reason": row.get("cancellation_reason"),
            "cancellation_requested_at": row.get("cancellation_requested_at"),
            "cancelled_at": row.get("cancelled_at"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def normalize_payment(self, row: dict[str, Any]) -> dict[str, Any]:
        order_id = row["purchase_order_id"]
        receipt_content_url = (
            f"/api/v1/commerce/orders/special_equipment/{order_id}/payments/"
            f"{row['id']}/receipt/content"
            if row.get("receipt_storage_key")
            else None
        )
        return {
            "id": row["id"],
            "order": _typed_ref(self.item_type, order_id),
            "payment_type": row["payment_type"],
            "amount": row["amount"],
            "status": row["status"],
            "payment_method": row.get("payment_method"),
            "error_message": row.get("error_message"),
            "fiscal_status": row.get("fiscal_status"),
            "expires_at": row.get("expires_at"),
            "paid_at": row.get("paid_at"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "receipt_content_url": receipt_content_url,
        }

    def normalize_schedule_item(self, row: dict[str, Any]) -> dict[str, Any]:
        order_id = row["purchase_order_id"]
        payment_id = row.get("payment_id")
        receipt_content_url = (
            f"/api/v1/commerce/orders/special_equipment/{order_id}/payments/"
            f"{payment_id}/receipt/content"
            if payment_id and row.get("receipt_content_url")
            else None
        )
        return {
            "id": row["id"],
            "order": _typed_ref(self.item_type, order_id),
            "payment_number": row["payment_number"],
            "due_date": row["due_date"],
            "amount": row["amount"],
            "principal": row.get("principal"),
            "interest": row.get("interest"),
            "payment_id": row.get("payment_id"),
            "is_paid": bool(row.get("is_paid")),
            "payment_status": row.get("payment_status"),
            "payment_paid_at": row.get("payment_paid_at"),
            "receipt_content_url": receipt_content_url,
            "can_pay": bool(row.get("can_pay")),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def create_order(
        self, command: CreateCommerceOrderCommand, session: AsyncSession
    ) -> dict[str, Any]:
        if not command.cart_item_ids:
            raise ServiceError("Нужно выбрать позиции серверной корзины", 422)
        try:
            result = await create_special_equipment_order(
                CreateSpecialEquipmentOrderCommand(
                    user_id=command.user_id,
                    purchase_type=SpecialEquipmentPurchaseType(command.purchase_type),
                    idempotency_key=command.idempotency_key,
                    payment_method=command.payment_method,
                    down_payment_percent=command.down_payment_percent,
                    cart_item_ids=command.cart_item_ids,
                    product_id=command.item.id,
                    quantity=command.quantity,
                ),
                session,
            )
        except CheckoutAllocationError as exc:
            raise ServiceError(
                str(exc),
                409,
                code=exc.code,
                requested=exc.requested,
                available=exc.available,
            ) from exc
        normalized = _normalize_checkout(result, self)
        response: dict[str, Any] = {
            "orders": [normalized["order"]],
            "payments": ([normalized["payment"]] if normalized.get("payment") else []),
            "replayed": normalized["replayed"],
        }
        if normalized.get("widgetData") is not None:
            response["widgetData"] = normalized["widgetData"]
        if normalized.get("sbpData") is not None:
            response["sbpData"] = normalized["sbpData"]
        return response

    async def list_orders(
        self, user_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while True:
            result = await list_special_equipment_orders(
                user_id,
                session,
                page=page,
                page_size=100,
            )
            rows.extend(result["items"])
            pages = int(result["pagination"]["pages"])
            if page >= pages:
                break
            page += 1
        return [self.normalize_order(row) for row in rows]

    async def get_order(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> dict[str, Any]:
        row = await get_special_equipment_order(user_id, order_id, session)
        return self.normalize_order(row)

    async def _owned_order(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> dict[str, Any]:
        return await get_special_equipment_order(user_id, order_id, session)

    async def list_payments(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        order = await self._owned_order(user_id, order_id, session)
        return [self.normalize_payment(row) for row in order.get("payments", [])]

    async def create_payment(
        self, command: CreateCommercePaymentCommand, session: AsyncSession
    ) -> dict[str, Any]:
        if command.scope == "scheduled":
            if command.schedule_id is None:
                raise PaymentNotFoundError("Не указан платёж из графика")
            result = await create_special_equipment_scheduled_payment(
                CreateSpecialEquipmentScheduledPaymentCommand(
                    user_id=command.user_id,
                    order_id=command.order.id,
                    schedule_id=command.schedule_id,
                    idempotency_key=command.idempotency_key,
                    payment_method=command.payment_method,
                ),
                session,
            )
        else:
            result = await create_special_equipment_remaining_payment(
                CreateSpecialEquipmentRemainingPaymentCommand(
                    user_id=command.user_id,
                    order_id=command.order.id,
                    idempotency_key=command.idempotency_key,
                    payment_method=command.payment_method,
                ),
                session,
            )
        return _normalize_checkout(result, self)

    async def get_payment_status(
        self,
        user_id: UUID,
        order_id: UUID,
        payment_id: UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        raw = await get_special_equipment_payment_status(
            user_id, order_id, payment_id, session
        )
        payment = await special_equipment_commerce_repository.get_payment(
            session, payment_id
        )
        if payment is None:
            raise PaymentNotFoundError()
        return self.normalize_payment({**payment, **raw})

    async def get_receipt_content(
        self,
        user_id: UUID,
        order_id: UUID,
        payment_id: UUID,
        session: AsyncSession,
        storage: ObjectStorage,
    ) -> StoredObject:
        return await get_special_equipment_payment_receipt_content(
            user_id, order_id, payment_id, session, storage
        )

    async def get_schedule(
        self, user_id: UUID, order_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        rows = await get_special_equipment_schedule(user_id, order_id, session)
        return [self.normalize_schedule_item(row) for row in rows]

    async def cancel_order(
        self,
        user_id: UUID,
        order_id: UUID,
        reason: str | None,
        session: AsyncSession,
    ) -> dict[str, Any]:
        row = await cancel_special_equipment_order(
            CancelSpecialEquipmentOrderCommand(
                user_id=user_id, order_id=order_id, reason=reason
            ),
            session,
        )
        return self.normalize_order(row)

    async def create_leasing_application(
        self,
        command: CreateCommerceLeasingApplicationCommand,
        session: AsyncSession,
    ) -> dict[str, Any]:
        company_id = command.company_id
        allow_dealer_client_company = False
        if command.actor_role == "dealer" and command.company is not None:
            if command.actor_company_id is None:
                raise ServiceError("Не указана компания дилера", 422)
            if not command.company.get("inn"):
                raise ServiceError(
                    "Для создания заявки выберите компанию из списка",
                    422,
                )
            created_company = (
                await company_registration_repository.create_or_get_company(
                    session,
                    cast(
                        "company_registration_repository.CompanyPayload",
                        command.company,
                    ),
                )
            )
            if created_company is None or created_company.get("id") is None:
                raise ServiceError("Компания не найдена", 404)
            company_id = created_company["id"]
            allow_dealer_client_company = True
        if company_id is None:
            raise ServiceError("Не указана компания", 422)
        result = await create_special_equipment_leasing_application(
            CreateSpecialEquipmentLeasingApplicationCommand(
                source_type=command.source_type,
                user_id=command.user_id,
                company_id=company_id,
                product_id=command.item.id,
                actor_role=command.actor_role,
                allow_dealer_client_company=allow_dealer_client_company,
                comment=command.comment,
                leasing_purpose=_persisted_leasing_purpose(
                    command.leasing_purpose,
                    command.leasing_purpose_comment,
                ),
                leasing_purposes=selected_purposes(command.leasing_purposes, command.leasing_purpose, command.leasing_purpose_comment),
                regions=command.regions,
                down_payment_percent=command.down_payment_percent,
                lease_term_months=command.lease_term_months,
            ),
            session,
        )
        return {
            "application_id": result["application_id"],
            **({"source_type": result["source_type"]} if "source_type" in result else {}),
            "item": command.item.as_dict(),
            "line_id": result["item_id"],
            "status": result.get("status") or result["item_status"],
        }


class CommerceFacade:
    """Explicit router-dispatch facade; never probes one store after another."""

    def __init__(self) -> None:
        self._adapters: dict[CommerceItemType, CommerceAdapter] = {
            CommerceItemType.VEHICLE: VehicleCommerceAdapter(),
            CommerceItemType.SPECIAL_EQUIPMENT: SpecialEquipmentCommerceAdapter(),
        }

    def adapter(self, item_type: CommerceItemType) -> CommerceAdapter:
        return self._adapters[item_type]

    async def get_item(
        self,
        ref: CommerceItemRef,
        session: AsyncSession,
        *,
        scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    ) -> dict[str, Any]:
        return await self.adapter(ref.type).get_item(ref.id, session, scope=scope)

    async def create_order(
        self, command: CreateCommerceOrderCommand, session: AsyncSession
    ) -> dict[str, Any]:
        return await self.adapter(command.item.type).create_order(command, session)

    async def create_leasing_application(
        self,
        command: CreateCommerceLeasingApplicationBatchCommand,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Create one parent application for every selected typed item.

        All catalog rows are locked and validated before the first write. The
        router commits once, so a failure in either bounded context rolls back
        the common parent and every child line together.
        """

        self._validate_leasing_lines(command.items)
        prepared = await self._prepare_leasing_batch(
            command.items,
            user_id=command.user_id,
            actor_role=command.actor_role,
            scope=command.scope,
            session=session,
        )
        requested_total = _requested_calculation_total(command.calculation)
        if requested_total is not None and requested_total != prepared.total_amount:
            raise ServiceError(
                "Стоимость товаров изменилась. Обновите корзину и повторите расчёт",
                409,
            )
        calculation = await self._canonical_leasing_calculation(
            command,
            prepared,
            session=session,
        )

        result = await handle_create_draft(
            CreateDraftCommand(
                source_type=command.source_type,
                actor_id=command.user_id,
                actor_role=command.actor_role,
                actor_company_id=command.actor_company_id,
                company_id=command.company_id,
                company=command.company,
                name=command.name,
                email=command.email,
                vehicles=[payload for _, payload in prepared.vehicles],
                special_equipment_items=[
                    payload for _, payload in prepared.special_equipment
                ],
                source_product_id=self._first_source_product_id(command, prepared),
                calculation=calculation,
                scope=command.scope,
            ),
            session,
        )
        special_cart_item_ids = tuple(
            cart_item_id
            for line in command.items
            if line.item.type == CommerceItemType.SPECIAL_EQUIPMENT
            for cart_item_id in line.cart_item_ids
        )
        if special_cart_item_ids:
            await special_equipment_commerce_repository.delete_cart_items_by_ids(
                session,
                user_id=command.user_id,
                cart_item_ids=special_cart_item_ids,
            )
        response_items = self._created_leasing_lines(command.items, prepared, result)
        return {
            "application_id": result["application_id"],
            **({"display_number": result["display_number"]} if result.get("display_number") is not None else {}),
            **({"source_type": result["source_type"]} if "source_type" in result else {}),
            "items": response_items,
            "status": result["status"],
        }

    @staticmethod
    def _first_source_product_id(
        command: CreateCommerceLeasingApplicationBatchCommand,
        prepared: _PreparedLeasingBatch,
    ) -> UUID | None:
        # Lock acquisition sorts the batch; provenance follows the original request.
        first = command.items[0]
        if first.item.type == CommerceItemType.VEHICLE:
            return first.item.id
        first_cart_item_id = first.cart_item_ids[0] if first.cart_item_ids else None
        product_id = next(
            (payload.product_id for line, payload in prepared.special_equipment
             if line is first and payload.source_cart_item_id == first_cart_item_id
             and payload.item_role == "offer"),
            None,
        )
        if product_id is None and command.source_type != "platform":
            raise ServiceError("Не удалось определить первый товар для источника заявки", 400)
        return product_id

    @staticmethod
    async def _canonical_leasing_calculation(
        command: CreateCommerceLeasingApplicationBatchCommand,
        prepared: _PreparedLeasingBatch,
        *,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Recompute every derived financial field from locked catalog rows.

        The browser snapshot is only a concurrency token plus calculator input.
        Values such as monthly payment, rate and savings are never persisted
        from the request body.
        """

        requested = dict(command.calculation or {})
        down_payment_percent = (
            command.down_payment_percent
            if command.down_payment_percent is not None
            else requested.get("down_payment_percent")
        )
        lease_term_months = (
            command.lease_term_months
            if command.lease_term_months is not None
            else requested.get("lease_term_months")
        )
        canonical: dict[str, Any] = {"total_amount": prepared.total_amount}
        if prepared.total_amount is None:
            if down_payment_percent is not None:
                canonical["down_payment_percent"] = Decimal(
                    str(down_payment_percent)
                )
            if lease_term_months is not None:
                canonical["lease_term_months"] = int(lease_term_months)
            return canonical
        if down_payment_percent is None or lease_term_months is None:
            return canonical

        percent = Decimal(str(down_payment_percent))
        down_payment = (
            prepared.total_amount * percent / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        vehicle_ids = [line.item.id for line, _payload in prepared.vehicles]
        vehicle_quantities = {
            line.item.id: line.quantity for line, _payload in prepared.vehicles
        }
        vehicle_price_overrides = {
            line.item.id: float(payload.custom_price or Decimal("0"))
            for line, payload in prepared.vehicles
            if line.custom_price is not None
        }
        vehicle_total = sum(
            (payload.custom_price or Decimal("0")) * Decimal(line.quantity)
            for line, payload in prepared.vehicles
        )
        additional_amount = (
            prepared.total_amount - vehicle_total if vehicle_ids else None
        )
        calculated = await handle_calculate(
            CalculateCommand(
                total_amount=float(prepared.total_amount),
                additional_amount=(
                    float(additional_amount)
                    if additional_amount is not None
                    else None
                ),
                down_payment=float(down_payment),
                down_payment_percent=float(percent),
                lease_term_months=int(lease_term_months),
                buyout_amount=float(requested.get("buyout_amount") or 0),
                vehicle_ids=vehicle_ids,
                vehicle_price_overrides=vehicle_price_overrides,
                vehicle_quantities=vehicle_quantities,
                selected_support=dict(requested.get("selected_support") or {}),
                user={
                    "id": command.user_id,
                    "role": command.actor_role,
                    "company_id": command.actor_company_id,
                },
                persist_history=False,
            ),
            session,
        )
        response = calculated.response
        parameters = response["calculation_parameters"]
        calculated_total = _authoritative_calculation_base_total(response)
        if calculated_total != prepared.total_amount:
            raise ServiceError(
                "Расчёт стоимости не соответствует составу заявки. "
                "Обновите корзину и повторите расчёт",
                409,
            )
        result = response["calculation"]
        canonical.update(
            {
                "down_payment": parameters["down_payment"],
                "down_payment_percent": parameters["down_payment_percent"],
                "lease_term_months": parameters["lease_term_months"],
                "monthly_payment": result["monthlyPayment"],
                "total_cost": result["totalCost"],
                "markup": result["markup"],
                "rate": result["rate"],
                "total_interest": result["totalInterest"],
                "buyout_amount": result["buyoutAmount"],
                "vat_refund": result["vatRefund"],
                "profit_tax_savings": result["profitTaxSavings"],
                "total_savings": result["totalSavings"],
                "selected_support": _json_safe(
                    requested.get("selected_support") or {}
                ),
                "support_per_vehicle": _json_safe(
                    response.get("support_per_vehicle") or []
                ),
                "support_per_program": _json_safe(
                    response.get("support_per_program") or []
                ),
                "support_program_details": _json_safe(
                    response.get("support_program_details") or []
                ),
                "calculations_per_vehicle": _json_safe(
                    response.get("calculations_per_vehicle") or []
                ),
            }
        )
        return canonical

    @staticmethod
    def _validate_leasing_lines(
        lines: list[CommerceLeasingApplicationLineCommand],
    ) -> None:
        if not lines:
            raise ServiceError("Не выбраны транспортные средства", 422)
        if len(lines) > 100:
            raise ServiceError("В одной заявке может быть не более 100 позиций", 422)
        refs = [line.item for line in lines]
        if len(refs) != len(set(refs)):
            raise ServiceError("Одна позиция не может повторяться в заявке", 422)
        for line in lines:
            if not 1 <= line.quantity <= (2147483647 if line.item.type == CommerceItemType.VEHICLE else 100):
                raise ServiceError("Некорректное количество позиции", 422)
            if line.custom_price is not None:
                _custom_price(line.custom_price)

    async def _prepare_leasing_batch(
        self,
        lines: list[CommerceLeasingApplicationLineCommand],
        *,
        user_id: UUID,
        actor_role: str,
        scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
        session: AsyncSession,
    ) -> _PreparedLeasingBatch:
        vehicles: list[
            tuple[CommerceLeasingApplicationLineCommand, ApplicationVehiclePayload]
        ] = []
        special_equipment: list[
            tuple[
                CommerceLeasingApplicationLineCommand,
                ApplicationSpecialEquipmentPayload,
            ]
        ] = []
        total_amount = Decimal("0.00")
        has_unknown_price = False

        # Every request uses this exact discriminator/UUID order, preventing
        # mixed-cart transactions from deadlocking each other.
        ordered_lines = sorted(
            lines,
            key=lambda line: (line.item.type.value, str(line.item.id)),
        )
        special_lines: list[CommerceLeasingApplicationLineCommand] = []
        for line in ordered_lines:
            if line.item.type == CommerceItemType.VEHICLE:
                (
                    vehicle_payload,
                    line_total,
                ) = await self._prepare_vehicle_line(
                    line, actor_role=actor_role, scope=scope, session=session
                )
                vehicles.append((line, vehicle_payload))
            else:
                special_lines.append(line)
                continue
            total_amount += line_total

        if special_lines:
            special_equipment, special_total = await self._prepare_special_lines(
                special_lines,
                user_id=user_id,
                actor_role=actor_role,
                session=session,
            )
            if special_total is None:
                if vehicles:
                    raise ServiceError(
                        "Технику без цены нельзя объединять с другими позициями",
                        422,
                    )
                has_unknown_price = True
            else:
                total_amount += special_total

        return _PreparedLeasingBatch(
            vehicles=vehicles,
            special_equipment=special_equipment,
            total_amount=(
                None
                if has_unknown_price
                else total_amount.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            ),
        )

    async def _prepare_vehicle_line(
        self,
        line: CommerceLeasingApplicationLineCommand,
        *,
        actor_role: str,
        scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
        session: AsyncSession,
    ) -> tuple[ApplicationVehiclePayload, Decimal]:
        _ = scope
        locked = await purchase_repository.get_vehicle_for_update(session, line.item.id)
        if locked is None:
            raise VehicleNotFoundError(line.item.id)
        if locked.get("status") != "available":
            raise ServiceError("Автомобиль недоступен для лизинга", 409)

        item = await self.adapter(CommerceItemType.VEHICLE).get_item(
            line.item.id, session
        )
        if not item.get("capabilities", {}).get("can_lease"):
            raise ServiceError("Автомобиль недоступен для лизинга", 409)
        counts = await special_equipment_commerce_repository.get_product(session, line.item.id)
        available_count = 1 if counts and counts.get("sale_status") == "available" else 0
        CartItem.ensure_stock_quantity(
            line.quantity, available=available_count,
            allow_overstock=line.allow_overstock,
        )
        catalog_price = _money(item.get("price"))
        if line.custom_price is not None:
            CartItem.ensure_custom_price_allowed(actor_role, catalog_price)
            unit_price = _custom_price(line.custom_price)
        else:
            unit_price = catalog_price
        line_total = (
            unit_price + _option_total(line.equipments, line.services)
        ) * Decimal(line.quantity)
        if line_total < 0:
            raise ServiceError("Стоимость позиции не может быть отрицательной", 422)
        return (
            ApplicationVehiclePayload(
                vehicle_id=line.item.id,
                quantity=line.quantity,
                allow_overstock=line.allow_overstock,
                custom_price=unit_price,
                comment=line.comment,
                equipments=line.equipments,
                services=line.services,
                leasing_purpose=_persisted_leasing_purpose(
                    line.leasing_purpose,
                    line.leasing_purpose_comment,
                ),
                leasing_purposes=selected_purposes(line.leasing_purposes, line.leasing_purpose, line.leasing_purpose_comment),
                regions=line.regions,
            ),
            line_total,
        )

    @staticmethod
    async def _prepare_special_lines(  # noqa: PLR0912, PLR0915 -- canonical bundle invariants
        lines: list[CommerceLeasingApplicationLineCommand],
        *,
        user_id: UUID,
        actor_role: str,
        session: AsyncSession,
    ) -> tuple[
        list[
            tuple[
                CommerceLeasingApplicationLineCommand,
                ApplicationSpecialEquipmentPayload,
            ]
        ],
        Decimal | None,
    ]:
        if any(not line.cart_item_ids for line in lines):
            raise ServiceError("Нужно выбрать позиции серверной корзины", 422)
        owner_by_cart_item: dict[UUID, CommerceLeasingApplicationLineCommand] = {}
        for line in lines:
            for cart_item_id in line.cart_item_ids:
                if cart_item_id in owner_by_cart_item:
                    raise ServiceError(
                        "Позиция серверной корзины выбрана несколько раз",
                        422,
                    )
                owner_by_cart_item[cart_item_id] = line

        try:
            allocation = await allocate_cart_items(
                session,
                user_id=user_id,
                cart_item_ids=tuple(owner_by_cart_item),
                allow_on_order=True,
                allow_overstock=True,
            )
        except CheckoutAllocationError as exc:
            raise ServiceError(
                str(exc),
                409,
                code=exc.code,
                requested=exc.requested,
                available=exc.available,
            ) from exc
        if not allocation.supports_unpriced_leasing:
            raise ServiceError(
                "Технику без цены можно оформить в лизинг только одной единицей "
                "без автомобилей и других платных позиций",
                422,
            )
        if allocation.total is None and any(
            _option_total(line.equipments, line.services) > 0 for line in lines
        ):
            raise ServiceError(
                "Технику без цены можно оформить в лизинг только одной единицей "
                "без автомобилей и других платных позиций",
                422,
            )
        for line in lines:
            if not any(
                owner_by_cart_item[allocated.cart_item_id] is line
                and allocated.representative_id == line.item.id
                for allocated in allocation.cart_lines
            ):
                raise ServiceError(
                    "Позиция серверной корзины не соответствует выбранному товару",
                    409,
                )
        component_ids = {
            component.component_product_id for component in allocation.components
        }
        states: dict[UUID, ProductCommerceState] = {}
        for product_id in allocation.concrete_product_ids:
            _row, state = await _load_special_equipment_product(session, product_id)
            if product_id not in component_ids:
                state.ensure_leasing_application_allowed()
            states[product_id] = state
        currencies = {state.currency_code for state in states.values()}
        if len(currencies) > 1:
            raise ServiceError(
                "Одна лизинговая заявка не может объединять товары в разных валютах",
                422,
            )

        prepared: list[
            tuple[
                CommerceLeasingApplicationLineCommand,
                ApplicationSpecialEquipmentPayload,
            ]
        ] = []
        total = Decimal("0.00")
        has_unknown_price = False
        for allocated_line in allocation.cart_lines:
            line = owner_by_cart_item[allocated_line.cart_item_id]
            if allocated_line.quantity + allocated_line.overstock_quantity != line.quantity:
                raise ServiceError(
                    "Количество позиции серверной корзины изменилось",
                    409,
                )
            first_offer = True
            for product in allocated_line.products:
                state = states[product["id"]]
                unit_price = allocated_line.agreed_unit_price(product)
                if line.custom_price is not None:
                    CartItem.ensure_custom_price_allowed(actor_role, state.price)
                    if _custom_price(line.custom_price) != unit_price:
                        raise ServiceError(
                            "Стоимость позиции серверной корзины изменилась",
                            409,
                        )
                line_total = (
                    unit_price + _option_total(line.equipments, line.services)
                    if unit_price is not None
                    else None
                )
                item_role = (
                    "attachment"
                    if allocated_line.parent_cart_item_id is not None
                    else "offer"
                )
                overstock_qty = 0
                if item_role == "offer" and first_offer:
                    overstock_qty = allocated_line.overstock_quantity
                    first_offer = False
                prepared.append(
                    (
                        line,
                        ApplicationSpecialEquipmentPayload(
                            product_id=state.id,
                            seller_company_id=state.seller_company_id,
                            unit_price=unit_price,
                            total_price=line_total,
                            currency_code=state.currency_code,
                            item_snapshot=state.snapshot(),
                            comment=line.comment,
                            equipments=line.equipments,
                            services=line.services,
                            leasing_purpose=_persisted_leasing_purpose(
                                line.leasing_purpose,
                                line.leasing_purpose_comment,
                            ),
                            leasing_purposes=selected_purposes(line.leasing_purposes, line.leasing_purpose, line.leasing_purpose_comment),
                            regions=line.regions,
                            source_cart_item_id=allocated_line.cart_item_id,
                            group_id=allocated_line.cart_item_id,
                            parent_group_id=allocated_line.parent_cart_item_id,
                            item_role=item_role,
                            overstock_requested_quantity=overstock_qty,
                        ),
                    )
                )
                if line_total is None:
                    has_unknown_price = True
                else:
                    total += line_total

        for component in allocation.components:
            line = owner_by_cart_item[component.source_cart_item_id]
            state = states[component.component_product_id]
            prepared.append(
                (
                    line,
                    ApplicationSpecialEquipmentPayload(
                        product_id=state.id,
                        seller_company_id=state.seller_company_id,
                        unit_price=Decimal("0.00"),
                        total_price=Decimal("0.00"),
                        currency_code=state.currency_code,
                        item_snapshot={
                            **state.snapshot(),
                            "composite_product_id": str(
                                component.composite_product_id
                            ),
                            "is_base": component.is_base,
                        },
                        comment=line.comment,
                        leasing_purpose=_persisted_leasing_purpose(
                            line.leasing_purpose,
                            line.leasing_purpose_comment,
                        ),
                        leasing_purposes=selected_purposes(line.leasing_purposes, line.leasing_purpose, line.leasing_purpose_comment),
                        regions=line.regions,
                        source_cart_item_id=component.source_cart_item_id,
                        group_id=component.source_cart_item_id,
                        parent_group_id=component.source_cart_item_id,
                        item_role="component",
                    ),
                )
            )
        return prepared, None if has_unknown_price else total

    @staticmethod
    def _created_leasing_lines(
        requested: list[CommerceLeasingApplicationLineCommand],
        prepared: _PreparedLeasingBatch,
        result: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        vehicle_ids = list(result.get("vehicle_line_ids") or [])
        special_ids = list(result.get("special_equipment_line_ids") or [])
        if len(vehicle_ids) != len(prepared.vehicles) or len(special_ids) != len(
            prepared.special_equipment
        ):
            raise RuntimeError("Created application line count mismatch")

        line_ids = {
            line.item: line_id
            for (line, _), line_id in zip(
                prepared.vehicles,
                vehicle_ids,
                strict=True,
            )
        }
        for (line, payload), line_id in zip(
            prepared.special_equipment,
            special_ids,
            strict=True,
        ):
            if payload.item_role != "component":
                line_ids.setdefault(line.item, line_id)
        return [
            {
                "item": line.item.as_dict(),
                "line_id": line_ids[line.item],
                "quantity": line.quantity,
            }
            for line in requested
        ]

    async def list_orders(
        self,
        user_id: UUID,
        session: AsyncSession,
        item_type: CommerceItemType | None = None,
    ) -> list[dict[str, Any]]:
        adapters = (
            [self.adapter(item_type)]
            if item_type is not None
            else list(self._adapters.values())
        )
        items: list[dict[str, Any]] = []
        for adapter in adapters:
            items.extend(await adapter.list_orders(user_id, session))
        return sorted(
            items,
            key=_order_sort_key,
            reverse=True,
        )


commerce_facade = CommerceFacade()
