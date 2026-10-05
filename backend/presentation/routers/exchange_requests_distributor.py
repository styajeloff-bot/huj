"""Distributor-only read API. No write routes or write scope are exposed."""
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError, domain_to_http
from application.queries.exchange.distributor_requests import (
    get_distributor_request,
    get_distributor_request_counts,
    list_distributor_requests,
)
from domain.errors import DomainError
from domain.services.scopes import EXCHANGE_READ
from presentation.dependencies.auth import (
    require_roles,
    require_scopes,
)
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)
from presentation.dependencies.notification_database import get_db
from presentation.schemas.exchange import (
    DistributorExchangeRequestListResponse,
    ExchangeRequestCountsResponse,
    ExchangeRequestDetailResponse,
)

router = APIRouter(dependencies=[Depends(require_roles("distributor")), Depends(require_scopes(EXCHANGE_READ))])


def _http(exc: ServiceError | DomainError) -> HTTPException:
    error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    return HTTPException(error.status_code, str(error))


@router.get("", response_model=DistributorExchangeRequestListResponse, summary="Заявки Биржи дистрибьютора",
    description="Только чтение заявок связанных дилеров и дилерских групп.")
async def list_requests(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = None, page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JSONResponse:
    try:
        result = await list_distributor_requests(session, user_id=user["id"],
            company_id=user.get("company_id"), status=status, page=page, limit=limit)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/counts", response_model=ExchangeRequestCountsResponse, summary="Счётчики Биржи дистрибьютора",
    description="Количество только доступных дистрибьютору заявок по статусам.")
async def counts(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await get_distributor_request_counts(session, user_id=user["id"], company_id=user.get("company_id"))
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/{request_id}", response_model=ExchangeRequestDetailResponse, summary="Заявка Биржи: просмотр дистрибьютора",
    description="Возвращает разрешённую заявку без возможности редактирования.")
async def get_request(
    request_id: UUID, user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await get_distributor_request(session, request_id=request_id,
            user_id=user["id"], company_id=user.get("company_id"))
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))
