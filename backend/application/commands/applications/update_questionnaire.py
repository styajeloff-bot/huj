
"""Upsert questionnaire on a draft application (Step 3 of checkout)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.display_number import (
    assign_display_number_if_missing,
)
from application.common import _isoformat
from application.permissions import (
    ensure_application_owned_by,
    require_can_mutate_application,
)
from application.services.company_sync import sync_company_from_questionnaire
from application.services.questionnaire import write_questionnaire
from domain.errors import ApplicationNotFoundError
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as repo


@dataclass
class UpdateQuestionnaireCommand:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    payload: dict[str, Any] = field(default_factory=dict)


async def handle_update_questionnaire(
    cmd: UpdateQuestionnaireCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await repo.get_by_id(session, cmd.application_id)
    if current is None:
        raise ApplicationNotFoundError(cmd.application_id)
    await require_can_mutate_application(
        session,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
        application=current,
    )
    entity = await ensure_application_owned_by(
        session,
        application=current,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
    )
    if cmd.actor_role == "client":
        has_children = await repo.has_lc_children(session, cmd.application_id)
        entity.ensure_editable(has_lc_children=has_children)

    saved_questionnaire = await write_questionnaire(session, cmd.application_id, cmd.payload)
    await sync_company_from_questionnaire(
        session,
        application_id=cmd.application_id,
        questionnaire_payload={key: saved_questionnaire.get(key) for key in cmd.payload},
        company_id=current.get("company_id"),
    )
    questionnaire = await repo.get_questionnaire(session, cmd.application_id)
    await assign_display_number_if_missing(
        session,
        application=current,
        questionnaire=questionnaire,
    )
    updated = await repo.get_by_id(session, cmd.application_id)
    if updated is not None:
        emit_leasing_application_changed({
            "application_id": str(updated["id"]),
            "display_number": updated.get("display_number"),
            "company_id": updated.get("company_id"),
            "dealer_company_id": updated.get("dealer_company_id"),
            "vehicle_id": updated.get("vehicle_id"),
            "name": updated.get("name"),
            "email": updated.get("email"),
            "status": updated.get("status"),
            "total_amount": updated.get("total_amount"),
            "down_payment": updated.get("down_payment"),
            "down_payment_percent": updated.get("down_payment_percent"),
            "lease_term_months": updated.get("lease_term_months"),
            "monthly_payment": updated.get("monthly_payment"),
            "total_cost": updated.get("total_cost"),
            "markup": updated.get("markup"),
            "rate": updated.get("rate"),
            "total_interest": updated.get("total_interest"),
            "buyout_amount": updated.get("buyout_amount"),
            "vat_refund": updated.get("vat_refund"),
            "profit_tax_savings": updated.get("profit_tax_savings"),
            "total_savings": updated.get("total_savings"),
            "selected_leasing_companies": updated.get("selected_leasing_companies"),
            "leasing_company_comments": updated.get("leasing_company_comments"),
            "requested_documents": updated.get("requested_documents"),
            "questionnaire_completed": updated.get("questionnaire_completed"),
            "questionnaire_progress": updated.get("questionnaire_progress"),
            "current_stage": updated.get("current_stage"),
            "created_at": _isoformat(updated.get("created_at")),
            "updated_at": _isoformat(updated.get("updated_at")),
            "_deleted": False,
        })
    if questionnaire:
        questionnaire.pop("field_sources", None)
        questionnaire.pop("people_identity_map", None)
    return {
        "message": "Анкета обновлена",
        "questionnaire": questionnaire,
    }
