"""Update a dealer's status within the distributor scope.

The dealer row is the underlying ``users`` record (role=dealer). Status
in the distributor's dealer-panel is a simple active/inactive toggle that
maps to ``users.is_active``. Accepted values: ``active`` / ``inactive``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.errors import DealerNotFoundError
from infrastructure.repositories import auth_repository

_ALLOWED_STATUSES = {"active", "inactive"}


@dataclass
class UpdateDealerStatusCommand:
    dealer_id: UUID
    status: str
    actor_id: UUID
    actor_role: str


async def handle_update_dealer_status(
    cmd: UpdateDealerStatusCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.status not in _ALLOWED_STATUSES:
        raise ServiceError(
            f"Недопустимый статус дилера: {cmd.status}", status_code=400
        )

    user = await auth_repository.find_user_by_id(session, cmd.dealer_id)
    if user is None:
        raise DealerNotFoundError(cmd.dealer_id)

    is_active = cmd.status == "active"
    old_user = await auth_repository.find_user_by_id(session, cmd.dealer_id)
    old_active = old_user.get("is_active") if old_user else None
    await auth_repository.set_user_active(
        session, cmd.dealer_id, is_active
    )
    from infrastructure.messaging.status_events import emit_client_status_changed
    emit_client_status_changed(
        user_id=cmd.dealer_id,
        field="is_active",
        old_value=old_active,
        new_value=is_active,
        changed_by=cmd.actor_id,
    )
    return {
        "id": cmd.dealer_id,
        "status": cmd.status,
        "is_active": is_active,
    }
