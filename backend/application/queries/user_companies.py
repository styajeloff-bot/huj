"""Queries for the user-companies domain."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.errors import UserNotFoundError
from infrastructure.repositories import admin_users_repository as admin_users_repo
from infrastructure.repositories import company_registration_repository as repo


@dataclass(frozen=True)
class GetUserCompaniesQuery:
    user_id: UUID


@dataclass(frozen=True)
class GetClientUserCompaniesQuery:
    user_id: UUID


@dataclass(frozen=True)
class GetCompanySelectHistoryQuery:
    user_id: UUID


async def handle_get_user_companies(
    session: AsyncSession, query: GetUserCompaniesQuery
) -> list[dict[str, Any]]:
    """List companies linked to the user (see Express UserService.getUserCompanies)."""
    return cast(
        "list[dict[str, Any]]",
        await repo.list_user_companies(session, query.user_id),
    )


async def handle_get_client_user_companies(
    session: AsyncSession, query: GetClientUserCompaniesQuery
) -> list[dict[str, Any]]:
    """List companies of an existing client for an administrator."""
    user = await admin_users_repo.get_by_id(session, query.user_id)
    if user is None:
        raise UserNotFoundError()
    if user["role"] != "client":
        raise ServiceError("Компании можно просматривать только у клиента", 400)
    return await handle_get_user_companies(
        session, GetUserCompaniesQuery(user_id=query.user_id)
    )


async def handle_get_company_select_history(
    session: AsyncSession, query: GetCompanySelectHistoryQuery
) -> dict[str, Any]:
    """Return last-selected company for the user.

    Matches Express UserService.getCompanySelectHistory 1:1:
    - no companies → ``{"company_id": None}``
    - no history row → create one pointing at the first company
    - stale history row (company no longer linked) → repoint to the first
    """
    companies = await repo.list_user_companies(session, query.user_id)
    if not companies:
        return {"company_id": None, "updated_at": None}

    row = await repo.get_company_select_history(session, query.user_id)
    allowed_ids = {c["id"] for c in companies}
    first_id = companies[0]["id"]

    if row is None or row["company_id"] not in allowed_ids:
        await repo.upsert_company_select_history(session, query.user_id, first_id)
        row = await repo.get_company_select_history(session, query.user_id)

    assert row is not None
    return {"company_id": row["company_id"], "updated_at": row["updated_at"]}
