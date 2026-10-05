"""Purchase routes."""
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.purchases import (
    ApproveCancellationCommand,
    CreatePurchaseOrdersCommand,
    PayRemainingCommand,
    PayScheduleItemCommand,
    RequestCancellationCommand,
    handle_approve_cancellation,
    handle_create_purchase_orders,
    handle_pay_remaining,
    handle_pay_schedule_item,
    handle_request_cancellation,
)
from application.errors import ServiceError, domain_to_http
from application.queries.purchases import (
    GetActiveVehicleIdsQuery,
    GetOrderDetailsQuery,
    GetOrderPaymentsQuery,
    GetOrderScheduleQuery,
    GetPaymentReceiptQuery,
    GetPaymentStatusQuery,
    GetUserOrdersQuery,
    handle_get_active_vehicle_ids,
    handle_get_order_details,
    handle_get_order_payments,
    handle_get_order_schedule,
    handle_get_payment_receipt,
    handle_get_payment_status,
    handle_get_user_orders,
)
from domain.commerce import VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.dependencies.auth import require_scopes
from presentation.schemas.purchases import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    CreatePurchaseRequest,
    CreatePurchaseResponse,
    OrderDetailResponse,
    OrderResponse,
    OrdersListResponse,
    PaymentsListResponse,
    PaymentStatusResponse,
    ReceiptResponse,
    RequestCancellationRequest,
    ScheduleListResponse,
    VehiclesResponse,
)

router = APIRouter()

# Reads (list, detail, schedule, payments, status, receipt, vehicle-ids).
# Granted to clients and employees alike.
_purchase_reader = require_scopes("purchases:read")
# Creating purchase orders — both clients and employees.
_purchase_writer = require_scopes("purchases:write")
# Client-only self-service actions on an own order: create-payment (remaining
# or scheduled), request-cancellation.
_purchase_self = require_scopes("purchases:self-pay")
# Employee-only: approving cancellations submitted by clients.
_purchase_admin = require_scopes("purchases:admin")


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _without_vehicle_commerce_metadata(payment: Any) -> Any:
    """Hide facade idempotency data while preserving provider metadata."""
    if not isinstance(payment, dict):
        return payment
    gateway_response = payment.get("gateway_response")
    if (
        not isinstance(gateway_response, dict)
        or VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE not in gateway_response
    ):
        return payment

    sanitized_gateway_response = dict(gateway_response)
    sanitized_gateway_response.pop(VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE)
    return {**payment, "gateway_response": sanitized_gateway_response}


def _without_nested_payment_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    payment = payload.get("payment")
    sanitized_payment = _without_vehicle_commerce_metadata(payment)
    if sanitized_payment is payment:
        return payload
    return {**payload, "payment": sanitized_payment}


@router.post(
    "",
    status_code=201,
    response_model=CreatePurchaseResponse,
    summary="Создать заказ",
    description=(
        "Создаёт один или несколько заказов на покупку или бронирование автомобилей. "
        "Если передан `payment_method`, сразу инициируется платёж: "
        "для `card` возвращается `widgetData` (токен виджета ModulBank), "
        "для `sbp` — `sbpData` (ссылка и QR-код). "
        "Для `bank_transfer` или без метода оплаты платёжные данные не возвращаются."
    ),
)
async def create_purchase(
    body: CreatePurchaseRequest,
    user: Annotated[dict, Depends(_purchase_writer)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        items = []
        for item in body.items:
            dumped = item.model_dump()
            if "vehicle_id" not in dumped:
                dumped["vehicle_id"] = item.product_id
            items.append(dumped)
        result = await handle_create_purchase_orders(
            CreatePurchaseOrdersCommand(
                user_id=user["id"],
                items=items,
                purchase_type=body.purchase_type,
                payment_method=body.payment_method,
                down_payment_percent=body.down_payment_percent,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result), status_code=201)


@router.get(
    "/my-vehicle-ids",
    response_model=VehiclesResponse,
    summary="Активные товары пользователя",
    description=(
        "Возвращает список товаров (`product_id`, `status`, `purchase_type`), "
        "по которым у текущего пользователя есть активные заказы. "
        "Используется, например, для блокировки повторного бронирования."
    ),
)
async def get_my_vehicle_ids(
    user: Annotated[dict, Depends(_purchase_reader)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    vehicles = await handle_get_active_vehicle_ids(
        GetActiveVehicleIdsQuery(user_id=user["id"]), session
    )
    for v in vehicles:
        if isinstance(v, dict) and "product_id" not in v and "vehicle_id" in v:
            v["product_id"] = v["vehicle_id"]
    return JSONResponse(content={"vehicles": jsonable_encoder(vehicles)})


@router.get(
    "/payments/{payment_id}/status",
    response_model=PaymentStatusResponse,
    summary="Статус платежа",
    description=(
        "Возвращает актуальный статус платежа из платёжного шлюза. "
        "Возвращает `null` в поле `payment`, если платёж не найден."
    ),
)
async def get_payment_status(
    payment_id: UUID,
    _user: Annotated[dict, Depends(_purchase_reader)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    status = await handle_get_payment_status(
        GetPaymentStatusQuery(payment_id=payment_id), session
    )
    if not status:
        raise HTTPException(status_code=404, detail="Платеж не найден")
    return JSONResponse(content={"payment": jsonable_encoder(status)})


@router.get(
    "/payments/{payment_id}/receipt",
    response_model=ReceiptResponse,
    summary="Чек платежа",
    description=(
        "Возвращает фискальный чек платежа и краткое описание заказа "
        "(марка, модель, VIN, год, итоговая сумма). "
        "Доступен только платёж, принадлежащий текущему пользователю."
    ),
)
async def get_payment_receipt(
    payment_id: UUID,
    user: Annotated[dict, Depends(_purchase_reader)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        receipt = await handle_get_payment_receipt(
            GetPaymentReceiptQuery(user_id=user["id"], payment_id=payment_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    receipt = _without_nested_payment_metadata(receipt)
    return JSONResponse(content={"receipt": jsonable_encoder(receipt)})


@router.get(
    "",
    response_model=OrdersListResponse,
    summary="Список заказов",
    description=(
        "Возвращает все заказы текущего пользователя с кратким описанием автомобиля "
        "(марка, модель, поколение, VIN, изображения, склад). "
        "Опциональный query-параметр `status` фильтрует по статусу заказа."
    ),
)
async def list_orders(
    user: Annotated[dict, Depends(_purchase_reader)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(default=None, description="Фильтр по статусу заказа"),
) -> JSONResponse:
    orders = await handle_get_user_orders(
        GetUserOrdersQuery(user_id=user["id"], status_filter=status), session
    )
    return JSONResponse(content={"orders": jsonable_encoder(orders)})


@router.get(
    "/{order_id}",
    response_model=OrderDetailResponse,
    summary="Детали заказа",
    description=(
        "Возвращает полную информацию по заказу: данные автомобиля, цены, "
        "статус, суммы оплаты и остатка, информацию по складу. "
        "Возвращает 403, если заказ принадлежит другому пользователю."
    ),
)
async def get_order(
    order_id: UUID,
    user: Annotated[dict, Depends(_purchase_reader)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        order = await handle_get_order_details(
            GetOrderDetailsQuery(user_id=user["id"], order_id=order_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content={"order": jsonable_encoder(order)})


@router.post(
    "/{order_id}/payments",
    status_code=201,
    response_model=CreatePaymentResponse,
    summary="Инициировать платёж по заказу",
    description=(
        "Создаёт новый платёж для заказа. Поле `scope` задаёт тип платежа: "
        "`remaining` — оплата оставшейся суммы по заказу (после резервации); "
        "`scheduled` — оплата конкретного взноса из графика лизинговых платежей "
        "(требует `schedule_id`). "
        "Для `card` возвращает `widgetData` (токен виджета ModulBank), "
        "для `sbp` — `sbpData` (deeplink и QR-код). "
        "Для `scheduled` в ответе также присутствует `scheduleItem`. "
        "Доступно только клиенту-владельцу заказа."
    ),
)
async def create_payment(
    order_id: UUID,
    body: CreatePaymentRequest,
    user: Annotated[dict, Depends(_purchase_self)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        if body.scope == "remaining":
            result = await handle_pay_remaining(
                PayRemainingCommand(
                    user_id=user["id"],
                    order_id=order_id,
                    payment_method=body.payment_method,
                ),
                session,
            )
        else:
            if body.schedule_id is None:
                raise HTTPException(
                    status_code=422,
                    detail="Необходимо указать schedule_id при оплате по графику",
                )
            result = await handle_pay_schedule_item(
                PayScheduleItemCommand(
                    user_id=user["id"],
                    order_id=order_id,
                    schedule_id=body.schedule_id,
                    payment_method=body.payment_method,
                ),
                session,
            )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    result = _without_nested_payment_metadata(result)
    return JSONResponse(content=jsonable_encoder(result), status_code=201)


@router.post(
    "/{order_id}/request-cancellation",
    response_model=OrderResponse,
    summary="Запросить отмену заказа",
    description=(
        "Клиент запрашивает отмену своего заказа. "
        "Переводит заказ в статус ожидания подтверждения отмены. "
        "Опциональное поле `reason` — причина отмены (до 1000 символов). "
        "Фактическая отмена выполняется сотрудником через `POST /{order_id}/cancel`."
    ),
)
async def request_cancellation(
    order_id: UUID,
    body: RequestCancellationRequest,
    user: Annotated[dict, Depends(_purchase_self)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_request_cancellation(
            RequestCancellationCommand(user_id=user["id"], order_id=order_id, reason=body.reason),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Подтвердить отмену заказа",
    description=(
        "Сотрудник (`carcraft_employee`) подтверждает отмену заказа. "
        "Переводит заказ в финальный статус отменён, освобождает автомобиль. "
        "Вызывается после того, как клиент подал запрос через `request-cancellation`."
    ),
)
async def approve_cancellation(
    order_id: UUID,
    _user: Annotated[dict, Depends(_purchase_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_approve_cancellation(
            ApproveCancellationCommand(order_id=order_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{order_id}/payments",
    response_model=PaymentsListResponse,
    summary="Платежи по заказу",
    description=(
        "Возвращает список всех платежей по заказу: суммы, статусы, "
        "методы оплаты, фискальные данные, ссылки на чеки."
    ),
)
async def get_order_payments(
    order_id: UUID,
    user: Annotated[dict, Depends(_purchase_reader)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        payments = await handle_get_order_payments(
            GetOrderPaymentsQuery(user_id=user["id"], order_id=order_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    payments = [_without_vehicle_commerce_metadata(payment) for payment in payments]
    return JSONResponse(content={"payments": jsonable_encoder(payments)})


@router.get(
    "/{order_id}/schedule",
    response_model=ScheduleListResponse,
    summary="График лизинговых платежей",
    description=(
        "Возвращает график платежей по лизинговому заказу: номер взноса, дата, "
        "сумма, разбивка на основной долг и проценты, статус оплаты и ссылка на чек."
    ),
)
async def get_order_schedule(
    order_id: UUID,
    user: Annotated[dict, Depends(_purchase_reader)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        schedule = await handle_get_order_schedule(
            GetOrderScheduleQuery(user_id=user["id"], order_id=order_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content={"schedule": jsonable_encoder(schedule)})
