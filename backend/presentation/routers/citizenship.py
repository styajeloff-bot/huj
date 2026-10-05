"""Authenticated citizenship reference endpoint."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.citizenship import list_citizenships
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user
from presentation.schemas.citizenship import CitizenshipListResponse

router = APIRouter()


@router.get(
    "",
    response_model=CitizenshipListResponse,
    summary="Получить справочник гражданств",
    description="Возвращает авторизованному пользователю детерминированный алфавитный список гражданств.",
)
async def get_citizenships(
    session: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(await list_citizenships(session)))
