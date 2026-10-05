"""Exchange requests API — dealer viewer surface (Phase 5 E2)."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError, domain_to_http
from application.queries.exchange import (
    GetDealerRequestCountsQuery,
    GetDealerRequestQuery,
    ListDealerRequestsQuery,
    handle_get_dealer_request,
    handle_get_dealer_request_counts,
    handle_list_dealer_requests,
)
from domain.errors import DomainError
from domain.services.scopes import EXCHANGE_READ
from presentation.dependencies.auth import (
    require_scopes,
)
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)
from presentation.dependencies.notification_database import get_db
from presentation.schemas.exchange import (
    ExchangeRequestCountsResponse,
    ExchangeRequestDetailResponse,
    ExchangeRequestListResponse,
)

router = APIRouter()

_read_access = require_scopes(EXCHANGE_READ)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _require_dealer(user: dict[str, Any]) -> None:
    role = str(user.get("role") or "")
    if role != "dealer":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Эндпоинт доступен только дилеру",
                "code": "INSUFFICIENT_PERMISSIONS",
            },
        )


@router.get(
    "",
    response_model=ExchangeRequestListResponse,
    summary="Список релевантных заявок биржи (дилер)",
    description=(
        "Возвращает заявки биржи, в которых текущий дилер привязан к "
        "одному из складов. Опциональный фильтр по статусу."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_dealer_requests(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query(description="Фильтр по статусу")] = None,
    page: Annotated[int, Query(ge=1, description="Номер страницы")] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description="Размер страницы")] = 20,
) -> JSONResponse:
    _require_dealer(user)
    try:
        result = await handle_list_dealer_requests(
            ListDealerRequestsQuery(dealer_id=user["id"], company_id=user.get("company_id"),
                status=status, page=page, limit=limit), session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/counts",
    response_model=ExchangeRequestCountsResponse,
    summary="Счётчики релевантных заявок биржи (дилер)",
    description=(
        "Возвращает количество заявок биржи, доступных текущему дилеру, "
        "сгруппированных по статусам."
    ),
    dependencies=[Depends(_read_access)],
)
async def dealer_request_counts(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_dealer(user)
    try:
        result = await handle_get_dealer_request_counts(
            GetDealerRequestCountsQuery(dealer_id=user["id"], company_id=user.get("company_id")), session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{request_id}",
    response_model=ExchangeRequestDetailResponse,
    summary="Детали заявки биржи (дилер view)",
    description=(
        "Возвращает заявку биржи с анонимизированными ставками конкурентов. "
        "Собственная ставка, склад и per-dealer комментарий видны полностью."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_dealer_request(
    request_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_dealer(user)
    try:
        result = await handle_get_dealer_request(
            GetDealerRequestQuery(
                request_id=request_id,
                dealer_id=user["id"],
                company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))
