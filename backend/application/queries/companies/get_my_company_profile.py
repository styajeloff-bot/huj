"""Query: fetch the current user's company profile via ``users.company_id``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.companies.get_company_profile import (
    GetCompanyProfileQuery,
    handle_get_company_profile,
)
from domain.errors import CompanyNotFoundError
from infrastructure.repositories import company_repository as repo


@dataclass(frozen=True)
class GetMyCompanyProfileQuery:
    user_id: UUID
    user_role: str | None


async def handle_get_my_company_profile(
    query: GetMyCompanyProfileQuery, session: AsyncSession
) -> dict[str, Any]:
    company_id = await repo.get_user_company_id(session, query.user_id)
    if company_id is None:
        # Mirror Express: 404 if the user is not yet associated with a company.
        raise CompanyNotFoundError("Компания не привязана к пользователю")

    return await handle_get_company_profile(
        GetCompanyProfileQuery(
            company_id=company_id,
            user_id=query.user_id,
            user_role=query.user_role,
        ),
        session,
    )
