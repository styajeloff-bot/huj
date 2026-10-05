"""Link existing documents (already in ``documents``) to a leasing application.

Used at checkout submit to glue the step-4 uploads — which land in the
user-scope ``documents`` without an application_id — into the application
via the ``document_applications`` M2M. The modal's «Приложенные документы»
block reads from this M2M, so without this step the step-4 files never
surface on the application page.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.permissions import (
    ensure_application_owned_by,
    require_can_mutate_application,
)
from domain.errors import ApplicationNotFoundError
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import documents_repository as documents_repo


@dataclass
class AttachDocumentsToApplicationCommand:
    application_id: UUID
    actor_id: UUID
    document_ids: list[UUID] = field(default_factory=list)
    actor_role: str = ""
    actor_company_id: UUID | None = None
    actor_leasing_company_id: UUID | None = None


async def handle_attach_documents_to_application(
    cmd: AttachDocumentsToApplicationCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await app_repo.get_by_id(session, cmd.application_id)
    if current is None:
        raise ApplicationNotFoundError(cmd.application_id)
    await require_can_mutate_application(
        session,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
        application=current,
    )
    await ensure_application_owned_by(
        session,
        application=current,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
        actor_leasing_company_id=cmd.actor_leasing_company_id,
    )

    linked: list[UUID] = []
    skipped: list[UUID] = []
    for document_id in cmd.document_ids:
        doc = await documents_repo.get_by_id(session, document_id)
        if doc is None:
            skipped.append(document_id)
            continue
        # Only let the applicant link their own company's documents — the
        # M2M is open for LC employees to upload review artifacts, so a
        # client shouldn't be able to attach an LC's document to their app.
        if cmd.actor_company_id is not None and doc.get("company_id") != cmd.actor_company_id:
            skipped.append(document_id)
            continue
        created = await documents_repo.link_to_application(
            session,
            document_id=document_id,
            application_id=cmd.application_id,
        )
        if created:
            linked.append(document_id)
    updated = await app_repo.get_by_id(session, cmd.application_id)
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
    return {
        "application_id": cmd.application_id,
        "linked_document_ids": linked,
        "skipped_document_ids": skipped,
    }
