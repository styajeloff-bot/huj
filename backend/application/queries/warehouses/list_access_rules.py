"""List warehouse access rules within the requesting actor's read scope."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.warehouse_scope import resolve_warehouse_dealer_filter
from infrastructure.repositories import warehouse_access_rule_repository as rule_repo


@dataclass
class ListAccessRulesQuery:
    page: int = 1
    limit: int = 20
    warehouse_id: UUID | None = None
    is_active: bool | None = None
    actor_id: UUID | None = None
    actor_role: str = "carcraft_employee"
    company_id: UUID | None = None


async def handle_list_access_rules(
    query: ListAccessRulesQuery, session: AsyncSession
) -> dict[str, Any]:
    dealer_filter = await resolve_warehouse_dealer_filter(
        session,
        actor_id=query.actor_id or UUID(int=0),
        actor_role=query.actor_role,
        company_id=query.company_id,
    )
    items, total = await rule_repo.list_access_rules(
        session,
        warehouse_id=query.warehouse_id,
        actor_filter=dealer_filter,
        is_active=query.is_active,
        page=query.page,
        limit=query.limit,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "rules": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
