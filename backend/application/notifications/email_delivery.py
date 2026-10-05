"""Claim/recheck/SMTP/complete use case; no DB connection spans SMTP I/O."""

from __future__ import annotations

import smtplib
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.recipients import event_is_current, resolve_recipients
from application.notifications.templates import build_email, next_delivery_at
from domain.events.notifications import NotificationEvent
from domain.notification_policy import POLICIES
from infrastructure.database import AsyncSessionLocal
from infrastructure.logging import log_event
from infrastructure.metrics import NOTIFICATION_DELIVERIES, NOTIFICATION_SMTP_SECONDS
from infrastructure.repositories import email_preferences_repository as preferences
from infrastructure.repositories import notification_email_repository as repo
from infrastructure.repositories import notification_recipients_repository as users
from infrastructure.services.email_sender import send_email
from infrastructure.settings import settings


def failure_policy(
    exc: Exception, attempt: int, now: datetime
) -> tuple[str, datetime | None, str]:
    code = getattr(exc, "smtp_code", None)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [reply[0] for reply in exc.recipients.values()]
        code = (
            codes[0] if codes and all(500 <= number < 600 for number in codes) else None
        )
    permanent = isinstance(code, int) and 500 <= code < 600
    error = type(exc).__name__ + (f":{code}" if isinstance(code, int) else "")
    delays = settings.notification_email_retry_delays_seconds
    if permanent or attempt > len(delays):
        return "failed", None, error
    return "retry_wait", now + timedelta(seconds=delays[attempt - 1]), error


async def _skip_reason(
    session: AsyncSession,
    member: dict[str, Any],
    recipient: dict[str, Any] | None,
    prefs: dict[str, Any],
    now: datetime,
) -> str | None:
    if recipient is None or not recipient["is_active"]:
        return "skipped_access_revoked"
    event = NotificationEvent.model_validate(member["payload"])
    allowed = await resolve_recipients(
        session,
        event,
        user_id=recipient["id"],
        company_id=member["recipient_company_id"],
    )
    if not any(
        context["role"] == member["recipient_role"]
        and context.get("company_id") == member["recipient_company_id"]
        for context in allowed
    ):
        return "skipped_access_revoked"
    category = POLICIES[event.event_type].category
    if category is None or not prefs[category]:
        return "skipped_preference"
    if not recipient.get("email"):
        return "skipped_no_email"
    if not await event_is_current(session, event, now):
        return "skipped_stale"
    return None


async def deliver_email(delivery_id: UUID | None = None) -> str:
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        batch = await repo.claim_batch(
            session,
            now=now,
            lease_seconds=settings.notification_email_lease_seconds,
            limit=settings.notification_batch_size,
            message_domain=urlsplit(settings.public_url).hostname
            or "notifications.invalid",
            delivery_id=delivery_id,
        )
        if batch is None:
            await session.commit()
            return "idle"
        members = await repo.batch_members(session, batch["id"])
        recipient = await users.get_user(session, batch["user_id"])
        prefs = await preferences.get_or_default(session, batch["user_id"])
        eligible: list[dict[str, Any]] = []
        for member in members:
            reason = await _skip_reason(session, member, recipient, prefs, now)
            if reason:
                await repo.skip_delivery(session, member["id"], reason, now)
                NOTIFICATION_DELIVERIES.labels(state=reason).inc()
            elif (
                batch["attempt_count"] == 0
                and prefs["email_frequency"] != batch["delivery_mode"]
            ):
                mode = prefs["email_frequency"]
                await repo.reschedule_unattempted_delivery(
                    session,
                    member["id"],
                    mode,
                    next_delivery_at(
                        now,
                        mode,
                        timezone=settings.notification_business_timezone,
                        hour=settings.notification_digest_hour,
                        weekday=settings.notification_digest_weekday,
                    ),
                )
            else:
                eligible.append(member)
        if not eligible:
            await repo.complete_batch(
                session, batch["id"], batch["lease_token"], status="skipped", now=now
            )
            await session.commit()
            return "skipped"
        message = build_email(
            eligible,
            public_url=settings.public_url,
            timezone=settings.notification_business_timezone,
        )
        attempt = await repo.begin_attempt(
            session,
            batch["id"],
            batch["lease_token"],
            datetime.now(UTC),
            lease_seconds=settings.notification_email_lease_seconds,
        )
        if attempt is None:
            await session.rollback()
            return "idle"
        await session.commit()
        email = str(recipient["email"]) if recipient is not None else ""
    # Session is closed, including on SMTP failure and worker cancellation.
    error: str | None = None
    smtp_started = monotonic()
    try:
        await send_email(
            email,
            message["subject"],
            message["body"],
            html=message["html"],
            message_id=batch["message_id"],
            timeout=settings.notification_smtp_timeout_seconds,
        )
    except Exception as exc:
        status, retry_at, error = failure_policy(exc, attempt, datetime.now(UTC))
    else:
        status, retry_at, error = "sent", None, None
    finally:
        NOTIFICATION_SMTP_SECONDS.observe(monotonic() - smtp_started)
    async with AsyncSessionLocal() as session:
        persisted = await repo.complete_batch(
            session,
            batch["id"],
            batch["lease_token"],
            status=status,
            now=datetime.now(UTC),
            next_attempt_at=retry_at,
            error=error,
        )
        await session.commit()
    if persisted:
        NOTIFICATION_DELIVERIES.labels(state=status).inc(len(eligible))
    log_event(
        "warning" if status == "failed" else "info",
        "notification.email.completed",
        "Notification email attempt completed",
        batch_id=str(batch["id"]),
        attempt=attempt,
        delivery_status=status,
        smtp_duration_seconds=round(monotonic() - smtp_started, 3),
        persisted=persisted,
        error_code=error,
    )
    return status
