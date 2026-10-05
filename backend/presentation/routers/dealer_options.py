"""Routes for /api/v1/exchange/dealer-options."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.dealer_options import (
    CreateDealerOptionCommand,
    DeleteDealerOptionCommand,
    UpdateDealerOptionCommand,
    handle_create_dealer_option,
    handle_delete_dealer_option,
    handle_update_dealer_option,
)
from application.errors import ServiceError, domain_to_http
from application.queries.dealer_options import (
    ListDealerOptionsQuery,
    handle_list_dealer_options,
)
from domain.errors import DomainError
from domain.services.scopes import (
    DEALER_OPTIONS_READ,
    DEALER_OPTIONS_WRITE,
)
from infrastructure.database import get_db
from presentation.dependencies.auth import require_scopes
from presentation.schemas.dealer_options import (
    DealerOptionCreateRequest,
    DealerOptionListResponse,
    DealerOptionResponse,
    DealerOptionUpdateRequest,
    MessageResponse,
)

router = APIRouter()

_read_only = require_scopes(DEALER_OPTIONS_READ)
_write_only = require_scopes(DEALER_OPTIONS_WRITE)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "",
    response_model=DealerOptionListResponse,
    summary="Список опций для дилеров",
    description=(
        "Возвращает справочник дополнительных опций. По умолчанию — только "
        "активные. Для администраторов поддерживается параметр "
        "`include_inactive=true` (требует scope `dealer-options:write`)."
    ),
    dependencies=[Depends(_read_only)],
)
async def list_dealer_options(
    session: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: bool = Query(default=False),
) -> JSONResponse:
    result = await handle_list_dealer_options(
        ListDealerOptionsQuery(include_inactive=include_inactive),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "",
    status_code=201,
    response_model=DealerOptionResponse,
    summary="Создать опцию",
    description=(
        "Создаёт опцию для дилеров. Требует роль сотрудника. "
        "Имя должно быть уникальным (409 при дубле)."
    ),
    dependencies=[Depends(_write_only)],
)
async def create_dealer_option(
    body: DealerOptionCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_dealer_option(
            CreateDealerOptionCommand(
                name=body.name,
                sort_order=body.sort_order,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "option": jsonable_encoder(result),
            "message": "Опция создана",
        },
        status_code=201,
        headers={"Location": f"/api/v1/exchange/dealer-options/{result['id']}"},
    )


@router.put(
    "/{option_id}",
    response_model=DealerOptionResponse,
    summary="Обновить опцию",
    description="Частичное обновление: применяются только переданные поля.",
    dependencies=[Depends(_write_only)],
)
async def update_dealer_option(
    option_id: UUID,
    body: DealerOptionUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_update_dealer_option(
            UpdateDealerOptionCommand(
                option_id=option_id,
                name=body.name,
                sort_order=body.sort_order,
                is_active=body.is_active,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "option": jsonable_encoder(result),
            "message": "Опция обновлена",
        }
    )


@router.delete(
    "/{option_id}",
    response_model=MessageResponse,
    summary="Деактивировать опцию",
    description="Soft-delete: переводит опцию в is_active=false.",
    dependencies=[Depends(_write_only)],
)
async def delete_dealer_option(
    option_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_delete_dealer_option(
            DeleteDealerOptionCommand(option_id=option_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))
