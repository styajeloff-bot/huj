"""Resolve a cabinet-link LC context without changing the global company."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import domain_to_http
from application.services.leasing_access import require_lc_context
from domain.errors import DomainError
from domain.services.scopes import LEASING_REVIEW, has_all_scopes
from infrastructure.database import get_db
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)


def can_review_leasing_context(user: dict[str, Any]) -> bool:
    """Match review scope with the freshly resolved company's write permission."""
    return has_all_scopes(user.get("scopes"), (LEASING_REVIEW,)) and (
        user.get("role") == "carcraft_employee"
        or user.get("can_create_applications") is True
    )


async def get_leasing_context(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    leasing_company_id: Annotated[UUID | None, Query()] = None,
) -> dict[str, Any]:
    """A query parameter selects a context, never grants membership or rights."""
    if user.get("role") != "leasing_company":
        return user
    try:
        context = await require_lc_context(
            session, user_id=user["id"],
            company_id=user.get("company_id"),
            leasing_company_id=leasing_company_id,
        )
    except DomainError as exc:
        error = domain_to_http(exc)
        raise HTTPException(status_code=error.status_code, detail=str(error)) from exc
    return user | context
