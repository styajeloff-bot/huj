"""Atomically allocate unassigned stock quantities to one linked dealer."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import require_distributor_application_read
from application.services.notification_company_context import (
    require_notification_company_context,
)
from domain.dealer_distribution import (
    DealerDistributionConflictError,
    DistributionItem,
    ensure_distribution_actor,
    ensure_distribution_candidate,
    ensure_distribution_items,
    ensure_distribution_quantity,
)
from domain.errors import (
    ApplicationNotFoundError,
    ApplicationNotOwnedError,
    ApplicationVehicleNotFoundError,
)
from infrastructure.repositories import (
    application_dealer_distribution_repository as repo,
)
from infrastructure.repositories.application_vehicle_assignment_repository import (
    get_linked_dealer_candidate,
)


@dataclass(frozen=True)
class DistributeDealerCommand:
    application_id: UUID
    dealer_id: UUID
    request_id: UUID
    items: tuple[DistributionItem, ...]
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None


def _fingerprint(command: DistributeDealerCommand) -> str:
    payload = {
        "dealer_id": str(command.dealer_id),
        "items": [
            {
                "id": str(item.application_vehicle_id),
                "quantity": item.quantity,
                "expected": item.expected_unassigned_quantity,
            }
            for item in sorted(
                command.items, key=lambda item: item.application_vehicle_id
            )
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def handle_distribute_dealer(
    command: DistributeDealerCommand, session: AsyncSession
) -> dict[str, Any]:
    ensure_distribution_actor(command.actor_role, command.actor_company_id)
    actor_company_id = cast("UUID", command.actor_company_id)
    ensure_distribution_items(command.items)
    await require_notification_company_context(
        session,
        user_id=command.actor_id,
        role=command.actor_role,
        company_id=actor_company_id,
    )
    await require_distributor_application_read(
        session,
        user_id=command.actor_id,
        actor_role=command.actor_role,
        actor_company_id=actor_company_id,
    )
    if not await repo.distributor_is_active(session, actor_company_id):
        raise ApplicationNotOwnedError(
            "Активная компания не является действующим дистрибьютором"
        )
    if not await repo.lock_application(session, command.application_id):
        raise ApplicationNotFoundError(command.application_id)
    fingerprint = _fingerprint(command)
    existing = await repo.get_request(
        session,
        application_id=command.application_id,
        company_id=actor_company_id,
        request_id=command.request_id,
    )
    if existing is not None:
        if existing["payload_hash"] != fingerprint:
            raise DealerDistributionConflictError(
                "Этот идентификатор операции уже использован с другими данными"
            )
        return {"application_vehicle_ids": existing["application_vehicle_ids"]}
    ensure_distribution_candidate(
        await get_linked_dealer_candidate(
            session,
            distributor_company_id=actor_company_id,
            dealer_company_id=command.dealer_id,
        )
    )
    ids = sorted(item.application_vehicle_id for item in command.items)
    rows = await repo.lock_distribution_lines(
        session, application_id=command.application_id, application_vehicle_ids=ids
    )
    for item in command.items:
        row = rows.get(item.application_vehicle_id)
        if row is None:
            raise ApplicationVehicleNotFoundError(item.application_vehicle_id)
        ensure_distribution_quantity(
            item, actor_company_id=actor_company_id, **row
        )
    await repo.save_distribution(
        session,
        application_id=command.application_id,
        company_id=actor_company_id,
        actor_id=command.actor_id,
        request_id=command.request_id,
        payload_hash=fingerprint,
        dealer_id=command.dealer_id,
        items=[(item.application_vehicle_id, item.quantity) for item in command.items],
    )
    return {"application_vehicle_ids": ids}
