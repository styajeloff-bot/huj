"""Persist validated per-LC field overrides; defaults belong to the use case."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.questionnaire_settings import LeasingQuestionnaireSettings


async def get_fields(session: AsyncSession, leasing_company_id: UUID) -> dict[str, Any]:
    fields = (await session.execute(select(LeasingQuestionnaireSettings.fields).where(
        LeasingQuestionnaireSettings.leasing_company_id == leasing_company_id
    ))).scalar_one_or_none()
    return dict(fields) if fields is not None else {}


async def replace_fields(
    session: AsyncSession, leasing_company_id: UUID, fields: dict[str, Any]
) -> None:
    statement = insert(LeasingQuestionnaireSettings).values(
        leasing_company_id=leasing_company_id, fields=fields
    )
    await session.execute(statement.on_conflict_do_update(
        index_elements=["leasing_company_id"], set_={"fields": fields}
    ))
