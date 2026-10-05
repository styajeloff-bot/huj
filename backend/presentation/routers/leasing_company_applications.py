"""/api/v1/leasing-company-applications — LCA list and detail.

This router exposes LeasingCompanyApplication rows directly so the
frontend cabinet can show child applications (LCA) instead of parent
aggregates (LA).
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError, domain_to_http
from application.queries.leasing_company_applications import (
    GetLcaQuery,
    ListLcaQuery,
    handle_get_lca,
    handle_list_lca,
)
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)

router = APIRouter()


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get(
    "/",
    summary="Список дочерних заявок (LCA)",
    description=(
        "Возвращает LeasingCompanyApplication rows, отфильтрованные по роли "
        "пользователя. Для client/dealer — только свои; для carcraft_employee — "
        "все; для leasing_company — только назначенные этой ЛК."
    ),
)
async def list_lca_endpoint(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
    application_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JSONResponse:
    try:
        result = await handle_list_lca(
            ListLcaQuery(
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=user.get("leasing_company_id"),
                status=status,
                application_id=application_id,
                page=page,
                limit=limit,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get(
    "/{lca_id}",
    summary="Детали дочерней заявки (LCA)",
    description=(
        "Возвращает LeasingCompanyApplication по ID с проверкой прав доступа "
        "через parent LeasingApplication."
    ),
)
async def get_lca_endpoint(
    lca_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_lca(
            GetLcaQuery(
                lca_id=lca_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=user.get("leasing_company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))
