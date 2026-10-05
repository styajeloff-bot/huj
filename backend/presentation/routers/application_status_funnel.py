"""Historical status funnel for leasing-company applications."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.application_status_funnel import (
    ApplicationFunnelError,
    GetApplicationStatusFunnelQuery,
    handle_get_application_status_funnel,
)
from domain.application_status_funnel import ApplicationFunnelSelectionMode
from infrastructure.database import get_db
from presentation.dependencies.auth import require_roles
from presentation.schemas.application_status_funnel import (
    ApplicationStatusFunnelErrorResponse,
    ApplicationStatusFunnelResponse,
)

router = APIRouter()
_SUPPORTED_ROLES = ("dealer", "distributor", "carcraft_employee")


def _uuid_claim(user: dict[str, Any], key: str, *, required: bool) -> UUID | None:
    value = user.get(key)
    if value is None and not required:
        return None
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            pass
    raise ApplicationFunnelError(
        "Некорректные данные пользователя",
        403,
        "ACCESS_DENIED",
    )


@router.get(
    "/applications/funnel",
    response_model=ApplicationStatusFunnelResponse,
    summary="Воронка заявок по статусам",
    description=(
        "Возвращает переходы заявок в ЛК за период и их состояние на конец "
        "периода. Доступно дилеру с актуальным правом просмотра заявок, "
        "дистрибьютору в рамках связанных дилеров и сотруднику Carcraft."
    ),
    responses={
        403: {
            "model": ApplicationStatusFunnelErrorResponse,
            "description": "Нет роли, company scope или актуального разрешения",
        },
        422: {
            "model": ApplicationStatusFunnelErrorResponse,
            "description": "Период выходит за доступную историю или невалиден",
        },
        503: {
            "model": ApplicationStatusFunnelErrorResponse,
            "description": "История не подготовлена или аналитика недоступна",
        },
    },
)
async def application_status_funnel(
    user: Annotated[dict[str, Any], Depends(require_roles(*_SUPPORTED_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db)],
    period_from: date | None = Query(default=None),
    period_to: date | None = Query(default=None),
    selection_mode: ApplicationFunnelSelectionMode = Query(
        default=ApplicationFunnelSelectionMode.CREATED_IN_PERIOD
    ),
) -> JSONResponse:
    try:
        query = GetApplicationStatusFunnelQuery(
            actor_id=cast("UUID", _uuid_claim(user, "id", required=True)),
            actor_role=str(user.get("role", "")),
            company_id=_uuid_claim(user, "company_id", required=False),
            period_from=period_from,
            period_to=period_to,
            selection_mode=selection_mode,
        )
        result = await handle_get_application_status_funnel(query, session)
    except ApplicationFunnelError as exc:
        detail = {"message": str(exc), "error_code": exc.error_code}
        if exc.history_available_from is not None:
            detail["history_available_from"] = (
                exc.history_available_from.isoformat()
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    response = ApplicationStatusFunnelResponse.model_validate(result)
    return JSONResponse(
        content=jsonable_encoder(response, by_alias=True),
    )
