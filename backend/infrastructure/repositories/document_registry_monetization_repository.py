"""Persistence for registry references; callers own transactions and validation."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.document_registry import (
    reference_document_monetization_programs as links,
)
from infrastructure.models.monetization import programs
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
)


async def resolve_catalog(session: AsyncSession, brand: str | None,
                          model: str | None) -> dict[str, Any] | None:
    """Resolve legacy name snapshots exactly; never turn an unknown name into a wildcard."""
    if not brand:
        return None if model else {"mark_id": None, "model_id": None}
    marks = list((await session.scalars(sa.select(SpecialEquipmentMark.id).where(
        SpecialEquipmentMark.name == brand, SpecialEquipmentMark.is_active.is_(True),
    ).limit(2))).all())
    if len(marks) != 1:
        return None
    model_id = None
    if model:
        models = list((await session.scalars(sa.select(SpecialEquipmentModel.id).where(
            SpecialEquipmentModel.mark_id == marks[0], SpecialEquipmentModel.name == model,
            SpecialEquipmentModel.is_active.is_(True),
        ).limit(2))).all())
        if len(models) != 1:
            return None
        model_id = models[0]
    return {"mark_id": marks[0], "model_id": model_id}


async def lock_program(session: AsyncSession, program_id: UUID) -> bool:
    return (await session.scalar(sa.select(programs.c.id).where(
        programs.c.id == program_id).with_for_update())) is not None


async def linked_ids(session: AsyncSession, program_id: UUID) -> list[UUID]:
    return list((await session.scalars(sa.select(links.c.document_id).where(
        links.c.program_id == program_id).order_by(links.c.document_id))).all())


async def replace_links(session: AsyncSession, program_id: UUID,
                        document_ids: list[UUID], actor_id: UUID) -> None:
    await session.execute(links.delete().where(links.c.program_id == program_id))
    if document_ids:
        await session.execute(links.insert(), [
            {"program_id": program_id, "document_id": document_id, "created_by": actor_id}
            for document_id in document_ids
        ])
