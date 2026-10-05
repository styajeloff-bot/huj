"""List applications (admin scope, full visibility) query."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.fast_deals.merged import (
    KIND_FAST_DEAL,
    created_key,
    merged_page,
    resolve_list_actor,
)
from domain.application_sources import source_filter_values
from domain.fast_deals.values import Role
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
    # ``application`` / ``fast_deal``: which kind of rows the shared list returns.
    kind: str | None = None


async def handle_list_admin_applications(
    query: ListAdminApplicationsQuery, session: AsyncSession
) -> dict[str, Any]:
    source_types = source_filter_values(query.source_type)

    async def fetch_ordinary(page: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        found: tuple[list[dict[str, Any]], int] = await repo.list_all(
            session,
            page=page,
            limit=limit,
            status=query.status,
            search=query.search,
            source_types=source_types,
        )
        return found

    # The platform sees every sent fast deal; an ordinary status or source filter
    # leaves them out (their statuses are their own dictionary).
    fast_actor = await resolve_list_actor(
        session, user_id=None, role=Role.PLATFORM, company_id=None
    )
    items, total = await merged_page(
        session,
        actor=fast_actor,
        kind=query.kind,
        ordinary_filtered=bool(query.status) or bool(source_types),
        search=query.search,
        page=query.page,
        limit=query.limit,
        fetch_ordinary=fetch_ordinary,
        ordinary_key=created_key,
    )
    applications = [item for item in items if item.get("kind") != KIND_FAST_DEAL]
    pending_counts = await app_repo.count_pending_requested_price_items(
        session,
        [item["id"] for item in applications],
    )
    for item in applications:
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
