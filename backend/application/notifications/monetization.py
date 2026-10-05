"""Internal-only facts; the caller's transaction owns both money and the outbox."""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.events import record_notification_event
from infrastructure.repositories import application_repository as applications

logger = logging.getLogger("carcraft-backend")


def _number(record: dict[str, Any], fallback: Any) -> str:
    return str(
        record.get("application_number") or record.get("display_number") or fallback
    )


async def notify_capture_result(
    session: AsyncSession,
    context: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Deduplicated created/failure facts from both successful and refused captures."""
    deal = result.get("deal")
    if deal is not None:
        await record_notification_event(
            session,
            event_type="monetization.deal_created",
            entity_type="monetization_deal",
            entity_id=deal["id"],
            aggregate_id=deal["id"],
            application_id=deal.get("application_id"),
            actor_user_id=context.get("actor_user_id"),
            request_number=_number(deal, deal["id"]),
            new_values={"status": deal["status"]},
            payload={"revision": deal["revision"]},
            occurrence_key=f"monetization.deal_created:{deal['id']}",
        )
        return
    origin = (
        context.get("leasing_company_application_id")
        or context.get("exchange_request_id")
        or context.get("application_id")
    )
    if origin is None:
        logger.warning("monetization_notification_missing_origin")
        return
    reason = str(result.get("reason") or "Недостаточно данных для расчёта монетизации")
    fingerprint = hashlib.sha256(reason.encode()).hexdigest()[:24]
    await record_notification_event(
        session,
        event_type="monetization.capture_failed",
        entity_type="monetization_capture",
        entity_id=origin,
        aggregate_id=origin,
        application_id=context.get("application_id"),
        actor_user_id=context.get("actor_user_id"),
        request_number=_number(context, origin),
        payload={
            "reason": reason,
            "exchange_request_id": context.get("exchange_request_id"),
        },
        occurrence_key=f"monetization.capture_failed:{origin}:{fingerprint}",
    )


async def notify_deal_confirmation(
    session: AsyncSession,
    deal: dict[str, Any],
    party: str,
    actor_user_id: UUID,
) -> None:
    """An administrator receives side confirmations; participants receive paid."""
    paid = deal["status"] == "paid"
    event_type = "monetization.deal_paid" if paid else "monetization.party_confirmed"
    payload = {"revision": deal["revision"]}
    if not paid:
        payload["confirmed_party"] = party
    await record_notification_event(
        session,
        event_type=event_type,
        entity_type="monetization_deal",
        entity_id=deal["id"],
        aggregate_id=deal["id"],
        application_id=deal.get("application_id"),
        actor_user_id=actor_user_id,
        request_number=_number(deal, deal["id"]),
        payload=payload,
        previous_values={"status": "pending_approval"} if paid else None,
        new_values={"status": "paid"} if paid else None,
        occurrence_key=f"{event_type}:{deal['id']}:{deal['revision']}:{party}",
    )


async def notify_deal_terms_changed(
    session: AsyncSession,
    deal: dict[str, Any],
    actor_user_id: UUID,
) -> None:
    """Record one information-only fact for the newly saved terms revision."""
    event_type = "monetization.deal_terms_changed"
    await record_notification_event(
        session,
        event_type=event_type,
        entity_type="monetization_deal",
        entity_id=deal["id"],
        aggregate_id=deal["id"],
        application_id=deal.get("application_id"),
        actor_user_id=actor_user_id,
        request_number=_number(deal, deal["id"]),
        payload={"revision": deal["revision"]},
        occurrence_key=f"{event_type}:{deal['id']}:{deal['revision']}",
    )


async def notify_condition_request(
    session: AsyncSession,
    request: dict[str, Any],
    action: str,
    actor_user_id: UUID,
) -> None:
    """Requests and replies remain information-only and contain no amounts."""
    event_type = f"monetization.condition_{action}"
    previous = {"requested": None, "responded": "sent", "decided": "countered"}[action]
    application_id = request["application_id"]
    # The request's source is readable to its recipient even before a first LCA.
    # Only its display number is projected; client data never enters the fact.
    application = await applications.get_by_id(session, application_id)
    number = _number(application or {}, application_id)
    await record_notification_event(
        session,
        event_type=event_type,
        entity_type="monetization_condition_request",
        entity_id=request["id"],
        aggregate_id=request["id"],
        application_id=application_id,
        request_number=number,
        actor_user_id=actor_user_id,
        previous_values={"status": previous},
        new_values={"status": request["status"]},
        payload={"application_id": application_id},
        occurrence_key=f"{event_type}:{request['id']}:{request['status']}",
    )
