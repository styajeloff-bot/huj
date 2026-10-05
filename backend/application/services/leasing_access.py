"""Current LC access shared by notification recipients and cabinet reads."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    ApplicationNotOwnedError,
    LeasingCompanyApplicationNotFoundError,
)
from infrastructure.repositories import leasing_company_application_repository as repo


async def require_lc_context(
    session: AsyncSession, *, user_id: UUID, company_id: UUID | None,
    leasing_company_id: UUID | None = None,
) -> dict[str, Any]:
    """Validate the exact selected context; missing/ambiguous access is denied.

    Callers may explicitly choose an LC independently of their global company,
    but must then pass company_id=None: the real target company comes from this
    fresh membership projection, never from a trusted query-string claim.
    """
    bindings = await repo.list_readable_lc_bindings(
        session, user_id=user_id, company_id=company_id,
        leasing_company_id=leasing_company_id,
    )
    if len(bindings) != 1:
        raise ApplicationNotOwnedError()
    return bindings[0]


async def require_lc_application_access(
    session: AsyncSession, *, application_id: UUID, user_id: UUID,
    company_id: UUID | None, leasing_company_id: UUID | None,
) -> dict[str, Any]:
    context = await require_lc_context(
        session, user_id=user_id, company_id=company_id,
        leasing_company_id=leasing_company_id,
    )
    link = await repo.get_link_for_app_and_lc(
        session, application_id=application_id,
        leasing_company_id=context["leasing_company_id"],
    )
    if link is None:
        raise LeasingCompanyApplicationNotFoundError(application_id)
    return cast("dict[str, Any]", link)
