
"""Admin status change for ``leasing_company_applications`` rows.

Validates the transition via the ``LeasingCompanyApplication`` aggregate
and appends a status-history row (backed by ``audit_log``). Scoped to
``carcraft_employee`` by the router.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization.integration import capture_source_transition
from application.common import _isoformat
from application.notifications.leasing_events import record_lca_transition
from domain.entities.leasing_company_application import (
    LeasingCompanyApplication,
)
from domain.errors import (
    LeasingCompanyApplicationNotFoundError,
)
from infrastructure.messaging.dwh_events import emit_lca_changed
from infrastructure.repositories import (
    application_repository as app_repo,
)
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo


@dataclass
class ChangeLeasingAppStatusCommand:
    link_id: UUID
    actor_user_id: UUID
    actor_role: str
    new_status: str
    change_reason: str | None = None


async def handle_change_leasing_app_status(
    cmd: ChangeLeasingAppStatusCommand, session: AsyncSession
) -> dict[str, Any]:
    link_raw = await lca_repo.get_link_by_id(session, cmd.link_id)
    if link_raw is None:
        raise LeasingCompanyApplicationNotFoundError()
    if link_raw.get("application_id") is not None:
        await app_repo.get_by_id(session, link_raw["application_id"], for_update=True)
    link_raw = await lca_repo.get_link_by_id(session, cmd.link_id, for_update=True)
    assert link_raw is not None
    link = LeasingCompanyApplication.from_dict(link_raw)
    link.ensure_can_change_status(cmd.new_status)

    old_status = link.status
    await lca_repo.update_link_status(
        session,
        link_id=link.id,
        new_status=cmd.new_status,
        review_notes=cmd.change_reason,
    )
    await hist_repo.append_lca_status_history(
        session,
        lca_id=link.id,
        application_id=link.application_id,
        old_status=old_status,
        new_status=cmd.new_status,
        changed_by=cmd.actor_user_id,
        review_notes=cmd.change_reason,
    )
    if cmd.new_status == "deal" and old_status != "deal":
        await capture_source_transition(session, actor_user_id=cmd.actor_user_id,
                                        leasing_company_application_id=link.id)

    updated = await lca_repo.get_link_by_id(session, link.id)
    app_raw = await app_repo.get_by_id(session, link.application_id) if link.application_id else None
    if app_raw is not None:
        await record_lca_transition(
            session, application=app_raw, link=link_raw,
            new_status=cmd.new_status, actor_user_id=cmd.actor_user_id,
        )
    if updated is not None:
        emit_lca_changed({
            "lca_id": updated["id"],
            "application_id": str(updated["application_id"]) if updated.get("application_id") else None,
            "leasing_company_id": updated.get("leasing_company_id"),
            "status": updated.get("status"),
            "review_notes": updated.get("review_notes"),
            "decision_comment": updated.get("decision_comment"),
            "response_pdf_s3_key": updated.get("response_pdf_s3_key"),
            "response_pdf_file_name": updated.get("response_pdf_file_name"),
            "response_pdf_size": updated.get("response_pdf_size"),
            "response_pdf_uploaded_at": _isoformat(updated.get("response_pdf_uploaded_at")),
            "submitted_at": _isoformat(updated.get("submitted_at")),
            "created_at": _isoformat(updated.get("created_at")),
            "updated_at": _isoformat(updated.get("updated_at")),
            "_deleted": False,
            # denormalized from parent application
            "dealer_id": None,
            "dealer_company_id": app_raw.get("dealer_company_id") if app_raw else None,
            "client_company_id": app_raw.get("company_id") if app_raw else None,
            "display_number": app_raw.get("display_number") if app_raw else None,
            "vehicle_id": app_raw.get("vehicle_id") if app_raw else None,
            "application_status": app_raw.get("status") if app_raw else None,
        })
    return {
        "success": True,
        "message": "Статус ЛК-заявки обновлён",
        "link_id": link.id,
        "application_id": link.application_id,
        "leasing_company_id": link.leasing_company_id,
        "old_status": old_status,
        "new_status": cmd.new_status,
    }
