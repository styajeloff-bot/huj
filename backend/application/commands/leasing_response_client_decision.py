
"""Client accepts or rejects a single КП issued by a leasing company.

The client sees one or more proposals (preliminary / final) per LC clone of
their application. They can:

- **Accept**: stamps ``client_decision_action='accepted'`` on the КП. The
  LCA status is left untouched — for a preliminary КП the LC continues
  to work on the final, for a final КП the LC is now expected to issue
  ("Выдано").
- **Reject**: stamps ``client_decision_action='rejected'`` and moves the
  LCA to ``closed`` ("Клиент отказался"). The LC sees the closed branch
  and stops working on it.
- **Cancel**: снимает ранее поставленное ``accepted`` (ТЗ №18 п. 2.10.1) —
  поля ``client_decision_*`` очищаются, статус LCA не меняется.

Authorization is delegated to ``LeasingApplication.ensure_owned_by`` —
only members of the application's owning company (or carcraft staff) may
decide.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.dwh_enrichment import build_lca_payload, build_proposal_payload
from application.notifications.leasing_events import record_leasing_event
from application.permissions import ensure_application_owned_by
from domain.entities.leasing_company_application import (
    LCA_STATUS_CLOSED,
    LeasingCompanyApplication,
)
from domain.entities.leasing_proposal import (
    CLIENT_DECISION_ACCEPTED,
    CLIENT_DECISION_CANCELLED,
    CLIENT_DECISION_REJECTED,
    LeasingProposal,
)
from domain.errors import (
    ApplicationNotFoundError,
    LeasingCompanyApplicationNotFoundError,
    LeasingProposalNotFoundError,
)
from infrastructure.messaging.dwh_events import (
    emit_lca_changed,
    emit_proposal_changed,
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
class ClientProposalDecisionCommand:
    application_id: uuid.UUID
    proposal_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    action: str  # "accepted" | "rejected" | "cancelled"
    comment: str | None = None


async def handle_client_proposal_decision(
    cmd: ClientProposalDecisionCommand, session: AsyncSession
) -> dict[str, Any]:
    raw_app = await app_repo.get_by_id(session, cmd.application_id, for_update=True)
    if raw_app is None:
        raise ApplicationNotFoundError(cmd.application_id)
    await ensure_application_owned_by(
        session,
        application=raw_app,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
    )

    raw_proposal = await proposals_repo.get_by_id(session, cmd.proposal_id)
    if raw_proposal is None:
        raise LeasingProposalNotFoundError(cmd.proposal_id)
    proposal = LeasingProposal.from_dict(raw_proposal)

    raw_link = await lca_repo.get_link_by_id(
        session, link_id=proposal.leasing_company_application_id, for_update=True,
    )
    if raw_link is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.application_id)
    if (
        raw_link.get("application_id")
        and uuid.UUID(str(raw_link["application_id"])) != cmd.application_id
    ):
        # Proposal belongs to a different application — refuse so the URL
        # path and the proposal can't be silently mismatched.
        raise LeasingProposalNotFoundError(cmd.proposal_id)
    link = LeasingCompanyApplication.from_dict(raw_link)

    raw_action = (cmd.action or "").lower().strip()
    if raw_action == CLIENT_DECISION_CANCELLED:
        proposal.ensure_client_can_cancel()
        action = None
        updated_proposal = await proposals_repo.clear_client_decision(
            session, proposal_id=cmd.proposal_id
        )
    else:
        action = LeasingProposal.normalize_client_decision(cmd.action)
        proposal.ensure_client_can_decide()
        updated_proposal = await proposals_repo.record_client_decision(
            session,
            proposal_id=cmd.proposal_id,
            action=action,
            comment=cmd.comment,
        )
    if updated_proposal is not None:
        lca_for_proposal = await lca_repo.get_link_by_id(session, proposal.leasing_company_application_id)
        app_raw = await app_repo.get_by_id(session, cmd.application_id) if cmd.application_id else None
        payload = await build_proposal_payload(session, updated_proposal, lca_for_proposal, app_raw)
        emit_proposal_changed(payload)

    new_lca_status = link.status
    if action == CLIENT_DECISION_REJECTED:
        link.ensure_can_change_status(LCA_STATUS_CLOSED)
        await lca_repo.update_link_status(
            session,
            link_id=link.id,
            new_status=LCA_STATUS_CLOSED,
            review_notes=cmd.comment,
        )
        await hist_repo.append_lca_status_history(
            session,
            lca_id=link.id,
            application_id=cmd.application_id,
            old_status=link.status,
            new_status=LCA_STATUS_CLOSED,
            changed_by=cmd.actor_id,
            review_notes=cmd.comment,
        )
        new_lca_status = LCA_STATUS_CLOSED

    updated_lca = await lca_repo.get_link_by_id(session, link.id)
    app_raw = await app_repo.get_by_id(session, cmd.application_id) if cmd.application_id else None
    if updated_lca is not None:
        payload = await build_lca_payload(session, updated_lca, app_raw)
        emit_lca_changed(payload)

    if action == CLIENT_DECISION_ACCEPTED:
        await record_leasing_event(
            session, application=raw_app,
            event_type=f"leasing.{proposal.kind}_offer_accepted",
            actor_user_id=cmd.actor_id,
            previous_values={"client_decision_action": proposal.client_decision_action},
            new_values={"client_decision_action": action},
            payload={
                "leasing_company_id": link.leasing_company_id,
                "leasing_company_application_id": link.id,
                "proposal_id": proposal.id, "proposal_kind": proposal.kind,
            },
        )
    return {
        "proposal_id": cmd.proposal_id,
        "application_id": cmd.application_id,
        "leasing_company_application_id": link.id,
        "client_decision_action": action,
        "lca_status": new_lca_status,
        "proposal": updated_proposal,
    }
