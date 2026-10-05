"""Get a single support program by id (admin)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.errors import SupportProgramNotFoundError
from infrastructure.repositories import support_repository as repo


@dataclass
class GetSupportProgramQuery:
    program_id: UUID
    actor_id: UUID | None = None
    actor_role: str = "carcraft_employee"
    company_id: UUID | None = None
    actor_company_id: UUID | None = None


async def handle_get_support_program(
    query: GetSupportProgramQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id or UUID(int=0),
        actor_role=query.actor_role,
        company_id=query.actor_company_id or query.company_id,
    )
    row = await repo.get_program_by_id(
        session,
        query.program_id,
        visible_distributor_id=scope.company_id,
        restrict_to_distributor=not scope.is_employee,
    )
    if row is None:
        raise SupportProgramNotFoundError(query.program_id)
    return cast("dict[str, Any]", row)
