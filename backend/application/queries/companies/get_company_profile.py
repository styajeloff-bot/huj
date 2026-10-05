"""Query: fetch a company profile by id with role/owner authorization."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.company import Company
from domain.errors import CompanyNotFoundError
from infrastructure.repositories import company_repository as repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)


@dataclass(frozen=True)
class GetCompanyProfileQuery:
    """Args for ``handle_get_company_profile``.

    The handler resolves the caller's ``users.company_id`` and the
    ``user_companies`` join itself — JWT payload is intentionally not
    trusted for the ownership check (it can be stale).
    """

    company_id: UUID
    user_id: UUID
    user_role: str | None


async def handle_get_company_profile(
    query: GetCompanyProfileQuery, session: AsyncSession
) -> dict[str, Any]:
    company_dict = await repo.get_company_by_id(session, query.company_id)
    if company_dict is None:
        raise CompanyNotFoundError()

    company = Company.from_dict(dict(company_dict))

    if query.user_role == "carcraft_employee":
        company.ensure_owned_by(
            user_id=query.user_id,
            user_role=query.user_role,
            user_company_id=None,
        )
    elif query.user_role == "leasing_company" and (
        await lca_repo.lc_user_has_review_access_to_company(
            session, user_id=query.user_id, company_id=query.company_id
        )
    ):
        # LC users get read access to a client's company profile only while
        # they have a leasing-company-application linking them to that client
        # — the LCA is the authorization, not company ownership.
        pass
    else:
        # Resolve the caller's primary company and join-table membership
        # from the database — JWT may be stale.
        primary_company_id = await repo.get_user_company_id(
            session, query.user_id
        )
        linked_ids = await repo.list_user_company_ids(session, query.user_id)
        company.ensure_owned_by(
            user_id=query.user_id,
            user_role=query.user_role,
            user_company_id=primary_company_id,
            user_company_ids=linked_ids,
        )

    extensions: dict[str, Any] = {}
    if company.company_type == "leasing_company":
        extensions["leasing_company"] = await repo.get_leasing_company_extension(
            session, company.id
        )
    elif company.company_type == "distributor":
        extensions["distributor"] = await repo.get_distributor_extension(
            session, company.id
        )

    payload: dict[str, Any] = dict(company_dict)
    payload.update(extensions)
    return payload
