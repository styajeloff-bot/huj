"""Commands for positions catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import positions_repository


@dataclass(frozen=True, slots=True)
class CreatePositionCommand:
    name: str
    code: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class UpdatePositionCommand:
    position_id: UUID
    name: str
    code: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class DeactivatePositionCommand:
    position_id: UUID


async def handle_create_position(
    command: CreatePositionCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Handle creating a new position with code uniqueness check."""
    existing = await positions_repository.get_position_by_code(session, command.code)
    if existing is not None:
        raise ServiceError("Должность с таким кодом уже существует", 400)

    result = await positions_repository.create_position(
        session,
        name=command.name,
        code=command.code,
        is_active=command.is_active,
    )
    return cast("dict[str, Any]", result)


async def handle_update_position(
    command: UpdatePositionCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Handle updating an existing position with code uniqueness check."""
    pos = await positions_repository.get_position_by_id(session, command.position_id)
    if pos is None:
        raise ServiceError("Должность не найдена", 404)

    existing = await positions_repository.get_position_by_code(session, command.code)
    if existing is not None and str(existing["id"]) != str(command.position_id):
        raise ServiceError("Должность с таким кодом уже существует", 400)

    updated = await positions_repository.update_position(
        session,
        position_id=command.position_id,
        name=command.name,
        code=command.code,
        is_active=command.is_active,
    )
    if updated is None:
        raise ServiceError("Должность не найдена", 404)
    return cast("dict[str, Any]", updated)


async def handle_deactivate_position(
    command: DeactivatePositionCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Handle deactivating a position."""
    pos = await positions_repository.get_position_by_id(session, command.position_id)
    if pos is None:
        raise ServiceError("Должность не найдена", 404)

    deactivated = await positions_repository.deactivate_position(
        session,
        command.position_id,
    )
    if deactivated is None:
        raise ServiceError("Должность не найдена", 404)
    return cast("dict[str, Any]", deactivated)
