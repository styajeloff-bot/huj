"""Registered equipment taxonomy for internal conditions, independent of inventory."""

from __future__ import annotations

import contextlib
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentTrim,
)


async def list_marks(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
            .where(SpecialEquipmentMark.is_active.is_(True))
            .order_by(SpecialEquipmentMark.name, SpecialEquipmentMark.id)
        )
    ).all()
    return [{"id": str(row.id), "ids": [str(row.id)], "name": row.name} for row in rows]


async def list_models(session: AsyncSession, mark_ids: list[str]) -> list[dict[str, Any]]:
    if not mark_ids:
        return []
    uids: list[UUID] = []
    for m in mark_ids:
        with contextlib.suppress(ValueError, TypeError):
            uids.append(UUID(str(m)))
    if not uids:
        return []
    rows = (
        await session.execute(
            select(SpecialEquipmentModel.id, SpecialEquipmentModel.name)
            .where(
                SpecialEquipmentModel.mark_id.in_(uids),
                SpecialEquipmentModel.name.is_not(None),
                SpecialEquipmentModel.name != "",
            )
            .order_by(SpecialEquipmentModel.name, SpecialEquipmentModel.id)
        )
    ).mappings()
    return [{"id": str(row["id"]), "name": row["name"]} for row in rows]


async def list_modifications(
    session: AsyncSession, mark_ids: list[str], model_id: str | None,
) -> list[dict[str, Any]]:
    if not mark_ids or not model_id:
        return []
    m_uid: UUID | None = None
    with contextlib.suppress(ValueError, TypeError):
        m_uid = UUID(str(model_id))
    if m_uid is None:
        return []
    rows = (
        await session.execute(
            select(SpecialEquipmentModification.id, SpecialEquipmentModification.name)
            .where(
                SpecialEquipmentModification.model_id == m_uid,
                SpecialEquipmentModification.name.is_not(None),
                SpecialEquipmentModification.name != "",
            )
            .order_by(SpecialEquipmentModification.name, SpecialEquipmentModification.id)
        )
    ).mappings()
    return [{"id": str(row["id"]), "name": row["name"]} for row in rows]


async def list_trims(
    session: AsyncSession, mark_ids: list[str], model_id: str | None,
    modification_id: UUID | None,
) -> list[dict[str, Any]]:
    if not mark_ids or not model_id or modification_id is None:
        return []
    try:
        model_uid = UUID(model_id)
    except (ValueError, TypeError):
        return []
    mark_uids: list[UUID] = []
    for mark_id in mark_ids:
        with contextlib.suppress(ValueError, TypeError):
            mark_uids.append(UUID(mark_id))
    if not mark_uids:
        return []
    rows = (
        await session.execute(
            select(SpecialEquipmentTrim.id, SpecialEquipmentTrim.name)
            .join(
                SpecialEquipmentModification,
                SpecialEquipmentModification.id == SpecialEquipmentTrim.modification_id,
            )
            .join(
                SpecialEquipmentModel,
                SpecialEquipmentModel.id == SpecialEquipmentModification.model_id,
            )
            .where(
                SpecialEquipmentTrim.modification_id == modification_id,
                SpecialEquipmentModel.id == model_uid,
                SpecialEquipmentModel.mark_id.in_(mark_uids),
                SpecialEquipmentTrim.name != "",
            )
            .order_by(SpecialEquipmentTrim.name, SpecialEquipmentTrim.id)
        )
    ).mappings()
    return [
        {"id": row["id"], "name": row["name"], "trim_name": row["name"]}
        for row in rows
    ]
