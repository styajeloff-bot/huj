"""Use cases for questionnaire reference dictionaries."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import questionnaire_dictionaries_repository as repo


async def list_dictionary(
    session: AsyncSession,
    kind: str,
    *,
    actor_role: str,
    include_inactive: bool = False,
    selected_id: UUID | None = None,
) -> dict[str, Any]:
    if include_inactive and actor_role != "carcraft_employee":
        raise ServiceError(
            "Просмотр всех неактивных записей доступен администратору", 403
        )
    return {
        "items": await repo.list_items(
            session, kind, include_inactive=include_inactive, selected_id=selected_id
        )
    }


async def create_dictionary_item(
    session: AsyncSession, kind: str, payload: dict[str, Any]
) -> dict[str, Any]:
    if await repo.code_exists(session, kind, payload["code"]):
        raise ServiceError("Запись с таким кодом уже существует", 409)
    try:
        return await repo.create_item(session, kind, payload)
    except IntegrityError as exc:
        raise ServiceError("Запись с таким кодом уже существует", 409) from exc


async def update_dictionary_item(
    session: AsyncSession, kind: str, identifier: UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    result = await repo.update_item(session, kind, identifier, payload)
    if result is None:
        raise ServiceError("Запись справочника не найдена", 404)
    return result
