"""List dealer options."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import dealer_option_repository as repo


@dataclass
class ListDealerOptionsQuery:
    """Query parameters.

    ``include_inactive=True`` returns every option (admin view).
    """

    include_inactive: bool = False


async def handle_list_dealer_options(
    query: ListDealerOptionsQuery, session: AsyncSession
) -> dict[str, Any]:
    items = (
        await repo.list_all_options(session)
        if query.include_inactive
        else await repo.list_active_options(session)
    )
    return {"options": items}
