"""REST resources for special-equipment commerce."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
)
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from application.application_create_idempotency import (
    begin_application_create,
    finish_application_create,
)
from application.errors import ServiceError
from application.queries.special_equipment_payment_reconciliation import (
    get_payment_reconciliation,
    list_payment_reconciliations,
)
from application.special_equipment_checkout import CheckoutAllocationError
from application.special_equipment_commerce import (
    CancelOrderCommand,
    ConfirmOfflinePaymentCommand,
    ConfirmOrderRefundCommand,
    CreateLeasingApplicationCommand,
    CreateOrderCommand,
    CreateRemainingPaymentCommand,
    CreateScheduledPaymentCommand,
    DeleteCartItemCommand,
    PatchCartItemCommand,
    PutCartItemCommand,
    TransferGuestCartCommand,
    UserProductCommand,
    cancel_order,
    clear_cart,
    clear_favorites,
    confirm_offline_payment,
    confirm_order_refund,
    create_leasing_application,
    create_order,
    create_remaining_payment,
    create_scheduled_payment,
    delete_cart_item,
    delete_favorite,
    get_leasing_payment_schedule,
    get_order,
    get_payment_receipt_content,
    get_payment_status,
    list_cart,
    list_favorites,
    list_orders,
    patch_cart_item,
    put_cart_item,
    put_favorite,
    transfer_guest_cart,
)
from domain.application_sources import SOURCE_VIEW_ROLES
from domain.errors import (
    ApplicationCreateIdempotencyConflictError,
    DomainError,
    PaymentGatewayError,
)
from domain.services.object_storage import ObjectStorage, StoredObject
from domain.special_equipment_commerce import (
    SpecialEquipmentCartConfigurationConflictError,
    SpecialEquipmentCartPositionConflictError,
    SpecialEquipmentIdempotencyConflictError,
    SpecialEquipmentOrderAccessError,
    SpecialEquipmentOrderNotFoundError,
    SpecialEquipmentOrderStateError,
    SpecialEquipmentPriceRequiredError,
    SpecialEquipmentProductNotFoundError,
    SpecialEquipmentProductUnavailableError,
    SpecialEquipmentPurchaseType,
    SpecialEquipmentRefundReferenceConflictError,
)
from domain.storefronts import CatalogScope
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.dependencies.storefront import resolve_catalog_scope
from presentation.schemas.special_equipment_commerce import (
    CancelOrderRequest,
    CartListResponse,
    CartPatchResponse,
    CartPutResponse,
    CheckoutConflictResponse,
    ConfirmOrderRefundRequest,
    CreateLeasingApplicationRequest,
    CreateOrderRequest,
    CreateOrderResponse,
    CreatePaymentResponse,
    CreateRemainingPaymentRequest,
    CreateScheduledPaymentRequest,
    CreateScheduledPaymentResponse,
    FavoriteListResponse,
    FavoritePutResponse,
    GuestCartTransferRequest,
    GuestCartTransferResponse,
    LeasingApplicationCreatedResponse,
    LeasingScheduleResponse,
    OrderDetailResponse,
    OrderListResponse,
    OrderMutationResponse,
    PatchCartItemRequest,
    PaymentConfirmationResponse,
    PaymentReconciliationDetailResponse,
    PaymentReconciliationListResponse,
    PutCartItemRequest,
    RefundConfirmationResponse,
    SpecialEquipmentPaymentStatusResponse,
)

router = APIRouter()

_CHECKOUT_CONFLICT_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {
        "model": CheckoutConflictResponse,
        "description": "Конфликт аллокации эквивалентных товаров",
    }
}

_applications_write = require_scopes("applications:write")
_purchases_write = require_scopes("purchases:write")
_purchases_read = require_scopes("purchases:read")
_purchases_admin = require_scopes("purchases:admin")


def _public_json(
    contract: type[BaseModel],
    payload: Any,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Serialize only fields declared by the public response contract.

    Returning a ``JSONResponse`` bypasses FastAPI response-model filtering.
    Commerce application dictionaries contain provider payloads, storage keys,
    idempotency hashes and analytics lineage, so every JSON response must pass
    through an explicit Pydantic allow-list before it crosses the HTTP boundary.
    """

    body = contract.model_validate(payload).model_dump(mode="json", by_alias=True)
    if body.get("source_type") is None:
        body.pop("source_type", None)
    return JSONResponse(content=body, status_code=status_code, headers=headers)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, ServiceError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    if isinstance(exc, PaymentGatewayError):
        status = 502
    elif isinstance(
        exc,
        (SpecialEquipmentProductNotFoundError, SpecialEquipmentOrderNotFoundError),
    ):
        status = 404
    elif isinstance(exc, SpecialEquipmentOrderAccessError):
        status = 403
    elif isinstance(
        exc,
        (
            SpecialEquipmentProductUnavailableError,
            SpecialEquipmentCartConfigurationConflictError,
            SpecialEquipmentCartPositionConflictError,
            SpecialEquipmentIdempotencyConflictError,
            ApplicationCreateIdempotencyConflictError,
            SpecialEquipmentRefundReferenceConflictError,
        ),
    ):
        status = 409
    elif isinstance(
        exc, (SpecialEquipmentPriceRequiredError, SpecialEquipmentOrderStateError)
    ):
        status = 422
    else:
        status = 400
    return HTTPException(status_code=status, detail=str(exc))


def _checkout_http(exc: CheckoutAllocationError) -> JSONResponse:
    detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
    if exc.requested is not None:
        detail["requested"] = exc.requested
    if exc.available is not None:
        detail["available"] = exc.available
    body = CheckoutConflictResponse.model_validate(detail).model_dump(
        mode="json", exclude_none=True
    )
    return JSONResponse(status_code=409, content=body)


def _structured_service_response(exc: ServiceError) -> JSONResponse | None:
    payload = exc.structured_payload()
    if payload is None:
        return None
    body = CheckoutConflictResponse.model_validate(payload).model_dump(
        mode="json", exclude_none=True
    )
    return JSONResponse(status_code=exc.status_code, content=body)


def _receipt_range(  # noqa: PLR0911 -- explicit invalid range exits
    value: str, size: int
) -> tuple[int, int] | None:
    if not value.startswith("bytes=") or "," in value:
        return None
    start_raw, separator, end_raw = value[6:].partition("-")
    if separator != "-":
        return None
    try:
        if not start_raw:
            suffix = int(end_raw)
            if suffix <= 0:
                return None
            return max(0, size - suffix), size - 1
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    except ValueError:
        return None
    if start < 0 or start >= size or end < start:
        return None
    return start, min(end, size - 1)


def _receipt_response(
    obj: StoredObject,
    request: Request,
    payment_id: UUID,
) -> Response:
    etag = obj.etag
    if etag and not etag.startswith('"'):
        etag = f'"{etag.strip(chr(34))}"'
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        "Content-Disposition": (
            f'attachment; filename="special-equipment-receipt-{payment_id}.pdf"'
        ),
    }
    if etag:
        headers["ETag"] = etag
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
    raw_range = request.headers.get("range")
    if raw_range:
        interval = _receipt_range(raw_range, obj.size)
        if interval is None:
            headers["Content-Range"] = f"bytes */{obj.size}"
            return Response(status_code=416, headers=headers)
        start, end = interval
        content = obj.data[start : end + 1]
        headers["Content-Range"] = f"bytes {start}-{end}/{obj.size}"
        headers["Content-Length"] = str(len(content))
        return Response(
            content=content,
            status_code=206,
            media_type=obj.content_type,
            headers=headers,
        )
    headers["Content-Length"] = str(obj.size)
    return Response(content=obj.data, media_type=obj.content_type, headers=headers)


@router.get(
    "/favorites",
    response_model=FavoriteListResponse,
    summary="Избранная спецтехника",
    description="Возвращает избранные единицы спецтехники текущего пользователя.",
)
async def get_favorites(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    return _public_json(
        FavoriteListResponse,
        {"items": await list_favorites(user["id"], session, scope=scope)},
    )


@router.put(
    "/favorites/{product_id}",
    response_model=FavoritePutResponse,
    summary="Добавить спецтехнику в избранное",
    description="Идемпотентно создаёт связь пользователя с опубликованным товаром.",
)
async def add_favorite(
    product_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    try:
        result = await put_favorite(
            UserProductCommand(user["id"], product_id),
            session,
            scope=scope,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(
        FavoritePutResponse,
        result,
        status_code=201 if result["created"] else 200,
        headers={"Location": f"/api/v1/special-equipment/favorites/{product_id}"},
    )


@router.delete(
    "/favorites/{product_id}",
    status_code=204,
    summary="Удалить спецтехнику из избранного",
    description="Идемпотентно удаляет одну связь избранного текущего пользователя.",
)
async def remove_favorite(
    product_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await delete_favorite(
        UserProductCommand(user["id"], product_id),
        session,
    )
    await session.commit()
    return Response(status_code=204)


@router.delete(
    "/favorites",
    status_code=204,
    summary="Очистить избранную спецтехнику",
    description="Удаляет все связи только при явном `confirm=true`.",
)
async def remove_all_favorites(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    confirm: Annotated[bool, Query()] = False,
) -> Response:
    if not confirm:
        raise HTTPException(status_code=422, detail="Для очистки передайте confirm=true")
    await clear_favorites(user["id"], session)
    await session.commit()
    return Response(status_code=204)


@router.get(
    "/cart-items",
    response_model=CartListResponse,
    summary="Корзина спецтехники",
    description="Возвращает единичные товары и их актуальную доступность без резервирования.",
)
async def get_cart_items(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    return _public_json(
        CartListResponse,
        {"items": await list_cart(user["id"], session, scope=scope)},
    )


@router.post(
    "/cart-items",
    response_model=CartPutResponse,
    status_code=201,
    summary="Положить спецтехнику в корзину",
    description=(
        "Создаёт или обновляет самостоятельную либо дочернюю строку корзины "
        "с независимым количеством."
    ),
    responses=_CHECKOUT_CONFLICT_RESPONSES,
)
async def add_cart_item(
    body: PutCartItemRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    try:
        result = await put_cart_item(
            PutCartItemCommand(
                user_id=user["id"],
                product_id=body.product_id,
                quantity=body.quantity,
                allow_overstock=body.allow_overstock,
                parent_item_id=body.parent_item_id,
                is_selected=body.is_selected,
                comment=body.comment,
                equipments=body.equipments,
                services=body.services,
            ),
            session,
            scope=scope,
        )
    except CheckoutAllocationError as exc:
        return _checkout_http(exc)
    except ServiceError as exc:
        if response := _structured_service_response(exc):
            return response
        raise _http(exc) from exc
    except DomainError as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(
        CartPutResponse,
        result,
        status_code=201 if result["created"] else 200,
        headers={
            "Location": (
                "/api/v1/special-equipment/cart-items/"
                f"{result['cart_item']['id']}"
            )
        },
    )


@router.patch(
    "/cart-items/{cart_item_id}",
    response_model=CartPatchResponse,
    summary="Изменить позицию корзины спецтехники",
    description="Частично обновляет выбор, комментарий, опции и разрешённую ролью цену.",
    responses=_CHECKOUT_CONFLICT_RESPONSES,
)
async def update_cart_item(
    body: PatchCartItemRequest,
    cart_item_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        item = await patch_cart_item(
            PatchCartItemCommand(
                user_id=user["id"],
                cart_item_id=cart_item_id,
                actor_role=str(user.get("role") or ""),
                changes=body.model_dump(exclude_unset=True),
            ),
            session,
        )
    except CheckoutAllocationError as exc:
        return _checkout_http(exc)
    except ServiceError as exc:
        if response := _structured_service_response(exc):
            return response
        raise _http(exc) from exc
    except DomainError as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(CartPatchResponse, {"cart_item": item})


@router.delete(
    "/cart-items/{cart_item_id}",
    status_code=204,
    summary="Удалить позицию корзины спецтехники",
    description="Идемпотентно удаляет одну позицию текущего пользователя.",
)
async def remove_cart_item(
    cart_item_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        await delete_cart_item(
            DeleteCartItemCommand(user["id"], cart_item_id),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return Response(status_code=204)


@router.put(
    "/cart-transfers/{transfer_id}",
    response_model=GuestCartTransferResponse,
    summary="Перенести гостевую корзину спецтехники",
    description=(
        "После входа идемпотентно переносит versioned localStorage-корзину. "
        "Повтор того же transfer_id и payload возвращает прежний результат."
    ),
    responses=_CHECKOUT_CONFLICT_RESPONSES,
)
async def transfer_special_equipment_guest_cart(
    transfer_id: Annotated[UUID, Path()],
    body: GuestCartTransferRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    try:
        result = await transfer_guest_cart(
            TransferGuestCartCommand(
                user_id=user["id"],
                transfer_id=transfer_id,
                version=body.version,
                items=tuple(
                    item.model_dump(mode="python") for item in body.items
                ),
                scope=scope,
            ),
            session,
        )
    except CheckoutAllocationError as exc:
        return _checkout_http(exc)
    except ServiceError as exc:
        if response := _structured_service_response(exc):
            return response
        raise _http(exc) from exc
    except DomainError as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(GuestCartTransferResponse, result)


@router.delete(
    "/cart-items",
    status_code=204,
    summary="Очистить корзину спецтехники",
    description="Удаляет все позиции только при явном `confirm=true`.",
)
async def remove_all_cart_items(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    confirm: Annotated[bool, Query()] = False,
) -> Response:
    if not confirm:
        raise HTTPException(status_code=422, detail="Для очистки передайте confirm=true")
    await clear_cart(user["id"], session)
    await session.commit()
    return Response(status_code=204)


@router.post(
    "/leasing-applications",
    status_code=201,
    response_model=LeasingApplicationCreatedResponse,
    summary="Создать лизинговую заявку на спецтехнику",
    description=(
        "Создаёт общую leasing application для компании пользователя и "
        "FK-корректную special-equipment строку без резерва. Сотрудник "
        "CarCraft или platform admin может действовать для любой компании."
    ),
    responses=_CHECKOUT_CONFLICT_RESPONSES,
)
async def create_special_equipment_leasing_application(
    body: CreateLeasingApplicationRequest,
    user: Annotated[dict[str, Any], Depends(_applications_write)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
) -> JSONResponse:
    endpoint = "POST /api/v1/special-equipment/leasing-applications"
    try:
        replay = await begin_application_create(
            session,
            endpoint=endpoint,
            key=idempotency_key,
            payload=body.model_dump(mode="json"),
        )
        if replay is not None:
            if user.get("role") not in SOURCE_VIEW_ROLES:
                replay.pop("source_type", None)
            return _public_json(LeasingApplicationCreatedResponse, replay)
        result = await create_leasing_application(
            CreateLeasingApplicationCommand(
                source_type=body.source_type,
                user_id=user["id"],
                company_id=body.company_id,
                cart_item_ids=tuple(body.cart_item_ids),
                actor_role=str(user.get("role") or "") or None,
                comment=body.comment,
                leasing_purpose=body.leasing_purpose,
                leasing_purposes=body.leasing_purposes,
                regions=body.regions,
                down_payment_percent=body.down_payment_percent,
                lease_term_months=body.lease_term_months,
                scope=scope,
            ),
            session,
        )
        result = LeasingApplicationCreatedResponse.model_validate(result).model_dump(mode="json", by_alias=True)
        if result.get("source_type") is None:
            result.pop("source_type", None)
        await finish_application_create(
            session,
            endpoint=endpoint,
            key=idempotency_key,
            result=result,
        )
    except CheckoutAllocationError as exc:
        return _checkout_http(exc)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(
        LeasingApplicationCreatedResponse,
        result,
        status_code=201,
        headers={
            "Location": f"/api/v1/applications/{result['application_id']}"
        },
    )


@router.post(
    "/purchase-orders",
    status_code=201,
    response_model=CreateOrderResponse,
    summary="Создать заказ или предоплату на спецтехнику",
    description=(
        "Блокирует конкретную единицу, повторно проверяет цену/статус и создаёт "
        "идемпотентный order. Для card возвращает widgetData, для sbp — sbpData."
    ),
    responses=_CHECKOUT_CONFLICT_RESPONSES,
)
async def create_special_equipment_order(
    body: CreateOrderRequest,
    user: Annotated[dict[str, Any], Depends(_purchases_write)],
    session: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
) -> JSONResponse:
    try:
        result = await create_order(
            CreateOrderCommand(
                user_id=user["id"],
                cart_item_ids=tuple(body.cart_item_ids),
                purchase_type=SpecialEquipmentPurchaseType(body.purchase_type),
                idempotency_key=idempotency_key,
                payment_method=body.payment_method,
                down_payment_percent=body.down_payment_percent,
            ),
            session,
        )
    except CheckoutAllocationError as exc:
        return _checkout_http(exc)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    order = result["order"]
    return _public_json(
        CreateOrderResponse,
        result,
        status_code=200 if result["replayed"] else 201,
        headers={
            "Location": f"/api/v1/special-equipment/purchase-orders/{order['id']}"
        },
    )


@router.get(
    "/purchase-orders",
    response_model=OrderListResponse,
    summary="Список заказов спецтехники",
    description="Возвращает immutable snapshots заказов текущего пользователя.",
)
async def get_special_equipment_orders(
    user: Annotated[dict[str, Any], Depends(_purchases_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JSONResponse:
    return _public_json(
        OrderListResponse,
        await list_orders(
            user["id"], session, page=page, page_size=page_size
        ),
    )


@router.get(
    "/purchase-orders/{order_id}",
    response_model=OrderDetailResponse,
    summary="Детали заказа спецтехники",
    description="Возвращает принадлежащий пользователю заказ и безопасные данные платежей.",
)
async def get_special_equipment_order(
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_purchases_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        order = await get_order(user["id"], order_id, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _public_json(OrderDetailResponse, {"order": order})


@router.get(
    "/purchase-orders/{order_id}/payment-schedule",
    response_model=LeasingScheduleResponse,
    summary="Получить график платежей по лизингу спецтехники",
    description=(
        "Возвращает owner-scoped график и только относительные FastAPI URL "
        "фискальных чеков. Storage keys и provider payloads не выдаются."
    ),
)
async def get_special_equipment_leasing_schedule(
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_purchases_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        items = await get_leasing_payment_schedule(
            user["id"], order_id, session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _public_json(LeasingScheduleResponse, {"items": items})


@router.post(
    "/purchase-orders/{order_id}/payment-schedule/{schedule_id}/payments",
    status_code=201,
    response_model=CreateScheduledPaymentResponse,
    summary="Создать платёж лизингового взноса спецтехники",
    description=(
        "Создаёт идемпотентную попытку оплаты выбранного взноса. Строка "
        "графика становится оплаченной только после callback провайдера либо "
        "employee-подтверждения банковского перевода."
    ),
)
async def create_special_equipment_scheduled_payment(
    body: CreateScheduledPaymentRequest,
    order_id: Annotated[UUID, Path()],
    schedule_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_purchases_write)],
    session: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
) -> JSONResponse:
    try:
        result = await create_scheduled_payment(
            CreateScheduledPaymentCommand(
                user_id=user["id"],
                order_id=order_id,
                schedule_id=schedule_id,
                idempotency_key=idempotency_key,
                payment_method=body.payment_method,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    payment = result["payment"]
    return _public_json(
        CreateScheduledPaymentResponse,
        result,
        status_code=200 if result["replayed"] else 201,
        headers={
            "Location": (
                f"/api/v1/special-equipment/purchase-orders/{order_id}"
                f"/payments/{payment['id']}"
            )
        },
    )


@router.post(
    "/purchase-orders/{order_id}/payments",
    status_code=201,
    response_model=CreatePaymentResponse,
    summary="Создать доплату по резерву спецтехники",
    description=(
        "Создаёт идемпотентный платёж на весь оставшийся баланс зарезервированной "
        "единицы. Для card возвращает widgetData, для sbp — sbpData."
    ),
)
async def create_special_equipment_remaining_payment(
    body: CreateRemainingPaymentRequest,
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_purchases_write)],
    session: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
) -> JSONResponse:
    try:
        result = await create_remaining_payment(
            CreateRemainingPaymentCommand(
                user_id=user["id"],
                order_id=order_id,
                idempotency_key=idempotency_key,
                payment_method=body.payment_method,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    payment = result["payment"]
    return _public_json(
        CreatePaymentResponse,
        result,
        status_code=200 if result["replayed"] else 201,
        headers={
            "Location": f"/api/v1/special-equipment/purchase-orders/{order_id}/payments/{payment['id']}"
        },
    )


@router.get(
    "/purchase-orders/{order_id}/payments/{payment_id}/status",
    response_model=SpecialEquipmentPaymentStatusResponse,
    summary="Статус платежа за спецтехнику",
    description=(
        "Возвращает состояние принадлежащего пользователю платежа для polling. "
        "Чек, если появится, доступен только через FastAPI content URL."
    ),
)
async def get_special_equipment_payment_status(
    order_id: Annotated[UUID, Path()],
    payment_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_purchases_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        payment = await get_payment_status(
            user["id"],
            order_id,
            payment_id,
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _public_json(
        SpecialEquipmentPaymentStatusResponse,
        {"payment": payment},
    )


@router.get(
    "/purchase-orders/{order_id}/payments/{payment_id}/receipt/content",
    response_model=None,
    summary="Фискальный чек платежа за спецтехнику",
    description=(
        "Owner-scoped FastAPI proxy для приватного object storage. Поддерживает "
        "ETag и один byte Range; storage key и provider URL наружу не выдаются."
    ),
    responses={
        200: {"content": {"application/pdf": {}}},
        206: {"content": {"application/pdf": {}}},
        304: {"description": "Чек не изменился"},
        404: {"description": "Платёж или чек не найден"},
        416: {"description": "Некорректный byte range"},
    },
)
async def get_special_equipment_payment_receipt(
    order_id: Annotated[UUID, Path()],
    payment_id: Annotated[UUID, Path()],
    request: Request,
    user: Annotated[dict[str, Any], Depends(_purchases_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        obj = await get_payment_receipt_content(
            user["id"],
            order_id,
            payment_id,
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _receipt_response(obj, request, payment_id)


@router.put(
    "/purchase-orders/{order_id}/cancellation",
    response_model=OrderMutationResponse,
    summary="Запросить отмену заказа спецтехники",
    description=(
        "Неоплаченный заказ отменяется сразу. Для оплаченного заказа создаётся "
        "запрос отмены без освобождения техники до подтверждения возврата."
    ),
)
async def cancel_special_equipment_order(
    body: CancelOrderRequest,
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_purchases_write)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        order = await cancel_order(
            CancelOrderCommand(
                user_id=user["id"],
                order_id=order_id,
                reason=body.reason,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(OrderMutationResponse, {"order": order})


@router.put(
    "/purchase-orders/{order_id}/refund-confirmation",
    response_model=RefundConfirmationResponse,
    summary="Подтвердить внешний возврат по спецтехнике",
    description=(
        "Employee/admin фиксирует уже успешно выполненный внешний возврат. "
        "Метод не вызывает платёжного провайдера и идемпотентен по внешней ссылке."
    ),
)
async def confirm_special_equipment_refund(
    body: ConfirmOrderRefundRequest,
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_purchases_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await confirm_order_refund(
            ConfirmOrderRefundCommand(
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                order_id=order_id,
                external_reference=body.external_reference,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(RefundConfirmationResponse, result)


@router.put(
    "/purchase-orders/{order_id}/payments/{payment_id}/offline-confirmation",
    response_model=PaymentConfirmationResponse,
    summary="Подтвердить банковский перевод по спецтехнике",
    description="Служебный employee-only переход для подтверждённого внешним банком перевода.",
)
async def confirm_special_equipment_bank_transfer(
    order_id: Annotated[UUID, Path()],
    payment_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_purchases_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await confirm_offline_payment(
            ConfirmOfflinePaymentCommand(
                actor_role=str(user.get("role") or ""),
                order_id=order_id,
                payment_id=payment_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(PaymentConfirmationResponse, result)


@router.get(
    "/payment-reconciliations",
    response_model=PaymentReconciliationListResponse,
    summary="Список ручных сверок платежей спецтехники",
    description=(
        "Employee/admin получает подписанные callback, которые нельзя было "
        "безопасно применить автоматически. Секреты и исходная подпись скрыты."
    ),
)
async def list_special_equipment_payment_reconciliations(
    user: Annotated[dict[str, Any], Depends(_purchases_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> JSONResponse:
    del user
    result = await list_payment_reconciliations(
        session,
        page=page,
        page_size=page_size,
    )
    return _public_json(PaymentReconciliationListResponse, result)


@router.get(
    "/payment-reconciliations/{reconciliation_id}",
    response_model=PaymentReconciliationDetailResponse,
    summary="Детали ручной сверки платежа спецтехники",
    description=(
        "Employee/admin получает безопасный operational read model одного "
        "конфликтного callback без подписи и персональных данных."
    ),
)
async def get_special_equipment_payment_reconciliation(
    reconciliation_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_purchases_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    del user
    try:
        result = await get_payment_reconciliation(session, reconciliation_id)
    except ServiceError as exc:
        raise _http(exc) from exc
    return _public_json(PaymentReconciliationDetailResponse, result)
