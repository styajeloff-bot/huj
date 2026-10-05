"""LC confirms it has seen the application ("Взять в работу").

Sets the LCA (leasing_company_applications) status from ``submitted`` to
``under_review``. The parent LA status remains ``active`` — LCA tracks
per-LC state independently.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.leasing_events import record_lca_transition
from domain.errors import (
    ApplicationNotFoundError,
    LeasingCompanyApplicationNotFoundError,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo


@dataclass
class TakeInWorkCommand:
    application_id: uuid.UUID
    actor_user_id: UUID
    actor_leasing_company_id: UUID | None


async def handle_take_in_work(
    cmd: TakeInWorkCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.actor_leasing_company_id is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.application_id)

    raw = await app_repo.get_by_id(session, cmd.application_id, for_update=True)
    if raw is None:
        raise ApplicationNotFoundError(cmd.application_id)

    # Verify the calling LC has an LCA row for this application.
    link = await lca_repo.get_link_for_app_and_lc(
        session,
        application_id=cmd.application_id,
        leasing_company_id=cmd.actor_leasing_company_id,
        for_update=True,
    )
    if link is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.application_id)

    # Transition LCA status from submitted → under_review.
    replayed = link.get("status") != "submitted"
    if not replayed:
        await lca_repo.update_link_status(
            session,
            link_id=link["id"],
            new_status="under_review",
        )
        await hist_repo.append_lca_status_history(
            session,
            lca_id=link["id"],
            application_id=cmd.application_id,
            old_status="submitted",
            new_status="under_review",
            changed_by=cmd.actor_user_id,
        )
        await record_lca_transition(
            session, application=raw, link=link, new_status="under_review",
            actor_user_id=cmd.actor_user_id,
        )
        link["status"] = "under_review"

    return {
        "application_id": cmd.application_id,
        "lca_id": link["id"],
        "lca_status": link["status"],
        "parent_status": raw.get("status"),
        "replayed": replayed,
        "message": (
            "Статус заявки уже изменён. Показано актуальное состояние."
            if replayed else "Заявка взята в работу"
        ),
    }
