"""Exchange requests API (LC-owned surface) — Phase 5 E2."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.exchange import (
    ArchiveExchangeRequestCommand,
    CreateExchangeRequestCommand,
    ExchangeRequestWarehousePayload,
    ResubmitExchangeRequestCommand,
    UpdateExchangeRequestCommand,
    UploadKpToBidCommand,
    handle_archive_exchange_request,
    handle_create_exchange_request,
    handle_resubmit_exchange_request,
    handle_update_exchange_request,
    handle_upload_kp_to_bid,
)
from application.errors import ServiceError, domain_to_http
from application.queries.exchange import (
    GetRequestCountsQuery,
    GetRequestQuery,
    ListLcRequestsQuery,
    handle_get_request,
    handle_get_request_counts,
    handle_list_lc_requests,
)
from application.queries.exchange.download_files import (
    download_request_file,
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
    CreateExchangeRequestBody,
    ExchangeBidFileResponse,
    ExchangeRequestCountsResponse,
    ExchangeRequestCreatedResponse,
    ExchangeRequestDetailResponse,
    ExchangeRequestListResponse,
    ExchangeRequestUpdatedResponse,
    PatchExchangeRequestBody,
    UpdateExchangeRequestBody,
)

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

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
                "error": "Эндпоинт доступен только лизинговой компании",
                "code": "INSUFFICIENT_PERMISSIONS",
            },
        )


@router.get(
    "/",
    response_model=ExchangeRequestListResponse,
    summary="Список заявок биржи (ЛК view)",
    description=(
        "Возвращает заявки, принадлежащие текущей ЛК. Опциональный фильтр "
        "по статусу: `open`, `deal`, `archived`."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_requests(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query(description="Фильтр по статусу")] = None,
    page: Annotated[int, Query(ge=1, description="Номер страницы")] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description="Размер страницы")] = 20,
) -> JSONResponse:
    _require_lc_role(user)
    try:
        result = await handle_list_lc_requests(
            ListLcRequestsQuery(lc_user_id=user["id"], company_id=user.get("company_id"), status=status, page=page, limit=limit), session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/counts",
    response_model=ExchangeRequestCountsResponse,
    summary="Счётчики заявок ЛК по статусам",
    description=(
        "Возвращает количество заявок биржи, принадлежащих текущей ЛК, "
        "сгруппированных по статусам `open` / `deal` / `archived`."
    ),
    dependencies=[Depends(_read_access)],
)
async def request_counts(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    try:
        result = await handle_get_request_counts(
            GetRequestCountsQuery(lc_user_id=user["id"], company_id=user.get("company_id")), session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/",
    status_code=201,
    response_model=ExchangeRequestCreatedResponse,
    summary="Создать заявку биржи",
    description=(
        "Создаёт заявку биржи от имени ЛК. Атомарно выделяет `batch_number`, "
        "фиксирует склады/дилеров и per-dealer комментарии."
    ),
    dependencies=[Depends(_write_access)],
)
async def create_request(
    body: CreateExchangeRequestBody,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    pid = getattr(body, "product_id", getattr(body, "vehicle_id", None))
    v_kw = "product_id" if "product_id" in getattr(CreateExchangeRequestCommand, "__dataclass_fields__", {}) else "vehicle_id"
    create_cmd_args: dict[str, Any] = {
        "lc_user_id": user["id"],
        "company_id": user.get("company_id"),
        "quantity": body.quantity,
        "discount_type": body.discount_type,
        "discount_value": body.discount_value,
        "file_url": body.file_url,
        "file_name": body.file_name,
        "expiration_at": body.expiration_at,
        "dealer_option_ids": list(body.dealer_option_ids),
        "selected_support_ids": list(body.selected_support_ids),
        "warehouses": [
            ExchangeRequestWarehousePayload(
                warehouse_id=w.warehouse_id,
                dealer_id=w.dealer_id,
                dealer_comment=w.dealer_comment,
            )
            for w in body.warehouses
        ],
        v_kw: pid,
    }
    cmd = CreateExchangeRequestCommand(**create_cmd_args)  # type: ignore[arg-type]
    try:
        result = await handle_create_exchange_request(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(result),
        status_code=201,
    )


@router.put(
    "/{request_id}",
    response_model=ExchangeRequestUpdatedResponse,
    summary="Обновить заявку биржи",
    description="Частичное обновление: применяются только переданные поля.",
    dependencies=[Depends(_write_access)],
)
async def update_request(
    request_id: UUID,
    body: UpdateExchangeRequestBody,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    cmd = UpdateExchangeRequestCommand(
        request_id=request_id,
        lc_user_id=user["id"], company_id=user.get("company_id"),
        quantity=body.quantity,
        discount_type=body.discount_type,
        discount_value=body.discount_value,
        expiration_at=body.expiration_at, expiration_at_set="expiration_at" in body.model_fields_set,
        file_url=body.file_url,
        file_name=body.file_name,
    )
    try:
        result = await handle_update_exchange_request(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/{request_id}",
    response_model=ExchangeRequestUpdatedResponse,
    summary="Обновить / архивировать / пересоздать заявку биржи",
    description=(
        "Частичное обновление с диспатчем по `status`: "
        "`{status: 'archived'}` — архивирует заявку (замена "
        "`PUT /exchange/requests/:id/archive`); "
        "`{status: 'open'}` — создаёт дубликат archived/deal-заявки в "
        "открытом статусе (замена `POST /exchange/requests/:id/resubmit`) "
        "и возвращает id нового ресурса в теле. Без `status` — обновление "
        "полей существующей заявки."
    ),
    dependencies=[Depends(_write_access)],
)
async def patch_request(
    request_id: UUID,
    body: PatchExchangeRequestBody,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    lc_user_id = user["id"]

    if body.status == "archived":
        try:
            result = await handle_archive_exchange_request(
                ArchiveExchangeRequestCommand(
                    request_id=request_id, lc_user_id=lc_user_id, company_id=user.get("company_id")
                ),
                session,
            )
        except (ServiceError, DomainError) as exc:
            raise _http(exc)
        await session.commit()
        return JSONResponse(content=jsonable_encoder(result))

    if body.status == "open":
        try:
            result = await handle_resubmit_exchange_request(
                ResubmitExchangeRequestCommand(
                    request_id=request_id, lc_user_id=lc_user_id, company_id=user.get("company_id")
                ),
                session,
            )
        except (ServiceError, DomainError) as exc:
            raise _http(exc)
        await session.commit()
        return JSONResponse(content=jsonable_encoder(result))

    if body.status is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Недопустимое значение status: ожидается 'archived' или 'open'"
            ),
        )

    cmd = UpdateExchangeRequestCommand(
        request_id=request_id,
        lc_user_id=lc_user_id, company_id=user.get("company_id"),
        quantity=body.quantity,
        discount_type=body.discount_type,
        discount_value=body.discount_value,
        expiration_at=body.expiration_at, expiration_at_set="expiration_at" in body.model_fields_set,
        file_url=body.file_url,
        file_name=body.file_name,
    )
    try:
        result = await handle_update_exchange_request(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{request_id}/bids/{bid_id}/kp",
    response_model=ExchangeBidFileResponse,
    summary="ЛК загружает КП файл для конкретной ставки",
    description=(
        "ЛК отправляет коммерческое предложение конкретной ставке дилера "
        "(multipart/form-data, поле `file`). Заявка должна быть в статусе "
        "`open`, ставка должна принадлежать этой заявке. Переводит "
        "`kp_status` в `sent` и фиксирует `kp_sent_at`."
    ),
    dependencies=[Depends(_write_access)],
)
async def upload_kp_to_bid(
    request_id: UUID,
    bid_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    _require_lc_role(user)
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Файл не прикреплён")
    if len(payload) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail="Файл превышает допустимый размер"
        )
    try:
        result = await handle_upload_kp_to_bid(
            UploadKpToBidCommand(
                request_id=request_id,
                bid_id=bid_id,
                lc_user_id=user["id"], company_id=user.get("company_id"),
                filename=file.filename or "file",
                content_type=file.content_type or "application/octet-stream",
                data=payload,
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{request_id}",
    response_model=ExchangeRequestDetailResponse,
    summary="Детали заявки биржи (ЛК)",
    description=(
        "Возвращает заявку со складами, опциями, комментариями, файлами и "
        "всеми ставками. Доступно только владельцу-ЛК."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_request(
    request_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_lc_role(user)
    try:
        result = await handle_get_request(
            GetRequestQuery(
                request_id=request_id,
                lc_user_id=user["id"], company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{request_id}/file",
    summary="Скачать файл заявки биржи",
    description=(
        "Проксирует приватный объект из S3 через backend. Доступ: ЛК — "
        "владелец, либо дилер, которому адресована заявка."
    ),
    dependencies=[Depends(_read_access)],
    response_class=Response,
)
async def download_request_file_endpoint(
    request_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        dl = await download_request_file(
            session, storage,
            request_id=request_id,
            viewer_user_id=user["id"],
            viewer_company_id=user.get("company_id"),
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return Response(
        content=dl.data,
        media_type=dl.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{dl.filename}"'
        },
    )
