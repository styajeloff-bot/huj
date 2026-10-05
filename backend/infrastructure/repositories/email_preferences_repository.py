"""Email preferences repository — returns dicts, never ORM objects."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.email_preferences import EmailPreferences
from infrastructure.repository_timing import timed_repository

_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "application_status_emails",
        "document_request_emails",
        "document_status_emails",
        "leasing_approval_emails",
        "system_emails",
        "exchange_emails",
        "weekly_digest",
        "marketing_emails",
        "email_frequency",
    }
)

class EmailPreferencesDict(TypedDict):
    user_id: UUID
    application_status_emails: bool
    document_request_emails: bool
    document_status_emails: bool
    leasing_approval_emails: bool
    system_emails: bool
    exchange_emails: bool
    weekly_digest: bool
    marketing_emails: bool
    email_frequency: str
    updated_at: datetime | None

def _to_dict(row: EmailPreferences) -> EmailPreferencesDict:
    return EmailPreferencesDict(
        user_id=row.user_id,
        application_status_emails=row.application_status_emails,
        document_request_emails=row.document_request_emails,
        document_status_emails=row.document_status_emails,
        leasing_approval_emails=row.leasing_approval_emails,
        system_emails=row.system_emails,
        exchange_emails=row.exchange_emails,
        weekly_digest=row.weekly_digest,
        marketing_emails=row.marketing_emails,
        email_frequency=row.email_frequency,
        updated_at=row.updated_at,
    )

def _default_prefs(user_id: UUID) -> EmailPreferencesDict:
    return EmailPreferencesDict(
        user_id=user_id,
        application_status_emails=True,
        document_request_emails=True,
        document_status_emails=True,
        leasing_approval_emails=True,
        system_emails=True,
        exchange_emails=True,
        weekly_digest=True,
        marketing_emails=False,
        email_frequency="immediate",
        updated_at=None,
    )

@timed_repository
async def get_or_default(
    session: AsyncSession, user_id: UUID
) -> EmailPreferencesDict:
    row = await session.get(EmailPreferences, user_id)
    if row is None:
        return _default_prefs(user_id)
    return _to_dict(row)

@timed_repository
async def get_or_create(
    session: AsyncSession, user_id: UUID
) -> EmailPreferencesDict:
    """Return user's prefs, creating defaults row on first access."""
    row = await session.get(EmailPreferences, user_id)
    if row is None:
        row = EmailPreferences(user_id=user_id)
        session.add(row)
        await session.flush()
        await session.refresh(row)
    return _to_dict(row)

@timed_repository
async def update_preferences(
    session: AsyncSession, user_id: UUID, updates: dict[str, Any]
) -> EmailPreferencesDict | None:
    """Update only whitelisted fields. Returns None if row doesn't exist."""
    clean = {k: v for k, v in updates.items() if k in _ALLOWED_FIELDS}
    if not clean:
        # Ensure row exists so caller sees current state even with no-op update.
        return await get_or_create(session, user_id)

    # Make sure row exists first (so UPDATE affects a row).
    await get_or_create(session, user_id)

    # Column is TIMESTAMP WITHOUT TIME ZONE — strip tzinfo.
    clean["updated_at"] = datetime.now(UTC).replace(tzinfo=None)
    stmt = (
        update(EmailPreferences)
        .where(EmailPreferences.user_id == user_id)
        .values(**clean)
    )
    await session.execute(stmt)

    result = await session.execute(
        select(EmailPreferences).where(EmailPreferences.user_id == user_id)
    )
    row = result.scalar_one()
    return _to_dict(row)

# ---------------------------------------------------------------------------
# Aggregations for /stats — derived from email_preferences only.
#
# The legacy Express implementation read from `email_notifications_log`,
# which has no FastAPI ORM model nor Alembic migration yet. Until that
# table is migrated, we return the only honest signal available: counts
# from the subscriber table itself.
# ---------------------------------------------------------------------------

class EmailPreferencesAggregates(TypedDict):
    subscribers: int
    frequency_breakdown: dict[str, int]

@timed_repository
async def aggregate_preferences(session: AsyncSession) -> EmailPreferencesAggregates:
    """Return subscriber count and a frequency-breakdown histogram."""
    total_stmt = select(func.count()).select_from(EmailPreferences)
    total_row = await session.execute(total_stmt)
    subscribers = int(total_row.scalar_one() or 0)

    freq_stmt = select(
        EmailPreferences.email_frequency,
        func.count().label("c"),
    ).group_by(EmailPreferences.email_frequency)
    freq_rows = await session.execute(freq_stmt)
    breakdown: dict[str, int] = {"immediate": 0, "daily": 0, "weekly": 0}
    for freq, count in freq_rows.all():
        if freq in breakdown:
            breakdown[freq] = int(count)

    return EmailPreferencesAggregates(
        subscribers=subscribers,
        frequency_breakdown=breakdown,
    )
