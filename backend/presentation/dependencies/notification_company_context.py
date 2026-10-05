"""Per-request company selector for notification destinations; no global switch."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import domain_to_http
from application.services.notification_company_context import (
    require_notification_company_context,
)
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user


async def get_notification_company_context(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    notification_company_id: Annotated[UUID | None, Query()] = None,
    lc_selector: Annotated[UUID | None, Query(alias="leasing_company_id")] = None,
) -> dict[str, Any]:
    """Copy verified company permissions into this request's actor context."""
    try:
        context = await require_notification_company_context(
            session, user_id=user["id"], role=user["role"],
            company_id=user.get("company_id"), notification_company_id=notification_company_id,
            leasing_company_id=lc_selector,
        )
    except DomainError as exc:
        error = domain_to_http(exc)
        raise HTTPException(status_code=error.status_code, detail=str(error)) from exc
    return user | context
