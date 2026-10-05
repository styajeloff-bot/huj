"""Materialize one event as atomic personal inbox items and delivery intents."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.recipients import event_is_current, resolve_recipients
from application.notifications.templates import build_inbox, next_delivery_at
from domain.events.notifications import NotificationEvent
from domain.notification_policy import POLICIES
from infrastructure.metrics import NOTIFICATION_EVENTS, NOTIFICATION_RECIPIENTS
from infrastructure.repositories import email_preferences_repository as preferences
from infrastructure.repositories import (
    notification_document_group_repository as document_groups,
)
from infrastructure.repositories import notification_email_repository as emails
from infrastructure.repositories import notification_outbox_repository as outbox
from infrastructure.repositories import notification_recipients_repository as users
from infrastructure.repositories import notification_repository as inbox
from infrastructure.settings import settings


async def process_notification_event(
    session: AsyncSession, event: NotificationEvent
) -> list[UUID]:
    """Caller commits the complete fan-out before acknowledging Kafka."""
    now = datetime.now(UTC)
    registry_expiry = event.event_type == "document_registry.expiring"
    # A suppressed expiry is not a completed delivery. The read lock spans
    # receipt + inbox, allowing explicit activation to replay that same event.
    if registry_expiry and not await event_is_current(session, event, now):
        return []
    if not await outbox.receive_once(session, event):
        NOTIFICATION_EVENTS.labels(stage="deduplicated").inc()
        return []
    NOTIFICATION_EVENTS.labels(stage="consumed").inc()
    if not registry_expiry and not await event_is_current(session, event, now):
        return []
    if event.event_type == "leasing.documents_uploaded" and await document_groups.include_upload(session, event):
        return []
    delivery_ids = []
    actor = (
        await users.get_user(session, event.actor_user_id)
        if event.actor_user_id
        else None
    )
    for recipient in await resolve_recipients(session, event):
        view = build_inbox(event, recipient)
        competitor = recipient["role"] == "dealer" and event.event_type in {
            "exchange.bid_created",
            "exchange.bid_updated",
            "exchange.bid_withdrawn",
        }
        if actor and not competitor:
            view["data"]["actor_name"] = actor["name"]
        if event.event_type == "leasing.documents_requested":
            view["data"]["requested_documents"] = [
                item.get("display_name", item.get("slug", "Документ"))
                for item in event.payload.get("requested_documents", [])
                if isinstance(item, dict)
            ]
        NOTIFICATION_RECIPIENTS.labels(outcome="eligible").inc()
        notification_id = await inbox.create_notification(
            session,
            user_id=recipient["user_id"],
            event_id=event.event_id,
            application_id=event.application_id,
            **view,
        )
        category = POLICIES[event.event_type].category
        if category is None:
            continue
        prefs = await preferences.get_or_default(session, recipient["user_id"])
        enabled = prefs[category]
        status = (
            "pending"
            if enabled and recipient.get("email")
            else ("skipped_preference" if not enabled else "skipped_no_email")
        )
        mode = prefs["email_frequency"]
        delivery_ids.append(
            await emails.create_delivery(
                session,
                notification_id=notification_id,
                event_id=event.event_id,
                user_id=recipient["user_id"],
                recipient_role=recipient["role"],
                recipient_company_id=recipient.get("company_id"),
                status=status,
                delivery_mode=mode,
                next_attempt_at=next_delivery_at(
                    now,
                    mode,
                    timezone=settings.notification_business_timezone,
                    hour=settings.notification_digest_hour,
                    weekday=settings.notification_digest_weekday,
                ),
            )
        )
    return delivery_ids
