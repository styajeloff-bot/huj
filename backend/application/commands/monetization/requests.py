"""Informational commission negotiations; never modify the application price."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization.deals import require_write
from application.errors import ServiceError
from application.notifications.monetization import notify_condition_request
from domain.monetization.requests import (
    transition_condition_request,
    validate_commission_request,
)
from infrastructure.repositories import monetization_repository as repo


async def create_requests(session: AsyncSession, application_id: UUID,
                          actor: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    require_write(actor)
    application = await repo.lock_application(session, application_id, actor)
    if application is None:
        raise ServiceError("Заявка не найдена", 404)
    values = {
        "application_id": application_id,
        "dealer_company_id": actor["company_id"],
        "requested_calc_type": payload["calc_type"],
        "requested_value": payload["value"],
        "has_lca": application["has_lca"],
    }
    validate_commission_request(values, "create", "dealer")
    requests = [
        await repo.create_condition_request(
            session, {**values, "leasing_company_id": leasing_id, "status": "sent"},
            actor["user_id"])
        for leasing_id in dict.fromkeys(payload["leasing_company_ids"])
    ]
    for request in requests:
        await notify_condition_request(session, request, "requested", actor["user_id"])
    return {"requests": requests}


async def respond(session: AsyncSession, request_id: UUID,
                  actor: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    require_write(actor)
    current = await repo.get_condition_request(session, request_id, actor, lock=True)
    if current is None:
        raise ServiceError("Запрос комиссии не найден", 404)
    updated = transition_condition_request(
        current, payload["decision"], "leasing",
        value=payload.get("counter_value"), calc_type=payload.get("counter_calc_type"),
    )
    updated.update(responded_by=actor["user_id"], responded_at=datetime.now(UTC))
    saved = await repo.update_condition_request(session, request_id, updated)
    await notify_condition_request(session, saved, "responded", actor["user_id"])
    return {"request": saved}


async def decide(session: AsyncSession, request_id: UUID,
                 actor: dict[str, Any], decision: str) -> dict[str, Any]:
    require_write(actor)
    current = await repo.get_condition_request(session, request_id, actor, lock=True)
    if current is None:
        raise ServiceError("Запрос комиссии не найден", 404)
    updated = transition_condition_request(current, decision, "dealer")
    updated.update(decided_by=actor["user_id"], decided_at=datetime.now(UTC))
    saved = await repo.update_condition_request(session, request_id, updated)
    await notify_condition_request(session, saved, "decided", actor["user_id"])
    return {"request": saved}
