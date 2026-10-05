"""Read distributor brand settings and brands present in dealer inventory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import distributor_brand_repository as repo
from infrastructure.repositories import (
    distributor_dealer_repository,
    distributor_repository,
)


@dataclass(frozen=True)
class GetDistributorBrandsQuery:
    company_id: UUID


async def handle_get_distributor_brands(
    query: GetDistributorBrandsQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    company = await repo.get_company(session, query.company_id)
    if company is None:
        raise ServiceError("Компания не найдена.", 404)
    if company["company_type"] != "distributor":
        raise ServiceError("Компания не является дистрибьютором.", 400)

    return {
        "available_brands": await repo.list_available_brands(session),
        "selected_brand_ids": await repo.list_active_brand_ids(
            session, query.company_id
        ),
    }


@dataclass(frozen=True)
class GetDistributorInventoryBrandsQuery:
    company_id: UUID


async def handle_get_distributor_inventory_brands(
    query: GetDistributorInventoryBrandsQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    company = await repo.get_company(session, query.company_id)
    if company is None:
        raise ServiceError("Компания не найдена.", 404)
    if company["company_type"] != "distributor":
        raise ServiceError("Компания не является дистрибьютором.", 400)

    dealer_ids = await distributor_dealer_repository.get_linked_dealer_ids(
        session, query.company_id
    )
    return {
        "brands": await distributor_repository.list_distributor_brand_options(
            session, dealer_filter=dealer_ids
        ),
    }
