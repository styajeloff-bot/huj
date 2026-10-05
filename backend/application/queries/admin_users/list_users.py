"""List users (admin) query."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import admin_users_repository as repo


@dataclass
class ListUsersQuery:
    page: int = 1
    limit: int = 20
    search: str | None = None
    role: str | None = None
    is_active: bool | None = None
    company_id: UUID | None = None
    phone: str | None = None
    sort_by: str | None = None
    sort_order: str = "asc"


async def handle_list_users(
    query: ListUsersQuery, session: AsyncSession
) -> dict[str, Any]:
    items, total = await repo.list_users(
        session,
        page=query.page,
        limit=query.limit,
        search=query.search,
        role=query.role,
        is_active=query.is_active,
        company_id=query.company_id,
        phone=query.phone,
        sort_by=query.sort_by,
        sort_order=query.sort_order,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "users": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
