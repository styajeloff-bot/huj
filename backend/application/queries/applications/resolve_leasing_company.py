"""Resolve the ``leasing_companies.id`` for a user's ``company_id``.

The jwt claim holds the ``companies`` table id; rest of the domain
(particularly the ``selected_leasing_companies`` array) works with the
``leasing_companies.id``. A single query keeps the router thin.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import application_repository as repo


@dataclass
class ResolveLeasingCompanyQuery:
    company_id: UUID | None
    role: str


async def handle_resolve_leasing_company(
    query: ResolveLeasingCompanyQuery, session: AsyncSession
) -> UUID | None:
    if query.role != "leasing_company":
        return None
    return cast(
        "UUID | None",
        await repo.resolve_leasing_company_id(session, query.company_id),
    )
