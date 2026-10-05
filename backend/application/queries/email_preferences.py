"""Email preferences queries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories.email_preferences_repository import (
    EmailPreferencesDict,
    aggregate_preferences,
    get_or_default,
)
from infrastructure.repositories.notification_email_repository import delivery_stats


@dataclass
class GetEmailPreferencesQuery:
    user_id: UUID


async def handle_get_email_preferences(
    query: GetEmailPreferencesQuery, session: AsyncSession
) -> EmailPreferencesDict:
    return cast("EmailPreferencesDict", await get_or_default(session, query.user_id))


# =============================================================================
# Admin queries — email statistics.
# =============================================================================


@dataclass
class GetEmailStatsQuery:
    """Marker query — admin email statistics. Carries no parameters."""


async def handle_get_email_stats(
    _query: GetEmailStatsQuery, session: AsyncSession
) -> dict[str, Any]:
    """Delivery intents accepted by SMTP, not provider delivery/open tracking."""
    aggregates = await aggregate_preferences(session)
    stats = await delivery_stats(session, datetime.now(UTC))
    return {
        **{key: value for key, value in stats.items() if key not in {"backlog", "oldest_age_seconds"}},
        "subscribers": aggregates["subscribers"],
        "frequency_breakdown": aggregates["frequency_breakdown"],
    }
