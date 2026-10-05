"""Beneficiary dictionary persistence; historical choices survive deactivation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.questionnaire_dictionaries import (
    BeneficialOwnerAbsenceReason,
    BeneficialOwnerBasis,
)

MODELS: dict[str, type[BeneficialOwnerBasis] | type[BeneficialOwnerAbsenceReason]] = {
    "beneficial_owner_bases": BeneficialOwnerBasis,
    "beneficial_owner_absence_reasons": BeneficialOwnerAbsenceReason,
}


def _dict(row: Any) -> dict[str, Any]:
    return {
        key: getattr(row, key)
        for key in ("id", "code", "name", "is_active", "created_at", "updated_at")
    }


async def list_items(
    session: AsyncSession,
    kind: str,
    *,
    include_inactive: bool = False,
    selected_id: UUID | None = None,
) -> list[dict[str, Any]]:
    model = MODELS[kind]
    stmt = select(model)
    if not include_inactive:
        stmt = stmt.where(model.is_active.is_(True) | (model.id == selected_id))
    return [
        _dict(row)
        for row in (
            await session.execute(stmt.order_by(model.created_at, model.code))
        ).scalars()
    ]


async def get_item(
    session: AsyncSession, kind: str, identifier: UUID
) -> dict[str, Any] | None:
    row = cast(
        "BeneficialOwnerBasis | BeneficialOwnerAbsenceReason | None",
        await session.get(MODELS[kind], identifier),
    )
    return _dict(row) if row else None


async def code_exists(session: AsyncSession, kind: str, code: str) -> bool:
    model = MODELS[kind]
    return (
        await session.execute(select(model.id).where(model.code == code))
    ).scalar_one_or_none() is not None


async def create_item(
    session: AsyncSession, kind: str, payload: dict[str, Any]
) -> dict[str, Any]:
    row = MODELS[kind](**payload)
    session.add(row)
    await session.flush()
    return _dict(row)


async def update_item(
    session: AsyncSession, kind: str, identifier: UUID, payload: dict[str, Any]
) -> dict[str, Any] | None:
    row = cast(
        "BeneficialOwnerBasis | BeneficialOwnerAbsenceReason | None",
        await session.get(MODELS[kind], identifier),
    )
    if row is None:
        return None
    for key, value in payload.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return _dict(row)
