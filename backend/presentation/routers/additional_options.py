"""Public additional equipment and services catalogs."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.additional_options import (
    handle_list_additional_equipments,
    handle_list_additional_services,
)
from infrastructure.database import get_db
from presentation.schemas.additional_options import (
    EquipmentListResponse,
    ServiceListResponse,
)

router = APIRouter()


@router.get(
    "/equipments",
    response_model=EquipmentListResponse,
    summary="Справочник дополнительного оборудования",
    description="Возвращает публичный справочник дополнительного оборудования.",
)
async def list_equipments(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_additional_equipments(session)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/services",
    response_model=ServiceListResponse,
    summary="Справочник дополнительных услуг",
    description="Возвращает публичный справочник дополнительных услуг автомобиля.",
)
async def list_services(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_additional_services(session)
    return JSONResponse(content=jsonable_encoder(result))
