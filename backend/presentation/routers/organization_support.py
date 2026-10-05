"""Read-only support-program API for organization cabinets."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError, domain_to_http
from application.queries.leasing import ResolveActorLcQuery, handle_resolve_actor_lc
from application.queries.support import (
    ListOrganizationSupportProgramsQuery,
    handle_list_organization_support_programs,
)
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.dependencies.auth import require_roles
from presentation.schemas.support import OrganizationSupportProgramListResponse

router = APIRouter()
_organization_reader = require_roles("dealer", "leasing_company")


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "/support-programs",
    response_model=OrganizationSupportProgramListResponse,
    summary="Программы поддержки текущей организации",
    description=(
        "Дилер видит программы своих групп, а при отсутствии ограничения по группам — "
        "программы связанного дистрибьютора. Лизинговая компания видит программы, "
        "выбранные для неё или доступные любым ЛК."
    ),
)
async def list_organization_support_programs(
    user: Annotated[dict[str, Any], Depends(_organization_reader)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None),
    mark_id: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> JSONResponse:
    role = str(user.get("role") or "")
    try:
        leasing_company_id = None
        if role == "leasing_company":
            leasing_company_id = await handle_resolve_actor_lc(
                ResolveActorLcQuery(user_id=user["id"], role=role), session
            )
        result = await handle_list_organization_support_programs(
            ListOrganizationSupportProgramsQuery(
                actor_role=role,
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=leasing_company_id,
                page=page,
                limit=limit,
                search=search,
                mark_id=mark_id,
                model_id=model_id,
                is_active=is_active,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


__all__ = ["router"]
