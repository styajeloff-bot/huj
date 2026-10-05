"""Count exchange requests grouped by status for a dealer viewer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_access import require_exchange_company
from infrastructure.repositories import exchange_request_repository as repo


@dataclass
class GetDealerRequestCountsQuery:
    dealer_id: UUID
    company_id: UUID | None = None


async def handle_get_dealer_request_counts(
    query: GetDealerRequestCountsQuery, session: AsyncSession
) -> dict[str, Any]:
    company = await require_exchange_company(session, user_id=query.dealer_id,
        role="dealer", company_id=query.company_id)
    counts = await repo.status_counts_for_dealer(
        session, dealer_id=query.dealer_id, company_id=company
    )
    return {"counts": counts}
