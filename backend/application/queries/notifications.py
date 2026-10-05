"""Notification queries."""
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.notification_policy import normalize_inbox_action_url
from infrastructure.repositories import notification_repository as repo


@dataclass
class ListNotificationsQuery:
    user_id: UUID
    page: int = 1
    limit: int = 10
    type_filter: str | None = None
    is_read: bool | None = None
    period: str | None = None
    since: datetime | None = None


@dataclass
class GetCountsQuery:
    user_id: UUID


async def handle_list_notifications(
    query: ListNotificationsQuery, session: AsyncSession
) -> dict:
    offset = (query.page - 1) * query.limit
    since = query.since
    if since is not None and since.tzinfo is not None:
        since = since.astimezone(UTC).replace(tzinfo=None)
    items, total = await repo.list_by_user(
        session,
        query.user_id,
        type_filter=query.type_filter,
        is_read=query.is_read,
        period=query.period,
        since=since,
        limit=query.limit,
        offset=offset,
    )
    pages = (total + query.limit - 1) // query.limit if query.limit else 0
    projected_items = [
        item | {"action_url": normalize_inbox_action_url(
            item.get("action_url"), item.get("application_id"), item.get("data"),
        )}
        for item in items
    ]
    return {
        "notifications": projected_items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }


async def handle_get_counts(
    query: GetCountsQuery, session: AsyncSession
) -> dict:
    return cast("dict[Any, Any]", await repo.get_counts(session, query.user_id))
