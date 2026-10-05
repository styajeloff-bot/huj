"""Admin command: link a dealer company to a distributor company."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    CompanyNotFoundError,
    DealerAlreadyLinkedError,
    InvalidCompanyTypeError,
)
from infrastructure.repositories import (
    company_repository as company_repo,
)
from infrastructure.repositories import (
    distributor_dealer_repository as link_repo,
)


@dataclass(frozen=True)
class LinkDistributorDealerCommand:
    distributor_company_id: UUID
    dealer_company_id: UUID


async def handle_link_distributor_dealer(
    cmd: LinkDistributorDealerCommand, session: AsyncSession
) -> dict[str, Any]:
    distributor = await company_repo.get_company_by_id(
        session, cmd.distributor_company_id
    )
    if distributor is None:
        raise CompanyNotFoundError("Дистрибьютор не найден")
    if distributor.get("company_type") != "distributor":
        raise InvalidCompanyTypeError("Компания не является дистрибьютором")

    dealer = await company_repo.get_company_by_id(session, cmd.dealer_company_id)
    if dealer is None:
        raise CompanyNotFoundError("Дилер не найден")
    if dealer.get("company_type") != "dealer":
        raise InvalidCompanyTypeError("Компания не является дилером")

    if await link_repo.dealer_is_linked(
        session,
        cmd.dealer_company_id,
        exclude_distributor_id=cmd.distributor_company_id,
    ):
        raise DealerAlreadyLinkedError()

    await link_repo.add_link(
        session,
        distributor_company_id=cmd.distributor_company_id,
        dealer_company_id=cmd.dealer_company_id,
    )
    return {"message": "Связь создана", "dealer": dealer}
