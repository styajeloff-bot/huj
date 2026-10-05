"""Authenticated reference reads and employee-only dictionary management."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.questionnaire_dictionaries import (
    create_dictionary_item,
    list_dictionary,
    update_dictionary_item,
)
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user, require_roles

router = APIRouter(
    prefix="/api/v1/questionnaire-dictionaries", tags=["questionnaire-dictionaries"]
)
Kind = Literal["beneficial_owner_bases", "beneficial_owner_absence_reasons"]


class Item(BaseModel):
    id: UUID
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class Items(BaseModel):
    items: list[Item]


class CreateItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    name: str = Field(min_length=1, max_length=2000)
    is_active: bool = True


class UpdateItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=2000)
    is_active: bool | None = None


@router.get(
    "/{kind}",
    response_model=Items,
    summary="Справочник бенефициаров",
    description="Доступен авторизованным пользователям; выбранная неактивная запись сохраняется, полный список — администратору.",
)
async def list_values(
    kind: Kind,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    include_inactive: bool = False,
    selected_id: UUID | None = None,
) -> JSONResponse:
    try:
        result = await list_dictionary(
            session,
            kind,
            actor_role=str(user.get("role")),
            include_inactive=include_inactive,
            selected_id=selected_id,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{kind}",
    status_code=201,
    response_model=Item,
    summary="Добавить запись справочника",
    description="Добавляет основание или причину. Только carcraft_employee.",
    dependencies=[Depends(require_roles("carcraft_employee"))],
)
async def create_value(
    kind: Kind, body: CreateItem, session: Annotated[AsyncSession, Depends(get_db)]
) -> JSONResponse:
    try:
        result = await create_dictionary_item(session, kind, body.model_dump())
        await session.commit()
    except ServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return JSONResponse(
        content=jsonable_encoder(result),
        status_code=201,
        headers={
            "Location": f"/api/v1/questionnaire-dictionaries/{kind}/{result['id']}"
        },
    )


@router.patch(
    "/{kind}/{identifier}",
    response_model=Item,
    summary="Изменить запись справочника",
    description="Переименование и активация/деактивация без физического удаления. Только carcraft_employee.",
    dependencies=[Depends(require_roles("carcraft_employee"))],
)
async def update_value(
    kind: Kind,
    identifier: UUID,
    body: UpdateItem,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await update_dictionary_item(
            session,
            kind,
            identifier,
            body.model_dump(exclude_unset=True, exclude_none=True),
        )
        await session.commit()
    except ServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return JSONResponse(content=jsonable_encoder(result))
