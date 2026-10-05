"""Thin HTTP adapter for the unified commerce facade."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from application.application_create_idempotency import (
    begin_application_create,
    finish_application_create,
)
from application.commerce import (
    CommerceLeasingApplicationLineCommand,
    CreateCommerceLeasingApplicationBatchCommand,
    CreateCommerceOrderCommand,
    CreateCommercePaymentCommand,
    commerce_facade,
)
from application.errors import ServiceError, domain_to_http
from domain.application_sources import SOURCE_VIEW_ROLES
from domain.commerce import CommerceItemRef, CommerceItemType, CommerceOrderRef
from domain.errors import DomainError, PaymentGatewayError
from domain.services.object_storage import ObjectStorage, StoredObject
from domain.special_equipment_commerce import (
    SpecialEquipmentIdempotencyConflictError,
    SpecialEquipmentOrderAccessError,
    SpecialEquipmentOrderNotFoundError,
    SpecialEquipmentOrderStateError,
    SpecialEquipmentPriceRequiredError,
    SpecialEquipmentProductNotFoundError,
    SpecialEquipmentProductUnavailableError,
)
from domain.storefronts import CatalogScope
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import require_any_scopes, require_scopes
from presentation.dependencies.storefront import resolve_catalog_scope
from presentation.schemas.commerce import (
    CancelCommerceOrderRequest,
    CommerceItemResponse,
    CommerceOrderListResponse,
    CommerceOrderResponse,
    CommercePaymentListResponse,
    CommercePaymentResponse,
    CommerceScheduleResponse,
    CreateCommerceLeasingApplicationRequest,
    CreateCommerceLeasingApplicationResponse,
    CreateCommerceOrderRequest,
    CreateCommerceOrderResponse,
    CreateCommercePaymentRequest,
    CreateCommercePaymentResponse,
)
from presentation.schemas.special_equipment_commerce import CheckoutConflictResponse

router = APIRouter()
storefront_router = APIRouter()

_CHECKOUT_CONFLICT_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {
        "model": CheckoutConflictResponse,
        "description": "Конфликт аллокации эквивалентных товаров",
    }
}

_read = require_scopes("purchases:read")
_item_read = require_any_scopes("purchases:read", "applications:write")
_write = require_scopes("purchases:write")
_self_pay = require_scopes("purchases:self-pay")
_applications_write = require_scopes("applications:write")


def _public_json(
    contract: type[BaseModel],
    payload: Any,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = contract.model_validate(payload).model_dump(mode="json", by_alias=True)
    if body.get("source_type") is None:
        body.pop("source_type", None)
    return JSONResponse(content=body, status_code=status_code, headers=headers)


def _http(  # noqa: PLR0911 -- explicit domain-to-status mapping
    exc: ServiceError | DomainError,
) -> HTTPException:
    if isinstance(exc, ServiceError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    if isinstance(exc, PaymentGatewayError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(
        exc,
        (SpecialEquipmentProductNotFoundError, SpecialEquipmentOrderNotFoundError),
    ):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SpecialEquipmentOrderAccessError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(
        exc,
        (
            SpecialEquipmentProductUnavailableError,
            SpecialEquipmentIdempotencyConflictError,
        ),
    ):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(
        exc,
        (SpecialEquipmentPriceRequiredError, SpecialEquipmentOrderStateError),
    ):
        return HTTPException(status_code=422, detail=str(exc))
    mapped = domain_to_http(exc)
    return HTTPException(status_code=mapped.status_code, detail=str(mapped))


def _structured_service_response(exc: ServiceError) -> JSONResponse | None:
    payload = exc.structured_payload()
    if payload is None:
        return None
    body = CheckoutConflictResponse.model_validate(payload).model_dump(
        mode="json", exclude_none=True
    )
    return JSONResponse(status_code=exc.status_code, content=body)


def _ref(item_type: CommerceItemType, item_id: UUID) -> CommerceItemRef:
    return CommerceItemRef(type=item_type, id=item_id)


def _receipt_range(  # noqa: PLR0911 -- each invalid form exits explicitly
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
        "Content-Disposition": f'attachment; filename="receipt-{payment_id}.pdf"',
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
    "/items/{item_type}/{item_id}",
    response_model=CommerceItemResponse,
    summary="Получить товар для единого commerce-flow",
    description=(
        "Возвращает нормализованную проекцию конкретного автомобиля или единицы "
        "спецтехники. Домен задаётся явно и не определяется по UUID."
    ),
)
@storefront_router.get(
    "/items/{item_type}/{item_id}",
    response_model=CommerceItemResponse,
    summary="Получить товар в области витрины для единого commerce-flow",
    description=(
        "Возвращает нормализованную проекцию товара с канонической ссылкой, "
        "ограниченной складами выбранной витрины."
    ),
)
async def get_commerce_item(
    item_type: Annotated[CommerceItemType, Path()],
    item_id: Annotated[UUID, Path()],
    _user: Annotated[dict[str, Any], Depends(_item_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    try:
        item = await commerce_facade.get_item(
            _ref(item_type, item_id), session, scope=scope
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _public_json(CommerceItemResponse, {"item": item})


@router.post(
    "/orders",
    status_code=201,
    response_model=CreateCommerceOrderResponse,
    summary="Создать заказ через единый commerce-flow",
    description=(
        "Повторно проверяет и блокирует товар в его исходном каталоге, затем "
        "делегирует создание существующему vehicle или special-equipment use case."
    ),
    responses=_CHECKOUT_CONFLICT_RESPONSES,
)
async def create_commerce_order(
    body: CreateCommerceOrderRequest,
    user: Annotated[dict[str, Any], Depends(_write)],
    session: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
) -> JSONResponse:
    item = CommerceItemRef(type=CommerceItemType(body.item.type), id=body.item.id)
    try:
        result = await commerce_facade.create_order(
            CreateCommerceOrderCommand(
                user_id=user["id"],
                item=item,
                purchase_type=body.purchase_type,
                payment_method=body.payment_method,
                idempotency_key=idempotency_key,
                quantity=body.quantity,
                down_payment_percent=body.down_payment_percent,
                cart_item_ids=tuple(body.cart_item_ids),
            ),
            session,
        )
    except ServiceError as exc:
        if response := _structured_service_response(exc):
            return response
        raise _http(exc) from exc
    except DomainError as exc:
        raise _http(exc) from exc
    await session.commit()
    status_code = 200 if result["replayed"] else 201
    return _public_json(
        CreateCommerceOrderResponse,
        result,
        status_code=status_code,
        headers={
            "Location": (
                f"/api/v1/commerce/orders/{item.type.value}/{result['orders'][0]['id']}"
            )
        },
    )


@router.get(
    "/orders",
    response_model=CommerceOrderListResponse,
    summary="Список всех заказов пользователя",
    description=(
        "Объединяет vehicle и special-equipment заказы в одну отсортированную "
        "проекцию. Query `type` позволяет запросить только один домен."
    ),
)
async def list_commerce_orders(
    user: Annotated[dict[str, Any], Depends(_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
    item_type: Annotated[CommerceItemType | None, Query(alias="type")] = None,
) -> JSONResponse:
    try:
        items = await commerce_facade.list_orders(user["id"], session, item_type)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _public_json(CommerceOrderListResponse, {"items": items})


@router.get(
    "/orders/{item_type}/{order_id}",
    response_model=CommerceOrderResponse,
    summary="Детали commerce-заказа",
    description="Возвращает owner-scoped нормализованный заказ выбранного домена.",
)
async def get_commerce_order(
    item_type: Annotated[CommerceItemType, Path()],
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        order = await commerce_facade.adapter(item_type).get_order(
            user["id"], order_id, session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _public_json(CommerceOrderResponse, {"order": order})


@router.get(
    "/orders/{item_type}/{order_id}/payments",
    response_model=CommercePaymentListResponse,
    summary="Платежи commerce-заказа",
    description="Возвращает owner-scoped историю платежей без provider payload и S3 key.",
)
async def list_commerce_payments(
    item_type: Annotated[CommerceItemType, Path()],
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        items = await commerce_facade.adapter(item_type).list_payments(
            user["id"], order_id, session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _public_json(CommercePaymentListResponse, {"items": items})


@router.post(
    "/orders/{item_type}/{order_id}/payments",
    status_code=201,
    response_model=CreateCommercePaymentResponse,
    summary="Создать платёж commerce-заказа",
    description=(
        "Создаёт доплату или платёж выбранного пункта графика через адаптер "
        "заказа и сохраняет owner-scoped результат для безопасного replay."
    ),
)
async def create_commerce_payment(
    body: CreateCommercePaymentRequest,
    item_type: Annotated[CommerceItemType, Path()],
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_self_pay)],
    session: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
) -> JSONResponse:
    try:
        result = await commerce_facade.adapter(item_type).create_payment(
            CreateCommercePaymentCommand(
                user_id=user["id"],
                order=CommerceOrderRef(type=item_type, id=order_id),
                scope=body.scope,
                schedule_id=body.schedule_id,
                payment_method=body.payment_method,
                idempotency_key=idempotency_key,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    status_code = 200 if result["replayed"] else 201
    return _public_json(
        CreateCommercePaymentResponse,
        result,
        status_code=status_code,
        headers={
            "Location": (
                f"/api/v1/commerce/orders/{item_type.value}/{order_id}/payments/"
                f"{result['payment']['id']}"
            )
        },
    )


@router.get(
    "/orders/{item_type}/{order_id}/payments/{payment_id}/status",
    response_model=CommercePaymentResponse,
    summary="Статус commerce-платежа",
    description="Owner-scoped polling платежа с относительной ссылкой на чек.",
)
async def get_commerce_payment_status(
    item_type: Annotated[CommerceItemType, Path()],
    order_id: Annotated[UUID, Path()],
    payment_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        payment = await commerce_facade.adapter(item_type).get_payment_status(
            user["id"], order_id, payment_id, session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _public_json(CommercePaymentResponse, {"payment": payment})


@router.get(
    "/orders/{item_type}/{order_id}/payments/{payment_id}/receipt/content",
    response_model=None,
    summary="Получить фискальный чек через FastAPI proxy",
    description=(
        "Проверяет владельца заказа и возвращает бинарный чек из приватного "
        "хранилища. Прямой URL и storage key не раскрываются."
    ),
    responses={
        200: {"content": {"application/pdf": {}}},
        206: {"content": {"application/pdf": {}}},
        304: {"description": "Чек не изменился"},
        404: {"description": "Чек не найден"},
        416: {"description": "Некорректный byte range"},
    },
)
async def get_commerce_payment_receipt(
    item_type: Annotated[CommerceItemType, Path()],
    order_id: Annotated[UUID, Path()],
    payment_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    request: Request,
) -> Response:
    try:
        obj = await commerce_facade.adapter(item_type).get_receipt_content(
            user["id"], order_id, payment_id, session, storage
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _receipt_response(obj, request, payment_id)


@router.get(
    "/orders/{item_type}/{order_id}/schedule",
    response_model=CommerceScheduleResponse,
    summary="График лизинговых платежей",
    description="Возвращает нормализованный owner-scoped график выбранного заказа.",
)
async def get_commerce_schedule(
    item_type: Annotated[CommerceItemType, Path()],
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_read)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        items = await commerce_facade.adapter(item_type).get_schedule(
            user["id"], order_id, session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return _public_json(CommerceScheduleResponse, {"items": items})


@router.put(
    "/orders/{item_type}/{order_id}/cancellation",
    response_model=CommerceOrderResponse,
    summary="Отменить или запросить отмену commerce-заказа",
    description=(
        "Применяет существующую доменную политику: неоплаченная спецтехника "
        "освобождается сразу, оплаченная сделка и автомобиль переходят в запрос отмены."
    ),
)
async def cancel_commerce_order(
    body: CancelCommerceOrderRequest,
    item_type: Annotated[CommerceItemType, Path()],
    order_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(_self_pay)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        order = await commerce_facade.adapter(item_type).cancel_order(
            user["id"], order_id, body.reason, session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(CommerceOrderResponse, {"order": order})


@router.post(
    "/leasing-applications",
    status_code=201,
    response_model=CreateCommerceLeasingApplicationResponse,
    summary="Создать единую лизинговую заявку на commerce-товары",
    description=(
        "Создаёт одну общую leasing_application и FK-корректные строки автомобилей "
        "и спецтехники, после чего клиент продолжает стандартный application flow."
    ),
    responses=_CHECKOUT_CONFLICT_RESPONSES,
)
@storefront_router.post(
    "/leasing-applications",
    status_code=201,
    response_model=CreateCommerceLeasingApplicationResponse,
    summary="Создать лизинговую заявку из автомобильной витрины",
    description=(
        "Создаёт единую лизинговую заявку и сохраняет область выбранной витрины "
        "для последующих чтений и коммерческих операций."
    ),
    responses=_CHECKOUT_CONFLICT_RESPONSES,
)
async def create_commerce_leasing_application(
    body: CreateCommerceLeasingApplicationRequest,
    user: Annotated[dict[str, Any], Depends(_applications_write)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
) -> JSONResponse:
    items = [
        CommerceLeasingApplicationLineCommand(
            item=CommerceItemRef(
                type=CommerceItemType(line.item.type),
                id=line.item.id,
            ),
            quantity=line.quantity,
            allow_overstock=line.allow_overstock,
            custom_price=line.custom_price,
            comment=line.comment,
            equipments=line.equipments,
            services=line.services,
            leasing_purpose=line.leasing_purpose,
            leasing_purposes=line.leasing_purposes,
            leasing_purpose_comment=line.leasing_purpose_comment,
            regions=line.regions,
            cart_item_ids=tuple(line.cart_item_ids),
        )
        for line in body.items
    ]
    endpoint = "POST /api/v1/commerce/leasing-applications"
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
            return _public_json(CreateCommerceLeasingApplicationResponse, replay)
        result = await commerce_facade.create_leasing_application(
            CreateCommerceLeasingApplicationBatchCommand(
                source_type=body.source_type,
                user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                items=items,
                company_id=body.company_id,
                company=(body.company.model_dump() if body.company else None),
                name=body.name,
                email=body.email,
                down_payment_percent=body.down_payment_percent,
                lease_term_months=body.lease_term_months,
                calculation=(
                    body.calculation.model_dump(exclude_none=True)
                    if body.calculation is not None
                    else None
                ),
                scope=scope,
            ),
            session,
        )
        result = CreateCommerceLeasingApplicationResponse.model_validate(result).model_dump(mode="json", by_alias=True)
        if result.get("source_type") is None:
            result.pop("source_type", None)
        await finish_application_create(
            session,
            endpoint=endpoint,
            key=idempotency_key,
            result=result,
        )
    except ServiceError as exc:
        if response := _structured_service_response(exc):
            return response
        raise _http(exc) from exc
    except DomainError as exc:
        raise _http(exc) from exc
    await session.commit()
    return _public_json(
        CreateCommerceLeasingApplicationResponse,
        result,
        status_code=201,
        headers={"Location": f"/api/v1/applications/{result['application_id']}"},
    )
