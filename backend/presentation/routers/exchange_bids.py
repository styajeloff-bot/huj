"""Exchange bids API (dealer + LC) — Phase 5 E2."""
from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.exchange import (
    AddBidCommentCommand,
    ApproveBidCommand,
    CreateBidCommand,
    RespondToKpCommand,
    UpdateBidCommand,
    UploadBidFileCommand,
    handle_add_bid_comment,
    handle_approve_bid,
    handle_create_bid,
    handle_respond_to_kp,
    handle_update_bid,
    handle_upload_bid_file,
)
from application.commands.exchange.withdraw_bid import (
    WithdrawBidCommand,
    handle_withdraw_bid,
)
from application.errors import ServiceError, domain_to_http
from application.queries.exchange import (
    GetBidQuery,
    ListBidsQuery,
    handle_get_bid,
    handle_list_bids,
)
from application.queries.exchange.download_files import (
    download_bid_file,
    download_bid_kp,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import EXCHANGE_READ, EXCHANGE_WRITE
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import (
    require_roles,
    require_scopes,
)
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)
from presentation.dependencies.notification_database import get_db
from presentation.schemas.exchange import (
    AddBidCommentBody,
    AddBidCommentResponse,
    CreateBidBody,
    ExchangeBidApproveResponse,
    ExchangeBidCreatedResponse,
    ExchangeBidDetailResponse,
    ExchangeBidFileResponse,
    ExchangeBidListResponse,
    RespondToKpBody,
    UpdateBidBody,
)

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

router = APIRouter()

_read_access = require_scopes(EXCHANGE_READ)
_write_access = require_scopes(EXCHANGE_WRITE)


@router.delete("/{bid_id}", status_code=204, response_model=None,
    summary="Отозвать ставку", description="Дилер отзывает свою непринятую ставку открытой заявки.",
    dependencies=[Depends(_write_access), Depends(require_roles("dealer"))])
async def withdraw_bid(
    bid_id: UUID, user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        await handle_withdraw_bid(WithdrawBidCommand(bid_id, user["id"], user.get("company_id")), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return Response(status_code=204)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _require_role(user: dict[str, Any], *roles: str) -> None:
    if str(user.get("role") or "") not in roles:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Недостаточно прав доступа",
                "code": "INSUFFICIENT_PERMISSIONS",
            },
        )


@router.get(
    "/",
    response_model=ExchangeBidListResponse,
    summary="Список ставок дилера",
    description=(
        "Возвращает ставки, созданные текущим дилером. Доступно только "
        "роли `dealer`."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_bids(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_role(user, "dealer")
    try:
        result = await handle_list_bids(
            ListBidsQuery(dealer_id=user["id"], company_id=user.get("company_id")), session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/",
    status_code=201,
    response_model=ExchangeBidCreatedResponse,
    summary="Создать ставку (дилер)",
    description=(
        "Дилер создаёт ставку на открытую заявку биржи. Повторная ставка "
        "на ту же заявку — 409. Заявка должна быть в статусе `open`."
    ),
    dependencies=[Depends(_write_access)],
)
async def create_bid(
    body: CreateBidBody,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_role(user, "dealer")
    cmd = CreateBidCommand(
        request_id=body.request_id,
        dealer_id=user["id"],
        price=body.price,
        quantity=body.quantity,
        comment=body.comment,
        dealer_option_ids=list(body.dealer_option_ids),
        company_id=user.get("company_id"),
    )
    try:
        result = await handle_create_bid(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(result), status_code=201
    )


@router.get(
    "/{bid_id}",
    response_model=ExchangeBidDetailResponse,
    summary="Детали ставки",
    description=(
        "Возвращает ставку с опциями и комментариями. Доступно дилеру-"
        "владельцу или ЛК-владельцу заявки; сотрудник видит всё."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_bid(
    bid_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_bid(
            GetBidQuery(
                bid_id=bid_id,
                user_id=user["id"],
                user_role=str(user.get("role") or ""), company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/{bid_id}",
    response_model=ExchangeBidCreatedResponse,
    summary="Обновить ставку (дилер)",
    description=(
        "Частичное обновление ставки. Дилер может менять только свои "
        "ставки. Заявка должна быть в статусе `open`."
    ),
    dependencies=[Depends(_write_access)],
)
async def update_bid(
    bid_id: UUID,
    body: UpdateBidBody,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_role(user, "dealer")
    cmd = UpdateBidCommand(
        bid_id=bid_id,
        dealer_id=user["id"],
        company_id=user.get("company_id"),
        price=body.price,
        quantity=body.quantity,
        comment=body.comment,
        dealer_option_ids=(
            list(body.dealer_option_ids)
            if body.dealer_option_ids is not None
            else None
        ),
    )
    try:
        result = await handle_update_bid(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/{bid_id}/approve",
    response_model=ExchangeBidApproveResponse,
    summary="ЛК одобряет ставку (KP flow)",
    description=(
        "Лизинговая компания подтверждает сделку. Ставка должна иметь "
        "`kp_status=accepted`. Переводит заявку в статус `deal` и "
        "записывает `accepted_bid_id`."
    ),
    dependencies=[Depends(_write_access)],
)
async def approve_bid(
    bid_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_role(user, "leasing_company")
    try:
        result = await handle_approve_bid(
            ApproveBidCommand(
                bid_id=bid_id,
                lc_user_id=user["id"], company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{bid_id}/comments",
    response_model=AddBidCommentResponse,
    summary="Добавить комментарий к ставке",
    description=(
        "Добавляет комментарий к ставке. Дилер-владелец и ЛК-владелец "
        "заявки могут комментировать; сотрудники — всегда. Возвращает "
        "созданный комментарий целиком."
    ),
    dependencies=[Depends(_write_access)],
)
async def add_bid_comment(
    bid_id: UUID,
    body: AddBidCommentBody,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_add_bid_comment(
            AddBidCommentCommand(
                bid_id=bid_id,
                user_id=user["id"],
                user_role=str(user.get("role") or ""), company_id=user.get("company_id"),
                comment=body.comment,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{bid_id}/file",
    response_model=ExchangeBidFileResponse,
    summary="Дилер прикрепляет файл к своей ставке",
    description=(
        "Дилер загружает supporting-файл (multipart/form-data, поле `file`) "
        "к своей ставке. Заявка должна быть в статусе `open`."
    ),
    dependencies=[Depends(_write_access)],
)
async def upload_bid_file(
    bid_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    _require_role(user, "dealer")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Файл не прикреплён")
    if len(payload) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail="Файл превышает допустимый размер"
        )
    try:
        result = await handle_upload_bid_file(
            UploadBidFileCommand(
                bid_id=bid_id,
                dealer_id=user["id"],
                company_id=user.get("company_id"),
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


@router.post(
    "/{bid_id}/kp/respond",
    response_model=ExchangeBidFileResponse,
    summary="Дилер принимает или отклоняет КП",
    description=(
        "Дилер отвечает на КП, прикреплённое к его ставке. Значения "
        "`action`: `accepted` или `rejected`. KP должно быть в статусе "
        "`sent`, заявка — `open`."
    ),
    dependencies=[Depends(_write_access)],
)
async def respond_to_kp(
    bid_id: UUID,
    body: RespondToKpBody,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_role(user, "dealer")
    try:
        result = await handle_respond_to_kp(
            RespondToKpCommand(
                bid_id=bid_id,
                dealer_id=user["id"],
                company_id=user.get("company_id"),
                action=body.action,
                comment=body.comment,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{bid_id}/file",
    summary="Скачать файл ставки (дилер или владелец-ЛК)",
    description=(
        "Проксирует приватный объект из S3 через backend. Доступ: дилер — "
        "владелец ставки, либо ЛК — владелец родительской заявки."
    ),
    dependencies=[Depends(_read_access)],
    response_class=Response,
)
async def download_bid_file_endpoint(
    bid_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        dl = await download_bid_file(
            session, storage, bid_id=bid_id, viewer_user_id=user["id"], viewer_company_id=user.get("company_id")
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return Response(
        content=dl.data,
        media_type=dl.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(dl.filename, safe='')}"
        },
    )


@router.get(
    "/{bid_id}/kp",
    summary="Скачать КП, прикреплённое к ставке",
    description=(
        "Проксирует КП из приватного S3 через backend. Доступ: дилер — "
        "владелец ставки, либо ЛК — владелец родительской заявки."
    ),
    dependencies=[Depends(_read_access)],
    response_class=Response,
)
async def download_bid_kp_endpoint(
    bid_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        dl = await download_bid_kp(
            session, storage, bid_id=bid_id, viewer_user_id=user["id"], viewer_company_id=user.get("company_id")
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return Response(
        content=dl.data,
        media_type=dl.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(dl.filename, safe='')}"
        },
    )
