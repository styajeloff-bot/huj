"""Routes for /api/v1/positions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.positions import (
    CreatePositionCommand,
    DeactivatePositionCommand,
    UpdatePositionCommand,
    handle_create_position,
    handle_deactivate_position,
    handle_update_position,
)
from application.errors import ServiceError, domain_to_http
from application.queries.positions import (
    ListPositionsQuery,
    handle_list_positions,
)
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.dependencies.auth import require_roles
from presentation.schemas.positions import (
    CreatePositionRequest,
    PositionOut,
    PositionsListResponse,
    UpdatePositionRequest,
)

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])

_employee = require_roles("carcraft_employee")


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "",
    response_model=PositionsListResponse,
    summary="Список должностей",
    description="Возвращает список должностей из справочника. Требует роль carcraft_employee.",
    dependencies=[Depends(_employee)],
)
async def list_positions(
    session: Annotated[AsyncSession, Depends(get_db)],
    only_active: bool = Query(default=False, description="Фильтр только по активным должностям"),
) -> JSONResponse:
    try:
        result = await handle_list_positions(
            ListPositionsQuery(only_active=only_active),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "",
    status_code=201,
    response_model=PositionOut,
    summary="Создать должность",
    description="Создаёт новую должность в справочнике. Требует роль carcraft_employee.",
    dependencies=[Depends(_employee)],
)
async def create_position(
    body: CreatePositionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_position(
            CreatePositionCommand(
                name=body.name,
                code=body.code,
                is_active=body.is_active,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result), status_code=201)


@router.put(
    "/{id}",
    response_model=PositionOut,
    summary="Обновить должность",
    description="Обновляет название, системный код и активность должности. Требует роль carcraft_employee.",
    dependencies=[Depends(_employee)],
)
async def update_position(
    body: UpdatePositionRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    position_id: Annotated[UUID, Path(alias="id", description="ID должности")],
) -> JSONResponse:
    try:
        result = await handle_update_position(
            UpdatePositionCommand(
                position_id=position_id,
                name=body.name,
                code=body.code,
                is_active=body.is_active,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/{id}/deactivate",
    response_model=PositionOut,
    summary="Деактивировать должность",
    description="Переводит должность в неактивное состояние (is_active=false). Требует роль carcraft_employee.",
    dependencies=[Depends(_employee)],
)
async def deactivate_position(
    session: Annotated[AsyncSession, Depends(get_db)],
    position_id: Annotated[UUID, Path(alias="id", description="ID должности")],
) -> JSONResponse:
    try:
        result = await handle_deactivate_position(
            DeactivatePositionCommand(position_id=position_id),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))
