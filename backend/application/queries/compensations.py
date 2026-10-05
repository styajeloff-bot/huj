"""Compensation queries and handlers."""
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import AccessDeniedError, CompensationNotFoundError
from infrastructure.repositories import compensation_repository as repo


@dataclass
class ListCompensationsQuery:
    user_role: str
    actor_company_id: UUID | None = None
    page: int = 1
    limit: int = 50
    application_id: uuid.UUID | None = None
    application_query: str | None = None
    applied_support_id: UUID | None = None
    support_query: str | None = None
    status: str | None = None
    payer: str | None = None
    recipient: str | None = None
    source: str | None = None
    due_date_from: date | None = None
    due_date_to: date | None = None


@dataclass
class GetCompensationQuery:
    compensation_id: UUID
    user_role: str
    actor_company_id: UUID | None = None


@dataclass
class GetCompensationsBySupportQuery:
    applied_support_id: UUID
    user_role: str
    actor_company_id: UUID | None = None


async def handle_list_compensations(
    query: ListCompensationsQuery, session: AsyncSession
) -> dict:
    participant_role, participant_scope = _participant_scope(query.user_role)
    if query.user_role == "distributor":
        participant_role, participant_scope = None, None
    items, total = await repo.list_compensations(
        session,
        application_id=query.application_id,
        application_query=query.application_query,
        applied_support_id=query.applied_support_id,
        support_query=query.support_query,
        status=query.status,
        payer=query.payer,
        recipient=query.recipient,
        source=query.source,
        due_date_from=query.due_date_from,
        due_date_to=query.due_date_to,
        participant_role=participant_role,
        participant_scope=participant_scope,
        visible_distributor_id=query.actor_company_id,
        restrict_to_distributor=query.user_role == "distributor",
        page=query.page,
        limit=query.limit,
    )
    pages = (total + query.limit - 1) // query.limit if total else 0
    return {
        "compensations": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
            "total_pages": pages,
        },
    }


async def handle_get_compensation(
    query: GetCompensationQuery, session: AsyncSession
) -> dict:
    row = await repo.get_compensation_by_id(
        session,
        query.compensation_id,
        visible_distributor_id=query.actor_company_id,
        restrict_to_distributor=query.user_role == "distributor",
    )
    if not row:
        raise CompensationNotFoundError(query.compensation_id)
    if query.user_role != "distributor":
        ensure_can_access_compensation(query.user_role, row)
    return cast("dict[str, Any]", row)


async def handle_get_compensations_by_support(
    query: GetCompensationsBySupportQuery, session: AsyncSession
) -> dict:
    items = await repo.get_compensations_for_support(
        session,
        query.applied_support_id,
        visible_distributor_id=query.actor_company_id,
        restrict_to_distributor=query.user_role == "distributor",
    )
    if query.user_role != "distributor":
        for item in items:
            ensure_can_access_compensation(query.user_role, item)

    return {"compensations": items}


def ensure_can_access_compensation(user_role: str, compensation: dict) -> None:
    if not can_access_compensation(user_role, compensation):
        raise AccessDeniedError("Нет доступа к данной компенсации")


def can_access_compensation(user_role: str, compensation: dict) -> bool:
    payer = str(compensation.get("payer") or "")
    recipient = str(compensation.get("recipient") or "")

    if user_role == "carcraft_employee":
        return True
    if user_role in {"client", "distributor"}:
        return user_role in {payer, recipient}
    if user_role == "dealer":
        return payer == "dealer" or recipient == "dealer"
    if user_role == "leasing_company":
        return recipient == "leasing_company"
    return False


def _participant_scope(
    user_role: str,
) -> tuple[str | None, Literal["payer", "recipient", "either"] | None]:
    if user_role == "carcraft_employee":
        return None, None
    if user_role in {"client", "distributor"}:
        return user_role, "either"
    if user_role == "dealer":
        return "dealer", "either"
    if user_role == "leasing_company":
        return "leasing_company", "recipient"
    return None, None
