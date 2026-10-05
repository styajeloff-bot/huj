"""List applications (admin scope, full visibility) query."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from domain.application_sources import source_filter_values
from infrastructure.repositories import (
    admin_applications_repository as repo,
)
from infrastructure.repositories import application_repository as app_repo


@dataclass
class ListAdminApplicationsQuery:
    page: int = 1
    limit: int = 20
    status: str | None = None
    search: str | None = None
    source_type: str | None = None


async def handle_list_admin_applications(
    query: ListAdminApplicationsQuery, session: AsyncSession
) -> dict[str, Any]:
    items, total = await repo.list_all(
        session,
        page=query.page,
        limit=query.limit,
        status=query.status,
        search=query.search,
        source_types=source_filter_values(query.source_type),
    )
    pending_counts = await app_repo.count_pending_requested_price_items(
        session,
        [item["id"] for item in items],
    )
    for item in items:
        pending_count = pending_counts.get(item["id"], 0)
        item["pending_price_items_count"] = pending_count
        item["can_assign_leasing_companies"] = (
            item.get("status") == "active" and pending_count == 0
        )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "applications": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
