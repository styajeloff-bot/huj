"""Retired whole-line dealer assignment; quantity distributions own new writes."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.permissions import require_distributor_application_read
from domain.dealer_distribution import ensure_distribution_actor


@dataclass(frozen=True)
class AssignDealerCommand:
    application_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    dealer_group_id: UUID
    dealer_company_id: UUID


async def handle_assign_dealer(
    command: AssignDealerCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    ensure_distribution_actor(command.actor_role, command.actor_company_id)
    await require_distributor_application_read(
        session,
        user_id=command.actor_id,
        actor_role=command.actor_role,
        actor_company_id=command.actor_company_id,
    )
    raise ServiceError(
        "Используйте распределение количества через dealer-distributions",
        409,
    )
