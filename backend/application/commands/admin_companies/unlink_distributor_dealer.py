"""Admin command: unlink a dealer company from a distributor company."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import DistributorDealerLinkNotFoundError
from infrastructure.repositories import distributor_dealer_repository as link_repo


@dataclass(frozen=True)
class UnlinkDistributorDealerCommand:
    distributor_company_id: UUID
    dealer_company_id: UUID


async def handle_unlink_distributor_dealer(
    cmd: UnlinkDistributorDealerCommand, session: AsyncSession
) -> dict[str, Any]:
    deleted = await link_repo.remove_link(
        session,
        distributor_company_id=cmd.distributor_company_id,
        dealer_company_id=cmd.dealer_company_id,
    )
    if not deleted:
        raise DistributorDealerLinkNotFoundError()
    return {"message": "Связь удалена"}
