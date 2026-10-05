
"""LC marks an approved application as issued ("Выдано").

Pre-conditions:

- The LCA must be in ``approved_final`` (final КП issued and not closed/rejected).
- The client must have accepted the final КП (``client_decision_action ==
  'accepted'`` on the final-kind proposal).

Side effects:

- LCA status → ``deal``.
- Parent ``leasing_applications.status`` → ``issued`` (the deal is done from
  the application's point of view as well).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization.integration import capture_source_transition
from application.common import _isoformat
from application.errors import ServiceError
from application.notifications.leasing_events import record_leasing_event
from application.special_equipment_commerce import (
    create_leasing_orders_for_issued_application,
)
from domain.entities.leasing_application import (
    STATUS_ISSUED,
    LeasingApplication,
)
from domain.entities.leasing_company_application import (
    LCA_STATUS_APPROVED_FINAL,
    LCA_STATUS_DEAL,
    LeasingCompanyApplication,
)
from domain.entities.leasing_proposal import (
    CLIENT_DECISION_ACCEPTED,
    KIND_FINAL,
)
from domain.errors import (
    ApplicationNotFoundError,
    LeasingCompanyApplicationNotFoundError,
)
from infrastructure.messaging.dwh_events import (
    emit_lca_changed,
    emit_leasing_application_changed,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import (
    leasing_proposals_repository as proposals_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo


@dataclass
class IssueApplicationCommand:
    application_id: uuid.UUID
    actor_user_id: UUID
    actor_leasing_company_id: UUID | None


async def handle_issue_application(
    cmd: IssueApplicationCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.actor_leasing_company_id is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.application_id)

    raw_app = await app_repo.get_by_id(session, cmd.application_id, for_update=True)
    if raw_app is None:
        raise ApplicationNotFoundError(cmd.application_id)

    raw_link = await lca_repo.get_link_for_app_and_lc(
        session,
        application_id=cmd.application_id,
        leasing_company_id=cmd.actor_leasing_company_id,
        for_update=True,
    )
    if raw_link is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.application_id)
    link = LeasingCompanyApplication.from_dict(raw_link)
    link.ensure_owned_by_lc(leasing_company_id=cmd.actor_leasing_company_id)

    replayed = link.status == LCA_STATUS_DEAL
    if link.status not in {LCA_STATUS_APPROVED_FINAL, LCA_STATUS_DEAL}:
        raise ServiceError(
            "Выдано можно проставить только после одобрения "
            "итогового КП клиентом",
            status_code=400,
        )

    proposals = await proposals_repo.list_by_lca(session, link.id)
    final_accepted = next(
        (
            p
            for p in proposals
            if p.get("kind") == KIND_FINAL
            and p.get("client_decision_action") == CLIENT_DECISION_ACCEPTED
        ),
        None,
    )
    if final_accepted is None:
        raise ServiceError(
            "Клиент ещё не принял итоговое КП — отметка «Выдано» недоступна",
            status_code=400,
        )

    if not replayed:
        link.ensure_can_issue()
        await lca_repo.update_link_status(
            session,
            link_id=link.id,
            new_status=LCA_STATUS_DEAL,
        )
        await hist_repo.append_lca_status_history(
            session,
            lca_id=link.id,
            application_id=cmd.application_id,
            old_status=LCA_STATUS_APPROVED_FINAL,
            new_status=LCA_STATUS_DEAL,
            changed_by=cmd.actor_user_id,
        )

    application = LeasingApplication.from_dict(raw_app)
    application_status_changed = application.status != STATUS_ISSUED
    if application.status != STATUS_ISSUED:
        # Parent status mirrors the per-LC outcome — the deal is done.
        await app_repo.update_application_status(
            session,
            cmd.application_id,
            new_status=STATUS_ISSUED,
        )
        from infrastructure.repositories.status_history_repository import (
            append_leasing_app_status_history,
        )
        await append_leasing_app_status_history(
            application_id=cmd.application_id,
            old_status=application.status,
            new_status=STATUS_ISSUED,
            changed_by=cmd.actor_user_id,
        )

    special_equipment_orders = await create_leasing_orders_for_issued_application(
        application=raw_app,
        final_proposal=final_accepted,
        session=session,
    )

    if not replayed:
        await capture_source_transition(session, actor_user_id=cmd.actor_user_id,
                                        leasing_company_application_id=link.id)

    updated_link = await lca_repo.get_link_by_id(session, link.id)
    updated_app = await app_repo.get_by_id(session, cmd.application_id)

    if updated_link is not None and (not replayed or application_status_changed):
        emit_lca_changed({
            "lca_id": updated_link["id"],
            "application_id": str(updated_link["application_id"]) if updated_link.get("application_id") else None,
            "leasing_company_id": updated_link.get("leasing_company_id"),
            "status": updated_link.get("status"),
            "review_notes": updated_link.get("review_notes"),
            "decision_comment": updated_link.get("decision_comment"),
            "response_pdf_s3_key": updated_link.get("response_pdf_s3_key"),
            "response_pdf_file_name": updated_link.get("response_pdf_file_name"),
            "response_pdf_size": updated_link.get("response_pdf_size"),
            "response_pdf_uploaded_at": _isoformat(updated_link.get("response_pdf_uploaded_at")),
            "submitted_at": _isoformat(updated_link.get("submitted_at")),
            "created_at": _isoformat(updated_link.get("created_at")),
            "updated_at": _isoformat(updated_link.get("updated_at")),
            "_deleted": False,
            # denormalized from parent application
            "dealer_id": None,
            "dealer_company_id": updated_app.get("dealer_company_id") if updated_app else None,
            "client_company_id": updated_app.get("company_id") if updated_app else None,
            "display_number": updated_app.get("display_number") if updated_app else None,
            "vehicle_id": updated_app.get("vehicle_id") if updated_app else None,
            "application_status": updated_app.get("status") if updated_app else None,
        })
    if updated_app is not None and (not replayed or application_status_changed):
        emit_leasing_application_changed({
            "application_id": str(updated_app["id"]),
            "display_number": updated_app.get("display_number"),
            "company_id": updated_app.get("company_id"),
            "dealer_company_id": updated_app.get("dealer_company_id"),
            "vehicle_id": updated_app.get("vehicle_id"),
            "name": updated_app.get("name"),
            "email": updated_app.get("email"),
            "status": updated_app.get("status"),
            "total_amount": updated_app.get("total_amount"),
            "down_payment": updated_app.get("down_payment"),
            "down_payment_percent": updated_app.get("down_payment_percent"),
            "lease_term_months": updated_app.get("lease_term_months"),
            "monthly_payment": updated_app.get("monthly_payment"),
            "total_cost": updated_app.get("total_cost"),
            "markup": updated_app.get("markup"),
            "rate": updated_app.get("rate"),
            "total_interest": updated_app.get("total_interest"),
            "buyout_amount": updated_app.get("buyout_amount"),
            "vat_refund": updated_app.get("vat_refund"),
            "profit_tax_savings": updated_app.get("profit_tax_savings"),
            "total_savings": updated_app.get("total_savings"),
            "selected_leasing_companies": updated_app.get("selected_leasing_companies"),
            "leasing_company_comments": updated_app.get("leasing_company_comments"),
            "requested_documents": updated_app.get("requested_documents"),
            "questionnaire_completed": updated_app.get("questionnaire_completed"),
            "questionnaire_progress": updated_app.get("questionnaire_progress"),
            "current_stage": updated_app.get("current_stage"),
            "created_at": _isoformat(updated_app.get("created_at")),
            "updated_at": _isoformat(updated_app.get("updated_at")),
            "_deleted": False,
        })
    if application_status_changed:
        await record_leasing_event(
            session, application=updated_app or raw_app,
            event_type="leasing.application_finalized",
            actor_user_id=cmd.actor_user_id,
            previous_values={"status": application.status},
            new_values={"status": STATUS_ISSUED},
            payload={"leasing_company_id": link.leasing_company_id,
                     "leasing_company_application_id": link.id},
        )
    return {
        "application_id": cmd.application_id,
        "leasing_company_application_id": link.id,
        "status": LCA_STATUS_DEAL,
        "message": "Заявка выдана",
        "replayed": replayed,
        "special_equipment_orders": [
            {
                "id": str(order["id"]),
                "product_id": str(order["product_id"]),
                "status": order["status"],
            }
            for order in special_equipment_orders
        ],
    }
