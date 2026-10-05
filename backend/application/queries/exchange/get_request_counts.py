"""Count LC requests grouped by status."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_access import require_exchange_company
from infrastructure.repositories import exchange_request_repository as repo


@dataclass
class GetRequestCountsQuery:
    lc_user_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)


async def handle_get_request_counts(
    query: GetRequestCountsQuery, session: AsyncSession
) -> dict[str, Any]:
    company_id = await require_exchange_company(session, user_id=query.lc_user_id,
        role="leasing_company", company_id=query.company_id)
    counts = await repo.status_counts_for_lc(
        session, lc_user_id=query.lc_user_id, lc_company_id=company_id
    )
    return {"counts": counts}
