"""Compatibility endpoint delegating to the shared application write use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.update_questionnaire import (
    UpdateQuestionnaireCommand,
    handle_update_questionnaire,
)
from domain.questionnaire import questionnaire_progress


@dataclass
class UpsertQuestionnaireCommand:
    application_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None
    payload: dict[str, Any]


async def handle_upsert_questionnaire(
    cmd: UpsertQuestionnaireCommand, session: AsyncSession
) -> dict[str, Any]:
    result = await handle_update_questionnaire(
        UpdateQuestionnaireCommand(
            application_id=cmd.application_id,
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            actor_company_id=cmd.actor_company_id,
            payload=cmd.payload,
        ),
        session,
    )
    progress, completed = questionnaire_progress(result["questionnaire"] or {})
    return {
        "completed": completed,
        "progress": progress,
        "message": "Анкета заполнена" if completed else "Данные сохранены",
    }
