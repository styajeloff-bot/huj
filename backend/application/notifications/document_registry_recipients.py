"""Expiry recipients share current company memberships and registry read ACL."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.document_registry.views import get_document
from domain.events.notifications import NotificationEvent
from infrastructure.repositories import (
    notification_document_registry_repository as documents,
)
from infrastructure.repositories import notification_recipients_repository as users


async def resolve_document_registry_recipients(
    session: AsyncSession,
    event: NotificationEvent,
    *,
    user_id: UUID | None = None,
    company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    record = await documents.get_document_context(session, event.entity_id)
    if record is None:
        return []
    company_roles = record["company_roles"]
    include_employees = record["platform_ml_participates"] or record["platform_ml_related"]
    candidates = await users.candidate_contexts(
        session, company_ids={company for _, company in company_roles},
        include_employees=include_employees, user_id=user_id, readable_only=False,
    )
    recipients: dict[UUID, dict[str, Any]] = {}
    for candidate in sorted(
        candidates, key=lambda row: (str(row["user_id"]), str(row.get("company_id"))),
    ):
        if company_id is not None and candidate.get("company_id") != company_id:
            continue
        if candidate["role"] == "carcraft_employee":
            if not include_employees:
                continue
        elif (candidate["role"], candidate["company_id"]) not in company_roles:
            continue
        actor = {
            "user_id": candidate["user_id"], "role": candidate["role"],
            "company_id": candidate["company_id"],
            "company_ids": [candidate["company_id"]] if candidate["company_id"] else [],
            "can_write": candidate["role"] == "carcraft_employee",
        }
        try:
            await get_document(session, event.entity_id, actor)
        except ServiceError as exc:
            if exc.status_code in {403, 404}:
                continue
            raise
        recipients.setdefault(candidate["user_id"], candidate)
    return list(recipients.values())
