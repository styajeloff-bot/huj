"""Exchange cart API (LC-owned) — Phase 5 E2, Phase 10 R5 REST cleanup."""
from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.exchange import (
    AddToExchangeCartCommand,
    ClearExchangeCartCommand,
    RemoveExchangeCartItemCommand,
    SubmitExchangeCartCommand,
    UpdateExchangeCartItemCommand,
    UploadCartItemFileCommand,
    handle_add_to_exchange_cart,
    handle_clear_exchange_cart,
    handle_remove_exchange_cart_item,
    handle_submit_exchange_cart,
    handle_update_exchange_cart_item,
    handle_upload_cart_item_file,
)
from application.errors import ServiceError, domain_to_http
from application.queries.exchange import (
    ListExchangeCartQuery,
    ListWarehousesForVehicleQuery,
    handle_list_exchange_cart,
    handle_list_warehouses_for_vehicle,
)
from application.queries.exchange.download_files import (
    download_cart_item_file,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import EXCHANGE_READ, EXCHANGE_WRITE
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import (
    require_scopes,
)
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)
from presentation.dependencies.notification_database import get_db
from presentation.schemas.exchange import (
    AddToExchangeCartBody,
    ExchangeCartAddResponse,
    ExchangeCartClearedResponse,
    ExchangeCartCountResponse,
    ExchangeCartListResponse,
    ExchangeCartSubmitResponse,
    ExchangeCartUpdateResponse,
    MessageResponse,
    UpdateExchangeCartItemBody,
)

router = APIRouter()

_read_access = require_scopes(EXCHANGE_READ)
_write_access = require_scopes(EXCHANGE_WRITE)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _require_lc_role(user: dict[str, Any]) -> None:
    role = str(user.get("role") or "")
    if role != "leasing_company":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Корзина биржи доступна только лизинговой компании",
                "code": "INSUFFICIENT_PERMISSIONS",
            },
        )


@router.get(
    "/",
    response_model=ExchangeCartListResponse,
    summary="Содержимое корзины биржи",
    description=(
        "Возвращает элементы корзины биржи текущей ЛК со связанными "
        "складами, опциями и per-dealer комментариями. Поддерживает "
        "лёгкую проекцию ``?fields=count`` — в этом режиме отдаётся "
        "только `{count: N}`."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_cart(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    fields: Annotated[
        Literal["count"] | None,
        Query(description="Лёгкая проекция: ``count`` → `{count: N}`."),
    ] = None,
) -> JSONResponse:
    _require_lc_role(user)
    result = await handle_list_exchange_cart(
        ListExchangeCartQuery(user_id=user["id"]), session
    )
    if fields == "count":
        summary = result.get("summary") or {}
        count = int(summary.get("total_items") or 0)
        return JSONResponse(content={"count": count})
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/",
    response_model=ExchangeCartAddResponse,
    status_code=201,
    summary="Добавить автомобиль в корзину биржи",
    description=(
        "Создаёт элемент корзины (уникальность по `(user_id, vehicle_id)`). "
        "Если элемент уже существует — увеличивает количество (upsert). "
        "Ответ 201 с телом созданного/обновлённого элемента и заголовком "
        "`Location: /api/v1/exchange/cart/{id}`."
    ),
    dependencies=[Depends(_write_access)],
)
async def create_cart_item(
    body: AddToExchangeCartBody,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    pid = getattr(body, "product_id", getattr(body, "vehicle_id", None))
    v_kw = "product_id" if "product_id" in getattr(AddToExchangeCartCommand, "__dataclass_fields__", {}) else "vehicle_id"
    add_cmd_args: dict[str, Any] = {
        "user_id": user["id"],
        "quantity": body.quantity,
        "warehouse_id": body.warehouse_id,
        "selected_support_ids": body.selected_support_ids,
        v_kw: pid,
    }
    try:
        result = await handle_add_to_exchange_cart(
            AddToExchangeCartCommand(**add_cmd_args),  # type: ignore[arg-type]
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    item = result.get("item") or {}
    headers = {"Location": f"/api/v1/exchange/cart/{item.get('id', '')}"}
    return JSONResponse(
        content=jsonable_encoder(result),
        status_code=201,
        headers=headers,
    )


@router.patch(
    "/{item_id}",
    response_model=ExchangeCartUpdateResponse,
    summary="Частичное обновление элемента корзины биржи",
    description=(
        "Применяет только переданные поля. Поля `warehouses` / `options` "
        "перезаписывают целиком (пустой список = очистить; отсутствие поля "
        "в body = не трогать). `dealer_comment` — upsert по `dealer_id`."
    ),
    dependencies=[Depends(_write_access)],
)
async def update_cart_item(
    item_id: UUID,
    body: UpdateExchangeCartItemBody,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    try:
        result = await handle_update_exchange_cart_item(
            UpdateExchangeCartItemCommand(
                item_id=item_id,
                user_id=user["id"],
                quantity=body.quantity,
                discount_type=body.discount_type,
                discount_value=body.discount_value,
                expiration_at=body.expiration_at, expiration_at_set="expiration_at" in body.model_fields_set,
                warehouses=body.warehouses,
                options=body.options,
                dealer_comment=(
                    (body.dealer_comment.dealer_id, body.dealer_comment.comment)
                    if body.dealer_comment is not None
                    else None
                ),
                selected_support_ids=body.selected_support_ids,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/{item_id}",
    response_model=MessageResponse,
    summary="Удалить элемент корзины биржи",
    description="Удаляет элемент; 404 если элемент не найден у текущего пользователя.",
    dependencies=[Depends(_write_access)],
)
async def remove_cart_item(
    item_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    try:
        result = await handle_remove_exchange_cart_item(
            RemoveExchangeCartItemCommand(
                item_id=item_id,
                user_id=user["id"],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/warehouses/{product_id}",
    summary="Склады, где доступна эта модификация",
    description=(
        "Возвращает склады, на которых есть в наличии товары с той же "
        "комплектацией. Используется в корзине биржи для выбора "
        "складов, куда будет направлена заявка."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_cart_warehouses(
    product_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    v_kw = "product_id" if "product_id" in getattr(ListWarehousesForVehicleQuery, "__dataclass_fields__", {}) else "vehicle_id"
    result = await handle_list_warehouses_for_vehicle(
        ListWarehousesForVehicleQuery(**{v_kw: product_id}), session
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/",
    response_model=ExchangeCartClearedResponse,
    summary="Очистить корзину биржи",
    description="Удаляет все элементы корзины биржи текущей ЛК.",
    dependencies=[Depends(_write_access)],
)
async def clear_cart(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    result = await handle_clear_exchange_cart(
        ClearExchangeCartCommand(user_id=user["id"]), session
    )
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{item_id}/upload",
    summary="Прикрепить файл к элементу корзины биржи",
    description=(
        "multipart/form-data; поле `file` (до 10 МБ). Сохраняет файл в "
        "объектное хранилище и пишет `file_url` + `file_name` на запись "
        "корзины. Позже при submit значения копируются на каждый "
        "`exchange_request`. Повторная загрузка заменяет предыдущий файл."
    ),
    dependencies=[Depends(_write_access)],
)
async def upload_cart_item_file(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    item_id: UUID,
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    _require_lc_role(user)
    data = await file.read()
    try:
        result = await handle_upload_cart_item_file(
            UploadCartItemFileCommand(
                item_id=item_id,
                user_id=user["id"],
                filename=file.filename or "file",
                content_type=file.content_type or "application/octet-stream",
                data=data,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{item_id}/file",
    summary="Скачать файл, прикреплённый к элементу корзины",
    description=(
        "Проксирует приватный объект S3 (или legacy прямой URL) через "
        "backend — бакет не публичный. Доступно только владельцу item'а."
    ),
    dependencies=[Depends(_read_access)],
    response_class=Response,
)
async def download_cart_item_file_endpoint(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    item_id: UUID,
) -> Response:
    _require_lc_role(user)
    try:
        dl = await download_cart_item_file(
            session, storage,
            item_id=item_id, user_id=user["id"],
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return Response(
        content=dl.data,
        media_type=dl.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{dl.filename}"'
        },
    )


@router.post(
    "/submit",
    response_model=ExchangeCartSubmitResponse,
    summary="Отправить корзину биржи дилерам",
    description=(
        "Конвертирует все элементы корзины в `exchange_requests` со статусом "
        "`open` в одном батче (общий `batch_number`, уникальный "
        "`batch_index` у каждого). Для каждого item создаются ссылки на "
        "выбранные склады, опции и per-dealer комментарии. После успеха "
        "корзина очищается. 400 — корзина пуста или ни у одной позиции нет "
        "выбранных складов (отправлять заявку некому)."
    ),
    dependencies=[Depends(_write_access)],
)
async def submit_cart(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    try:
        result = await handle_submit_exchange_cart(
            SubmitExchangeCartCommand(user_id=user["id"], company_id=user.get("company_id")), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


__all__ = ["ExchangeCartCountResponse", "router"]
