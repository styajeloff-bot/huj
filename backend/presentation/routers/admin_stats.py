"""Admin routes for /api/v1/admin/stats + /leasing-companies + /dealers (F2)."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.admin_companies import (
    ListDealersAllQuery,
    ListDistributorsAllQuery,
    ListLeasingCompaniesAllQuery,
    handle_list_dealers_all,
    handle_list_distributors_all,
    handle_list_leasing_companies_all,
)
from application.queries.admin_stats import (
    GetAdminStatsQuery,
    handle_get_admin_stats,
)
from domain.services.scopes import ADMIN_STATS_READ, has_all_scopes
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.schemas.admin import (
    AdminStatsResponse,
    DealersListResponse,
    DistributorsListResponse,
    LeasingCompaniesListResponse,
)

router = APIRouter()

_employee_only = require_scopes(ADMIN_STATS_READ)


async def _leasing_companies_access(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    if user.get("role") == "distributor" or has_all_scopes(
        user.get("scopes"), (ADMIN_STATS_READ,)
    ):
        return user
    raise HTTPException(
        status_code=403,
        detail={
            "error": "Недостаточно прав доступа",
            "code": "INSUFFICIENT_PERMISSIONS",
        },
    )


setattr(  # noqa: B010
    _leasing_companies_access,
    "_required_roles",
    frozenset({"distributor", "carcraft_employee"}),
)


@router.get(
    "/stats",
    response_model=AdminStatsResponse,
    summary="[admin] Платформенные метрики",
    description=(
        "Top-level метрики: пользователи по ролям, компании по типам, "
        "заявки по статусам, итоги по автомобилям. Агрегат — всегда "
        "актуальный (без кэша)."
    ),
    dependencies=[Depends(_employee_only)],
)
async def get_stats(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_get_admin_stats(GetAdminStatsQuery(), session)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/leasing-companies",
    response_model=LeasingCompaniesListResponse,
    summary="[admin] Полный справочник лизинговых компаний",
    description=(
        "Возвращает все лизинговые компании (включая неактивные) для "
        "admin-UI: селекты назначения, справочники."
    ),
    dependencies=[Depends(_leasing_companies_access)],
)
async def list_leasing_companies_all(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_leasing_companies_all(
        ListLeasingCompaniesAllQuery(), session
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/dealers",
    response_model=DealersListResponse,
    summary="[admin] Полный список дилеров",
    description=(
        "Возвращает активных дилеров с базовыми полями компании для "
        "admin-UI (назначение складов, выбор в селектах)."
    ),
    dependencies=[Depends(_employee_only)],
)
async def list_dealers_all(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_dealers_all(ListDealersAllQuery(), session)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/distributors",
    response_model=DistributorsListResponse,
    summary="[admin] Полный список дистрибьюторов",
    description=(
        "Возвращает активных дистрибьюторов (распределителей) с базовыми "
        "полями компании. Используется в admin-UI для выбора при назначении "
        "программ поддержки и закреплении автомобилей. Отдельно от "
        "`/admin/dealers` — те предназначены для привязки складов."
    ),
    dependencies=[Depends(_employee_only)],
)
async def list_distributors_all(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_distributors_all(
        ListDistributorsAllQuery(), session
    )
    return JSONResponse(content=jsonable_encoder(result))
