"""Current membership and the same object scope as monetization HTTP."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.monetization.views import is_deal_participant
from domain.events.notifications import NotificationEvent
from domain.monetization.deals import required_confirmations
from domain.notification_policy import POLICIES
from infrastructure.repositories import contractors_repository as contractors
from infrastructure.repositories import monetization_repository as monetization
from infrastructure.repositories import notification_recipients_repository as users


async def resolve_monetization_recipients(
    session: AsyncSession,
    event: NotificationEvent,
    *,
    user_id: UUID | None = None,
    company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Do not include group observers or customers in financial notifications."""
    if event.entity_type == "monetization_deal":
        record = await monetization.get_deal(session, event.entity_id)
    elif event.entity_type == "monetization_condition_request":
        record = await monetization.get_condition_request(session, event.entity_id)
    else:
        record = {}
    if record is None:
        return []
    companies = await _recipient_companies(session, record, event)
    policy = POLICIES[event.event_type]
    candidates = await users.candidate_contexts(
        session,
        company_ids=companies,
        include_employees="carcraft_employee" in policy.roles,
        user_id=user_id,
    )
    recipients: dict[UUID, dict[str, Any]] = {}
    for candidate in sorted(
        candidates, key=lambda item: (str(item["user_id"]), str(item.get("company_id")))
    ):
        if candidate["role"] not in policy.roles:
            continue
        if company_id is not None and candidate.get("company_id") != company_id:
            continue
        actor = await monetization.resolve_actor(
            session,
            candidate["user_id"],
            candidate["role"],
            candidate.get("company_id"),
        )
        if actor is None or not await _authorized(session, event, record, actor):
            continue
        recipient = dict(
            candidate,
            leasing_company_id=UUID(str(record["leasing_company_id"]))
            if record.get("leasing_company_id")
            else None,
        )
        recipients.setdefault(candidate["user_id"], recipient)
    return list(recipients.values())


async def _recipient_companies(
    session: AsyncSession,
    record: dict[str, Any],
    event: NotificationEvent,
) -> set[UUID]:
    companies = set()
    for field in ("dealer_company_id", "distributor_company_id"):
        if field == "distributor_company_id" and (
            event.entity_type != "monetization_deal"
            or "distributor" not in required_confirmations(record)
        ):
            continue
        if record.get(field):
            companies.add(UUID(str(record[field])))
    if record.get("leasing_company_id"):
        company = await contractors.get_leasing_company_by_id(
            session, UUID(str(record["leasing_company_id"]))
        )
        if company and company["company_id"]:
            companies.add(UUID(str(company["company_id"])))
    return companies


async def _authorized(
    session: AsyncSession,
    event: NotificationEvent,
    record: dict[str, Any],
    actor: dict[str, Any],
) -> bool:
    if event.entity_type == "monetization_capture":
        return bool(actor["role"] == "carcraft_employee")
    if event.entity_type == "monetization_condition_request":
        return (
            await monetization.get_condition_request(session, event.entity_id, actor)
            is not None
        )
    if await monetization.get_deal(session, event.entity_id, actor) is None:
        return False
    return bool(
        actor["role"] == "carcraft_employee" or is_deal_participant(record, actor)
    )
