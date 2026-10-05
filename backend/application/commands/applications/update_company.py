
"""Update draft application's company_id (Step 2 of checkout)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.display_number import (
    assign_display_number_if_missing,
)
from application.common import _isoformat
from application.errors import ServiceError
from application.permissions import (
    ensure_application_owned_by,
    require_can_mutate_application,
)
from domain.errors import (
    ApplicationNotFoundError,
    CompanyNotFoundError,
)
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as repo


@dataclass
class UpdateCompanyCommand:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    company_id: UUID


def _same_id(left: Any, right: Any) -> bool:
    return left is not None and right is not None and str(left) == str(right)


async def handle_update_company(
    cmd: UpdateCompanyCommand, session: AsyncSession
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

    if (
        cmd.actor_role == "dealer"
        and not _same_id(current.get("company_id"), cmd.company_id)
    ):
        raise ServiceError("Дилер не может менять компанию клиента в созданной заявке", 403)

    if not await repo.company_exists(session, cmd.company_id):
        raise CompanyNotFoundError()

    await repo.update_application_fields(
        session,
        cmd.application_id,
        fields={"company_id": cmd.company_id},
    )

    updated = await repo.get_by_id(session, cmd.application_id)
    assert updated is not None
    await assign_display_number_if_missing(session, application=updated)
    updated = await repo.get_by_id(session, cmd.application_id)
    assert updated is not None
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
        "message": "Компания заявки обновлена",
        "application": updated,
    }
