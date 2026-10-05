
"""Change application status — validates transition via aggregate root."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.notifications.leasing_events import record_leasing_event
from application.permissions import (
    ensure_application_owned_by,
    require_can_mutate_application,
)
from domain.errors import ApplicationNotFoundError
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as repo


@dataclass
class ChangeStatusCommand:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    new_status: str


async def handle_change_status(
    cmd: ChangeStatusCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await repo.get_by_id(session, cmd.application_id, for_update=True)
    if current is None:
        raise ApplicationNotFoundError(cmd.application_id)
    entity = await ensure_application_owned_by(
        session,
        application=current,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
    )
    await require_can_mutate_application(
        session,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
        application=current,
    )
    entity.ensure_can_change_status(cmd.new_status)

    old_status = entity.status
    await repo.update_application_status(
        session,
        cmd.application_id,
        new_status=cmd.new_status,
        changed_by=cmd.actor_id,
    )
    from infrastructure.repositories.status_history_repository import (
        append_leasing_app_status_history,
    )
    await append_leasing_app_status_history(
        application_id=cmd.application_id,
        old_status=old_status,
        new_status=cmd.new_status,
        changed_by=cmd.actor_id,
    )
    updated = await repo.get_by_id(session, cmd.application_id)
    assert updated is not None
    if cmd.new_status == "rejected" and cmd.actor_role == "client":
        event_type = "leasing.application_cancelled"
    elif cmd.new_status in {"rejected", "issued"}:
        event_type = "leasing.application_finalized"
    else:
        event_type = "leasing.application_status_changed"
    await record_leasing_event(
        session, application=updated, event_type=event_type,
        actor_user_id=cmd.actor_id,
        previous_values={"status": old_status},
        new_values={"status": cmd.new_status},
    )
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
    return {
        "message": "Статус заявки обновлён",
        "application": updated,
    }
